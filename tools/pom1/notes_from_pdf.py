# -*- coding: utf-8 -*-
"""Turn the upper-year PoM 1 study notes into the portal's notes tab.

Purpose: fill pom1/data/notes/<slug>.json with written notes, so the notes tab
         carries the course rather than 149 placeholders.
Author:  Noor Sims
Date:    2026-09-25
Input:   the study-note PDFs in $POM1_NOTES_DIR
Output:  pom1/data/notes/*.json, rewritten in place over the vault roster

Run after tools/pom1/rosters_from_vault.py, which builds the roster this fills
in. The roster is the map - every lecture in the course, written up or not -
and this flips hasNote on the ones a note was found for and leaves the rest
showing as gaps, which is the whole habit of the notes tab.

How a PDF becomes notes
-----------------------
All four documents are laid out the same way once you read the type rather
than the text:

* a **section heading** is a line at the left margin (x ~ 36) in the body size
  that is *not* bold, short, and the first line of its own block - "Blood
  Flow", "Embryology", "Heart Failure";
* a **bold** left-margin line is a sub-head or a defined term, not a section;
* bullets carry a SymbolMT or Wingdings dot;
* and the pages are two-column, so blocks are read down the left column and
  then down the right, not across.

Whose notes these are
---------------------
The cover page, the running title and any line naming the author are dropped
on the way through - AUTHOR_RE below. The portal credits the upper-year
resources it is built on once, on the hub, rather than on every page.

Filing a section under a lecture
--------------------------------
The two cardiology documents print a table of contents with a page number per
lecture, so their sections are filed by the document's own structure. The
respirology and gastroenterology documents have none, so each section heading
is scored against the lecture titles of that block in the vault. A section that
matches nothing strongly enough joins the lecture above it, because these notes
run in teaching order; where that is wrong, MAP is the line to edit.
"""

import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)

import pymupdf                                                   # noqa: E402
from PIL import Image                                            # noqa: E402

import question_figures                                          # noqa: E402

NOTES_DIR = os.environ.get(
    "POM1_NOTES_DIR", os.path.join(ROOT, "pom1", "Nicole_s Notes"))

# document, the block it belongs to, the weeks it covers, and whether its first
# page is a table of contents to read the lecture split out of
SOURCES = [
    (u"Principles of Medicine 1 Cardiology Notes Week 1-3.pdf", "cardio", [1, 2, 3], True),
    (u"Principles of Medicine 1 Cardiology Notes Week 4-5.pdf", "cardio", [4, 5], False),
    (u"Principles of Medicine 1 Respiratory Notes.pdf",         "resp",   [6, 7, 8], False),
    (u"GI PT3.pdf",                                             "gi",     [10, 11, 12, 13], False),
]

AUTHOR_RE = re.compile(u"nicole", re.I)
# The dot is often the whole line - these documents set the glyph and its text
# in separate boxes - so a trailing space cannot be required of it. The letter
# "o" as a sub-bullet still needs one, or every word starting with o is a list.
BULLET_RE = re.compile(u"^[\\u2022\\u25cf\\u25aa\\u25e6\\u00b7]\\s*|^o\\s+|^[-\\u2013]\\s+")
WEEK_RE = re.compile(u"^Week\\s+(\\d+)\\s*[:\\u2013-]?\\s*(.*)$")
COL_SPLIT = 255.0        # x that divides the two columns on a two-column page
X_MARGIN = 46.0          # a section heading starts here
HEAD_MAX = 72            # and is no longer than this
MIN_FIG = 70             # a picture smaller than this each way is a bullet glyph

# Sections these notes print that no lecture in the vault is named for. Written
# out rather than guessed at: the left side is the heading as the document
# prints it, the right side the lecture it belongs under.
MAP = {
    u"Blood Flow": u"Introduction to Cardiac Physiology",
    u"Oxygen Delivery": u"Introduction to Cardiac Physiology",
    u"Pathways of Blood Flow": u"Introduction to Cardiac Physiology",
    u"Capacitance": u"Introduction to Cardiac Physiology",
    u"Compensation in a Low-Flow State": u"Introduction to Cardiac Physiology",
}


