# Principles of Medicine 1

One course in the [pre-clerkship portal](../README.md). Its pages live in this
directory; the engine they run on (`base.css`, `portal.css`, `portal.js`,
`quiz.js`, `notes.js`) is shared and sits at the repo root.

The second half of first year, system by system. Five block pages, each with a
**notes** tab and an **Anki** tab, plus one **question bank** holding every
question in the course at once.

What makes this course this course rather than another is three things, all of
them data in [`tools/portal.py`](../tools/portal.py): its block list, its
question-set families, and the key its progress is stored under.

## What is in it

**2,109 practice questions** across five blocks, weeks 1 to 17, transcribed out
of the block Question Bank PDFs and the Pre-Clerkship Workbook rather than
rewritten. None of it is AI-generated.

| Block | Weeks | Questions | Lecture notes |
|---|---|---|---|
| 1 · Cardiology | 1–5 | 619 | 26 of 43 |
| 2 · Respirology | 6–8 | 259 | 16 of 25 |
| 3 · Ear, Nose & Throat | 9 | 121 | 0 of 7 |
| 4 · Gastroenterology | 10–13 | 596 | 12 of 41 |
| 5 · Nephrology & Urology | 14–17 | 514 | 0 of 33 |

95 questions carry a figure — ECGs, rhythm strips, chest films, angiograms,
histology, anatomical diagrams.

### Five blocks out of four PDFs

The question banks ship as four documents and the course runs as five blocks,
because the **Respirology and ENT** bank covers weeks 6 to 9 and week 9 is ENT
— a block of its own on the timetable and in the vault's lecture tree. The Resp
PDF is therefore read twice and split on the week number, which is the same
rule everything else here is filed by.

The vault is what settles that, and every other question of where a week
belongs: its `99 - PoM 1` tree is five folders of `Week N` directories, and both
tabs take their block, their week and their lecture list from it.

### The question sets

Every question keeps the set it arrived in, and the **Question set** filter is
that split:

- **Module questions** (644): the knowledge checks inside each week's Elentra
  asynchronous learning modules.
- **Weekly quizzes** (124): the week's quiz as it was sat, kept whole.
- **Meds 2024 bank** (546): the student-written bank the Class of 2024 Academic
  Directors built in May 2021, re-filed week by week by the Meds 2025
  volunteers. About half the cardiology questions and a handful of the
  respirology ones were reviewed by faculty; the rest were not, and the bank
  says so on its own second page.
- **New questions** (331): written fresh by the Meds 2025 volunteers through the
  spring of 2022 to fill the gaps. Not verified by faculty.
- **Pre-Clerkship Workbook** (464): the 2023 edition handed down through the
  Schulich classes of 2015 to 2025 — its Cardiology, Respiration & Airways, Ear
  Nose & Throat, Gastroenterology and Genitourinary chapters.

The standalone *P1 Practice Questions, Class of 2024* PDF is **not** a sixth
set. The block banks' Meds 2024 sections already re-file it: 515 of its 552
checkable questions are in them verbatim.
[`tools/pom1/check_practice.py`](../tools/pom1/check_practice.py) is that check
rather than an assertion of it. The 37 it does not find belong to a 2021
timetable that ran to eighteen weeks and no longer maps onto the seventeen the
banks and the vault use; they are left out rather than filed by guess.

### The workbook is filed by organ system, not by week

Which **block** a workbook question belongs to is never in doubt here, unlike in
Foundations: PoM 1's blocks are organ systems and so are the workbook's
chapters, so the two line up one to one, and the ENT chapter is the whole of the
ENT block with no inference at all. The **week** inside the other four blocks is
scored against the vocabulary of that week's own lectures, taken from the vault.
That table is written out in
[`tools/pom1/parse_workbook_pom1.py`](../tools/pom1/parse_workbook_pom1.py)
rather than hidden, so a filing you disagree with is a line you can edit. **61
questions** matched nothing strongly enough and are flagged *filed by best
guess* on their own face.

## What is flagged, and why

Three kinds of rough edge are marked on the face of the question rather than
quietly patched:

- **Letter only** (305). Many keys give a letter and no reasoning. The letter is
  shown as printed, with a note saying that is all the bank offers.
- **No key in the source** (11). Those render, marked unscorable, and sit
  outside the accuracy figures. Inventing a letter would be worse than admitting
  there isn't one.
- **Filed by best guess** (61). The workbook questions above.

Where a question's own answer looks wrong it is left as the bank wrote it.

### What is left out, and why

