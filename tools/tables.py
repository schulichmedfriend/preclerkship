# -*- coding: utf-8 -*-
"""Recover a ruled table out of a study-note page.

Purpose: turn the tables in the upper-year note PDFs into the portal's table
         block, so a chart arrives as a grid instead of a column of stray cells.
Author:  Noor Sims
Date:    2026-09-25
Input:   a pymupdf Page
Output:  [(bbox, title html, {"t": "table", "cols": [...], "rows": [[...]]})]

Not run on its own; imported by tools/pom1/notes_from_pdf.py and
tools/fom/parse_summative.py, which read PoM 1's and FoM's note documents.

Read the ruling lines, not the type
-----------------------------------
Both parsers used to infer a table from typography - FoM from an 8pt size and
a cluster of x anchors, PoM 1 not at all - and both got it wrong: FoM merged
the two tables on the ADHD page into one and promoted a sentence to its
heading, and PoM 1 emitted every cell as its own paragraph. These documents
do draw their tables ruled, so PyMuPDF's table finder locates the grid
exactly and neither inference is needed.

What the finder gets wrong, and why
-----------------------------------
It splits a column on every ruling line it can see, including the ones drawn
*inside* a merged header cell, so the esophagus chart comes back as 8 columns
where it has 6 and the acid-lowering chart as 15 where it has 5. Two passes
put that right, in this order:

1. **A wrapped heading** - "Gastroesophageal Reflux Disease" over "(GERD)" -
   arrives as a second row with an empty first cell. It is folded back into
   the heading above it. Only a heading is folded this way: a *body* row with
   an empty first cell means the label above spans down into it (the four
   antacids under one "Antacids"), which the portal renders as a rowspan and
   which must survive.
2. **A column holding nothing in any body row** is one of those phantom
   splits, and is merged into the group on its left. A split that landed
   mid-word is rejoined without a space, which is what turns "I" + "on
   Channels Involved" back into "Ion Channels Involved".

Both passes are shape-driven rather than tuned to a page, so a new document
needs no new constants.

Keeping the bold
----------------
`Table.extract()` returns plain strings, and in these notes **bold is the
discriminator** - the gold-standard test, the one drug that breaks the class
rule. Dropping it would cost the chart the thing it is for, so the cells are
filled from the page's own spans instead: every line whose centre falls in a
cell's rectangle, rendered with its bold and italic intact.
"""

import re


# A column heading is a label. Her longest is "Gastroesophageal Reflux Disease
# (GERD)" at 38 characters, so anything past this is a row of prose that the
# grid happened to put first, and calling it a heading is what used to set a
# column a few thousand pixels wide. A title is allowed to run longer - the
# ADHD chart's is 143 characters - but not without limit.
HEAD_CELL_MAX = 80
TITLE_MAX = 200


def esc(s):
    return s.replace(u"&", u"&amp;").replace(u"<", u"&lt;").replace(u">", u"&gt;")


def strip_tags(s):
    return re.sub(u"<[^>]+>", u"", s or u"")


def join(a, b):
    """Two fragments of one cell, or two cells that are being merged.

    A phantom split lands mid-word, so "I" followed by "on Channels Involved"
    is rejoined with nothing between it. Anything else gets its space.
    """
    a, b = (a or u"").strip(), (b or u"").strip()
    if not a:
        return b
    if not b:
        return a
    ta, tb = strip_tags(a), strip_tags(b)
    if ta and tb and ta[-1].isalpha() and tb[0].islower():
        return a + b
    return a + u" " + b


def line_html(spans):
    """One line of a cell, keeping the bold and the italic and nothing else."""
    out = []
    for s in spans:
        t = esc(s["text"])
        if t.strip():
            if s["flags"] & 16:
                t = u"<strong>%s</strong>" % t
            if s["flags"] & 2:
                t = u"<em>%s</em>" % t
        out.append(t)
    h = u"".join(out)
    h = re.sub(u"</strong>(\\s*)<strong>", u"\\1", h)
    h = re.sub(u"</em>(\\s*)<em>", u"\\1", h)
    return h.strip()


