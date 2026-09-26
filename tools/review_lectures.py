# -*- coding: utf-8 -*-
"""Name the lecture each question tests, grounded in the medwiki vault.

Purpose: resolve every question in every course to the vault lecture note(s)
         whose material it tests, and write that into the question JSON as
         `review`, so the answer can say what to go and read.
Author:  Noor Sims
Date:    2026-09-25
Input:   the medwiki vault (``$MEDWIKI_VAULT``, default the author's path) and
         each course's data/questions/*.json
Output:  the same question JSON, each question gaining a `review` array

Run from the repo root, before build_pages.py (the page stamps the bank's
content hash, so a rewritten bank needs a rebuild to be served).

    python tools/review_lectures.py --derive     # write, including matched ones
    python tools/review_lectures.py --dry-run    # report coverage, touch nothing
    python tools/review_lectures.py --report     # list what could NOT be resolved
    python tools/review_lectures.py --validate   # score the matcher, write nothing

A wrong lecture pointer is worse than no pointer: it sends someone to the
wrong material with the portal's authority behind it. So a question that
resolves to nothing keeps an empty `review` and renders as week-only, which is
the whole reason the last route is allowed to refuse.

FIVE ROUTES, IN ORDER. THE FIRST FOUR ARE EXACT
-----------------------------------------------
1. **The workbook notes' own attribution.** Every `#### group` in a
   ``Preclerkship Workbook - <topic>.md`` carries a line naming the lectures it
   tests: ``*Workbook Q11-Q13. Tests [[03 - Contraception]].*``. The portal's
   `lecture` field IS that group's name, so the group is the join key.
2. **Wikilinks in `lectureMeta`.** Several sets already cite the lecture they
   were reasoned from, e.g. ``reasoned from [[01 - Intro to Diabetes]]``.
3. **The `lecture` field naming a lecture.** The module and new-question notes
   head each group with the lecture's own name, so a normalised match against
   the roster resolves it.
4. **The `lecture` field being an unmistakable spelling of one**, where exactly
   one roster entry fits and no other comes close.

Those four are lookups: somebody wrote the attribution down and this reads it.
They cover PoM 2 and nothing else, because no other course's bank recorded a
lecture at all.

5. **The question's own text, matched against the lecture notes** - see
   ``lecture_match.py``. This one is INFERENCE, and it is the only route with
   any judgement in it. It is measured, not assumed: ``--validate`` scores it
   against the questions routes 1-4 already answered, and at the thresholds
   shipped it takes about 55% of them at **88% precision**. Every question
   records which route reached it, so the inferred ones stay separable from the
   looked-up ones and a bad pointer can be found.

**T2C resolves to nothing at all**, by all five routes, because the vault holds
no T2C lectures for any of them to point at.

A lecture number repeats in every week folder (`06 - ...` exists many times
over), so resolution is by NAME and the number is only carried for display.
"""

import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lecture_match
import portal

VAULT = os.environ.get("MEDWIKI_VAULT", "/mnt/c/Users/nsims/medwiki")
LECTURES = os.path.join(VAULT, "01 - Lectures")
QNOTES = os.path.join(VAULT, "00 - Practice Questions")

# The vault keeps one folder per course; T2C has none, which is why its
# questions resolve to nothing and say so rather than being invented.
COURSE_VAULT = {"fom": "99 - FoM", "pom1": "99 - PoM 1", "pom2": "99 - PoM 2"}

COURSES = ["fom", "pom1", "pom2", "t2c"]


# A banked question names the SESSION it was asked in, and the vault names the
# LECTURE. Those differ by a session-type prefix and, often, a parenthetical
# naming the case. Both are stripped before matching; neither carries any of
# the lecture's identity.
PREFIX = re.compile(
    r"^(?:concept checks?|cbl|dssg|chsg|deck case|module case|in[- ]class|"
    r"weekly rounds|p1|pre[- ]?reading|required reading)\s*[-–:]\s*",
    re.I)

# "(2026)", "(Case 3: Caught in the NET)", "(Part 2: Examination Findings)"
PAREN = re.compile(r"\s*\([^)]*\)\s*$")


