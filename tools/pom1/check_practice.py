# -*- coding: utf-8 -*-
"""Is "P1 Practice Questions, Class of 2024" already inside the block banks?

Purpose: test, rather than assert, the claim that the standalone Class of 2024
         practice-question PDF is not a fifth question set.
Author:  Noor Sims
Date:    2026-09-25
Input:   the PDFs under $POM1_QBANK_DIR
Output:  how many of its questions appear verbatim in the four block banks

The block banks each carry a "Questions from the Meds2024 Question Bank"
section, which is the Class of 2024 bank re-filed week by week. If that is
what it says it is, every question in the standalone PDF is already in the
portal under its own week, and adding the PDF as its own set would double
them. This script is the check; parse_qbank.py acts on its answer.

FoM's bank turned out the same way - 484 of 492 already present - and the
stragglers were left out rather than shipped as a set of eight.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pymupdf                                                   # noqa: E402
import parse_qbank                                               # noqa: E402

PRACTICE = u"P1-Practice-Questions-Class of 2024.pdf"
# The label is usually its own line box with the stem tabbed to x ~ 144, but
# where a stem is short the two share one box, so the rest of the line counts.
Q_RE = re.compile(u"^Question\\s+(\\d+)\\.\\s*(.*)$")
WEEK_RE = re.compile(u"^Week\\s+(\\d+)\\s*$")
OPT_RE = re.compile(u"^[a-z][.)]\\s*")
X_STEM = 135.0                   # the stem column; option letters sit left of it
MIN_LEN = 40


def flatten(s):
    s = s.replace(u"’", u"'").replace(u"“", u'"').replace(u"”", u'"')
    s = s.replace(u"–", u"-").replace(u"—", u"-")
    return re.sub(u"\\s+", u"", s).lower()


def practice_stems():
    """-> [(week, question number, stem)] for the questions half of the PDF."""
    doc = pymupdf.open(os.path.join(parse_qbank.QBANK_DIR, PRACTICE))
    out, week, cur = [], None, None
    for page in doc:
        lines = []
        for b in page.get_text("dict")["blocks"]:
            if b["type"]:
                continue
            for l in b["lines"]:
                t = u"".join(s["text"] for s in l["spans"]).strip()
                if t:
                    lines.append((round(l["bbox"][1], 1), l["bbox"][0], t,
                                  max(s["size"] for s in l["spans"])))
        lines.sort()
        for _y, x, t, size in lines:
            if size >= 20:                     # the "Questions" / "Answers" divider
                if t.strip().lower() == "answers":
                    doc.close()
                    return out
                continue
            m = WEEK_RE.match(t)
            if m:
                week, cur = int(m.group(1)), None
                continue
            m = Q_RE.match(t)
            if m:
                cur = [week, int(m.group(1)), []]
                if m.group(2).strip():
                    cur[2].append(m.group(2).strip())
                out.append(cur)
                continue
            if cur is None:
                continue
            if x < X_STEM and OPT_RE.match(t):
                cur = None                     # the option list closes the stem
                continue
            if x >= X_STEM:
                cur[2].append(t)
    doc.close()
    return out


def main():
    banks = {}
    for _slug, _n, pdf, _weeks in parse_qbank.BLOCKS:
        if pdf in banks:
            continue
        doc = pymupdf.open(os.path.join(parse_qbank.QBANK_DIR, pdf))
        banks[pdf] = flatten(u" ".join(p.get_text() for p in doc))
        doc.close()

    rows = practice_stems()
    checked = hits = 0
    misses = []
    for week, num, parts in rows:
        stem = flatten(u" ".join(parts))
        if len(stem) < MIN_LEN:
            continue
        checked += 1
        probe = stem[:120]
        if any(probe in t for t in banks.values()):
            hits += 1
        else:
            misses.append((week, num, stem[:90]))

    print("%d questions read out of %s" % (len(rows), PRACTICE))
    print("%d of %d checkable stems are already in the four block banks (%.1f%%)"
          % (hits, checked, 100.0 * hits / max(checked, 1)))
    for week, num, stem in misses:
        print("   not found  week %-3s question %-4d %s" % (week, num, stem))


if __name__ == "__main__":
    main()