def page_lines(page):
    """Every text line on the page with its centre and its html."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"]:
            continue
        for line in b["lines"]:
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            x0, y0, x1, y1 = line["bbox"]
            out.append({"cx": (x0 + x1) / 2.0, "cy": (y0 + y1) / 2.0,
                        "x": x0, "y": y0, "html": line_html(spans)})
    return out


def fill(rect, lines):
    """The lines sitting inside one cell, top to bottom, as one html string."""
    x0, y0, x1, y1 = rect
    inside = [l for l in lines if x0 <= l["cx"] <= x1 and y0 <= l["cy"] <= y1]
    inside.sort(key=lambda l: (round(l["y"], 1), l["x"]))
    return u"<br>".join(l["html"] for l in inside if l["html"]).strip()


def fold_header(grid):
    """Fold a wrapped heading back into the heading row above it.

    Folded only while every value in the row sits under a heading the first row
    already filled. A body row with a blank first cell is a group member, not a
    continuation, and is left for the portal to render as a rowspan.
    """
    while len(grid) > 1:
        head, nxt = grid[0], grid[1]
        if strip_tags(nxt[0]).strip():
            break
        filled = [i for i, c in enumerate(nxt) if strip_tags(c).strip()]
        if not filled or not all(strip_tags(head[i]).strip() for i in filled):
            break
        grid = [[join(head[i], nxt[i]) for i in range(len(head))]] + grid[2:]
    return grid


def merge_cols(grid):
    """A column with nothing in any body row is a phantom split; merge it left."""
    if not grid:
        return grid
    # With no body rows there is nothing under the headings to tell the real
    # columns from the phantom ones, so the one row speaks for itself. That is
    # what collapses a lone criteria row from six ruled columns back to one.
    body = grid[1:] if len(grid) > 1 else grid
    wide = len(grid[0])
    has = [any(strip_tags(r[c]).strip() for r in body) for c in range(wide)]
    groups, cur = [], None
    for c, h in enumerate(has):
        if h or cur is None:
            cur = [c]
            groups.append(cur)
        else:
            cur.append(c)
    out = []
    for r in grid:
        row = []
        for g in groups:
            v = u""
            for c in g:
                v = join(v, r[c])
            row.append(v)
        out.append(row)
    return out


def is_header(row):
    """Only a row whose every filled cell is bold is a heading.

    Several of these tables open straight into data - the four rows of the
    cardiac cycle, with no heading over them - and promoting the first of them
    would lose a row and label the rest with it.
    """
    filled = [strip_tags(c).strip() for c in row if strip_tags(c).strip()]
    if not filled or any(len(c) > HEAD_CELL_MAX for c in filled):
        return False
    return all(u"<strong>" in c for c in row if strip_tags(c).strip())


def lift_title(grid):
    """-> (title, grid). Her chart title is the table's own top row.

    "Obstructive Lung Disease" is drawn as a row spanning the whole grid, not
    as a line above it, so leaving it in the table costs the note its heading -
    and with it the match that files the section under a lecture. A top row
    with exactly one value and more than one column is that title; a row with
    a value in several columns is a set of column headings and stays.
    """
    if len(grid) < 2 or len(grid[0]) < 2:
        return u"", grid
    filled = [c for c in grid[0] if strip_tags(c).strip()]
    if len(filled) != 1 or len(strip_tags(filled[0]).strip()) > TITLE_MAX:
        return u"", grid
    return filled[0], grid[1:]


def sections(grid):
    """Split one ruled box into the tables actually stacked inside it.

    The ADHD chart draws its A-E criteria and its inattention/hyperactivity
    comparison in a single ruled box, so the finder returns one grid four
    columns wide in which each half fills two of them and leaves the other two
    empty - and the second half's headings land a column to the right of the
    text they head. Splitting at the interior heading row lets each half
    collapse to the width it actually has.
    """
    out, cur = [], []
    for i, row in enumerate(grid):
        filled = [c for c in row if strip_tags(c).strip()]
        if i and cur and len(filled) >= 2 and is_header(row):
            out.append(cur)
            cur = [row]
        else:
            cur.append(row)
    if cur:
        out.append(cur)
    return out


def as_prose(grid):
    """A single column is a paragraph that happens to be ruled, not a table."""
    lines = [c.strip() for r in grid for c in r if strip_tags(c).strip()]
    if not lines:
        return None
    return {"t": "note", "html": u"<p>%s</p>" % u"<br>".join(lines)}


def tables_on(page):
    """-> [(bbox, title, block)] for every table the page draws, in reading order."""
    out = []
    try:
        found = page.find_tables().tables
    except Exception:                      # a page the finder cannot read
        return out
    lines = page_lines(page)
    for t in found:
        grid = []
        for row in t.rows:
            grid.append([fill(c, lines) if c else u"" for c in row.cells])
        if not grid or len(grid[0]) < 2:
            continue
        title, grid = lift_title(fold_header(grid))
        if not grid:
            continue
        # the title belongs to the first of the stacked tables, not to each
        for part in sections(grid):
            part = merge_cols(part)
            if len(part[0]) < 2:
                block = as_prose(part)
                if block:
                    out.append((t.bbox, title.strip(), block))
                    title = u""
                continue
            if is_header(part[0]):
                cols, body = part[0], part[1:]
            else:
                cols, body = [u""] * len(part[0]), part
            body = [r for r in body if any(strip_tags(c).strip() for c in r)]
            if not body:
                continue
            out.append((t.bbox, title.strip(),
                        {"t": "table", "cols": cols, "rows": body}))
            title = u""
    out.sort(key=lambda p: (round(p[0][1], 1), p[0][0]))
    return out