# A heading is set like the body, so what marks it is everything it is NOT: it
# does not wrap, it does not punctuate, it does not start mid-sentence. These
# are the shapes that turned out to be body text at the left margin - a wrapped
# clause, a numbered step, a labelled row, a line of symbols.
NOT_HEAD_RE = re.compile(u"[.;=:,/]|[\u2191\u2193\u2192\u2265\u2264<>]|^\\d|^[a-z]")
CONTINUES_RE = re.compile(u"^(and|or|but|which|with|that|the|a|an|to|for|in|of|"
                          u"leads|causes|due|can|may|it|they|this)\\b", re.I)


# Furniture: the cover title and the week banner. Held to an absolute size
# rather than "bigger than the body", because these documents set whole
# stretches of content one step up from their own body size - the cardiology
# notes run at 7.9 and set a third of their text at 10.1 - and reading "bigger
# than the body" as "not content" threw 1,425 lines of it away.
FURNITURE = 12.0


def is_heading(it, body, size):
    """True when this line opens a section rather than continuing one.

    Type size cannot do it here: these documents set both headings and whole
    stretches of body one step above their own body size, so a size test read
    "Dizzy, lightheaded; needs to be differentiated from vertigo" as a heading.
    Position and punctuation can: a heading sits at the left margin, is not
    bold, is short, and is not punctuated like a sentence.
    """
    if it["bullet"] or it["bold"] or len(body) > HEAD_MAX:
        return False
    if it["x"] >= X_MARGIN:
        return False
    if NOT_HEAD_RE.search(body) or CONTINUES_RE.match(body):
        return False
    return True


def esc(s):
    return (s.replace(u"&", u"&amp;").replace(u"<", u"&lt;").replace(u">", u"&gt;"))


# The same budget the PoM 2 figures are held to (tools/embed_image.py). A study
# document embeds its pictures at whatever the screenshot was, and these four
# carried 84 MB of them - a repo that has to be cloned to be served cannot take
# that for 425 pictures nobody will view at 2,000 pixels wide.
MAX_W = 900
QUALITY = 82


def shrink(raw, ext):
    """-> (bytes, extension), scaled into the figure budget.

    An image already inside it is returned untouched, so re-running this does
    not re-encode 500 files and change 500 hashes.
    """
    try:
        im = Image.open(io.BytesIO(raw))
    except Exception:
        return raw, ext
    if im.width <= MAX_W and len(raw) <= 180000:
        return raw, ext
    if im.mode not in ("RGB", "L"):
        # JPEG has no alpha; flatten onto white rather than letting it go black
        flat = Image.new("RGB", im.size, (255, 255, 255))
        flat.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
        im = flat
    if im.width > MAX_W:
        im = im.resize((MAX_W, max(1, int(im.height * MAX_W / float(im.width)))),
                       Image.LANCZOS)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=QUALITY, optimize=True)
    return buf.getvalue(), "jpg"


# ------------------------------------------------------------- reading a page

def page_lines(page, pno):
    """Every line and picture on one page, read down one column then the next."""
    items = []
    for b in page.get_text("dict")["blocks"]:
        x0, y0, x1, y1 = b["bbox"]
        col = 0 if x0 < COL_SPLIT else 1
        if b["type"] == 1:
            if (x1 - x0) >= MIN_FIG and (y1 - y0) >= MIN_FIG and b.get("image"):
                items.append({"t": "img", "col": col, "y": y0, "bytes": b["image"],
                              "ext": b.get("ext") or "png", "page": pno})
            continue
        for i, line in enumerate(b["lines"]):
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = u"".join(s["text"] for s in spans).strip()
            fonts = u" ".join(s["font"] for s in spans)
            items.append({
                "t": "txt", "col": col, "y": line["bbox"][1], "x": line["bbox"][0],
                "size": max(s["size"] for s in spans),
                "bold": bool(spans[0]["flags"] & 16),
                "first": i == 0,
                "bullet": ("Symbol" in fonts or "Wingdings" in fonts
                           or bool(BULLET_RE.match(text))),
                "text": text, "page": pno,
            })
    items.sort(key=lambda i: (i["col"], round(i["y"], 1)))
    return items