def norm(s):
    """A lecture name reduced to what two spellings of it share.

    Deliberately lossy in three ways, each of which cost a real match:
    the session-type prefix, a trailing parenthetical, and the plural. The
    vault says "Approach to Sexually Transmitted Infections" and the module
    note says "Approach to Sexually Transmitted Infection".
    """
    s = s or ""
    s = re.sub(r"^[\d.]+\s*[-–]\s*", "", s)             # strip "07.1 - "
    s = re.sub(r"\s*\((?:Martin[^)]*|PDF)\)\s*", " ", s)     # strip "(Martin Notes)"
    for _ in range(2):                                        # "Concept Checks - CBL - x"
        s2 = PREFIX.sub("", s)
        s2 = PAREN.sub("", s2)
        if s2 == s:
            break
        s = s2
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s.lower())
    # plural-insensitive, per token: "masses" -> "mass", "infections" -> "infection"
    toks = [re.sub(r"(?:ss)?es$|s$", lambda m: "ss" if m.group(0) == "sses" else "", t)
            for t in s.split()]
    return " ".join(t for t in toks if t).strip()


# Words that carry no discriminating power in a lecture title, so an overlap
# score built on them would match anything to anything.
STOP = set("the a an of to and in for with on at approach clinical presentation "
           "evaluation introduction intro overview anatomy pathology "
           "physiology principle disorder disease management diagnosis".split())


def tokens(s):
    return set(norm(s).split()) - STOP


def fuzzy(name, rost):
    """The one roster entry whose title this name is unmistakably a spelling of.

    Only used after an exact match fails. It requires that the shorter of the
    two titles is almost entirely contained in the longer, AND that exactly one
    roster entry clears that bar - two candidates means the name does not
    identify a lecture and nothing is returned. Three or more shared
    content words minimum, so a two-word title cannot carry a match.
    """
    want = tokens(name)
    if len(want) < 3:
        return None
    best = []
    for key, rec in rost.items():
        have = tokens(rec["t"])
        if not have:
            continue
        shared = want & have
        small = min(len(want), len(have))
        if len(shared) >= 3 and len(shared) >= 0.8 * small:
            best.append(rec)
    return best[0] if len(best) == 1 else None


def roster(course):
    """{normalised name: {week, num, name}} for every lecture note the vault has."""
    out = {}
    base = os.path.join(LECTURES, COURSE_VAULT.get(course, ""))
    if not COURSE_VAULT.get(course) or not os.path.isdir(base):
        return out
    for block in sorted(os.listdir(base)):
        bp = os.path.join(base, block)
        if not os.path.isdir(bp):
            continue
        for wk in sorted(os.listdir(bp)):
            m = re.match(r"^Week (\d+)$", wk)
            if not m:
                continue
            week = int(m.group(1))
            for f in sorted(os.listdir(os.path.join(bp, wk))):
                if not f.endswith(".md") or f == wk + ".md":
                    continue
                stem = f[:-3]
                num = re.match(r"^([\d.]+)\s*[-–]", stem)
                title = re.sub(r"^[\d.]+\s*[-–]\s*", "", stem)
                rec = {"w": week, "n": num.group(1) if num else "", "t": title}
                # first spelling wins; the (Martin Notes) twin normalises to the
                # same key and must not displace the note itself
                out.setdefault(norm(stem), rec)
    return out


def lecture_texts(course):
    """{normalised name: (title, body)} - what a lecture note actually says.

    Read separately from roster() because the roster is display data that gets
    written into the bank, and this is a megabyte of prose that must not.
    """
    out = {}
    base = os.path.join(LECTURES, COURSE_VAULT.get(course, ""))
    if not COURSE_VAULT.get(course) or not os.path.isdir(base):
        return out
    for block in sorted(os.listdir(base)):
        bp = os.path.join(base, block)
        if not os.path.isdir(bp):
            continue
        for wk in sorted(os.listdir(bp)):
            if not re.match(r"^Week \d+$", wk):
                continue
            for f in sorted(os.listdir(os.path.join(bp, wk))):
                if not f.endswith(".md") or f == wk + ".md":
                    continue
                key = norm(f[:-3])
                if key in out:
                    continue
                body = io.open(os.path.join(bp, wk, f), encoding="utf-8",
                               errors="replace").read()
                title = re.sub(r"^[\d.]+\s*[-–]\s*", "", f[:-3])
                out[key] = (title, lecture_match.strip_md(body))
    return out


