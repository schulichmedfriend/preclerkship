# Pre-clerkship portal

A static study portal for the pre-clerkship years at Schulich. One directory per
course, one page per block, two tabs per page: **notes**, a coverage map of every
lecture in the block whether or not it has been written up, and **practice
questions**, a quiz runner that keeps score. The questions tab reads the whole
block as one scrolling stream by default, and answers on the spot; a **View**
switch takes it one question at a time, and a **Mode** switch turns it into a
sat block of however many questions you ask for, marked only once you submit.

No build step, no framework, no server. HTML, three JS files, two stylesheets and
a folder of JSON per course. Serve the folder and it works.

By the **Open-Source Medicine Club** and the **AI in Medicine Club**.

Live at **<https://schulichmedfriend.github.io/preclerkship/>**.
Questions, corrections and contributions: <schulichmedfriends@gmail.com>.

## The four courses

| Course | Year | State |
| --- | --- | --- |
| [Foundations of Medicine](fom/) | 1 | 4 blocks, weeks 1–15, 1,979 questions |
| [Principles of Medicine 1](pom1/) | 1 | not built yet |
| [Principles of Medicine 2](pom2/) | 2 | 5 blocks, weeks 1–20, 1,487 questions |
| [Transition to Clerkship](t2c/) | 2 | not built yet |

The two empty ones still have a card on the hub, greyed and unlinked. That is
deliberate, and it is the same habit the rest of the portal keeps: a lecture with
no note still renders on the notes tab, a question set with nothing in it still
renders in the filter bar. Showing the shape of the whole thing, gaps included,
is more useful than showing only the parts that happen to be done.

## How a week gets built

Every week of a course is assembled by the same run, and the pipeline below is
what it does. One reservoir of content, three exposures to it, one repo out the
front.

![How a week of the course is built: a weekly run keeps a content reservoir
current - the Obsidian vault of inherited upper-year notes, this year's slides
pulled through the OneNote MCP server, and review slides. From that reservoir
come three exposures to the same material - charts to understand, Anki to
remember, and a question bank to apply - and all three feed this repo, which in
turn feeds class workshops and the public site.](docs/pipeline.svg)

The run itself is a Claude Code skill, [`skills/pom2-week/`](skills/pom2-week/),
which is published here rather than kept local because it is the recipe, not
just the output: its `SKILL.md` is the stage-by-stage order, and
[`pipeline.html`](skills/pom2-week/pipeline.html) is the same diagram with
screenshots of each stage.

Read it as one group's working recipe rather than something that runs anywhere
as-is. It names absolute paths on the machine it was written on, and it assumes
an Obsidian vault laid out a particular way.

## Layout

```
index.html         the hub, one card per course
base.css           design tokens, the reset, the page frame   ) the engine,
portal.css         everything the portal draws                ) shared by
portal.js          tab switching, shared helpers              ) every
notes.js           the notes tab, including the PDF printing  ) course
quiz.js            the question runner and the progress store )

fom/               one course: its pages, its data, its README
pom2/              the same
pom1/  t2c/        placeholders, a landing page and nothing behind it

tools/portal.py       the course roster: blocks, families, accents, store keys
tools/build_pages.py  every course's block pages, from one template
tools/build_index.py  every course's landing page
tools/build_hub.py    the front door
tools/                PoM 2's extractors (an Obsidian vault in)
tools/fom/            FoM's extractors (the question-bank PDFs in)
```

### What makes a course a course

Only three things, and all of them are data in
[`tools/portal.py`](tools/portal.py): its **block list**, its **question-set
families**, and the **localStorage prefix** its progress is kept under. The
engine reads all three off `window.QUIZ_BLOCK`, which the builders write into
each page. Adding a fifth course is a dictionary, a directory and some JSON.

That matters because the alternative was a copy of `quiz.js` per course, and
those copies diverge. When Foundations was first built as its own site, its copy
of the engine had already drifted in three places within a day.

## Run it

```bash
python -m http.server 8000
```

Then open <http://localhost:8000>. A plain `file://` open works too, except that
browsers block `fetch` of local JSON, so the tabs come up empty. Use the server.

## Rebuilding

Always from the repo root. The three builders read only what is already in the
repo, so they run anywhere; each course's extractors read sources outside it and
take their paths from the environment.

```bash
python tools/fom/parse_qbank.py         # the question-bank PDFs -> fom/data/questions/
python tools/fom/rosters_from_vault.py  # the vault              -> fom/data/notes/
python tools/rosters_from_vault.py      # the vault              -> pom2/data/notes/
python tools/charts_from_vault.py       # folds written notes on top

python tools/build_pages.py             # every course's block pages
python tools/build_index.py             # every course's landing page
python tools/build_hub.py               # the hub and its totals
```

Run the last three after editing any CSS or JS as well, because they stamp each
asset's content hash into its URL and the stamp goes stale otherwise.

Each course's README covers its own sources and its own quirks:
[fom/README.md](fom/README.md), [pom2/README.md](pom2/README.md).

## Progress stays on the device

Answers, stars and per-lecture accuracy are written to the browser's
`localStorage`, under a **separate prefix per course**, so the four never read or
overwrite each other even though they share an origin. Nothing is sent anywhere
and there is no backend.

The flip side is that it does not follow you, so each course's questions tab has
**Download all my progress** and **Restore from a file**, which move a JSON file
by hand. One file holds every block of that course, and a restore only adds and
updates, so an out of date file cannot overwrite newer answers.

## Open source

The beauty of open source is that anyone can access the work, improve it or
customize it to their needs. It is crowdsourced expertise that creates
user-vetted products.

**To customize it.** Anything here can change, from the courses it covers to the
wording and the layout. Paste this into Claude Code:

```
Clone this repo and read the README so you understand how the portal is built. I want to
make it mine: [what you want changed, for example: cut it down to the course I am on,
import my own lecture notes and questions, restyle the pages, or build an Anki deck from
only the questions I got wrong]. Work out which files that touches, make the change, and
rebuild with the scripts in tools/.
```

You can also just take the material out. The questions and the notes are plain
JSON under each course's `data/`, so you can extract either into whatever you
already study from. They are updated week by week, so what you pull is a snapshot.

**To improve it.** Suggest a feature, fix an answer you think is wrong, or send in
questions of your own. Corrections and questions are the two most useful things
to send.

## Licence and content

The code is MIT, see [LICENSE](LICENSE).

The study content under each course's `data/` came out of shared course material
that students already pass between years: class question banks, the
Pre-Clerkship Workbook, Elentra module knowledge checks, weekly quizzes, slide
concept checks and questions written from the case and small-group sessions.

**They are here on purpose.** Putting them somewhere public is the reason this
repository exists, not an accident of packaging. Where a question came out of a
peer-written bank, its errors and gaps are flagged on the question itself rather
than quietly patched, so you can see what you are trusting before you trust it.