def body_size(doc):
    """The size most of the document is set in - everything else is furniture."""
    counts = {}
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            if b["type"]:
                continue
            for line in b["lines"]:
                for s in line["spans"]:
                    if s["text"].strip():
                        counts[round(s["size"], 1)] = (counts.get(round(s["size"], 1), 0)
                                                       + len(s["text"]))
    return max(counts, key=lambda k: counts[k]) if counts else 10.1


# ------------------------------------------------------------ the TOC, if any

def read_toc(doc):
    """-> [(lecture name, first page)] off the contents page.

    The name and its page number are separate line boxes on the same row, so
    they are paired by y rather than by reading order.
    """
    rows = []
    for b in doc[0].get_text("dict")["blocks"]:
        if b["type"]:
            continue
        for line in b["lines"]:
            t = u"".join(s["text"] for s in line["spans"]).strip()
            if t:
                rows.append((round(line["bbox"][1]), line["bbox"][0], t))
    rows.sort()
    out, pend = [], None
    for _y, x, t in rows:
        if re.match(u"^\\d{1,3}$", t) and pend:
            out.append((pend, int(t)))
            pend = None
            continue
        if WEEK_RE.match(t) or AUTHOR_RE.search(t) or len(t) < 3:
            pend = None
            continue
        if x < 200:
            pend = re.sub(u"\\s+", u" ", t)
    return out


# ------------------------------------------------------- lecture title match

def tokens(s):
    s = re.sub(u"[^a-z0-9 ]+", u" ", s.lower())
    stop = set(("the", "of", "and", "to", "in", "a", "an", "for", "with", "its",
                "introduction", "intro", "approach", "overview", "basics"))
    return set(w for w in s.split() if len(w) > 2 and w not in stop)


def best_lecture(title, lectures):
    """-> (lecture, score). Score is the share of the shorter title's words shared."""
    want = tokens(title)
    if not want:
        return None, 0.0
    best, score = None, 0.0
    for lec in lectures:
        have = tokens(lec["name"])
        if not have:
            continue
        shared = len(want & have)
        s = float(shared) / min(len(want), len(have))
        if s > score:
            best, score = lec, s
    return best, score


# -------------------------------------------------------------- emitting html

def flush(buf, blocks):
    """Turn a run of collected lines into one note block."""
    if not buf:
        return
    html = []
    lis = []
    for kind, text in buf:
        if kind == "li":
            lis.append(u"<li>%s</li>" % text)
            continue
        if lis:
            html.append(u"<ul>%s</ul>" % u"".join(lis))
            lis = []
        if kind == "h":
            html.append(u"<h5>%s</h5>" % text)
        else:
            html.append(u"<p>%s</p>" % text)
    if lis:
        html.append(u"<ul>%s</ul>" % u"".join(lis))
    if html:
        blocks.append({"t": "list", "html": u"".join(html)})
    del buf[:]


