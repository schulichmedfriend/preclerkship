# -*- coding: utf-8 -*-
"""Pull the three FoM chapters out of the Pre-Clerkship Workbook.

Purpose: add the workbook's Foundations, Hematology and Infection & Immunity
         chapters to the portal as a fifth question set.
Author:  Noor Sims
Date:    2026-09-20
Input:   Preclerkship WB 2023_FINAL_ (1).pdf (path via $FOM_WORKBOOK)
Output:  a list of question dicts per block, consumed by parse_qbank.py

Why this is not parse_qbank.py
------------------------------
The block banks indent: a question number at the left margin, its stem one
indent in, options at a second. The workbook indents nothing - every line of
every question sits at x = 42.6 - so geometry tells you nothing here and the
line's own shape has to carry the parse.

That is only safe because the workbook numbers each chapter straight through,
1..N, with no restarts. A line is a new question when it is numbered AND that
number is the one due next, which is what stops a stem sentence opening "3. " or
an option reading "D) 2007" from starting a phantom question. Option letters are
held to the same rule: they ascend from A within a question or they are prose.

The workbook covers the whole pre-clerkship, so only three of its seventeen
chapters are FoM. The rest is PoM 1 and PoM 2 and is left alone.
"""

import os
import re
import sys

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import question_figures

WORKBOOK = os.environ.get(
    "FOM_WORKBOOK",
    u"/mnt/c/Users/nsims/OneDrive/Documents/Question Bank/Preclerkship WB 2023_FINAL_ (1).pdf")

# chapter, question pages, answer pages, and the blocks it can land in.
# Page numbers are the PDF's own, not the printed ones, which run 1 behind.
CHAPTERS = [
    ("fom",  u"Foundations of Medicine",  (9, 30),  (232, 239), [1, 2]),
    ("heme", u"Hematology",               (31, 45), (240, 247), [3]),
    ("ii",   u"Infection & Immunity",     (46, 56), (248, 252), [4]),
]

Y_FOOTER = 725.0
SUBJ_RE = re.compile(u"^\\*?Subject areas?:\\s*(.+?)\\s*\\*?$", re.I)
NUM_RE = re.compile(u"^(\\d{1,3})[.):]\\s*")
OPT_RE = re.compile(u"^([A-Z])\\s*[.)]\\s+\\S")
# "*Use the options below for questions 2-10 ...*"
GROUP_RE = re.compile(u"questions?\\s+(\\d{1,3})\\s*[-–]\\s*(\\d{1,3})", re.I)
INSTR_RE = re.compile(u"^\\*|use the (options|following)|for questions", re.I)
# A shared-option block opens with one of these. The Foundations chapter always
# has a "Subject area:" line above it, which closes the question before it; the
# Hematology chapter has no subject areas at all, so the instruction itself has
# to be what closes the previous question, or its option list is read as that
# question's last option and the run below it is left optionless.
OPEN_RE = re.compile(u"^\\*?\\s*(use the options|use the following|for questions?\\s+\\d"
                     u"|match each|match the following)", re.I)
ANS_RE = re.compile(u"^(?:Answer:\\s*)?([A-Z])((?:\\s*(?:,|;|and|&|/|or)\\s*[A-Z])*)\\s*[.,:]?(\\s|$)")


def esc(s):
    return s.replace(u"&", u"&amp;").replace(u"<", u"&lt;").replace(u">", u"&gt;")


def runs_html(runs):
    out = []
    for text, bold, ital in runs:
        t = esc(text)
        if t.strip():
            if bold:
                t = u"<strong>%s</strong>" % t
            if ital:
                t = u"<em>%s</em>" % t
        out.append(t)
    return u"".join(out)


def plain(html):
    return (re.sub(u"<[^>]+>", u"", html)
            .replace(u"&amp;", u"&").replace(u"&lt;", u"<").replace(u"&gt;", u">"))


