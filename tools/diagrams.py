# -*- coding: utf-8 -*-
"""Recover the diagrams a study-note PDF draws rather than embeds.

Purpose: find the vector artwork on a page, hand back a raster of it, and say
         which text belongs to it, so a drawn figure arrives as a figure
         instead of its labels arriving as loose paragraphs.
Author:  Noor Sims
Date:    2026-09-25
Input:   a pymupdf Page, plus the rectangles its tables already occupy
Output:  [(rect, png bytes)] - one per diagram, in reading order

Not run on its own; imported by tools/pom1/notes_from_pdf.py.

The problem this solves
-----------------------
An embedded picture is a block PyMuPDF hands over whole. A diagram *drawn* in
the PDF - a box-and-arrow axis, a labelled gradient, a flow chart - is not a
block at all: it is a few hundred vector operations, and its labels are
ordinary text lines. So the cardiac action potential page yielded

    Chemical Gradients / Net Electrical Gradient / + / Ca2+ / - / Na+ / K+

as seven paragraphs, which is the diagram's labels read in coordinate order
with the diagram itself missing. Every such figure cost the note twice: the
picture was lost and its labels became noise.

Rasterising is the honest answer. The artwork cannot be reproduced as markup,
and the labels only mean anything sitting where they were drawn.

How a diagram is found
----------------------
Vector operations are merged into clusters by overlap, with a small margin so
a label's leader line joins the box it points at, and a cluster is kept when
it is big enough to be a figure and is made of enough curve and line segments
to be a drawing at all. That last test is what separates a diagram from the
dashed box these documents put round a callout: the box is rectangles and
nothing else, and its text is already being read as text. A cluster lying
inside a table that has already been recovered is skipped too, or every table
would be rasterised as a picture of itself.

A cluster covering nearly the whole page is dropped: that is a page border or
a full-page tint, not a diagram, and rasterising it would swallow the page.
"""

import pymupdf

MIN_W = 80          # smaller than this each way is a rule, a tick or a glyph
MIN_H = 60
MIN_ART = 6         # curve and line segments needed before it is artwork
TABLE_OVERLAP = 0.6  # a cluster this far inside a table IS the table
PAD = 6.0           # a leader line stops just short of what it points at
MARGIN = 14.0       # a label printed just outside the strokes is still the
                    # diagram's - "Na+", "Ca2+", the sign on an axis - so the
                    # crop takes a line of air rather than stranding them
DPI = 200           # enough to read a hand-set label, not enough to be heavy
FULL_PAGE = 0.8     # wider and taller than this share of the page is furniture


def _grow(r, by):
    return pymupdf.Rect(r.x0 - by, r.y0 - by, r.x1 + by, r.y1 + by)


def _merge(items):
    """Cluster (rect, art) that touch, carrying the segment count along."""
    out = []
    for r, n in items:
        hit = None
        for i, (m, c) in enumerate(out):
            if m.intersects(_grow(r, PAD)):
                hit = i
                break
        if hit is None:
            out.append([pymupdf.Rect(r), n])
        else:
            out[hit][0].include_rect(r)
            out[hit][1] += n
    return [(m, c) for m, c in out]


def _covered_by(r, boxes):
    """The share of r's area lying inside any one of boxes."""
    area = r.get_area()
    if area <= 0:
        return 0.0
    best = 0.0
    for b in boxes:
        hit = pymupdf.Rect(r) & b
        if not hit.is_empty:
            best = max(best, hit.get_area() / area)
    return best


def diagrams_on(page, table_rects=()):
    """-> [(rect, png bytes)] for each diagram drawn on the page."""
    skip = [pymupdf.Rect(b) for b in table_rects]
    parts = []
    for d in page.get_drawings():
        r = pymupdf.Rect(d["rect"])
        if r.width < 4 and r.height < 4:
            continue
        # Curves and line segments are what a drawing is made of. A rectangle
        # is not: these documents box their callouts and set their bullets as
        # little filled squares, and counting those as artwork rasterised
        # twelve pages of perfectly good text - unsearchable, unselectable,
        # and heavier than the words it replaced.
        art = len([i for i in d["items"] if i[0] in ("c", "l", "qu")])
        parts.append((r, art))
    if not parts:
        return []

    merged = _merge(parts)
    for _ in range(3):                     # merging creates new neighbours
        grown = _merge(merged)
        if len(grown) == len(merged):
            break
        merged = grown

    page_rect = page.rect
    out = []
    for r, art in merged:
        if r.width < MIN_W or r.height < MIN_H:
            continue
        if (r.width > FULL_PAGE * page_rect.width
                and r.height > FULL_PAGE * page_rect.height):
            continue
        # A ruled table is drawn too, and its rules cluster into a rectangle
        # the size of the table. Rasterising that gave every table a picture of
        # itself sitting directly above it.
        if _covered_by(r, skip) > TABLE_OVERLAP:
            continue
        # A callout - "Clinical Relevance", "Important Ions" - is a rectangle
        # round text that has already been read, and holds no drawing at all.
        if art < MIN_ART:
            continue
        clip = _grow(r, MARGIN) & page_rect
        if clip.is_empty:
            continue
        out.append((clip, page.get_pixmap(clip=clip, dpi=DPI).tobytes("png")))
    out.sort(key=lambda p: (round(p[0].y0, 1), p[0].x0))
    return out