- The workbook's Cardiology chapter also prints **25 Extended Match items** and a
  run of **LMCC cases**. Both are shaped unlike anything else in the workbook —
  one 17-option list serving 25 numbered items whose whole key is a single line,
  and cases whose questions carry no numbers at all — and neither survives the
  numbered-line rule the parser is built on.
- The workbook's **Respiration chapter prints 39 questions and 45 answers**.
  Questions 40 to 45 are not in the document; the gap is the source's, and the
  six orphan answers are left where they are rather than reverse-engineered into
  questions.

## Is it really a transcription?

[`tools/pom1/check_parse.py`](../tools/pom1/check_parse.py) looks for every long
stem and option back in the PDF it came from:

```
cardio  stems  432/441   options   646/646
resp    stems  191/196   options   279/280
ent     stems   74/75    options    99/100
gi      stems  428/440   options   631/634
gu      stems  360/363   options   565/567
total   stems 1485/1515 (98.0%)  options 2220/2227 (99.7%)
```

The remainder are matching questions, where the walker rebuilds a roman-numeral
item list as its own `<ol>` and so no longer matches the source's single line of
running text.

## The notes tab

Every lecture in the course is listed whether or not a note has been written
for it, so the tab reads as a map of the block rather than a list of whatever
happens to be done. **54 of 149** carry a written note today, with 425 figures
between them, lifted out of the upper-year study notes by
[`tools/pom1/notes_from_pdf.py`](../tools/pom1/notes_from_pdf.py).

The ENT and Nephrology & Urology blocks have no note at all yet, because no
source covering them has been handed in. They render as a full block of
placeholders, which is the point of the tab.

## Rebuilding

Always from the repo root, in this order.

```bash
python tools/pom1/parse_qbank.py         # the bank PDFs + workbook -> data/questions/
python tools/roman_items.py              # item lists read as options -> back in the stem
python tools/pom1/rosters_from_vault.py  # the vault               -> data/notes/ (the map)
python tools/pom1/notes_from_pdf.py      # the study notes         -> data/notes/ (filled in)
python tools/question_figures.py         # any newly-inlined picture -> assets/figures/

python tools/build_pages.py              # the five block pages and the bank
python tools/build_index.py              # the landing page and its counts
python tools/build_hub.py                # the hub and its totals
```

`rosters_from_vault.py` rewrites the roster from scratch, so `notes_from_pdf.py`
has to follow it or the notes it wrote are the ones thrown away.

The extractors read sources outside the repo and take their paths from the
environment:

```bash
export POM1_QBANK_DIR="/path/to/Question Bank"                 # the four block PDFs
export POM1_WORKBOOK="/path/to/Preclerkship WB 2023_FINAL_ (1).pdf"
export POM1_NOTES_DIR="/path/to/the upper-year study notes"
export POM1_VAULT="/path/to/medwiki/01 - Lectures/99 - PoM 1"  # the lecture tree
```

Each defaults to a folder under `pom1/`, which is where the sources were dropped
while this was built. **Those source PDFs are not in the repo** — see
`.gitignore` — because they are the upstream documents, not the portal's output.

### How the PDFs are parsed

`tools/pom1/parse_qbank.py` reads coordinates, not flat text, and imports the
Foundations walker rather than copying it: the two banks were laid out by the
same volunteers a year apart and share a grid. Three things differ and each is
commented in the file — the section vocabulary (module / weekly quiz / Meds2024
/ new, under a *Questions from the Week* parent that is not itself a set), an
option letter set in its own line box with its text tabbed away from it, and a
different option indent per PDF, which is why an option is recognised by having
the letter that is due next rather than by sitting at a particular x.

## Progress stays on the device

Answers, stars and per-lecture accuracy are written to `localStorage` under
`nsq.pom1.v1.<block>`, a different prefix from every other course, so the four
can be served from one origin without touching each other's progress. The
questions tab has **Download all my progress** and **Restore from a file** for
moving it between browsers.

## Licence and content

The code is MIT, see [LICENSE](../LICENSE).

The questions came out of shared course material that students already pass
between years: the PoM 1 block question banks compiled by Meds 2025 volunteers
in 2022, which themselves re-file the student-written bank the Class of 2024
Academic Directors built in 2021, plus the Pre-Clerkship Workbook, written by
the Class of 2017 and revised by every class since. Neither was verified by
faculty in full, and the compilers say so on their own second page. Where a
question came out of a peer-written bank, its gaps are flagged on the question
rather than quietly patched, so you can see what you are trusting before you
trust it.