def join(parts):
    out = u""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if not out:
            out = p
        elif re.search(u"[a-z]-(?:</strong>|</em>)*$", out):
            out = re.sub(u"-((?:</strong>|</em>)*)$", u"\\1", out) + p
        else:
            out = out + u" " + p
    return re.sub(u"\\s{2,}", u" ", out).strip()


def drop_prefix(html, n):
    out, seen, i = [], 0, 0
    while i < len(html):
        if html[i] == u"<":
            j = html.index(u">", i)
            out.append(html[i:j + 1])
            i = j + 1
            continue
        if seen >= n:
            out.append(html[i])
        seen += 1
        i += 1
    return u"".join(out).lstrip()


def lines(doc, a, b):
    """Every line and image on pages a..b, in reading order."""
    out = []
    for pno in range(a - 1, b):
        page = doc[pno]
        items = []
        for blk in page.get_text("dict")["blocks"]:
            if blk["type"] == 1:
                if blk.get("image") and (blk["bbox"][2] - blk["bbox"][0]) > 60:
                    items.append({"t": "img", "y": blk["bbox"][1],
                                  "bytes": blk["image"], "ext": blk.get("ext") or "png",
                                  "page": pno + 1})
                continue
            for ln in blk["lines"]:
                runs = [(s["text"], bool(s["flags"] & 16), bool(s["flags"] & 2))
                        for s in ln["spans"] if s["text"]]
                txt = u"".join(r[0] for r in runs)
                if not txt.strip() or ln["bbox"][1] > Y_FOOTER:
                    continue
                items.append({"t": "txt", "y": ln["bbox"][1], "runs": runs,
                              "size": max(s["size"] for s in ln["spans"]),
                              "page": pno + 1})
        items.sort(key=lambda i: round(i["y"], 1))
        out.extend(items)
    return out


class WQ(object):
    def __init__(self, num, subj, page):
        self.num, self.subjects, self.page = num, subj, page
        self.stem, self.opts, self.imgs = [], [], []
        self.preamble = None


def parse_questions(doc, a, b):
    items = lines(doc, a, b)
    qs, order = {}, []
    cur, subj = None, []
    group = None                  # (lo, hi, instr_html, opts)
    pend_instr, pend_opts = [], []
    nxt = 1

    for it in items:
        if it["t"] == "img":
            if cur is not None:
                cur.imgs.append(it)
            continue
        raw = runs_html(it["runs"])
        txt = plain(raw).strip()
        if it["size"] >= 13:                      # chapter heading
            continue

        m = SUBJ_RE.match(txt)
        if m:
            subj = [s.strip().lower() for s in re.split(u"\\s*,\\s*", m.group(1)) if s.strip()]
            cur = None
            continue

        m = NUM_RE.match(txt)
        # The chapters number straight through but do skip the odd number where
        # a question was pulled, so "the one due next" means at or just after the
        # counter - never behind it, which is what a stray "3." in a stem is.
        if m and nxt <= int(m.group(1)) <= nxt + 5:
            nxt = int(m.group(1))
            # an instruction block that named a range becomes this run's options
            # An instruction may carry an option list, or may just say what to do
            # ("identify each activity as an ADL or an IADL"). Either way the run
            # below it needs the instruction, or a one-word stem like "Eating"
            # arrives with nothing to answer against.
            if pend_instr:
                g = GROUP_RE.search(plain(u" ".join(pend_instr)))
                if g:
                    # The ranges these instructions quote are stale - "questions
                    # 48-51" sits above questions 42-45, left over from an edition
                    # that numbered differently. How MANY questions it covers did
                    # survive the renumbering, so the span is used and the stated
                    # start is ignored.
                    span = int(g.group(2)) - int(g.group(1)) + 1
                    group = (nxt, nxt + span - 1,
                             u"".join(u"<p>%s</p>" % p for p in pend_instr),
                             list(pend_opts))
            pend_instr, pend_opts = [], []
            cur = WQ(nxt, list(subj), it["page"])
            qs[nxt] = cur
            order.append(nxt)
            if group and group[0] <= nxt <= group[1]:
                cur.preamble = group[2]
                if group[3]:
                    cur.opts = [[l, list(p)] for l, p in group[3]]
            cur.stem.append(drop_prefix(raw, m.end()))
            nxt += 1
            continue

        if OPEN_RE.match(txt):
            cur, pend_opts = None, []
            pend_instr = [raw]
            continue

        m = OPT_RE.match(txt)
        if m:
            want = chr(ord(cur.opts[-1][0]) + 1) if (cur and cur.opts and
                                                     not getattr(cur, "shared", False)) else u"A"
            if cur is not None and not cur.preamble and m.group(1) == want:
                cur.opts.append([m.group(1), [drop_prefix(raw, 2).lstrip()]])
                continue
            if cur is None:
                want2 = chr(ord(pend_opts[-1][0]) + 1) if pend_opts else u"A"
                if m.group(1) == want2:
                    pend_opts.append([m.group(1), [drop_prefix(raw, 2).lstrip()]])
                    continue

        if cur is None:
            if txt and (INSTR_RE.search(txt) or pend_instr):
                pend_instr.append(raw)
            continue

        if cur.opts and not cur.preamble:
            cur.opts[-1][1].append(raw)
        else:
            cur.stem.append(raw)

    return [qs[n] for n in order]


