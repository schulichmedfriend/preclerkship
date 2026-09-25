# -*- coding: utf-8 -*-
"""Lift every inlined question picture out of the banks into a shipped file.

Purpose: replace each data: URI in */data/questions/*.json with a content-hashed
         file under <course>/assets/figures/, so a picture is fetched once and
         cached rather than re-downloaded inside the JSON on every visit.
Author:  Noor Sims
Date:    2026-09-25
Input:   every course's data/questions/*.json (rewritten in place)
Output:  <course>/assets/figures/<hash>.<ext>, and the banks pointing at them

This is the backfill. The two places that MAKE inlined pictures - tools/fom's
parse_qbank.py and parse_workbook.py, and the embed_image.py authoring helper -
write files now, so a rebuild does not put them back.

tools/figures.py already said why, of the notes side, and named the questions
side as the place still doing it wrong:

    "the questions side already shows the failure mode - the cortisol figure is
     byte-identical in four of them, because that format has no way to share one"

Naming the file after the hash of its own bytes is what fixes that: four copies
of the cortisol figure resolve to one asset. Across PoM 2 and FoM that is 92
pictures in 83 files.

No Pillow here, deliberately. The bytes in the banks have already been through
compress() - by embed_image.py when a question was authored, or by the PDF that
FoM's parser read them out of - so re-encoding them would lose detail to no end.
This decodes and writes what is already there, and is lossless.

Idempotent: a second run finds nothing to do.
"""

import argparse
import base64
import hashlib
import io
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portal

LOG = logging.getLogger("question_figures")

# The URL is relative to the page that carries it, and every page of a course -
# its block pages and its qbank - sits one level down from the repo root, so one
# relative path serves them all. Same convention as figures.py.
ASSET_URL = "assets/figures"

INLINE = re.compile(r"data:image/([a-z]+);base64,([A-Za-z0-9+/=]+)")

# What the extension says versus what the file is called. jpeg and jpg are the
# same picture, and the directory already holds .jpg from figures.py.
SUFFIX = {"jpeg": "jpg"}


def asset_name(raw, ext):
    """<12 hex of the content hash>.<ext> - the same name figures.py would give it.

    md5 rather than anything stronger for one reason: figures.py already writes
    md5[:12] into this same directory, and two tools naming the same kind of
    file two different ways is how a directory stops being readable. Nothing
    here is a security boundary; the hash is an identity, and its whole job is
    that four questions embedding one picture land on one file.
    """
    return "%s.%s" % (hashlib.md5(raw).hexdigest()[:12], SUFFIX.get(ext, ext))


def write_asset(course_slug, raw, ext="jpeg"):
    """Put these bytes in the course's figures directory. Returns the page's URL.

    The one place a question picture becomes a file, shared by this backfill,
    by FoM's two PDF parsers and by the embed_image authoring helper - so the
    three of them cannot drift into three naming schemes the way the inlining
    did. Writing the same bytes twice is a no-op, which is what makes a picture
    used by four questions cost one file.
    """
    name = asset_name(raw, ext)
    asset_dir = os.path.join(course_slug, *ASSET_URL.split("/"))
    target = os.path.join(asset_dir, name)
    if not os.path.exists(target):
        if not os.path.isdir(asset_dir):
            os.makedirs(asset_dir)
        io.open(target, "wb").write(raw)
        LOG.info("%s/%s  %.0f KB", course_slug, name, len(raw) / 1024.0)
    return "%s/%s" % (ASSET_URL, name)


def banks(course):
    """Every question bank a course has, in block order."""
    out = []
    for slug, _n, _name, _weeks in course["blocks"]:
        p = os.path.join(course["slug"], "data", "questions", "%s.json" % slug)
        if os.path.exists(p):
            out.append((slug, p))
    return out


def lift(course, dry_run=False):
    """Rewrite one course's banks. Returns (pictures found, files written)."""
    asset_dir = os.path.join(course["slug"], *ASSET_URL.split("/"))
    found = written = 0
    # what this run has already accounted for, so the tally counts a picture
    # shared by four questions as one file - including under --dry-run, where
    # nothing lands on disk for os.path.exists to find
    done = set()

    for slug, path in banks(course):
        text = io.open(path, encoding="utf-8").read()
        seen = []

        def swap(m):
            ext, payload = m.group(1), m.group(2)
            raw = base64.b64decode(payload + "=" * (-len(payload) % 4))
            name = asset_name(raw, ext)
            target = os.path.join(asset_dir, name)
            had = name in done or os.path.exists(target)
            seen.append((name, len(payload), len(raw), had))
            if not had and not dry_run:
                if not os.path.isdir(asset_dir):
                    os.makedirs(asset_dir)
                io.open(target, "wb").write(raw)
            done.add(name)
            return "%s/%s" % (ASSET_URL, name)

        out = INLINE.sub(swap, text)
        if not seen:
            continue

        found += len(seen)
        fresh = len([s for s in seen if not s[3]])
        written += fresh
        was, now = len(text.encode("utf-8")), len(out.encode("utf-8"))
        LOG.info("%-5s %-7s %2d picture%s, %2d new file%s, bank %.0f KB -> %.0f KB",
                 course["slug"], slug, len(seen), "" if len(seen) == 1 else "s",
                 fresh, "" if fresh == 1 else "s", was / 1024.0, now / 1024.0)
        for name, b64, dec, existed in seen:
            LOG.debug("    %s  %.0f KB base64 -> %.0f KB file%s",
                      name, b64 / 1024.0, dec / 1024.0, "  (shared)" if existed else "")
        if not dry_run:
            io.open(path, "w", encoding="utf-8", newline="\n").write(out)

    return found, written


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would move without touching anything")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="name every picture, and say which ones are shared")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(message)s")

    found = written = 0
    for course in portal.COURSES:
        f, w = lift(course, dry_run=args.dry_run)
        found += f
        written += w

    if not found:
        LOG.info("no inlined pictures left in any bank")
        return 0
    LOG.info("%d picture%s in %d file%s%s", found, "" if found == 1 else "s",
             written, "" if written == 1 else "s",
             " (dry run, nothing written)" if args.dry_run else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
