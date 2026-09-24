# Foundations of Medicine

One course in the [pre-clerkship portal](../README.md). Its pages live in this
directory; the engine they run on (`base.css`, `portal.css`, `portal.js`,
`quiz.js`, `notes.js`) is shared and sits at the repo root.

A static study portal for Foundations of Medicine, built around one page per
block. Each page has two tabs: **notes**, a coverage map of every lecture in the
block whether or not it has been written up, and **practice questions**, a quiz
runner that keeps score.

No build step, no framework, no server. Five HTML files, three JS files, two
stylesheets and a folder of JSON. Serve the folder and it works.

It runs on the same engine as every other course in the portal. What makes it
this course rather than another is three things, all of them data: its block
list, its question-set families, and the key its progress is stored under. All
three live in `tools/portal.py`.

## What is in it

**1,979 practice questions** across the four blocks, weeks 1 to 15, transcribed
out of the Question Bank PDFs and the Pre-Clerkship Workbook rather than
rewritten. None of it is AI-generated.

| Block | Weeks | Questions |
|---|---|---|
| 1 · Principles & Development | 1–4 | 508 |
| 2 · Regulation, Neoplasia & Aging | 5–8 | 513 |
| 3 · Blood & Malignancy | 9–12 | 581 |
| 4 · Infection & Immunity | 13–15 | 377 |

Every question keeps the set it arrived in, and the **Question set** filter is
that split:

- **Module questions**: the knowledge checks inside each week's Elentra
  asynchronous learning modules.
- **Readiness assessments** and **self-assessments**: the week's RA and SA.
  Several early weeks never had one, and those say so rather than going quietly
  missing.
- **Meds 2024 bank**: the student-written, *instructor-approved* bank the Class
  of 2024 Academic Directors built in December 2020. Their questions went to the
  teaching faculty and the instructors' edits are folded in, except for a tail of
  each week that time ran out on.
- **New questions**: written by the Meds 2025 volunteers in December 2021 to
  fill the gaps. The bank states on its own second page that these were **not
  verified by faculty**.
- **Pre-Clerkship Workbook**: the 2023 edition of the workbook handed down
  through the Schulich classes of 2015 to 2025. Only three of its seventeen
  chapters are FoM (Foundations, Hematology, Infection & Immunity); the rest is
  PoM 1 and PoM 2 and is left alone.

The standalone *FoM Practice Questions, Class of 2024* PDF is **not** a sixth
set. The block banks already re-file all 492 of its questions week by week, with
the same rationales, so including it would have doubled 484 questions and left 8
stragglers looking like new material.

67 questions carry a figure (graphs, blood films, radiographs, Gram stains,
a pedigree), inlined into the question as a `data:` URI so there is no second
file to lose.

### The workbook is filed by subject, not by week

Which **block** a workbook question belongs to is the workbook's own: its three
FoM chapters map onto blocks 1–2, 3 and 4. The **week** inside that block is
inferred, in two ways:

- Its Foundations chapter labels every question with a *subject area*. Those
  labels are the source's own filing, so they do the work. 90 questions are
  placed by a subject that names one week outright, and 51 by a subject that
  narrows it to two or three, with the wording choosing between just those. The
  same labels fill the **Topic** dropdown in the question toolbar.
- Hematology and Infection & Immunity carry no labels at all, so those 186 are
  scored against the vocabulary of their block's own lectures. That table is
  written out in `tools/parse_workbook.py` rather than hidden, so a filing you
  disagree with is a line you can edit.

27 questions matched nothing strongly enough and are flagged **filed by best
guess** on their own face.

## What is flagged, and why

A bank handed between years has rough edges, and hiding them is worse than
showing them. Three kinds are marked on the face of the question rather than
quietly patched:

- **No key in the source** (18 questions). Week 12's readiness assessment says
  *not yet released* where its answer key should be. Those questions render,
  marked unscorable, and sit outside the accuracy figures. Inventing a letter
  would have been worse than admitting there isn't one.
- **Letter only.** Many keys give a letter and no reasoning. The letter is shown
  as printed, with a note saying that is all the bank offers.
- **Renumbered.** Week 4's self-assessment prints its questions 8–15 and then
  restarts at 9, while its answer key runs straight through 1–12. Those are
  numbered by position, which is what the key actually answers, and each one
  says so on its face.

Where a question's own answer looks wrong it is left as the bank wrote it.

## Run it

```bash
python -m http.server 8000
```