def read_pdf(path, has_toc, lects=None):
    """-> [(section title, [note blocks])] in document order.

    A heading only opens a new section when it names a lecture the block
    actually has. Everything else stays a sub-head inside the section it was
    found in, which is what keeps a wrapped line that happens to look like a
    heading from starting a note of its own.
    """
    doc = pymupdf.open(path)
    size = body_size(doc)
    toc = read_toc(doc) if has_toc else []
    starts = dict((p, n) for n, p in toc)

    sections = []
    cur = None
    buf = []
    pending_bullet = [False]        # a list, so the nested loop can set it

    def open_section(name):
        flush(buf, cur[1] if cur else [])
        sections.append((name, []))
        return sections[-1]

    for pno, page in enumerate(doc, start=1):
        if has_toc and pno == 1:
            continue                                   # the contents page
        if pno in starts:
            cur = open_section(starts[pno])
        for it in page_lines(page, pno):
            if it["t"] == "img":
                if cur is None:
                    continue
                flush(buf, cur[1])
                raw, ext = shrink(it["bytes"], it["ext"])
                src = question_figures.write_asset("pom1", raw, ext)
                cur[1].append({"t": "figure", "src": src,
                               "alt": u"Figure from the %s notes" % cur[0]})
                continue
            text = it["text"]
            if AUTHOR_RE.search(text):
                continue
            if re.match(u"^\\d{1,3}$", text):
                continue                               # a page number
            m = WEEK_RE.match(text)
            if m and it["size"] > size:
                continue                               # the week banner
            if it["size"] >= FURNITURE and it["size"] > size:
                continue                               # the cover or week banner
            body = esc(BULLET_RE.sub(u"", text)).strip()
            if it["bullet"] and not body:
                # the dot is its own line box and its text is the next one, so
                # the mark has to be carried forward or every bullet renders as
                # an empty list item with its text loose underneath
                pending_bullet[0] = True
                continue
            if not body:
                continue
            if it["bullet"] or pending_bullet[0]:
                pending_bullet[0] = False
                if cur is not None:
                    buf.append(("li", body))
                continue
            head = is_heading(it, body, size)
            if head and not has_toc:
                name = re.sub(u"\\s+", u" ", body)
                _lec, score = best_lecture(MAP.get(name, name), lects or [])
                if score >= 0.5:
                    cur = open_section(name)
                    continue
            if cur is None:
                continue
            if head or (it["bold"] and it["x"] < X_MARGIN and len(body) <= HEAD_MAX):
                buf.append(("h", body))
            else:
                buf.append(("p", u"<strong>%s</strong>" % body if it["bold"] else body))
    flush(buf, cur[1] if cur else [])
    doc.close()
    return [(n, b) for n, b in sections if b]


# ------------------------------------------------------------------ the build

def main():
    rosters = {}
    for slug in ("cardio", "resp", "ent", "gi", "gu"):
        p = os.path.join(ROOT, "pom1", "data", "notes", "%s.json" % slug)
        rosters[slug] = json.load(io.open(p, encoding="utf-8"))

    unmatched = []
    for pdf, slug, weeks, has_toc in SOURCES:
        path = os.path.join(NOTES_DIR, pdf)
        if not os.path.exists(path):
            print("missing, skipped: %s" % pdf)
            continue
        roster = rosters[slug]
        lects = [l for w in roster["weeks"] if w["n"] in weeks for l in w["lectures"]]
        last = None
        filed = 0
        for title, blocks in read_pdf(path, has_toc, lects):
            name = MAP.get(title, title)
            lec, score = best_lecture(name, lects)
            if score < 0.5:
                # before the first match there is nothing above to continue, so
                # it goes to the block's opening lecture rather than nowhere
                lec = last if last is not None else lects[0]
                if last is None:
                    unmatched.append((pdf, title))
            else:
                last = lec
            lec.setdefault("blocks", [])
            if not lec.get("hasNote"):
                lec["hasNote"] = True
                lec["title"] = name if name != lec["name"] else lec["name"]
            lec["blocks"].extend(blocks)
            filed += 1
        print("%-52s %-7s %3d sections filed" % (pdf[:52], slug, filed))

    for slug, roster in rosters.items():
        p = os.path.join(ROOT, "pom1", "data", "notes", "%s.json" % slug)
        io.open(p, "w", encoding="utf-8", newline="\n").write(
            json.dumps(roster, indent=1, ensure_ascii=False))
        lects = [l for w in roster["weeks"] for l in w["lectures"]]
        print("%-7s %3d of %3d lectures have a note"
              % (slug, len([l for l in lects if l.get("hasNote")]), len(lects)))
    for pdf, title in unmatched:
        print("   unfiled  %-30s %s" % (pdf[:30], title))


if __name__ == "__main__":
    main()