def parse_answers(doc, a, b):
    items = lines(doc, a, b)
    keys, cur, nxt = {}, None, 1
    for it in items:
        if it["t"] != "txt" or it["size"] >= 13:
            continue
        raw = runs_html(it["runs"])
        txt = plain(raw).strip()
        m = NUM_RE.match(txt)
        if m and nxt <= int(m.group(1)) <= nxt + 5:
            nxt = int(m.group(1))
            cur = [drop_prefix(raw, m.end())]
            keys[nxt] = cur
            nxt += 1
            continue
        if cur is not None:
            cur.append(raw)
    return keys


def parse_key(parts):
    """-> (letters, rationale_html). The workbook writes 'Answer: B ...'."""
    raw = join(parts)
    txt = plain(raw).strip()
    lead = re.match(u"^Answer:\\s*", txt, re.I)
    if lead:
        raw, txt = drop_prefix(raw, lead.end()), txt[lead.end():]
    m = ANS_RE.match(txt)
    if not m:
        return [], (u"<p>%s</p>" % raw if txt else u"")
    span = len(m.group(1)) + len(m.group(2))
    letters = re.findall(u"[A-Z]", m.group(1) + m.group(2))
    rest = drop_prefix(raw, span).lstrip()
    rest = re.sub(u"^((?:<[^>]+>)*)[.,:]\\s*", u"\\1", rest).lstrip()
    return letters, (u"<p>%s</p>" % rest if plain(rest).strip() else u"")


def read():
    """-> {chapter_key: (questions, keys)}"""
    doc = pymupdf.open(WORKBOOK)
    out = {}
    for key, name, (qa, qb), (aa, ab), blocks in CHAPTERS:
        out[key] = (parse_questions(doc, qa, qb), parse_answers(doc, aa, ab))
    doc.close()
    return out


if __name__ == "__main__":
    for key, (qs, ks) in read().items():
        noopt = [q.num for q in qs if not q.opts]
        nokey = [q.num for q in qs if q.num not in ks]
        subj = len([q for q in qs if q.subjects])
        print("%-5s questions=%-4d answers=%-4d with-subject=%-4d figures=%d"
              % (key, len(qs), len(ks), subj, sum(len(q.imgs) for q in qs)))
        print("      no options: %d %s" % (len(noopt), noopt[:12]))
        print("      no key    : %d %s" % (len(nokey), nokey[:12]))


# ------------------------------------------------------- filing into a block

