# -*- coding: utf-8 -*-
"""Regenerate every course's block pages from one template.

Purpose: build one page per block, for every course in the portal, so the four
         courses cannot drift into four layouts.
Author:  Noor Sims
Date:    2026-09-21
Input:   tools/portal.py (the course roster), each course's data/, and the page
         being replaced (for its blurb and accent, so hand edits survive)
Output:  <course>/<block>.html

Run from the repo root. A course with no blocks yet is skipped; its landing page
still renders from build_index.py, saying it is empty.
"""

import io, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portal

HOWTO = """<details class="howto">
<summary>You can save your progress</summary>
<div class="body">
<p><strong>On this device, and nowhere else.</strong> What you have answered is written to
your browser&rsquo;s local storage. It is never sent to this site, never stored in its
repository, and nobody else can see it, not even me.</p>
<p>That also means it does not follow you. A different browser, a different laptop, or
clearing your site data all start from zero.</p>
<p><strong>To carry it with you:</strong> press <strong>Download all my progress</strong> in
the panel on the left and keep the JSON file it writes. One file holds every block of this
course, and it can be pressed from any of them. On the other machine, open any block and
press <strong>Restore from a file</strong> to put all of it back at once. A restore only ever
adds and updates, so an out of date file cannot wipe out newer answers. Doing that now and
then is also the only backup there is.</p>
</div>
</details>"""

# Used only when a page does not exist yet. After that the page itself is the
# source of truth for these three, so anything reworded by hand survives.
SEED = {
    ("fom", "b1"): (u"Weeks 1 to 4: what a physician actually does, the ethics and "
                    u"epidemiology underneath it, then cells and tissues, genetics and the "
                    u"newborn, and the health of children and adolescents.",
                    u"Practice questions for weeks 1 to 4 of Foundations of Medicine.",
                    u"--q-accent:#8a5320;--q-accent-soft:#f6e8d8;--q-accent-ink:#70431a;"),
    ("fom", "b2"): (u"Weeks 5 to 8: how the body holds its fluids and pressure steady, what "
                    u"goes wrong when growth stops obeying, how ageing changes the encounter, "
                    u"and the pharmacology that runs underneath all of it.",
                    u"Practice questions for weeks 5 to 8 of Foundations of Medicine.",
                    u"--q-accent:#2f6b4f;--q-accent-soft:#e2efe9;--q-accent-ink:#275844;"),
    ("fom", "b3"): (u"Weeks 9 to 12: the anemias, then bleeding and clotting, then the white "
                    u"cells and the malignancies that arise from them, ending in lymphoma and "
                    u"myeloma.",
                    u"Practice questions for weeks 9 to 12 of Foundations of Medicine.",
                    u"--q-accent:#9c2b2b;--q-accent-soft:#f7dedb;--q-accent-ink:#802222;"),
    ("fom", "b4"): (u"Weeks 13 to 15: fever and the microbes behind it, how infection travels "
                    u"and what is used against it, and what happens when the immune system is "
                    u"absent, overreacting, or turned on its owner.",
                    u"Practice questions for weeks 13 to 15 of Foundations of Medicine.",
                    u"--q-accent:#3d4f8f;--q-accent-soft:#e5e8f5;--q-accent-ink:#333f75;"),
    ("t2c", "peds"): (u"Weeks 1 and 2: prescribing for a child, the acute asthma "
                      u"exacerbation, and the developmental surveillance that runs "
                      u"under every well-child visit.",
                      u"Practice questions for the pediatrics weeks of Transition to Clerkship.",
                      u"--q-accent:#0f6b6b;--q-accent-soft:#dcefef;--q-accent-ink:#0c5555;"),
    ("t2c", "surg"): (u"Weeks 3 and 4: the GI bleed from anatomy to disposition, then "
                      u"the paperwork that surgery actually runs on - perioperative "
                      u"care, the OR note, admission orders and a courteous consult.",
                      u"Practice questions for the surgery weeks of Transition to Clerkship.",
                      u"--q-accent:#7a4a9c;--q-accent-soft:#eee3f6;--q-accent-ink:#623c7e;"),
    ("t2c", "psych"): (u"Weeks 5 and 6: psychiatry on the wards, then delirium, the "
                       u"palliative emergencies, and managing pain and dyspnea at the "
                       u"end of life.",
                       u"Practice questions for the psychiatry and palliative weeks of "
                       u"Transition to Clerkship.",
                       u"--q-accent:#2f6b4f;--q-accent-soft:#e2efe9;--q-accent-ink:#275844;"),
    ("t2c", "em"): (u"Week 7, and the largest block here by some way: resuscitation and "
                    u"shock, cardiac arrest, trauma and ATLS, toxicology - and a "
                    u"37-question ER practice test sat as one paper.",
                    u"Practice questions for the emergency medicine week of Transition "
                    u"to Clerkship.",
                    u"--q-accent:#a83232;--q-accent-soft:#f8dedd;--q-accent-ink:#8a2828;"),
    ("t2c", "fmob"): (u"Weeks 8 and 9: family medicine and obstetrics. The thinnest "
                      u"block in the bank - eight questions between two rotations - "
                      u"and the gap is left visible rather than padded.",
                      u"Practice questions for the family medicine and obstetrics weeks "
                      u"of Transition to Clerkship.",
                      u"--q-accent:#8a5320;--q-accent-soft:#f6e8d8;--q-accent-ink:#70431a;"),
    ("t2c", "dermim"): (u"Weeks 10 to 13: the dermatology rotation, then internal "
                        u"medicine - the last two rotations before clerkship proper.",
                        u"Practice questions for the dermatology and internal medicine "
                        u"weeks of Transition to Clerkship.",
                        u"--q-accent:#35608f;--q-accent-soft:#e2ebf5;--q-accent-ink:#2b4d73;"),
}