from the repo root, then open <http://localhost:8000/fom/>. A plain `file://` open works too, except that
browsers block `fetch` of local JSON, so the tabs come up empty. Use the server.

## Files

```
fom/index.html             the landing page, four block cards
fom/b1|b2|b3|b4.html       one page per block
fom/data/questions/*.json  the question bank
fom/data/notes/*.json      the lecture rosters

../base.css     design tokens, the reset, the page frame   (shared)
../portal.css   everything the portal draws                (shared)
../portal.js    tab switching, shared helpers              (shared)
../notes.js     the notes tab, including the PDF printing  (shared)
../quiz.js      the question runner and the progress store (shared)
../tools/fom/   this course's extractors (the PDFs in, the JSON out)
../tools/       the three builders that render every course's pages
```

## Rebuilding

```bash
python tools/parse_qbank.py         # PDFs      -> data/questions/b*.json
python tools/rosters_from_vault.py  # the vault -> data/notes/b*.json
python tools/build_pages.py         # the four block pages
python tools/build_index.py         # the landing page and its counts
```

The first two read sources outside the repo and take a path from the
environment; the last two read only `data/` and the pages already here, so they
run anywhere. Run the last two after editing any CSS or JS as well, because they stamp
each asset's content hash into its URL, and the stamp goes stale otherwise.

```bash
export FOM_QBANK_DIR="/path/to/Question Bank"                  # the four block PDFs
export FOM_WORKBOOK="/path/to/Preclerkship WB 2023_FINAL_ (1).pdf"
export FOM_VAULT="/path/to/medwiki/01 - Lectures/99 - FoM"     # the lecture tree
```

### How the PDFs are parsed

`parse_qbank.py` reads coordinates, not flat text. All four PDFs lay out the
same grid (a question number at the left margin, its stem one indent in, an
option letter at a second indent, a wrap at a third) and set headings in
larger type. Reading x and the font size makes the parse structural rather than
a pile of regexes guessing at `1.`, which matters because these stems are full
of sentences that open with a number and a period, and full of fill-in-the-blank
runs of underscores.

Three shapes need the geometry specifically, and each is commented in the file:
extended-match blocks where one option list serves several questions,
two-column matching questions, and figures, which are attached to whichever
question is open when the flow reaches them.

The workbook needed its own parser. The block banks indent (number at the
margin, stem one in, options at a second) and the workbook indents nothing, so
geometry tells you nothing there and the line's own shape has to carry it. That
is safe only because each chapter numbers straight through: a line starts a
question when it is numbered *and* that number is the one due next, which is
what stops a stem sentence opening "3. " from starting a phantom question.

Both parsers are checked against the PDFs they came from. Of the block banks'
793 prose stems, 791 are present verbatim in the source text, and of 1,716 long
options, 1,715 are; of the workbook's 147 long stems and 307 long options, all
of them are. The places where a bank contradicts itself are listed above.

## The notes tab

Every lecture in the course is listed whether or not a note has been written for
it, so the tab reads as a map of the block rather than a list of whatever
happens to be done. All 158 are placeholders today, taken from the vault's
lecture folders. Because no block has a written note yet, every page opens on
the questions tab; the notes tab takes over as soon as one is written.

`rosters_from_vault.py` is what builds them. The PoM 2 portal has a second
script that lifts a written chart out of the top of each lecture note and folds
it into this roster; nothing in the FoM tree carries one yet, so that step has
no counterpart here.

## Progress stays on the device

Answers, stars and per-lecture accuracy are written to the browser's
`localStorage`, under `nsq.fom.v1.<block>`, a different prefix from the PoM 2
portal, so the two can be served from one origin without touching each other's
progress. Nothing is sent anywhere and there is no backend.

The flip side is that it does not follow you between browsers or machines, so
the questions tab has **Download all my progress** and **Restore from a file**.
One file holds every block and can be written or read from any of them, and a
restore only adds and updates, so an out of date file cannot overwrite newer
answers.

## Licence and content

The code is MIT, see [LICENSE](LICENSE).

The questions came out of shared course material: the FoM Question Bank compiled
by Meds 2025 volunteers in December 2021, which itself re-files the
student-written, instructor-approved bank the Class of 2024 Academic Directors
built in December 2020, plus the Pre-Clerkship Workbook, written by the Class of
2017 and revised by every class since. Neither was verified by faculty in full, and the 2021
compilers say so on their own second page. Where a question came out of a
peer-written bank, its gaps are flagged on the question rather than quietly
patched, so you can see what you are trusting before you trust it.