# The workbook is organised by subject and the portal by week, so a week has to
# be inferred. This table is that inference, written out rather than hidden in a
# model: each week owns the terms its own lectures are about, taken from the
# lecture titles in the vault plus the vocabulary the workbook actually uses.
# A question is scored against every week in its chapter's blocks - its subject
# areas count triple, its stem and options once - and the best week wins.
#
# It is a best effort and it is not the source's own filing. The block is never
# in doubt (the workbook's three FoM chapters map onto blocks 1-2, 3 and 4); only
# the week within it is inferred, and anything that matches nothing at all is
# flagged on the question rather than filed silently.
WEEK_TERMS = {
    1: u"""ethics, ethical, deontology, utilitarian, casuistry, principlism, virtue ethics,
        moral distress, autonomy, beneficence, physicianship, patient-centred, patient-centered,
        history of medicine, galen, hippocrat, osler, humoral, miasma, germ theory,
        epidemiology, population health, primordial, primary prevention, prevention paradox,
        secondary prevention, tertiary prevention, risk factor, health promotion,
        social determinants, cultural competence, cultural safety, refugee, implicit bias,
        disparities, health equity, clinical presentation, undifferentiated, multimorbidity,
        professionalism, hidden curriculum, conflict of interest, differential diagnosis,
        iatrogenic, degenerative, congenital, neoplastic""",
    2: u"""biochemistry, osmosis, osmolarity, tonicity, homeostasis, histology, epithelial,
        epithelium, muscle tissue, connective tissue, collagen, elastin, fibroblast,
        desmosome, tight junction, gap junction, cadherin, claudin, connexin,
        myelin, schwann, oligodendrocyte, action potential, membrane potential,
        depolaris, depolariz, repolaris, repolariz, sodium-potassium, ion channel,
        facilitated diffusion, simple diffusion, active transport, sglt, carrier-mediated,
        autocrine, paracrine, signaling, signalling,
        radiograph, radiologic, ultrasound, magnetic resonance, computed tomography,
        evidence-based, sensitivity, specificity, predictive value, randomized, randomised,
        systematic review, meta-analysis, study design, case-control, critical appraisal, pico,
        neuromuscular junction, acetylcholine, sarcolemma, troponin, tropomyosin,
        darrow-yannet, extracellular fluid, intracellular fluid""",
    3: u"""genetics, genetic, allele, missense, nonsense, frameshift, frame shift,
        inheritance, autosomal dominant, autosomal recessive, x-linked, mitochondrial,
        pedigree, karyotype, chromosome, chromosomal, trisomy, turner, klinefelter,
        mosaicism, aneuploidy, cytogenetic, newborn screening, prenatal, amniocentesis,
        cystic fibrosis, dystrophin, duchenne, osteogenesis imperfecta, haploinsufficiency,
        penetrance, expressivity, pleiotropy, heterogeneity,
        child development, developmental milestone, piaget, sensorimotor,
        preoperational, concrete operational, formal operational,
        infant nutrition, breast milk, breastfeeding, vitamin d, nutrition, malnutrition,
        rickets, weaning, growth chart, well newborn, birthweight, embryology, teratogen""",
    4: u"""adhd, attention-deficit, hyperactivity, adolescent, adolescence, puberty,
        tanner stage, school age, temper tantrum, well child, anticipatory guidance,
        social pediatrics, social paediatrics, disability, impairment, immunization,
        immunisation, vaccine, vaccination, hpv, measles, mmr, live vaccine,
        vaccine preventable, attachment, peer group""",
    5: u"""body fluid, blood pressure, baroreceptor, raas, renin, angiotensin,
        aldosterone, vasopressin, natriuretic, thirst, hyponatremia, hypernatremia,
        osmolality, nervous system, neurofunction, cellular stress, hypertrophy,
        hyperplasia, atrophy, metaplasia, necrosis, apoptosis, regeneration, scarring,
        diagnostic pathway, laboratory medicine, pre-analytical, post-analytical,
        reference interval, abnormal test, anxiety, gad7, phq9, choosing wisely,
        perpetuating, predisposing, precipitating, vital signs, screening""",
    6: u"""lumps and bumps, neoplasia, neoplasm, tumour, tumor, carcinoma, oncology,
        malignant, benign, metastasis, metastatic, staging, grading, biopsy,
        fine needle, core needle, mammogram, breast mass, breast cancer, melanoma, mole,
        cancer genetics, brca, oncogene, tumour suppressor, warburg, pathology report,
        cancer screening, spikes, breaking bad news""",
    7: u"""aging, ageing, geriatric, older adult, older patient, frailty, frail, falls,
        sarcopenia, geriatric assessment, cognitive testing, moca, mmse,
        cognitive decline, dementia, alzheimer, delirium, elder abuse,
        polypharmacy, deprescribing, interdisciplinary, caregiver,
        functional status, activities of daily living, instrumental activity,
        adl, iadl, periodic health encounter, hearing impairment""",
    8: u"""prescribing, prescription, pharmacology, pharmacodynamic, pharmacokinetic,
        bioavailability, half-life, clearance, first pass, cytochrome, enzyme induction,
        agonist, antagonist, inverse agonist, potency, efficacy, ec50, ed50,
        therapeutic index, receptor binding, adverse drug, side effect, idiosyncratic,
        drug interaction, adherence, clinical trial, phase i, phase ii, phase iii,
        healthcare system, provincial, formulary, therapeutics""",
    9: u"""hematopoiesis, erythropoiesis, erythrocyte, reticulocyte, erythroblast,
        anemia, anaemia, microcytic, normocytic, macrocytic, hemolytic, haemolytic,
        iron, ferritin, transferrin, tibc, b12, cobalamin, folate,
        hemoglobinopathy, thalassemia, thalassaemia, sickle, spherocytosis, g6pd,
        haptoglobin, bilirubin, jaundice, scleral icterus, mcv, rdw,
        myelodysplastic, pernicious, intrinsic factor, hepcidin, sideroblastic,
        blood film, blood smear, schistocyte, target cell, erythropoietin""",
    10: u"""bleeding, hemostasis, haemostasis, coagulation, coagulopathy,
        platelet, thrombocytopenia, thrombosis, thrombus, von willebrand, vwf,
        hemophilia, haemophilia, factor viii, factor ix, prothrombin time, ptt, inr,
        fibrin, fibrinogen, d-dimer, anticoagulant, warfarin, heparin, doac,
        apixaban, rivaroxaban, deep vein, pulmonary embolism, wells score,
        itp, ttp, disseminated intravascular, vitamin k, protein c, protein s,
        antithrombin, thrombophilia""",
    11: u"""neutrophil, white blood cell, leukocyte, leukocytosis, leukopenia,
        neutropenia, febrile neutropenia, leukemia, leukaemia, cml, cll, aml,
        blast, myeloid, lymphoblastic, erythrocytosis, polycythemia, polycythaemia,
        thrombocytosis, myelofibrosis, myeloproliferative, jak2, philadelphia,
        bcr-abl, tyrosine kinase, monocyte, basophil, granulocyte, flow cytometry,
        left shift, band cell, phlebotomy, hydroxyurea""",
    12: u"""lymphadenopathy, lymph node, mediastinal, lymphoma, hodgkin,
        ann arbor, ann arbour, reed-sternberg, b symptoms, multiple myeloma,
        plasma cell, monoclonal, paraprotein, bence jones, m-peak, amyloid,
        radiation oncology, radiotherapy, rituximab, chemotherapy""",
    13: u"""fever, pyrexia, thermoregulation, pyrogen,
        gram-positive, gram negative, gram stain, cocci, bacilli, staphylococc,
        streptococc, clostridi, enterococc, listeria, spore, catalase, coagulase,
        microbiome, commensal, colonisation, colonization, blood culture,
        innate immunity, complement, macrophage, toll-like, pattern recognition,
        opsonin, phagocyt, chemotaxis, cytokine, interleukin, interferon,
        acute inflammation, cardinal, exudate, transudate, margination, diapedesis,
        histamine, bradykinin, adaptive immunity, lymphocyte, t cell, b cell,
        helper, cytotoxic, antigen presentation, histocompatibility, mhc, hla,
        antibody, immunoglobulin, iga, igd, ige, igg, igm, isotype,
        lymphoid organ, spleen, thymus, germinal, central tolerance,
        positive selection, negative selection, clonal, capsid, viral replication,
        febrile infant""",
    14: u"""transmission, droplet, airborne, contact precaution, ppe, n95,
        infection control, hand hygiene, isolation, outbreak, contact tracing,
        epidemic, pandemic, notifiable, antibiotic, antimicrobial, resistance,
        stewardship, penicillin, cephalosporin, macrolide, vancomycin,
        vaccine platform, mrna, adjuvant, vaccine hesitancy,
        antiviral, oseltamivir, acyclovir, sepsis, septic shock, meningitis""",
    15: u"""immunocompromised, immunosuppress, opportunistic,
        fungal, fungi, candida, aspergill, cryptococc, pneumocystis, histoplasm,
        antifungal, azole, fluconazole, amphotericin, echinocandin,
        immunodeficiency, scid, agammaglobulin, allergy, allergic, atopy, atopic,
        anaphylaxis, hypersensitivity, mast cell, degranulation, eosinophil,
        skin prick, autoantibody, antinuclear, rheumatoid factor,
        chronic inflammation, granuloma, granulomatous,
        autoimmunity, autoimmune, molecular mimicry, lupus, sjogren, scleroderma,
        vasculitis, herpes, hsv, vzv, cmv, ebv, shingles, zoster, latency,
        transplant, lymphoproliferative""",
}

