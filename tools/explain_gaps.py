# -*- coding: utf-8 -*-
"""Find the questions with no written explanation, and merge written ones back.

Purpose: 1,271 banked questions carry a key and no rationale, because their
         source never wrote one. This finds them, hands out the material needed
         to explain each, and merges the explanations back into the bank.
Author:  Noor Sims
Date:    2026-09-25
Input:   each course's data/questions/*.json, the vault lecture notes, and
         tools/explanations/<course>.json (the written ones)
Output:  a work packet on stdout, or the bank with explanations merged in

    python tools/explain_gaps.py list                    # what is still missing
    python tools/explain_gaps.py packet pom2 repro       # material for one block
    python tools/explain_gaps.py packet pom2 repro --family hipponotes
    python tools/explain_gaps.py merge                   # write them into the bank
    python tools/explain_gaps.py merge --dry-run

WHAT COUNTS AS MISSING
----------------------
An `answer` whose prose is under 80 characters once the markup is stripped.
That is not arbitrary: it is the length of "The correct answer is B." plus the
option restated, which is exactly the shape the un-explained ones take. Above
it, every sampled question had real reasoning in it.

WHAT AN EXPLANATION MAY BE BUILT FROM
-------------------------------------
The lecture note the question resolves to, and nothing else. This is the same
rule the pom2-week skill states for questions themselves: nothing enters a
question that the material did not put there. An explanation invented from
general knowledge is precisely the "AI-generated trivia" the portal's README
promises the bank does not contain, and it would be indistinguishable from a
real one once merged - so the packet carries the lecture text, and a question
whose lecture did not resolve is packeted LAST and marked, because it has no
grounding to write from.

Merging flags every question it touches. The reader is told the rationale was
reasoned from a named lecture rather than transcribed from the source's own
key, because those are not the same thing and the portal says which is which
everywhere else.

THE FILE FORMAT
---------------
``tools/explanations/<course>.json`` maps a qid to either the explanation's
HTML, or an object carrying that HTML plus extra flags:

    {
      "hippo-repro-Q15": "<p>Three of the four Amsel criteria are ...</p>",
      "hippo-repro-Q16": {
        "html": "<p>...</p>",
        "flags": [{"type": "red", "title": "The key looks wrong",
                   "html": "<p>...</p>"}]
      }
    }

The second shape exists because writing an explanation against the lecture is
the moment a bad key is found. Reasoning from the material and then quietly
defending an answer the material contradicts would be the worst thing this
script could do, so it can say so instead.

An entry may also carry ``"review"``, which replaces what
``review_lectures.py`` matched. Reading a lecture closely enough to explain a
question is the same act that catches the matcher sending it to the wrong one,
and a correction made here is a hand-checked fact that should outrank a
derived guess. Use it sparingly and only after reading both lectures.
"""

import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import review_lectures as rl

COURSES = ["fom", "pom1", "pom2", "t2c"]
WRITTEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "explanations")

THIN = 80           # characters of prose below which there is no explanation

FLAG_TITLE = "Explanation reasoned, not transcribed"


