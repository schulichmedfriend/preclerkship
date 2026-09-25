# -*- coding: utf-8 -*-
"""Resolve a vault image, re-compress it, ship it, and print the <img> tag for a question.

Purpose: turn an Obsidian embed into a file the question banks can point at.
Author:  Noor Simsam
Date:    2026-09-07
Input:   an image name as the vault writes it - "cortisol excess and deficiency.jpg",
         or the whole embed including the width hint, "![[incretin effect.png|600]]"
Output:  <course>/assets/figures/<hash>.jpg, and the <img> tag for it on stdout

Pictures ship as FILES the question points at, written by question_figures.
write_asset and named after their own bytes. quiz.js needs no image handling
either way - it renders the stem as HTML and the browser does the rest - but a
file is fetched once and then cached, where a data: URI is re-downloaded inside
the bank on every visit and cannot be shared by two questions that use it.

They used to be inlined here, and the cost was measured before that changed:
92 pictures across PoM 2 and FoM, 3.1 MB of base64 inside the JSON, 1.9 MB as
83 deduped files. endo.json alone was 2.8 MB, of which 1.4 MB was pictures.

Three things it does that doing it by hand does not:

  * **Re-compresses.** The vault original can be far larger than the site needs -
    the incretin graph is a 3 MB PNG and ships as a 75 KB JPEG. This walks the
    JPEG quality down, then the width, until the encoded bytes fit the budget.
  * **Reports the size it landed on**, so a picture that will not fit is a visible
    failure rather than a 400 KB line quietly pasted into the bank.
  * **Shares.** The filename is the hash of the bytes, so running it again on a
    picture the banks already carry writes nothing and hands back the same path.

Unlike the four rebuild scripts this one needs Pillow (present in the pyenv 3.9.13
that already carries PyMuPDF). It is an authoring helper for Stage 4, not part of
the portal build.

It cannot tell a cadaveric image from a clinical photograph, and does not try.
That call is made by looking at the picture; see the pom2-week skill.
"""

import argparse
import io
import logging
import os
import re
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import question_figures

LOG = logging.getLogger("embed_image")

# The site never shows a question picture wider than the question column. The
# budget is the file on disk now rather than the base64 string, which buys a
# third more picture for the same number - and it is a browser-cached file
# rather than bytes inside a bank that is re-fetched whole.
MAX_KB = 100
MAX_WIDTH = 900

# Quality floor is where JPEG artefacts start showing on a radiograph; below
# this, drop the width instead and re-try at good quality.
QUALITY_STEPS = (85, 75, 65, 55)
WIDTH_STEPS = (900, 750, 600, 480)

VAULT = os.environ.get("POM2_VAULT", u"C:/Users/nsims/medwiki/01 - Lectures/99 - PoM 2")
ATTACHMENTS = os.environ.get("POM2_ATTACHMENTS", "")


def attachment_roots() -> tuple:
    """Where to look for an embed's target, most likely first.

    Obsidian resolves ![[name]] against the whole vault, so the folder the note
    lives in is irrelevant and only the filename matters. POM2_VAULT points at
    the lectures subtree, so the vault root is two levels above it.

    Returns (recursive roots, vault root). The vault root is checked only at its
    top level, never walked: rglob over the whole vault dies on the anatomy
    folder, whose nested-structure directories run past the Windows path limit.
    """
    roots = []
    if ATTACHMENTS:
        roots.append(Path(ATTACHMENTS))
    vault_root = Path(VAULT).parent.parent
    roots.append(vault_root / "Attachments")
    return roots, vault_root


def clean_name(raw: str) -> str:
    """Accept a bare filename, a full ![[embed|600]], or a path; return the filename."""
    s = raw.strip()
    m = re.search(r"!\[\[([^\]|]+)", s)
    if m:
        s = m.group(1)
    s = s.split("|")[0].strip()
    return Path(s).name