# The Foundations chapter labels every question with its own subject area, and
# that is the workbook's filing, not a guess at it. Each subject names the week
# (or the two or three weeks) that teach it; where it names more than one, the
# keyword score below picks between just those, never across the whole block.
# Only the Hematology and Infection & Immunity chapters, which carry no subject
# labels at all, are scored across their block from scratch.
SUBJECT_WEEKS = {
    u"history of medicine": [1], u"thinking like a physician": [1],
    u"medical ethics": [1], u"professionalism": [1], u"epidemiology": [1],
    u"social determinants of health": [1], u"cultural sensitivity": [1],
    u"evidence-based medicine": [2], u"statistics": [2], u"critical appraisal": [2],
    u"biochemistry": [2], u"histology": [2], u"anatomy": [2],
    u"cellular physiology": [2], u"physiology": [2], u"homeostasis": [2],
    u"genetics": [3], u"cytogenetics": [3], u"prenatal testing": [3],
    u"development": [3], u"nutrition": [3], u"embryology": [3],
    u"pediatrics": [3, 4], u"paediatrics": [3, 4],
    u"fluid balance": [5], u"neurology": [5], u"choosing wisely": [5],
    u"psychiatry": [5, 7], u"pathology": [5, 6], u"lifestyle": [1, 7],
    u"family medicine": [5, 7], u"cancer": [6], u"oncology": [6],
    u"geriatrics": [7],
    u"pharmacology": [8], u"antibiotics": [8], u"healthcare systems": [8],
}