def prose(html):
    s = re.sub(r"<[^>]+>", " ", html or "")
    s = re.sub(r"&[a-z]+;|&#\d+;", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def is_thin(q):
    return len(prose(q.get("answer"))) < THIN


def banks(course):
    d = os.path.join(course, "data", "questions")
    if not os.path.isdir(d):
        return []
    return [(f[:-5], os.path.join(d, f))
            for f in sorted(os.listdir(d)) if f.endswith(".json")]


def written(course):
    p = os.path.join(WRITTEN, "%s.json" % course)
    if not os.path.exists(p):
        return {}
    return json.load(io.open(p, encoding="utf-8"))


def cmd_list():
    total = done = 0
    for course in COURSES:
        have = written(course)
        for slug, p in banks(course):
            qs = json.load(io.open(p, encoding="utf-8"))
            thin = [q for q in qs if is_thin(q)]
            if not thin:
                continue
            fam = {}
            for q in thin:
                k = q["family"]
                fam[k] = fam.get(k, [0, 0])
                fam[k][0] += 1
                if q["qid"] in have:
                    fam[k][1] += 1
            total += len(thin)
            done += len([q for q in thin if q["qid"] in have])
            print("%-5s %-7s %4d missing  %s" % (
                course, slug, len(thin),
                "  ".join("%s %d/%d" % (k, v[1], v[0]) for k, v in sorted(fam.items()))))
    print("\nTOTAL %d of %d written" % (done, total))


def cmd_packet(course, slug, family=None, limit=None):
    """Everything needed to explain one block's unexplained questions."""
    rost = rl.roster(course)
    texts = rl.lecture_texts(course)
    by_title = {}
    for key, rec in rost.items():
        by_title[(rec["w"], rec["t"])] = key

    have = written(course)
    out = []
    for s, p in banks(course):
        if s != slug:
            continue
        for q in json.load(io.open(p, encoding="utf-8")):
            if not is_thin(q) or q["qid"] in have:
                continue
            if family and q["family"] != family:
                continue
            lec = []
            for r in q.get("review") or []:
                key = by_title.get((r["w"], r["t"]))
                if key and key in texts:
                    lec.append({"where": "Week %s - %s %s" % (r["w"], r["n"], r["t"]),
                                "text": texts[key][1]})
            out.append({
                "qid": q["qid"],
                "family": q["family"],
                "week": q.get("week"),
                "stem": prose(q.get("stem")),
                "options": [(o["letter"], prose(o["html"])) for o in q.get("options") or []],
                "correct": q.get("correct"),
                "keyLine": prose(q.get("answer")),
                "flags": [f.get("title") for f in (q.get("flags") or [])],
                "grounding": lec or None,
            })
    # ungrounded ones last: they are the ones that cannot honestly be written
    out.sort(key=lambda d: (d["grounding"] is None, d["week"] or 0, d["qid"]))
    if limit:
        out = out[:int(limit)]
    io.open(1, "w", encoding="utf-8", closefd=False).write(
        json.dumps(out, ensure_ascii=False, indent=1))


def cmd_merge(dry=False):
    grand = 0
    for course in COURSES:
        have = written(course)
        if not have:
            continue
        used = set()
        for slug, p in banks(course):
            qs = json.load(io.open(p, encoding="utf-8"))
            n = 0
            for q in qs:
                entry = have.get(q["qid"])
                if not entry:
                    continue
                used.add(q["qid"])
                if not is_thin(q):
                    sys.stderr.write("%s already has an explanation; skipped\n" % q["qid"])
                    continue
                if isinstance(entry, dict):
                    body, extra = entry.get("html") or "", entry.get("flags") or []
                    # writing the explanation is the moment the matched lecture
                    # is read properly, so it is also the moment a wrong match
                    # gets caught. An entry may correct it.
                    if entry.get("review"):
                        q["review"] = entry["review"]
                else:
                    body, extra = entry, []

                # the key sentence the source did give is kept and led with;
                # the reasoning is added under it, never in place of it
                keep = (q.get("answer") or "").strip()
                q["answer"] = keep + body if keep else body

                where = " and ".join(
                    "%s%s" % (r["n"] + " - " if r["n"] else "", r["t"])
                    for r in (q.get("review") or [])) or "the week's material"
                flags = [f for f in (q.get("flags") or [])
                         if f.get("title") != FLAG_TITLE
                         and f.get("title") not in [e.get("title") for e in extra]]
                flags.extend(extra)
                flags.append({
                    "type": "note",
                    "title": FLAG_TITLE,
                    "html": "<p>The source gave the letter and no reasoning. This "
                            "explanation is reasoned from <em>%s</em>, not transcribed "
                            "from an official key. Check it against the lecture before "
                            "relying on it.</p>" % where})
                q["flags"] = flags
                n += 1
            if n and not dry:
                io.open(p, "w", encoding="utf-8", newline="\n").write(
                    json.dumps(qs, ensure_ascii=False))
            if n:
                print("%-5s %-7s %d explanations merged" % (course, slug, n))
                grand += n
        for qid in sorted(set(have) - used):
            sys.stderr.write("%s: written but no such question in the bank\n" % qid)
    print("TOTAL %d%s" % (grand, " (dry run, nothing written)" if dry else ""))


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    if a[0] == "list":
        cmd_list()
    elif a[0] == "packet":
        fam = a[a.index("--family") + 1] if "--family" in a else None
        lim = a[a.index("--limit") + 1] if "--limit" in a else None
        cmd_packet(a[1], a[2], fam, lim)
    elif a[0] == "merge":
        cmd_merge("--dry-run" in a)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