FAVICON = {"fom": ("FM", "1f4e5f"), "pom2": ("P2", "84223b"),
           "pom1": ("P1", "6b5a2f"), "t2c": ("T2C", "3f4a5a")}


def existing(course, slug):
    p = os.path.join(course["slug"], "%s.html" % slug)
    if not os.path.exists(p):
        return SEED[(course["slug"], slug)]
    s = io.open(p, encoding="utf-8").read()
    lead = re.search(r'<p class="lead">\s*(.*?)\s*</p>', s, re.S).group(1)
    desc = re.search(r'<meta name="description" content="(.*?)">', s, re.S).group(1)
    accent = re.search(r'(--q-accent:.*?;--q-accent-soft:.*?;--q-accent-ink:.*?;)', s).group(1)
    return lead, desc, accent


def block_counts(course, slug):
    d = course["slug"]
    qs = json.load(io.open(os.path.join(d, "data", "questions", "%s.json" % slug),
                           encoding="utf-8"))
    nt = json.load(io.open(os.path.join(d, "data", "notes", "%s.json" % slug),
                           encoding="utf-8"))
    lects = [l for w in nt["weeks"] for l in w["lectures"]]
    return len(qs), len([l for l in lects if l.get("hasNote")]), len(lects)


def blocknav(course, active):
    rows = ['<a class="home" href="%s">All courses</a>' % portal.HUB_URL]
    for slug, n, name, _w in course["blocks"]:
        cls = ' class="here"' if slug == active else ''
        rows.append('<a href="%s.html"%s>%d &middot; %s</a>' % (slug, cls, n, name))
    return "\n".join(rows)


PAGE = u"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} &middot; {course}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="noindex, nofollow">
{favicon}

{nocache}
{fonts}
<link rel="stylesheet" href="{base_css}">
<link rel="stylesheet" href="{portal_css}">
<style>
:root{{{accent}}}
</style>
{cf}
</head>
<body>

<div class="pom2-page">

<nav class="blocknav">
{blocknav}
</nav>

<header class="q-masthead">
<div>
<p class="eyebrow" id="m-eyebrow"></p>
<h1>{name}</h1>
<p class="lead">{lead}</p>
</div>
<div class="scoreboard" id="sb-notes">
<div class="score"><b><span id="cv-notes">0</span><span class="of" id="cv-of"></span></b><span>Notes written</span></div>
<div class="score"><b><span id="cv-weeks">0</span><span class="of" id="cv-weeks-of"></span></b><span>Weeks covered</span></div>
</div>
<div class="scoreboard" id="sb-questions" hidden>
<div class="score"><b><span id="sc-done">0</span><span class="of" id="sc-of"></span></b><span>Attempted</span></div>
<div class="score"><b id="sc-first">&ndash;</b><span>Correct</span></div>
<div class="score is-bad"><b id="sc-wrong">0</b><span>Wrong</span></div>
<div class="score is-star"><b id="sc-star">0</b><span>Starred</span></div>
</div>
</header>

<div class="tabs" role="tablist" aria-label="Notes, Anki or questions">
<button type="button" id="tab-notes" role="tab" aria-selected="true" aria-controls="panel-notes">Notes <span class="tc" id="tc-notes">{written}/{lectures}</span></button>
<button type="button" id="tab-anki" role="tab" aria-selected="false" aria-controls="panel-anki">Anki</button>
<button type="button" id="tab-questions" role="tab" aria-selected="false" aria-controls="panel-questions">Practice questions <span class="tc">{questions}</span></button>
</div>

<div class="q-shell is-solo" id="panel-anki" role="tabpanel" aria-labelledby="tab-anki" hidden>
<div class="tab-empty">
<h2>The decks are not up yet.</h2>
<p>This is where the {course} Anki cards for weeks {weeks} will live, filed by week and
lecture the way the notes are. Nothing has been uploaded into it yet.</p>
</div>
</div>

<div class="q-shell" id="panel-notes" role="tabpanel" aria-labelledby="tab-notes">
<aside class="rail">

<section>
<p class="panel-h">Week</p>
<div class="chips" id="note-week-chips"></div>
</section>

<section>
<p class="panel-h">Lectures</p>
<nav class="lecindex" id="note-index" aria-label="Jump to a lecture"></nav>
</section>