CHAPTER_BLOCKS = {"fom": [1, 2], "heme": [3], "ii": [4]}
CHAPTER_WEEKS = {"fom": [1, 2, 3, 4, 5, 6, 7, 8],
                 "heme": [9, 10, 11, 12], "ii": [13, 14, 15]}
BLOCK_OF_WEEK = dict([(w, 1) for w in (1, 2, 3, 4)] + [(w, 2) for w in (5, 6, 7, 8)] +
                     [(w, 3) for w in (9, 10, 11, 12)] + [(w, 4) for w in (13, 14, 15)])
DEFAULT_WEEK = {"fom": 1, "heme": 9, "ii": 13}

def _entries(text):
    return [e.strip() for e in re.split(u"\\s*,\\s*", re.sub(u"\\s+", u" ", text)) if e.strip()]


# Entries are comma-separated so a phrase stays whole. That matters: an earlier
# version split on whitespace, which turned "infection control" into a bare
# "infection" that scored on every question in the chapter and dragged fungal
# questions into the antimicrobials week.
_ALL = dict((w, _entries(t)) for w, t in WEEK_TERMS.items())
_PHRASES = dict((w, [e for e in v if u" " in e]) for w, v in _ALL.items())
_TERMS = dict((w, sorted([e for e in v if u" " not in e], key=len, reverse=True))
              for w, v in _ALL.items())


