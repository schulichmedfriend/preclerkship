# -*- coding: utf-8 -*-
"""Turn the 2021-22 summative note set into the FoM notes tab.

Purpose: parse the 2021-22 Foundations of Medicine summative note PDF into the
         portal's notes schema, filed against the medwiki lecture roster.
Author:  Noor Sims
Date:    2026-09-22
Input:   the summative note PDF (path via $FOM_SUMMATIVE_PDF)
Output:  fom/data/notes/b1.json .. b4.json, fom/assets/figures/*

How the document is read
------------------------
The typography carries the structure and nothing else has to be guessed:

    18pt   "Progress Test N"      the four blocks
    16pt / 14pt  "Week N: title"  the week
    10pt at the left margin       a section heading, or a bullet, or a number
    8pt                           table text, in columns

Tables ARE ruled, which this file originally had wrong. They are read by
tools/tables.py, which works off the ruling lines; the x-anchor clustering
below stays for the few the finder cannot see, where the cells are recovered
by clustering x within each table region and merging any row that has no first
column into the row above it, which is what a wrapped cell is.

Reading the rules rather than the type is what split the ADHD page back into
the two tables it actually is, and stopped the bold sentence above them -
"Diagnostic Criteria - thorough Hx ..." - being promoted to the heading of a
column, where at 143 characters it set that column thousands of pixels wide
and pushed the criteria off the side of the page.

Sections are filed against the lecture list already in the vault, because a note
is worth more sitting under the lecture it belongs to than in a list of its own.
Where a section matches no lecture it keeps its own heading and sits at the end
of its week, so nothing in the document is dropped on the floor.
"""

import collections
import hashlib
import io
import json
import os
import re
import sys

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import coverage                                                  # noqa: E402
import tables                                                    # noqa: E402

SUMMATIVE_PDF = os.environ.get("FOM_SUMMATIVE_PDF", u"")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIGDIR = os.path.join(ROOT, "fom", "assets", "figures")

BLOCK_OF_WEEK = dict([(w, "b1") for w in (1, 2, 3, 4)] +
                     [(w, "b2") for w in (5, 6, 7, 8)] +
                     [(w, "b3") for w in (9, 10, 11, 12)] +
                     [(w, "b4") for w in (13, 14, 15)])

END_PAGE = 154            # "Notes" and the closing letter follow; not content
BULLETS = u"•Ø§o-○–"
MARK_RE = re.compile(u"^[•Ø§○–o-]$")
NUM_RE = re.compile(u"^(\\d{1,2})[.)]\\s+")
WEEK_RE = re.compile(u"^Week\\s+(\\d+)\\s*[:–-]\\s*(.+?)\\s*$")


def esc(s):
    return s.replace(u"&", u"&amp;").replace(u"<", u"&lt;").replace(u">", u"&gt;")


def runs_html(spans):
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
    return h


def tidy(s):
    """The PDF's arrows and stray spacing, as HTML wants them."""
    s = s.replace(u"à", u" → ").replace(u"è", u" → ")
    s = re.sub(u"\\s{2,}", u" ", s)
    return s.strip()


