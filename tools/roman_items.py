# -*- coding: utf-8 -*-
"""Put roman-numeral item lists back in the stem where they belong.

Purpose: repair questions whose "i. ii. iii." item list was read as if it were
         the answer options, across every course's question bank.
Author:  Noor Sims
Date:    2026-09-25
Input:   <course>/data/questions/*.json
Output:  the same files, rewritten in place, and a report on stdout

What it is fixing
-----------------
A matching question lists its items in roman numerals and then offers letters
to match them against:

    Which of the following infections are diagnosed using serology?
      i. Chlamydia  ii. Gonorrhea  iii. Syphilis  iv. Hepatitis B  v. HIV
      A. i, ii, iv   B. i, iii, v   C. iii, i   D. iii, iv, v

When the items sit at the same indent as the option letters, a parser reading
geometry sees "i." and "v." as two more options - so the question renders with
six choices, two of which are the item list with its own numbering glued into
one line ("Chlamydia ii. Gonorrhea iii. Syphilis iv. Hepatitis B"), and one of
which can be clicked and marked wrong. It looked like one bad question in the
HippoNotes bank and was 61 across four courses.

Why a pass and not a parser change
----------------------------------
Two of the four banks this touches have no parser in this repo - the HippoNotes
and Meds 2029 questions arrived as JSON - so a fix inside the PDF walkers would
have missed them. This runs last, over whatever the banks currently hold, and
is idempotent: a question already repaired has no roman-lettered options left
to find.

The test for "this is an item list, not an option"
--------------------------------------------------
Both of these have to hold, because either alone is wrong:

* Removing the roman-lettered options leaves the remaining letters a clean
  A, B, C, ... run. A genuine nine-option list ending at I does not qualify,
  since removing its I leaves A to H - which is clean - so the second test is
  what actually separates them.
* At least one of the roman-lettered options carries the next item's numeral
  inside its own text ("... ii. Gonorrhea iii. Syphilis"). That is the glue
  that only happens when several printed items were flattened into one.
"""

import glob
import io
import json
import os
import re
import string
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROMAN_LETTERS = ("I", "V", "X")

# " ii. ", " iii) ", " iv. " - a roman numeral used as an item marker inside a
# line. Anchored on a space so "vi" inside "cervical" cannot match.
GLUE_RE = re.compile(u"\\s(i{2,3}|iv|vi{0,3}|ix|xi{0,2})[.)]\\s+", re.I)

# the same, but as the split point, keeping the numeral out of the item text
SPLIT_RE = re.compile(u"\\s+(?=(?:i{1,3}|iv|vi{0,3}|ix|xi{0,2})[.)]\\s+)", re.I)
LEAD_RE = re.compile(u"^((?:<[^>]+>)*)\\s*(?:i{1,3}|iv|vi{0,3}|ix|xi{0,2})[.)]\\s*", re.I)


def plain(html):
    return re.sub(u"<[^>]+>", u"", html)


def clean_run(letters):
    return letters == list(string.ascii_uppercase[:len(letters)])


def split_items(html):
    """One flattened line -> its items, each without its numeral."""
    out = []
    for part in SPLIT_RE.split(html):
        part = part.strip()
        if not part:
            continue
        out.append(LEAD_RE.sub(u"\\1", part).strip())
    return out


# An option whose whole text is a list of item numerals. The banks type these
# inconsistently ("I, ii, IV" for i, ii, iv), and a capital I next to the item
# list's own lower-case i reads as a different item.
CITE_RE = re.compile(u"^[ivx]{1,4}(?:\\s*(?:,|and|&|\\+)\\s*[ivx]{1,4})*$", re.I)


def normalise_citations(q):
    """-> True if an option's numerals were re-cased to match the item list."""
    changed = False
    for o in q.get("options") or []:
        txt = plain(o["html"]).strip().rstrip(u".")
        if len(txt) > 1 and CITE_RE.match(txt) and txt != txt.lower():
            o["html"] = o["html"].lower()
            changed = True
    return changed


def repair(q):
    """-> True if this question was changed."""
    opts = q.get("options") or []
    if not opts:
        return False
    roman = [i for i, o in enumerate(opts) if o["letter"] in ROMAN_LETTERS]
    if not roman:
        return False
    rest = [o["letter"] for i, o in enumerate(opts) if i not in roman]
    if not clean_run(rest):
        return False
    if not any(GLUE_RE.search(plain(opts[i]["html"])) for i in roman):
        return False

    items = []
    for i in roman:
        o = opts[i]
        pieces = split_items(o["html"])
        # the option's own letter is the first item's numeral, and the parser
        # stripped it; put the piece back without inventing a numeral for it
        items.extend(pieces if pieces else [o["html"]])

    q["options"] = [o for i, o in enumerate(opts) if i not in roman]
    q["stem"] = (q["stem"] or u"") + (u"<ol class=\"match-items\">%s</ol>"
                                      % u"".join(u"<li>%s</li>" % it for it in items))

    valid = [o["letter"] for o in q["options"]]
    q["correct"] = [l for l in (q.get("correct") or []) if l in valid]
    if not q["options"]:
        # nothing left to click: it is a matching question answered by writing
        q["kind"] = "matching"
        q["free"] = True
        q["correct"] = []
        q["multi"] = False
    elif q.get("kind") == "matching" and q["correct"]:
        q["kind"] = "mcq"
        q["free"] = False
    return True


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    total = 0
    for path in sorted(glob.glob(os.path.join(root, "*", "data", "questions", "*.json"))):
        qs = json.load(io.open(path, encoding="utf-8"))
        hits = [q for q in qs if repair(q)]
        cased = [q for q in qs if normalise_citations(q)]
        if cased and not hits:
            io.open(path, "w", encoding="utf-8", newline="\n").write(
                json.dumps(qs, ensure_ascii=False))
            print("%-38s %2d option numerals re-cased"
                  % (os.path.relpath(path, root), len(cased)))
        if not hits:
            continue
        total += len(hits)
        io.open(path, "w", encoding="utf-8", newline="\n").write(
            json.dumps(qs, ensure_ascii=False))
        print("%-38s %2d repaired  %s"
              % (os.path.relpath(path, root), len(hits),
                 " ".join(q["qid"] for q in hits[:4])))
    print("%d questions repaired" % total)


if __name__ == "__main__":
    main()