def score_week(chapter, subjects, body):
    """-> (week, confidence). confidence is "subject" | "subject+terms" | a score.

    A subject area that names exactly one week settles it outright. One that
    names several narrows the field and the terms choose inside it. No usable
    subject at all falls back to scoring the whole chapter, and a question that
    then matches almost nothing is flagged rather than filed quietly.
    """
    cands = []
    for s in subjects:
        cands.extend(SUBJECT_WEEKS.get(s.strip().lower(), []))
    cands = [w for w in sorted(set(cands)) if w in CHAPTER_WEEKS[chapter]]
    if len(cands) == 1:
        return cands[0], "subject"
    weeks = cands or CHAPTER_WEEKS[chapter]
    w, n = _score(weeks, subjects, body)
    if cands:
        return w, "subject+terms"
    return w, n


def _score(weeks, subjects, body):
    """Longer terms count for more: "sideroblastic" is evidence, "cell" is not.

    Confidence is the winning week's margin over the runner-up, not its raw
    total - one unambiguous word is a better reason to file something than a
    dozen words every week in the block shares.
    """
    subj = u" ".join(subjects).lower()
    text = body.lower()
    hits = {}
    for w in weeks:
        n = 0.0
        for p in _PHRASES[w]:
            if p in text:
                n += 1.5 * len(p)
            if p in subj:
                n += 4.0 * len(p)
        for t in _TERMS[w]:
            if len(t) < 4 or u" " in t:
                continue
            if re.search(u"\\b%s" % re.escape(t), text):
                n += float(len(t))
            if re.search(u"\\b%s" % re.escape(t), subj):
                n += 3.0 * len(t)
        hits[w] = n
    ranked = sorted(weeks, key=lambda w: (-hits[w], w))
    best = ranked[0]
    if hits[best] <= 0:
        return best, 0.0
    second = hits[ranked[1]] if len(ranked) > 1 else 0.0
    return best, (hits[best] - second) / hits[best]


MULTI_RE = re.compile(u"choose (\\d+|two|three|four)|select (all|\\d+|two|three|four)"
                      u"|\\(choose \\d+\\)|choose as many", re.I)
MATCH_RE = re.compile(u"^\\s*match (each|the)", re.I)

SLUG = {1: "b1", 2: "b2", 3: "b3", 4: "b4"}

# the workbook spells a few subjects both ways; the Topic rail should not
SUBJ_ALIAS = {u"paediatrics": u"pediatrics", u"cancer": u"oncology"}
CHAPTER_NAME = dict((k, n) for k, n, _q, _a, _b in CHAPTERS)

META = (u"The Pre-Clerkship Workbook, 2023 edition - the student bank handed down "
        u"through the Schulich classes of 2015 to 2025. Its %s chapter. The workbook "
        u"files by subject rather than by week, so the week here is inferred from the "
        u"question's own wording against that block's lecture titles; the block it "
        u"belongs to is the workbook's own.")


