# -*- coding: utf-8 -*-
"""Regenerate each course's landing page so its cards state the real counts.

Purpose: build one landing page per course from the shared shell, keeping the
         hand-written prose that already sits on the page.
Author:  Noor Sims
Date:    2026-09-21
Input:   tools/portal.py, each course's data/ and block pages, and the landing
         page being replaced (for its hero blurb and its prose section)
Output:  <course>/index.html

Run from the repo root, after build_pages.py. The prose under each landing page
is read back out of the page being replaced rather than held here, for the same
reason the block pages keep their own blurbs: it is written by hand, it is long,
and a rebuild must not quietly revert it. A course with no page yet gets the
seed below, which is deliberately thin - it is a placeholder saying the course
is not built, not a pretence that it is.
"""

import io, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portal

FAVICON = {"fom": ("FM", "1f4e5f"), "pom2": ("P2", "84223b"),
           "pom1": ("P1", "6b5a2f"), "t2c": ("T2C", "3f4a5a")}

EMPTY_PROSE = u"""<div class="prose">

</div>"""


def part(page, opener, closer="\n</div>"):
    i = page.index(opener)
    j = page.index(closer, i)
    return page[i:j + len(closer)]


def existing(course):
    """(hero blurb, prose block) from the page being replaced, or the seed."""
    p = os.path.join(course["slug"], "index.html")
    if not os.path.exists(p):
        return course["blurb"], EMPTY_PROSE
    s = io.open(p, encoding="utf-8").read()
    hero = re.search(r'<div class="page-hero">\s*<h1>.*?</h1>\s*(.*?)\s*</div>', s, re.S)
    prose = part(s, '<div class="prose">')
    return (hero.group(1) if hero else course["blurb"]), prose


def qbank_card(course):
    """The one card that is not a block: every question in the course.

    It sits after the blocks and spans the grid, because it is not a sixth
    block competing with the five - it is the other thing on the site, and a
    card the same size and shape as its neighbours would say it was one more
    of them.
    """
    if len(course["blocks"]) <= 1:
        return u""
    total = 0
    for slug, _n, _name, _weeks in course["blocks"]:
        total += len(json.load(io.open(
            os.path.join(course["slug"], "data", "questions", "%s.json" % slug),
            encoding="utf-8")))
    return (u'<a class="qbank-card" href="qbank.html">\n'
            u'<p class="bmeta">Every block &middot; %d questions</p>\n'
            u'<h2>Question bank</h2>\n'
            u'<p>All %d blocks in one bank, filtered by block, week, question set '
            u'and whether you got it right. Build a practice test any length you '
            u'like out of whatever you filter to, and sit it against a clock.</p>\n'
            u'</a>' % (total, len(course["blocks"])))


def cards(course):
    """A block is its notes and its Anki deck; its questions are in the bank."""
    out = []
    for slug, n, name, weeks in course["blocks"]:
        page = io.open(os.path.join(course["slug"], "%s.html" % slug),
                       encoding="utf-8").read()
        blurb = re.search(r'<p class="lead">\s*(.*?)\s*</p>', page, re.S).group(1)
        hue = re.search(r'--q-accent:(#\w+);', page).group(1)
        qs = json.load(io.open(os.path.join(course["slug"], "data", "questions",
                                            "%s.json" % slug), encoding="utf-8"))
        nt = json.load(io.open(os.path.join(course["slug"], "data", "notes",
                                            "%s.json" % slug), encoding="utf-8"))
        lects = [l for w in nt["weeks"] for l in w["lectures"]]
        written = len([l for l in lects if l.get("hasNote")])
        out.append(
            u'<a class="block-card" href="%s.html" style="--hue:%s">\n'
            u'<p class="bmeta">Block %d &middot; Weeks %s</p>\n'
            u'<h2>%s</h2>\n<p>%s</p>\n'
            u'<span class="tally">\n'
            u'<span><b>%d</b> of %d lecture notes</span>\n'
            u'<span><b>%d</b> questions in the bank</span>\n'
            u'</span>\n'
            u'</a>' % (slug, hue, n, weeks, name, blurb, written, len(lects), len(qs)))
    return "\n".join(out)


TEMPLATE = u"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{short}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="noindex, nofollow">
{favicon}

{nocache}
{fonts}
<link rel="stylesheet" href="{base_css}">
<link rel="stylesheet" href="{portal_css}">
<style>
:root{{--q-accent:{accent};--q-accent-soft:#e6e6e6;--q-accent-ink:{accent};}}
</style>
{cf}
</head>
<body>

<div class="pom2-page">

{uplink}

<div class="page-hero">
<h1>{short}.</h1>
{hero}
</div>

<div class="block-grid">
{cards}
</div>

{qbank}

{prose}

{footer}

</div>

</body>
</html>
"""


def main():
    for course in portal.COURSES:
        hero, prose = existing(course)
        label, fill = FAVICON[course["slug"]]
        html = TEMPLATE.format(
            short=course["short"], desc=course["blurb"],
            favicon=portal.favicon(label, fill), fonts=portal.FONTS, nocache=portal.NOCACHE,
            base_css=portal.asset("base.css"), portal_css=portal.asset("portal.css"),
            accent=course["accent"], cf=portal.CF, uplink=portal.uplink(1),
            hero=hero, cards=cards(course) or "", qbank=qbank_card(course),
            prose=prose, footer=portal.footer())
        io.open(os.path.join(course["slug"], "index.html"), "w",
                encoding="utf-8", newline="\n").write(html)
        q, w, l = portal.counts(course)
        print("%-5s %d blocks  %d/%d lecture notes  %d questions"
              % (course["slug"], len(course["blocks"]), w, l, q))


if __name__ == "__main__":
    main()