def lines_of(page):
    """Every text line with its y, x, size and html, plus images and tables.

    A ruled table is read by tools/tables.py and the text inside it suppressed.
    That is what splits the ADHD page back into the two tables it is - the A-E
    criteria, and inattention against hyperactivity side by side - which the
    x-anchor clustering below had merged into one, with the bold sentence above
    them promoted to its heading.

    The clustering stays for the tables this document draws without ruling
    lines, which the finder cannot see at all.
    """
    out = []
    tabs = tables.tables_on(page)
    rects = [bb for bb, _t, _b in tabs]
    for bb, title, block in tabs:
        out.append({"t": "tbl", "y": bb[1], "x": bb[0],
                    "title": title, "block": block})

    def ruled(bbox):
        cx, cy = (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0
        return any(r[0] <= cx <= r[2] and r[1] <= cy <= r[3] for r in rects)

    for b in page.get_text("dict")["blocks"]:
        if b["type"] == 1:
            if b.get("image") and (b["bbox"][2] - b["bbox"][0]) > 70 \
                    and (b["bbox"][3] - b["bbox"][1]) > 50:
                out.append({"t": "img", "y": b["bbox"][1], "x": b["bbox"][0],
                            "w": b["bbox"][2] - b["bbox"][0],
                            "h": b["bbox"][3] - b["bbox"][1],
                            "bytes": b["image"], "ext": b.get("ext") or "png"})
            continue
        for l in b["lines"]:
            txt = u"".join(s["text"] for s in l["spans"])
            if not txt.strip():
                continue
            if ruled(l["bbox"]):
                continue                   # a cell, already carried by the table
            out.append({"t": "txt", "y": l["bbox"][1], "x": l["bbox"][0],
                        "size": max(s["size"] for s in l["spans"]),
                        "text": txt.strip(), "html": runs_html(l["spans"]),
                        "bold": bool(l["spans"][0]["flags"] & 16)})
    out.sort(key=lambda i: (round(i["y"], 0), i["x"]))
    return out


def save_figure(img):
    """Named after the hash of its own bytes, so one picture is stored once."""
    if not os.path.isdir(FIGDIR):
        os.makedirs(FIGDIR)
    h = hashlib.md5(img["bytes"]).hexdigest()[:12]
    ext = "jpg" if img["ext"] in ("jpeg", "jpg") else img["ext"]
    name = "%s.%s" % (h, ext)
    path = os.path.join(FIGDIR, name)
    if not os.path.exists(path):
        io.open(path, "wb").write(img["bytes"])
    return {"t": "figure", "src": "assets/figures/%s" % name,
            "alt": "Figure from the 2021-22 summative notes", "w": int(img["w"]), "h": int(img["h"])}


# ------------------------------------------------------------------- tables

def build_table(items):
    """Recover a table from its 8pt lines by clustering their x anchors.

    The tables are drawn without ruling lines, so a cell is identified by which
    column anchor its x sits on. A row that has nothing in the first column is a
    wrapped continuation of the row above it, not a new row, and is merged up -
    which is also how a cell spanning several rows ends up attached to the first
    of them rather than floating.
    """
    xs = collections.Counter(round(i["x"], 0) for i in items)
    anchors = sorted(x for x, n in xs.items() if n >= 2)
    merged = []
    for x in anchors:
        if merged and x - merged[-1] < 12:
            continue
        merged.append(x)
    if len(merged) < 2:
        return None
    anchors = merged

    def col_of(x):
        best, bi = 1e9, 0
        for i, a in enumerate(anchors):
            if abs(x - a) < best:
                best, bi = abs(x - a), i
        return bi

    rows = collections.OrderedDict()
    for it in items:
        rows.setdefault(round(it["y"], 0), []).append(it)

    grid = []
    for y in sorted(rows):
        cells = [u""] * len(anchors)
        for it in sorted(rows[y], key=lambda i: i["x"]):
            c = col_of(it["x"])
            cells[c] = (cells[c] + u" " + it["html"]).strip() if cells[c] else it["html"]
        starts_row = bool(cells[0].strip())
        if grid and not starts_row:
            for i, c in enumerate(cells):
                if c:
                    grid[-1][i] = (grid[-1][i] + u"<br>" + c) if grid[-1][i] else c
        else:
            grid.append(cells)

    if len(grid) < 2:
        return None

    # an anchor that collected nothing is a column that never existed
    keep = [i for i in range(len(anchors)) if any(r[i].strip() for r in grid)]
    grid = [[r[i] for i in keep] for r in grid]
    if len(grid[0]) < 2:
        return None

    # Only a bold first row is a header. Several of these tables open straight
    # into data, and promoting their first row to a heading would lose it.
    headed = all(u"<strong>" in c or not c.strip() for c in grid[0])
    if headed:
        head, body = grid[0], grid[1:]
    else:
        head, body = [u""] * len(grid[0]), grid
    body = [r for r in body if any(c.strip() for c in r)]
    if not body:
        return None
    return {"t": "table", "cols": [tidy(c) for c in head],
            "rows": [[tidy(c) for c in r] for r in body]}


# -------------------------------------------------------------- the walker

def parse():
    """-> {week: [ {heading, blocks} ]}, plus the two unnumbered chapters."""
    doc = pymupdf.open(SUMMATIVE_PDF)
    weeks = collections.OrderedDict()
    week = None
    section = None
    pending = []            # bullet/number lines gathered into one list block
    table_buf = []
    # A bullet's marker and its text usually share a baseline, but not always:
    # a fraction of a point apart puts them in separate y groups and strands the
    # marker on its own. A stranded marker is held and spent on the next line,
    # which is what stops every such bullet being emitted as loose prose.
    carry = [None]

    def flush_list():
        if not pending or section is None:
            del pending[:]
            return
        html = u"<ul>%s</ul>" % u"".join(u"<li>%s</li>" % tidy(p) for p in pending)
        section["blocks"].append({"t": "list", "html": html})
        del pending[:]

    def flush_table():
        if not table_buf:
            return
        if section is not None:
            t = build_table(table_buf)
            if t:
                section["blocks"].append(t)
        del table_buf[:]

    def open_section(name):
        flush_list(); flush_table()
        s = {"heading": tidy(name), "blocks": []}
        weeks.setdefault(week, []).append(s)
        return s

    for pno in range(1, END_PAGE):
        items = lines_of(doc[pno])
        # a line's marker and its text share a y; glue them before walking
        byy = collections.OrderedDict()
        for it in items:
            byy.setdefault(round(it["y"], 0), []).append(it)

        for y in sorted(byy):
            group = sorted(byy[y], key=lambda i: i["x"])
            imgs = [g for g in group if g["t"] == "img"]
            txts = [g for g in group if g["t"] == "txt"]
            tbls = [g for g in group if g["t"] == "tbl"]
            for im in imgs:
                flush_list(); flush_table()
                if section is not None:
                    section["blocks"].append(save_figure(im))
            for tb in tbls:
                flush_list(); flush_table()
                if week is None:
                    continue
                if section is None:
                    section = open_section(u"Notes")
                # her chart title is the table's own top row, and it is the
                # sentence that used to end up as a heading of the grid
                if tb["title"]:
                    section["blocks"].append(
                        {"t": "note", "html": u"<p>%s</p>" % tidy(tb["title"])})
                section["blocks"].append(tb["block"])
            if not txts:
                continue

            size = max(t["size"] for t in txts)
            joined = u" ".join(t["text"] for t in txts).strip()
            x0 = txts[0]["x"]

            # the page number, set on its own away from the left margin
            if re.match(u"^\\d{1,3}$", joined) and x0 > 120:
                continue

            if size >= 12.5:
                m = WEEK_RE.match(joined)
                if m:
                    flush_list(); flush_table()
                    week = int(m.group(1)); section = None
                    weeks.setdefault(week, [])
                elif re.match(u"^Progress Test", joined):
                    pass
                elif joined.startswith(u"The Immune System"):
                    flush_list(); flush_table()
                    week = 13; section = None      # sits with Fever Part 1's block
                    weeks.setdefault(week, [])
                elif joined.startswith(u"Medical Conditions and Disorders"):
                    flush_list(); flush_table()
                    week = 4; section = None
                    weeks.setdefault(week, [])
                continue

            if week is None:
                continue

            if size < 9.2:                       # table text
                flush_list()
                table_buf.extend(txts)
                continue
            flush_table()

            marker = txts[0]["text"]
            rest = [t for t in txts[1:]]
            if MARK_RE.match(marker) and not rest:
                carry[0] = 0 if x0 < 45 else 1
                continue
            if carry[0] is not None and not MARK_RE.match(marker):
                if section is None:
                    section = open_section(u"Notes")
                pending.append((u"\u2003" * carry[0]) +
                               u" ".join(t["html"] for t in txts))
                carry[0] = None
                continue
            if MARK_RE.match(marker) and rest:
                if section is None:
                    section = open_section(u"Notes")
                depth = 0 if x0 < 45 else 1
                body = u" ".join(t["html"] for t in rest)
                pending.append((u" " * depth) + body)
                carry[0] = None
                continue

            # a wrapped bullet: indented, unmarked, and a list is open
            if pending and x0 >= 45 and not NUM_RE.match(joined):
                pending[-1] = pending[-1] + u" " + u" ".join(t["html"] for t in txts)
                continue

            m = NUM_RE.match(joined)
            if m:
                if section is None:
                    section = open_section(u"Notes")
                pending.append(u" ".join(t["html"] for t in txts))
                continue

            # a plain left-margin line: a section heading, or running prose
            if (x0 < 45 and len(joined) < 75 and re.search(u"[A-Za-z]", joined)
                    and not joined.endswith((u".", u",", u";"))):
                section = open_section(joined)
            else:
                if section is None:
                    section = open_section(u"Notes")
                flush_list()
                section["blocks"].append(
                    {"t": "note", "html": u"<p>%s</p>" % tidy(
                        u" ".join(t["html"] for t in txts))})

        flush_list(); flush_table()

    flush_list(); flush_table()
    doc.close()
    for w in weeks:
        weeks[w] = [s for s in weeks[w] if s["blocks"]]
    return weeks


if __name__ == "__main__":
    ws = parse()
    tot = collections.Counter()
    for w in sorted(ws):
        kinds = collections.Counter(b["t"] for s in ws[w] for b in s["blocks"])
        tot.update(kinds)
        print("week %-3s %3d sections  %s" % (w, len(ws[w]), dict(kinds)))
    print("TOTAL", dict(tot))


# ------------------------------------------------- filing against the vault

STOP = set(u"""the a an and or of to in for with on approach introduction intro
    to a part i ii iii 1 2 3 4 5 and & vs versus its their from into at is are
    overview review basics principles general common important types type""".split())


def tokens(s):
    s = re.sub(u"[^a-z0-9 ]", u" ", s.lower())
    return set(w for w in s.split() if len(w) > 2 and w not in STOP)


def match_score(heading, lecture):
    """How strongly a section heading belongs to a lecture title."""
    a, b = tokens(heading), tokens(lecture)
    if not a or not b:
        return 0.0
    hit = a & b
    if not hit:
        return 0.0
    # a shared long word says more than a shared short one
    weight = sum(len(w) for w in hit)
    return weight / float(sum(len(w) for w in b))


def file_sections(weeks, roster_dir):
    """Fold the parsed sections into each block's existing lecture roster.

    Matching on the heading alone files about a third of the document: where
    A section named the way the course names a lecture lands exactly
    ("Microcytic Anemia" on "Approach to Microcytic Anemia"), but most sections
    are sub-topics that share no vocabulary with any lecture title at all -
    "Iron Metabolism", "The Coulter Counter", "Cytokines".

    Document order supplies the rest. Those sub-topics follow the section that
    introduced the topic, so an unmatched section is filed under the last
    lecture that did match, and a run of them stays together in the order they
    wrote them. A run that reaches no lecture at all - anything before the first
    match in a week - is kept as its own entry rather than dropped.

    The roster itself is left intact: every vault lecture still renders, and one
    with nothing filed against it stays a gap on the coverage map.
    """
    out = {}
    for slug in ("b1", "b2", "b3", "b4"):
        p = os.path.join(roster_dir, "%s.json" % slug)
        out[slug] = json.load(io.open(p, encoding="utf-8"))

    report = []
    for wk in sorted(weeks):
        slug = BLOCK_OF_WEEK[wk]
        wobj = None
        for w in out[slug]["weeks"]:
            if w["n"] == wk:
                wobj = w
        if wobj is None:
            continue
        lects = wobj["lectures"]
        buckets = collections.defaultdict(list)
        orphan, anchor, direct = [], None, 0

        for sec in weeks[wk]:
            best, score = None, 0.28
            for i, lec in enumerate(lects):
                sc = match_score(sec["heading"], lec["name"])
                if sc > score:
                    best, score = i, sc
            if best is not None:
                anchor = best
                direct += 1
                buckets[anchor].append(sec)
            elif anchor is not None:
                buckets[anchor].append(sec)
            else:
                orphan.append(sec)

        # Sections that arrive before anything naming a lecture belong to the
        # first lecture that follows them: the same document-order carry the
        # matched sections already use, run backwards instead of forwards.
        carried = 0
        if orphan and lects:
            first = min(buckets) if buckets else 0
            buckets[first] = orphan + buckets.get(first, [])
            carried, orphan = len(orphan), []

        for i, lec in enumerate(lects):
            secs = buckets.get(i)
            if not secs:
                continue
            blocks = []
            for sec in secs:
                blocks.append({"t": "note",
                               "html": u"<p><strong>%s</strong></p>" % esc(sec["heading"])})
                blocks.extend(sec["blocks"])
            lec["hasNote"] = True
            lec["title"] = secs[0]["heading"] if len(secs) == 1 else lec["name"]
            lec["framing"] = (
                u"<p>From a <strong>2021-22 Foundations of Medicine summative "
                u"note set</strong>, week %d. %s</p>"
                % (wk, u"" if len(secs) == 1 else
                   u"Gathers %d of its sections, in the order they were written."
                   % len(secs)))
            lec["keypoints"] = None
            lec["blocks"] = blocks

        report.append((wk, len(weeks[wk]), direct,
                       sum(len(v) for v in buckets.values()) - direct - carried,
                       carried, len(orphan)))
    return out, report


def main():
    # the roster is rebuilt first so a re-run starts from the vault's own list
    # rather than folding these notes into the copy the last run already wrote
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import rosters_from_vault
    rosters_from_vault.main()

    weeks = parse()
    roster = os.path.join(ROOT, "fom", "data", "notes")
    out, report = file_sections(weeks, roster)
    for doc in out.values():
        coverage.mark_covered(doc)
    for slug, doc in out.items():
        io.open(os.path.join(roster, "%s.json" % slug), "w",
                encoding="utf-8", newline="\n").write(
                    json.dumps(doc, indent=1, ensure_ascii=False))
    print("week  sections  by-name  by-order  carried-back  unplaced")
    for wk, n, direct, order, carried, orph in report:
        print("  %-4d %6d %8d %9d %13d %9d" % (wk, n, direct, order, carried, orph))
    tot = sum(1 for d in out.values() for w in d["weeks"]
              for l in w["lectures"] if l.get("hasNote"))
    alll = sum(len(w["lectures"]) for d in out.values() for w in d["weeks"])
    print("lectures with a note: %d of %d" % (tot, alll))


if __name__ == "__main__":
    main()