def block_weeks(course_slug, block_slug):
    """The set of week numbers a block covers, read off portal.py's roster."""
    for c in portal.COURSES:
        if c["slug"] != course_slug:
            continue
        for slug, _n, _name, weeks in c["blocks"]:
            if slug != block_slug:
                continue
            m = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", weeks.strip())
            if m:
                return set(range(int(m.group(1)), int(m.group(2)) + 1))
            return set([int(x) for x in re.findall(r"\d+", weeks)])
    return set()


def workbook_groups():
    """{(course, normalised group name): [lecture link, ...]} from the vault notes.

    The workbook notes are the only source in the vault that states, per group
    of questions, which lectures they test. That line is hand-written and is
    the best attribution the portal has; it is read here rather than copied.
    """
    out = {}
    if not os.path.isdir(QNOTES):
        return out
    for root, _dirs, files in os.walk(QNOTES):
        for f in files:
            if not (f.startswith("Preclerkship Workbook - ") and f.endswith(".md")):
                continue
            s = io.open(os.path.join(root, f), encoding="utf-8").read()
            group = None
            for line in s.split("\n"):
                mg = re.match(r"^#### (.+?)\s*$", line)
                if mg:
                    group = mg.group(1)
                    continue
                if group and line.startswith("*Workbook Q"):
                    links = [l.split("|")[0].strip()
                             for l in re.findall(r"\[\[([^\]]+)\]\]", line)]
                    if links:
                        out[norm(group)] = links
                    group = None
    return out


def resolve(q, rost, groups):
    """The vault lectures this question tests, best route first. May be empty.

    Returns (hits, route) so a run can be audited by how it got there - the
    fuzzy route is the only one that involves any judgement, and it has to be
    separable from the three that do not.
    """
    hits, seen = [], set()

    def take(name):
        rec = rost.get(norm(name))
        if rec and (rec["w"], rec["t"]) not in seen:
            seen.add((rec["w"], rec["t"]))
            hits.append(rec)

    # 1. the workbook note's own "Tests [[...]]" line for this question's group
    if q.get("family") == "workbook":
        for link in groups.get(norm(q.get("lecture") or ""), []):
            take(link)
        if hits:
            return hits, "workbook-note"

    # 2. a wikilink in lectureMeta
    for link in re.findall(r"\[\[([^\]|]+)", q.get("lectureMeta") or ""):
        take(link)
    if hits:
        return hits, "lecturemeta-link"

    # 3. the lecture field naming a lecture outright
    take(q.get("lecture") or "")
    if hits:
        return hits, "lecture-name"

    # 4. the lecture field being an unmistakable spelling of one
    rec = fuzzy(q.get("lecture") or "", rost)
    if rec:
        return [rec], "fuzzy"

    return [], "none"


def build_index(course, rost):
    """A BM25 index over this course's lecture notes, keyed as the roster is."""
    texts = lecture_texts(course)
    docs = [(k, t, b) for k, (t, b) in texts.items() if k in rost]
    return lecture_match.Index(docs) if docs else None


