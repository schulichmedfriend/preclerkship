# -*- coding: utf-8 -*-
"""Title a note with every lecture it covers, instead of leaving them blank.

Purpose: mark the lectures whose material is written up under a neighbouring
         lecture's heading, so the notes tab names both rather than showing one
         of them as a gap.
Author:  Noor Sims
Date:    2026-09-25
Input:   a course roster already filled in by an extractor
Output:  the same roster, hosts gaining `covers` and the covered `coveredBy`

Not run on its own; imported by tools/pom1/notes_from_pdf.py and
tools/fom/parse_summative.py.

Why
---
The upper-year documents are not written one note per lecture. A single chart -
"Esophagus Pathologies", "Small Bowel Obstruction", "Upper GI bleeding" beside
"Lower GI bleeding" - carries two or three of the course's lectures at once, so
filing it under one of them left the rest reading as material nobody had
written up. They render as a pointer to the note that holds them instead.

What it takes to claim a lecture
--------------------------------
Only the headings filed under the host are searched, never its body, and the
claim needs both of:

* **every** word of the blank lecture's name appearing somewhere in them,
* **one** heading carrying at least half of those words, and
* the two lectures sitting within a few places of each other in the week.

The first is what stops a passing mention claiming a lecture. The second is
what stops a long note accumulating enough stray words across thirty headings
to claim one it never mentions. Together they take "Upper GI bleeding" plus
"Lower GI bleeding" as covering *Upper and Lower GI Bleeding*, and leave
*Pulmonary Function Testing* alone, which is named nowhere in the note that
ended up holding its text.

The third is what the other two could not do on their own. These documents
close a block with a summary table naming every topic in it, and each row
label reads exactly like a heading, so *Epistaxis* was claimed by the note
that happened to hold that table - the pediatric asthma one, four lectures
and one organ system away. A chart that genuinely runs two lectures together
runs consecutive ones, because the document is written in teaching order.

A claim is a statement about where to read, so it is better to leave a gap
showing than to point at the wrong note.
"""

import re

STOP = set((u"the", u"of", u"and", u"to", u"in", u"a", u"an", u"for", u"with",
            u"its", u"introduction", u"intro", u"approach", u"overview",
            u"basics",
            # "Class" heads every pharmacology grid in these documents, so it
            # matches in almost any note and carries no information about which
            # lecture a heading is naming.
            u"class"))

# The roster's own scheduling prefix. "In Class - Epistaxis" is the Epistaxis
# lecture; keeping the prefix let it be claimed by any note holding a drug
# table, since that table's first heading is "Class".
# How far apart two lectures may sit and still be one chart's subject.
NEAR = 3

PREFIX_RE = re.compile(u"^(?:in[- ]class|cbl|lab|seminar)\\s*[-\\u2013]\\s*", re.I)


def tokens(s):
    s = PREFIX_RE.sub(u"", (s or u"").strip())
    s = re.sub(u"[^a-z0-9 ]+", u" ", s.lower())
    return set(w for w in s.split() if len(w) > 2 and w not in STOP)


def headings_of(lec):
    """Every heading, sub-head and table heading filed under one lecture.

    The two extractors spell a heading differently - PoM 1 writes <h5> inside a
    list block, FoM a bold paragraph in a note block - so both are read, along
    with the table headings and row labels, which is where a chart states what
    it is about.
    """
    out = []
    for b in lec.get("blocks") or []:
        kind = b.get("t")
        if kind in ("list", "note"):
            html = b.get("html") or u""
            out.extend(re.findall(u"<h5>(.*?)</h5>", html, re.S))
            out.extend(re.findall(u"<p><strong>(.*?)</strong></p>", html, re.S))
        elif kind == "table":
            out.extend(b.get("cols") or [])
            for r in b.get("rows") or []:
                if r:
                    out.append(r[0])
    return [re.sub(u"<[^>]+>", u"", h) for h in out]


def mark_covered(roster):
    """Point every blank lecture at the note that already holds its material."""
    for w in roster["weeks"]:
        at = dict((l["id"], i) for i, l in enumerate(w["lectures"]))
        written = [l for l in w["lectures"] if l.get("hasNote")]
        blank = [l for l in w["lectures"] if not l.get("hasNote")]
        for host in written:
            heads = [tokens(h) for h in headings_of(host)]
            if not heads:
                continue
            seen = set()
            for h in heads:
                seen |= h
            for lec in blank:
                if lec.get("coveredBy"):
                    continue
                if abs(at[lec["id"]] - at[host["id"]]) > NEAR:
                    continue
                want = tokens(lec["name"])
                if not want or not want <= seen:
                    continue
                need = (len(want) + 1) // 2
                if not any(len(want & h) >= need for h in heads):
                    continue
                lec["coveredBy"] = {"num": host["num"], "name": host["name"],
                                    "key": host["id"]}
                host.setdefault("covers", []).append(
                    {"num": lec["num"], "name": lec["name"], "key": lec["id"]})
