# -*- coding: utf-8 -*-
"""Check the parsed PoM 1 bank against the PDFs it came from.

Purpose: prove the question bank is a transcription and not an invention, by
         looking for every long stem and option back in the source text.
Author:  Noor Sims
Date:    2026-09-25
Input:   pom1/data/questions/*.json and the PDFs under $POM1_QBANK_DIR
Output:  a pass rate per block on stdout, and the misses themselves

A miss is not automatically a bug: PyMuPDF joins hyphenated and tab-stopped
text differently from the way the walker rebuilds a wrapped line, so a handful
of stems legitimately differ by a space. What the number is for is catching the
other kind - a stem that swallowed the option list, or an option that swallowed
the next question - which shows up as a cliff, not as a handful.
"""

import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)

import pymupdf                                                   # noqa: E402
import parse_qbank                                               # noqa: E402

MIN_LEN = 40                    # short strings collide by chance; skip them


def flatten(s):
    """Whitespace, case, and the quote characters PDFs and HTML disagree about."""
    s = s.replace(u"’", u"'").replace(u"“", u'"').replace(u"”", u'"')
    s = s.replace(u"–", u"-").replace(u"—", u"-")
    return re.sub(u"\\s+", u"", s).lower()


def norm(s):
    """A question's HTML, flattened to what it says.

    The tag strip belongs on this side only. Running it over the PDF's own text
    as well looked harmless and was not: a lone "<" in a stem matched every
    character through to the next ">" pages later, deleted a third of the
    document, and turned a clean parse into a 56% pass rate.
    """
    s = re.sub(u"<[^>]+>", u" ", s)
    s = (s.replace(u"&amp;", u"&").replace(u"&lt;", u"<").replace(u"&gt;", u">")
          .replace(u"&rsquo;", u"’").replace(u"&nbsp;", u" "))
    return flatten(s)


def source_text(pdf):
    doc = pymupdf.open(os.path.join(parse_qbank.QBANK_DIR, pdf))
    t = u" ".join(page.get_text() for page in doc)
    doc.close()
    return flatten(t)


def main():
    src = {}
    for _slug, _n, pdf, _weeks in parse_qbank.BLOCKS:
        if pdf not in src:
            src[pdf] = source_text(pdf)

    tot_s = hit_s = tot_o = hit_o = 0
    for slug, _n, pdf, _weeks in parse_qbank.BLOCKS:
        qs = json.load(io.open(os.path.join(ROOT, "pom1", "data", "questions",
                                            "%s.json" % slug), encoding="utf-8"))
        text = src[pdf]
        bs = bh = bo = boh = 0
        misses = []
        for q in qs:
            if q["family"] == "workbook":
                continue                      # a different document, checked separately
            stem = norm(q["stem"])
            if len(stem) >= MIN_LEN:
                bs += 1
                if stem in text:
                    bh += 1
                else:
                    misses.append(("stem", q["qid"], stem[:70]))
            for o in q["options"]:
                body = norm(o["html"])
                if len(body) < MIN_LEN:
                    continue
                bo += 1
                if body in text:
                    boh += 1
                else:
                    misses.append(("opt", q["qid"], body[:70]))
        tot_s += bs
        hit_s += bh
        tot_o += bo
        hit_o += boh
        print("%-7s stems %4d/%-4d  options %5d/%-5d" % (slug, bh, bs, boh, bo))
        for kind, qid, txt in misses[:6]:
            print("        miss %-4s %-28s %s" % (kind, qid, txt))
        if len(misses) > 6:
            print("        ... and %d more" % (len(misses) - 6))
    print("total   stems %d/%d (%.1f%%)  options %d/%d (%.1f%%)"
          % (hit_s, tot_s, 100.0 * hit_s / max(tot_s, 1),
             hit_o, tot_o, 100.0 * hit_o / max(tot_o, 1)))


if __name__ == "__main__":
    main()
