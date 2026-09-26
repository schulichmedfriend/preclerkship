# -*- coding: utf-8 -*-
"""Rebuild pom1/data/notes/<slug>.json as a lecture roster.

Purpose: list every PoM 1 lecture so the notes tab reads as a coverage map of
         the course rather than a list of whatever happens to be written up.
Author:  Noor Sims
Date:    2026-09-25
Input:   the vault's "99 - PoM 1" tree (dir via $POM1_VAULT)
Output:  pom1/data/notes/cardio|resp|ent|gi|gu.json

The vault's five block folders are what make PoM 1 five blocks rather than the
four its question banks ship as: the Respirology bank covers weeks 6 to 9 and
the vault splits week 9 out as ENT, which is where the course's own timetable
puts it. Every lecture lands here whether or not a note has been written for it.

A written note arrives later, from tools/pom1/charts_from_notes.py, which folds
an upper year's study notes into this roster and flips hasNote. Run this first;
it is the map, and the charts are what fills it in.
"""

import io
import json
import os
import re

VAULT = os.environ.get(
    "POM1_VAULT", u"/mnt/c/Users/nsims/medwiki/01 - Lectures/99 - PoM 1")

BLOCKS = [
    ("cardio", u"01 - Cardiology",    [1, 2, 3, 4, 5]),
    ("resp",   u"02 - Respirology",   [6, 7, 8]),
    ("ent",    u"03 - ENT",           [9]),
    ("gi",     u"04 - Gastroenterology", [10, 11, 12, 13]),
    ("gu",     u"05 - Genitourinary", [14, 15, 16, 17]),
]


def week_labels(slug):
    """Reuse the week headings the questions tab already shows, so both tabs
       name the same week the same way."""
    p = "pom1/data/questions/%s.json" % slug
    labels = {}
    if os.path.exists(p):
        for q in json.load(io.open(p, encoding="utf-8")):
            w, lab = q.get("week"), q.get("weekLabel")
            if w and lab and w not in labels:
                labels[w] = lab
    return labels


def sortkey(name):
    m = re.match(r"^(\d+)(?:\.(\d+))?\s*-\s*", name)
    if m:
        return (0, int(m.group(1)), int(m.group(2) or 0), name)
    return (1, 0, 0, name)          # In-Class notes carry no number and sort last


def main():
    grand = 0
    for slug, folder, weeks in BLOCKS:
        labels = week_labels(slug)
        out = {"block": slug, "weeks": []}
        for n in weeks:
            d = os.path.join(VAULT, folder, "Week %d" % n)
            files = [f for f in os.listdir(d)
                     if f.endswith(".md") and f != ("Week %d.md" % n)]
            files.sort(key=sortkey)
            lects = []
            for f in files:
                stem = f[:-3]
                m = re.match(r"^([\d.]+)\s*-\s*(.+)$", stem)
                num, name = (m.group(1), m.group(2)) if m else ("", stem)
                key = num or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
                lects.append({
                    "id": "%s-w%d-%s" % (slug, n, key),
                    "num": num or u"—",
                    "name": name,
                    "hasNote": False,
                })
            out["weeks"].append({"n": n, "label": labels.get(n, "Week %d" % n),
                                 "lectures": lects})
        p = "pom1/data/notes/%s.json" % slug
        if not os.path.isdir(os.path.dirname(p)):
            os.makedirs(os.path.dirname(p))
        io.open(p, "w", encoding="utf-8", newline="\n").write(
            json.dumps(out, indent=1, ensure_ascii=False))
        total = sum(len(w["lectures"]) for w in out["weeks"])
        grand += total
        print("%-7s %d weeks  %3d lectures" % (slug, len(out["weeks"]), total))
    print("total %d lectures" % grand)


if __name__ == "__main__":
    main()