def fig_html(img):
    src = question_figures.write_asset("fom", img["bytes"], img.get("ext") or "png")
    return (u'<figure><img loading="lazy" src="%s" '
            u'alt="Figure from the Pre-Clerkship Workbook, page %d"></figure>'
            % (img["ext"], b64, img["page"]))


def build_blocks(week_label):
    """-> {slug: [question dicts]}, plus a filing report."""
    data = read()
    out, report = {}, []
    for chapter, (qs, keys) in data.items():
        for q in qs:
            stem = join(q.stem)
            opts = [{"letter": l, "html": join(p)} for l, p in q.opts]
            parts = keys.get(q.num)
            letters, rationale = parse_key(parts) if parts else ([], u"")

            body = u" ".join([plain(stem)] + [plain(o["html"]) for o in opts] +
                             [plain(rationale)])
            week, conf = score_week(chapter, q.subjects, body)
            slug = SLUG[BLOCK_OF_WEEK[week]]

            valid = [o["letter"] for o in opts]
            if valid:
                letters = [l for l in letters if l in valid]
            multi = len(letters) > 1 or bool(MULTI_RE.search(plain(stem)))
            is_match = bool(MATCH_RE.match(plain(stem)))

            kind, free, unscorable, keyed = "mcq", False, False, True
            flags = []
            if parts is None:
                kind, keyed, unscorable = "broken", False, True
                answer = (u"<p>The workbook prints no answer for this one - its answer "
                          u"section skips the number.</p>")
                flags.append({"type": "warning", "title": "No key in the source",
                              "html": u"<p>Left out of the accuracy figures on purpose.</p>"})
            elif not letters or not opts or is_match:
                kind = "matching" if (is_match or not opts) else "short"
                free = True
                answer = (rationale if (rationale and not letters)
                          else u"<p><strong>%s</strong></p>%s"
                               % (u", ".join(letters) or plain(join(parts)), rationale))
                if not opts and letters:
                    answer = (u"<p><strong>The correct answer is %s.</strong></p>%s"
                              % (u", ".join(letters), rationale))
            else:
                answer = (u"<p><strong>The correct answer is %s.</strong></p>"
                          % u", ".join(letters)) + rationale

            if not isinstance(conf, str) and conf < 0.25:
                flags.append({
                    "type": "note", "title": "Filed by best guess",
                    "html": u"<p>The workbook files by subject, not by week, and nothing "
                            u"in this question matched the vocabulary of any week in the "
                            u"block strongly enough to place it. It is parked in week %d. "
                            u"The block it sits in is the workbook&rsquo;s own.</p>" % week})

            out.setdefault(slug, []).append({
                "qid": u"%s-wb-%s-q%d" % (slug, chapter, q.num),
                "num": u"%d" % q.num,
                "week": week,
                "weekLabel": week_label[week],
                "retired": False,
                "family": "workbook",
                "source": "workbook",
                "sourceLabel": u"Pre-Clerkship Workbook",
                "lecture": CHAPTER_NAME[chapter],
                "lectureMeta": META % CHAPTER_NAME[chapter],
                "tags": sorted(set(SUBJ_ALIAS.get(t, t) for t in q.subjects)),
                "preamble": ({"title": "Shared instructions", "html": q.preamble}
                             if q.preamble else None),
                "stem": ((u"<p>%s</p>" % stem if stem else u"")
                         + u"".join(fig_html(i) for i in q.imgs)),
                "kind": kind,
                "options": opts,
                "correct": [] if free else letters,
                "multi": bool(multi and letters and not free),
                "free": free,
                "unscorable": unscorable,
                "keyed": keyed,
                "answerTitle": "Answer",
                "answer": answer,
                "flags": flags,
            })
            report.append((chapter, q.num, slug, week, conf))

    for slug in out:
        out[slug].sort(key=lambda q: (q["week"], int(q["num"])))
    return out, report