def resolve(name: str) -> Path:
    """Find the image in the vault, or raise with the places that were tried."""
    direct = Path(name)
    if direct.is_file():
        return direct
    roots, vault_root = attachment_roots()
    tried = []
    for root in roots + [vault_root]:
        candidate = root / name
        tried.append(str(candidate))
        if candidate.is_file():
            return candidate
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for found in root.rglob(name):
                return found
        except OSError as exc:
            # a path past the Windows limit, or a folder that vanished under us
            LOG.warning("stopped searching %s: %s", root, exc)
    raise SystemExit(
        "cannot find %r. Tried:\n  %s\nSet POM2_ATTACHMENTS if the vault is elsewhere."
        % (name, "\n  ".join(tried))
    )


def compress(path: Path, max_width: int, fits) -> tuple:
    """Re-compress to the smallest JPEG that still looks right and passes fits().

    Returns (jpeg bytes, width used, quality used, ok) where ok says whether
    fits() was ever satisfied; when it was not, the smallest attempt is
    returned so the caller can decide between warning and failing.

    Quality is spent first because dropping pixels is what actually loses
    detail, and a keyed anatomy or radiology image is often keyed on detail.

    Shared with figures.py and with this module's own caller, which want
    different budgets against the same encoder, so the test is a callback
    rather than a byte count.
    """
    src = Image.open(path)
    if src.mode not in ("RGB", "L"):
        # JPEG has no alpha; flatten onto white rather than letting it go black.
        # A palette image keeps its transparency in the palette rather than in a
        # band, so "A" in src.mode is False, the paste runs with no mask, and the
        # transparent area comes out as whatever colour palette entry 0 happens
        # to be - slate blue on the Rise uterus diagrams. Convert first.
        if src.mode in ("P", "PA"):
            src = src.convert("RGBA")
        flat = Image.new("RGB", src.size, (255, 255, 255))
        flat.paste(src, mask=src.split()[-1] if "A" in src.mode else None)
        src = flat

    widths = [w for w in WIDTH_STEPS if w <= max_width] or [max_width]
    best = None

    for width in widths:
        scaled = src
        if src.width > width:
            height = int(round(src.height * (float(width) / src.width)))
            scaled = src.resize((width, height), Image.LANCZOS)
        for quality in QUALITY_STEPS:
            buf = io.BytesIO()
            scaled.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
            raw = buf.getvalue()
            if best is None:
                best = (raw, scaled.width, quality, False)
            if fits(raw):
                return raw, scaled.width, quality, True

    return best


def encode(path: Path, max_kb: int, max_width: int) -> tuple:
    """The JPEG a question ships. Returns (bytes, their length, width, quality)."""
    budget = max_kb * 1024
    raw, width, quality, ok = compress(path, max_width, lambda b: len(b) <= budget)

    if not ok:
        LOG.warning(
            "%s will not fit under %d KB; smallest was %.1f KB at %dpx q%d",
            path.name, max_kb, len(raw) / 1024.0, width, quality)
    return raw, len(raw), width, quality


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("name", help='vault image name, or the whole ![[embed]]')
    ap.add_argument("--course", default="pom2",
                    help="whose assets/figures to write into (default pom2)")
    ap.add_argument("--max-kb", type=int, default=MAX_KB,
                    help="file size budget in KB (default %d)" % MAX_KB)
    ap.add_argument("--max-width", type=int, default=MAX_WIDTH,
                    help="widest the picture may ship (default %d)" % MAX_WIDTH)
    ap.add_argument("--alt", default="",
                    help="alt text; worth setting when the picture IS the question")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)

    name = clean_name(args.name)
    path = resolve(name)
    raw, size, width, quality = encode(path, args.max_kb, args.max_width)
    src = question_figures.write_asset(args.course, raw, "jpeg")

    LOG.info("%s -> %s, %.1f KB, %dpx wide, q%d",
             path.name, src, size / 1024.0, width, quality)
    alt = ' alt="%s"' % args.alt.replace('"', "&quot;") if args.alt else ""
    sys.stdout.write('<img loading="lazy"%s src="%s">\n' % (alt, src))
    return 0


if __name__ == "__main__":
    sys.exit(main())