<section>
<p class="panel-h">Save as PDF</p>
<button class="print-cta" id="print-all" type="button" disabled>Save every note as one PDF</button>
<p class="railnote">Each note has its own <strong>PDF</strong> button, and each week can be
saved in one go. Print it, annotate it, keep it.</p>
</section>

</aside>

<main class="stream" id="note-stream">
<div class="q-loading">Loading notes&hellip;</div>
</main>

<div class="posbar notebar" id="notebar" hidden>
<button class="pb-step pb-top" id="nb-top" type="button" title="Back to the top" aria-label="Back to the top">Top</button>
</div>
</div>

<div class="q-shell q-flow" id="panel-questions" role="tabpanel" aria-labelledby="tab-questions" data-view="stream" data-mode="tutor" hidden>

{howto}

<div class="qbar" id="qbar">

<div class="qbar-filters">
<label class="qsel"><span>Question set</span><select id="f-family"></select></label>
<label class="qsel"><span>Week</span><select id="f-week"></select></label>
<label class="qsel" id="f-tag-wrap" hidden><span>Topic</span><select id="f-tag"></select></label>
<label class="qsel"><span>Status</span><select id="f-status"></select></label>
<button class="review-cta" id="review-wrong" type="button" disabled>Review wrong only <span class="n" id="review-n">0</span></button>
</div>

<div class="qbar-modes">
<div class="qseg" id="view-seg" role="group" aria-label="How the questions are laid out">
<span class="qseg-h">View</span>
<button type="button" data-view="stream" aria-pressed="true">Continuous</button>
<button type="button" data-view="paged" aria-pressed="false">One at a time</button>
</div>
<div class="qseg" id="mode-seg" role="group" aria-label="When answers are shown">
<span class="qseg-h">Mode</span>
<button type="button" data-mode="tutor" aria-pressed="true">Tutor</button>
<button type="button" data-mode="test" aria-pressed="false">Test block</button>
</div>
</div>

<div class="applied" id="applied" hidden></div>

</div>

<div class="testbar" id="testbar" hidden></div>

<main class="stream" id="stream">
<div class="q-loading">Loading {questions} questions&hellip;</div>
</main>

<div class="pagebar" id="pagebar" hidden></div>

<section class="progress-foot" id="progress-foot">
<p class="panel-h">Progress</p>
<p class="storenote" id="storenote" hidden></p>
<div class="resets">
<button class="backup-btn" id="export-progress" type="button">Download all my progress</button>
<button class="backup-btn" id="import-progress" type="button">Restore from a file</button>
<input type="file" id="import-file" accept="application/json,.json" hidden>
<button class="danger" id="reset-shown" type="button" disabled>Reset the questions shown (0)</button>
<button class="danger" id="reset-all" type="button">Reset all progress</button>
</div>
</section>

<div class="posbar" id="posbar" hidden>
<span class="pb-where" id="pb-where"></span>
<span class="pb-count" id="pb-count"></span>
<span class="pb-steps">
<button class="pb-step pb-top" id="pb-top" type="button" title="Back to the top" aria-label="Back to the top">Top</button>
<button class="pb-step" id="pb-prev" type="button" title="Previous question (k)" aria-label="Previous question">&uarr;</button>
<button class="pb-step" id="pb-next" type="button" title="Next question (j)" aria-label="Next question">&darr;</button>
</span>
<button class="pb-mark" id="pb-mark" type="button" hidden></button>
</div>
</div>

<script>
window.QUIZ_BLOCK = {block_json};
</script>
<script src="{quiz_js}"></script>
<script src="{notes_js}"></script>
<script src="{portal_js}"></script>

{footer}

</div>

</body>
</html>
"""


def main():
    for course in portal.COURSES:
        for slug, n, name, weeks in course["blocks"]:
            lead, desc, accent = existing(course, slug)
            q, written, lectures = block_counts(course, slug)
            d = course["slug"]
            cfg = {
                "slug": slug, "n": n, "name": name, "weeks": weeks,
                "course": course["short"], "store": course["store"],
                "families": course["families"],
                "qv": portal.digest(os.path.join(d, "data", "questions", "%s.json" % slug)),
                "nv": portal.digest(os.path.join(d, "data", "notes", "%s.json" % slug)),
            }
            label, fill = FAVICON[d]
            html = PAGE.format(
                base_css=portal.asset("base.css"), portal_css=portal.asset("portal.css"),
                quiz_js=portal.asset("quiz.js"), notes_js=portal.asset("notes.js"),
                portal_js=portal.asset("portal.js"),
                name=name, course=course["short"], weeks=weeks, lead=lead, desc=desc, accent=accent,
                fonts=portal.FONTS, nocache=portal.NOCACHE, cf=portal.CF, footer=portal.footer(), howto=HOWTO, favicon=portal.favicon(label, fill),
                blocknav=blocknav(course, slug), questions=q,
                written=written, lectures=lectures,
                block_json=json.dumps(cfg, ensure_ascii=False))
            io.open(os.path.join(d, "%s.html" % slug), "w",
                    encoding="utf-8", newline="\n").write(html)
            print("%-5s %-6s %2d/%d notes  %4d questions" % (d, slug, written, lectures, q))


if __name__ == "__main__":
    main()