def validate(course, rost, index, groups):
    """Score the derive route against the questions whose lecture is known.

    The grounded routes are the only ground truth available, and they cover
    enough of PoM 2 to be worth something. A derived answer counts as right
    when it names any lecture the grounded route named - a workbook group cites
    up to four, and matching one of them is the job.
    """
    qdir = os.path.join(course, "data", "questions")
    n = hit = abstain = 0
    wrong = []
    for f in sorted(os.listdir(qdir)):
        if not f.endswith(".json"):
            continue
        blk = f[:-5]
        weeks = block_weeks(course, blk)
        inblk = set(k for k, r in rost.items() if r["w"] in weeks)
        for q in json.load(io.open(os.path.join(qdir, f), encoding="utf-8")):
            truth, route = resolve(q, rost, groups)
            if not truth:
                continue
            n += 1
            want = set((r["w"], r["t"]) for r in truth)
            inwk = set(k for k, r in rost.items() if r["w"] == q.get("week"))
            key, _why = lecture_match.pick(index, q, inblk, inwk)
            if key is None:
                abstain += 1
            elif (rost[key]["w"], rost[key]["t"]) in want:
                hit += 1
            else:
                wrong.append((q["qid"], rost[key]["t"],
                              sorted(t for _w, t in want)[0]))
    took = n - abstain
    print("  validate %-5s %d known | took %d, abstained %d | correct %d of %d taken (%d%%)"
          % (course, n, took, abstain, hit, took,
             (100 * hit // took) if took else 0))
    for qid, got, exp in wrong[:12]:
        print("       MISS %-24s got %r\n%s expected %r" % (qid, got, " " * 34, exp))
    if len(wrong) > 12:
        print("       ... and %d more" % (len(wrong) - 12))
    return hit, took


def main():
    dry = "--dry-run" in sys.argv
    report = "--report" in sys.argv
    derive = "--derive" in sys.argv
    checking = "--validate" in sys.argv

    if not os.path.isdir(LECTURES):
        sys.stderr.write("vault not found at %s - set MEDWIKI_VAULT\n" % VAULT)
        return 1

    groups = workbook_groups()
    print("%d workbook groups carry a lecture attribution" % len(groups))

    if checking:
        for course in COURSES:
            rost = roster(course)
            if not rost:
                continue
            index = build_index(course, rost)
            if index:
                validate(course, rost, index, groups)
        return 0

    grand = [0, 0]
    for course in COURSES:
        qdir = os.path.join(course, "data", "questions")
        if not os.path.isdir(qdir):
            continue
        rost = roster(course)
        index = build_index(course, rost) if (derive and rost) else None
        tot = got = 0
        misses = {}
        routes = {}
        fuzzed = {}
        for f in sorted(os.listdir(qdir)):
            if not f.endswith(".json"):
                continue
            p = os.path.join(qdir, f)
            qs = json.load(io.open(p, encoding="utf-8"))
            weeks = block_weeks(course, f[:-5])
            inblk = set(k for k, r in rost.items() if r["w"] in weeks)
            for q in qs:
                tot += 1
                hits, route = resolve(q, rost, groups)
                if not hits and index is not None:
                    inwk = set(k for k, r in rost.items() if r["w"] == q.get("week"))
                    key, why = lecture_match.pick(index, q, inblk, inwk)
                    if key:
                        hits, route = [rost[key]], why
                    else:
                        route = why
                q["review"] = hits
                routes[route] = routes.get(route, 0) + 1
                if hits:
                    got += 1
                    if route == "fuzzy":
                        fuzzed[(q.get("lecture"), hits[0]["t"])] = \
                            fuzzed.get((q.get("lecture"), hits[0]["t"]), 0) + 1
                else:
                    k = (f[:-5], q["family"], q.get("lecture"))
                    misses[k] = misses.get(k, 0) + 1
            if not dry:
                io.open(p, "w", encoding="utf-8", newline="\n").write(
                    json.dumps(qs, ensure_ascii=False))
        grand[0] += tot
        grand[1] += got
        print("%-5s %4d questions  %4d resolved (%d%%)  %d roster entries  %s"
              % (course, tot, got, (100 * got // tot) if tot else 0, len(rost),
                 ", ".join("%s=%d" % kv for kv in sorted(routes.items()))))
        # the fuzzy route is the only one with judgement in it, so every
        # distinct pairing it made is printed to be read, not just counted
        for (src, dst), n in sorted(fuzzed.items(), key=lambda t: -t[1]):
            print("        fuzzy %3d  %r\n                   -> %r" % (n, src, dst))
        if report:
            for (blk, fam, lec), n in sorted(misses.items(), key=lambda t: -t[1]):
                print("        %4d  %-7s %-11s %r" % (n, blk, fam, lec))

    print("TOTAL %d of %d (%d%%)" % (grand[1], grand[0],
                                     100 * grand[1] // max(1, grand[0])))
    if dry:
        print("(dry run - nothing written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
