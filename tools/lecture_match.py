# -*- coding: utf-8 -*-
"""Match a question to the vault lecture note whose material it tests.

Purpose: the content-based half of tools/review_lectures.py, for the question
         sets that carry no lecture attribution at all - HippoNotes, and every
         FoM and PoM 1 family.
Author:  Noor Sims
Date:    2026-09-25
Input:   vault lecture note text, and a question's own text
Output:  the best-matching lecture, or None

Not imported for its own sake; run tools/review_lectures.py.

HOW IT DECIDES, AND WHEN IT REFUSES
-----------------------------------
Okapi BM25 over the lecture notes, which is chosen over plain TF-IDF cosine
for one reason that matters here: the notes run from 43 characters to 57,000,
and BM25's length normalisation is what stops "Contraception" - the longest
note in the vault - from winning every gynecology question by sheer size.

A match is only taken when it is **unambiguous**, on two tests that a question
must pass both of:

- an absolute **floor**, so a question about nothing the block teaches (a stray
  GI question in the psychiatry bank, and there is one) matches nothing; and
- a **margin** over the runner-up, so a question that two lectures cover
  equally well is left alone rather than arbitrarily given to one.

Both thresholds were set by running this against the 926 PoM 2 questions whose
lecture is already known from a link or a name somebody wrote, and reading the
accuracy off that. They are not guesses, and `--validate` re-runs that check.

A question is scored against its OWN BLOCK first. Failing that it is scored
against the whole course at a higher bar, which is how a question filed in the
wrong block still finds its lecture - a real case, since the HippoNotes
neurology chapter opens with nine rheumatology questions.
"""

import io
import math
import os
import re

# Tuned on the 924-question validation set; see --validate. Each tier is set
# where measured precision is 90% or better, and the scopes widen as the
# evidence for the question's own filing weakens.
FLOOR = 6.0          # an absolute bar, so a question about nothing here matches nothing
WEEK_MARGIN = 1.4    # 90% precision, 53% coverage - the primary tier
BLOCK_MARGIN = 1.6   # 90% precision, for a question whose week is wrong or absent
XMARGIN = 1.8        # 92%, and only ever used outside the question's own block

_WORD = re.compile(r"[a-z][a-z0-9\-]{2,}")

# Medical prose is full of words that carry no discriminating power, plus the
# scaffolding every question is built from ("which of the following is TRUE").
STOP = set("""
the and for with that this from are was were has have had not but they you
your его which following true false correct incorrect answer question option
options select all apply choose best most least likely next step patient
presents presenting year old man woman male female his her their who
also can may might would could should will shall does did done being been
one two three four five six seven eight nine ten first second third
about above after again against because before below between both during
each few further here how into itself more other once only over own same
some such than then there these those through too under until very what
when where while why
""".split())


def words(text):
    return [w for w in _WORD.findall((text or "").lower()) if w not in STOP]


def strip_md(s):
    """Vault markdown reduced to the words in it."""
    s = re.sub(r"^---.*?^---", " ", s or "", flags=re.S | re.M)   # frontmatter
    s = re.sub(r"```.*?```", " ", s, flags=re.S)                  # code / mermaid
    s = re.sub(r"!\[\[[^\]]*\]\]", " ", s)                        # embeds
    s = re.sub(r"\[\[([^\]|]*)(?:\|[^\]]*)?\]\]", r"\1", s)       # wikilinks
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"[#>*_`|\-]+", " ", s)
    return s


def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"&[a-z]+;|&#\d+;", " ", s)
    return s


def question_text(q):
    """Everything the question says, which is what gets matched.

    The answer body is included deliberately: a stem can be four words
    ("Which of the following is FALSE?") and carry nothing to match on, while
    its explanation names the mechanism, the drug and the diagnosis. Options
    are included for the same reason.
    """
    parts = [strip_html(q.get("stem")), strip_html(q.get("answer"))]
    for o in q.get("options") or []:
        parts.append(strip_html(o.get("html")))
    # a preamble is usually {"title", "html"} but a few banks carry a bare string
    pre = q.get("preamble")
    if isinstance(pre, dict):
        parts.append(strip_html(pre.get("html")))
    elif isinstance(pre, str):
        parts.append(strip_html(pre))
    return " ".join(parts)


class Index(object):
    """A BM25 index over one course's lecture notes."""

    K1 = 1.4
    B = 0.72
    TITLE_WEIGHT = 8     # a title word is worth this many body words

    def __init__(self, docs):
        """docs: [(key, title, body_text)] - key is whatever the caller wants back."""
        self.keys = []
        self.tf = []
        self.length = []
        df = {}
        for key, title, body in docs:
            bag = {}
            for w in words(body):
                bag[w] = bag.get(w, 0) + 1
            # the title is the one part of a note guaranteed to be about the
            # lecture rather than about something it mentions in passing
            for w in words(title):
                bag[w] = bag.get(w, 0) + self.TITLE_WEIGHT
            self.keys.append(key)
            self.tf.append(bag)
            self.length.append(sum(bag.values()) or 1)
            for w in bag:
                df[w] = df.get(w, 0) + 1
        n = len(self.tf) or 1
        self.avg = sum(self.length) / float(n)
        self.idf = dict((w, math.log(1.0 + (n - c + 0.5) / (c + 0.5)))
                        for w, c in df.items())

    def score(self, query_words, only=None):
        """[(score, key)] descending. `only` limits which docs may be scored."""
        qbag = {}
        for w in query_words:
            qbag[w] = qbag.get(w, 0) + 1
        out = []
        for i, key in enumerate(self.keys):
            if only is not None and key not in only:
                continue
            tf, dl, s = self.tf[i], self.length[i], 0.0
            for w, qn in qbag.items():
                f = tf.get(w)
                if not f:
                    continue
                idf = self.idf.get(w, 0.0)
                denom = f + self.K1 * (1 - self.B + self.B * dl / self.avg)
                # a query word repeated twenty times in one question must not
                # count twenty times over
                s += idf * (f * (self.K1 + 1) / denom) * min(qn, 3)
            if s > 0:
                out.append((s, key))
        out.sort(key=lambda t: -t[0])
        return out


def pick(index, q, in_block, in_week):
    """(key, route) for the lecture this question tests, or (None, reason).

    Three tiers, narrowest scope first, because the narrower the scope the
    stronger the outside evidence for it and the fewer near-identical lectures
    there are to confuse:

    1. the **week** the question carries. Ten or so candidates rather than
       forty, and measured 90% precision against the known set - three points
       better than the block at eight points more coverage.
    2. the **block**, for a question whose week is missing or wrong. The
       HippoNotes weeks are known to be wrong in places, which is exactly the
       case this tier exists for.
    3. the **whole course**, and only accepted when the winner sits OUTSIDE
       the question's own block - a question that is simply filed in the wrong
       block, of which there are real examples.
    """
    qw = words(question_text(q))
    if len(qw) < 8:
        return None, "too-short"

    def best(only, margin):
        r = index.score(qw, only=only)
        if not r:
            return None
        top, second = r[0], (r[1][0] if len(r) > 1 else 0.0)
        if top[0] >= FLOOR and top[0] >= margin * max(second, 1e-9):
            return top[1]
        return None

    if in_week:
        k = best(in_week, WEEK_MARGIN)
        if k:
            return k, "derived-week"

    if in_block:
        k = best(in_block, BLOCK_MARGIN)
        if k:
            return k, "derived-block"

    k = best(None, XMARGIN)
    if k and k not in (in_block or ()):
        return k, "derived-xblock"

    return None, "ambiguous"
