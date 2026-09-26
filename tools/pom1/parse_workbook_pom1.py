# -*- coding: utf-8 -*-
"""Pull the five PoM 1 chapters out of the Pre-Clerkship Workbook.

Purpose: add the workbook's Cardiology, Respiration & Airways, Ear Nose &
         Throat, Gastroenterology and Genitourinary chapters to PoM 1 as a
         fifth question set.
Author:  Noor Sims
Date:    2026-09-25
Input:   Preclerkship WB 2023_FINAL_ (1).pdf (path via $POM1_WORKBOOK)
Output:  a list of question dicts per block, consumed by parse_qbank.py

The workbook is one document for the whole of pre-clerkship and one parser
reads it, so the machinery here is FoM's, imported: the same rule that a line
starts a question only when it is numbered AND that number is the one due next,
which is what stops a stem sentence opening "3. " from starting a phantom
question. What this file adds is which chapters are PoM 1's, and how a week
inside one of them is chosen.

Two things in these chapters the FoM ones do not have, and both are handled
below rather than papered over:

* **More than one numbering run per chapter.** Cardiology prints 122 questions,
  then an Extended Match block numbered 1-25, then a set of LMCC cases, then ten
  "New Questions" added in the 2023 edition that start again at 1. A chapter is
  therefore a list of SECTIONS with their own question and answer pages, not one
  range, and each section is numbered and keyed on its own.

* **Numbers that are not question numbers.** The Respiration chapter prints a
  pulmonary-function table whose DLCO row reads "20.73", which the straight
  "numbered line" rule read as question 20 and which swallowed questions 17 to
  19 behind it. A number followed immediately by a digit is a decimal, never a
  question, and NUM_RE says so here.

Which BLOCK a question belongs to is never in doubt here - PoM 1's blocks are
organ systems and so are the workbook's chapters, so the two line up one to
one, which they did not for FoM. Week 9 needs no inference at all: the ENT
chapter is the whole of the ENT block. The WEEK inside the other four blocks is
inferred by scoring the question against the vocabulary of that week's own
lectures, taken from the vault's "99 - PoM 1" tree. That table is written out
below rather than hidden in a model, so a filing you disagree with is a line
you can edit, and anything that matches nothing is flagged on the question
rather than filed silently.
"""

import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)

import pymupdf                                                   # noqa: E402
import question_figures                                          # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fom = _load("fom_parse_workbook", os.path.join(TOOLS, "fom", "parse_workbook.py"))

parse_questions, parse_answers = fom.parse_questions, fom.parse_answers
parse_key, join, plain = fom.parse_key, fom.join, fom.plain
MULTI_RE, MATCH_RE = fom.MULTI_RE, fom.MATCH_RE

WORKBOOK = os.environ.get(
    "POM1_WORKBOOK",
    os.path.join(ROOT, "pom1", "Preclerkship WB 2023_FINAL_ (1).pdf"))

# chapter key, name, the sections it prints, the block it is, and its weeks.
# A section is (label, question pages, answer pages); page numbers are the PDF's
# own, not the printed ones, which run 1 behind. Most chapters are one section.
# Cardiology is four, of which two are taken - see SKIPPED below.
CHAPTERS = [
    ("cardio", u"Cardiology", [
        (u"", (57, 74), (253, 259)),
        (u"New Questions", (79, 80), (260, 262)),
    ], "cardio", [1, 2, 3, 4, 5]),
    ("resp", u"Respiration & Airways", [
        (u"", (81, 86), (263, 266)),
    ], "resp", [6, 7, 8]),
    ("ent", u"Ear, Nose & Throat", [
        (u"", (87, 92), (267, 268)),
    ], "ent", [9]),
    ("gi", u"Gastroenterology", [
        (u"", (93, 108), (269, 276)),
    ], "gi", [10, 11, 12, 13]),
    ("gu", u"Genitourinary", [
        (u"", (109, 124), (277, 285)),
    ], "gu", [14, 15, 16, 17]),
]

# What is left on the table, said out loud rather than quietly dropped. Both are
# in the Cardiology chapter and both are shaped unlike anything else in the
# workbook: an Extended Match block of 25 items sharing one 17-option list whose
# whole key is a single line ("1) A D E G B, 2) I Q, ..."), and a run of LMCC
# cases whose questions carry no numbers at all and whose answers are filed by
# case. Neither survives the numbered-line rule the rest of this file is built
# on, and inventing numbers for them would make them look like questions the
# workbook prints, which it does not.
SKIPPED = u"Cardiology: 25 Extended Match items (pp. 75-76) and the LMCC cases (pp. 77-78)"

# A number followed straight away by another digit is a decimal inside a table,
# not a question number. A range ("119-122.") is matched on its first number and
# expanded afterwards by _expand_ranges. "10 Answer: A" - the GI chapter's one
# missing period - is matched on the word that follows it.
NUM_RE = re.compile(u"^(\\d{1,3})(?:(?=\\s*[-\u2013]\\s*\\d{1,3}[.):])"
                    u"|[.):](?!\\d)\\s*|\\s+(?=Answer|ANSWER))")
RANGE_RE = re.compile(u"^\\s*[-\u2013]\\s*(\\d{1,3})[.):]\\s*")

# Each week owns the terms its own lectures are about. Entries are comma
# separated so a phrase stays whole - splitting on whitespace would turn
# "heart failure" into a bare "heart" that scores on every cardiology question
# in the chapter.
WEEK_TERMS = {
    1: u"""action potential, resting membrane potential, membrane potential, pacemaker cell,
        sinoatrial, sinus node, sa node, av node, atrioventricular node, purkinje,
        depolaris, depolariz, repolaris, repolariz, refractory period, phase 0, phase 4,
        automaticity, electrocardiogram, ecg, ekg, p wave, qrs, pr interval, qt interval,
        st segment, einthoven, cardiac axis, precordial lead, limb lead,
        preload, afterload, contractility, inotrop, stroke volume, cardiac output,
        ejection fraction, frank-starling, starling, pressure-volume loop, wiggers,
        law of laplace, laplace, isovolumetric, diastolic filling, venous return,
        mediastinum, pericardium, great vessels, coronary artery anatomy, aortic arch,
        capillary, oncotic, hydrostatic, interstitial fluid, lymphatic, lymph, lymphatics,
        microcirculation, vascular resistance, peripheral resistance, poiseuille,
        vascular compliance, capacitance, baroreceptor, autoregulation,
        sympathetic, parasympathetic, muscarinic, nicotinic, acetylcholine, cholinergic,
        anticholinergic, atropine, glycopyrrolate, acetylcholinesterase, adrenergic,
        catecholamine, norepinephrine, epinephrine, isoproterenol, alpha agonist,
        beta agonist, sympathomimetic, autonomic""",
    2: u"""murmur, systolic murmur, diastolic murmur, ejection murmur, holosystolic,
        pansystolic, heart sound, first heart sound, second heart sound, s1, s2, s3, s4,
        opening snap, ejection click, splitting, auscultation, precordium, thrill,
        valvular, valve disease, aortic stenosis, aortic regurgitation, aortic insufficiency,
        mitral stenosis, mitral regurgitation, mitral prolapse, tricuspid regurgitation,
        pulmonic stenosis, rheumatic fever, rheumatic heart, valve replacement,
        prosthetic valve, mitraclip, tavi, tavr, valvuloplasty,
        endocarditis, vegetation, duke criteria, janeway, osler node, splinter hemorrhage,
        echocardiogram, echocardiograph, transthoracic, transesophageal, doppler,
        pericarditis, pericardial effusion, pericardial, tamponade, pulsus paradoxus,
        constrictive, friction rub, electrical alternans""",
    3: u"""atherosclerosis, atheroma, atherosclerotic plaque, fatty streak, foam cell,
        intimal, endothelial injury, lipid core, fibrous cap, plaque rupture,
        ischemic heart disease, ischemia, angina, stable angina, unstable angina,
        acute coronary syndrome, myocardial infarction, infarct, stemi, nstemi,
        troponin, creatine kinase, ck-mb, st elevation, st depression, q wave,
        stress test, exercise tolerance test, perfusion imaging, coronary angiography,
        percutaneous coronary, angioplasty, stent, thrombolysis, fibrinolytic,
        coronary bypass, cabg, revascularis, revascularix, revasculariz,
        papillary muscle rupture, free wall rupture, ventricular septal rupture,
        dressler, ventricular aneurysm, mural thrombus,
        cardiac rehabilitation, secondary prevention, smoking cessation, lipid lowering,
        claudication, peripheral arterial disease, peripheral vascular, ankle-brachial,
        critical limb ischemia, aneurysm, abdominal aortic aneurysm, aortic dissection,
        varicose, arteritis, vasculitis""",
    4: u"""heart failure, systolic dysfunction, diastolic dysfunction, hfref, hfpef,
        congestive, cardiomyopathy, dilated cardiomyopathy, hypertrophic cardiomyopathy,
        restrictive cardiomyopathy, ventricular remodel, orthopnea,
        paroxysmal nocturnal dyspnea, nyha, natriuretic peptide, bnp, pulmonary edema,
        jugular venous pressure, peripheral edema, fluid overload, decompensat,
        ace inhibitor, angiotensin receptor blocker, arb, sacubitril, spironolactone,
        mineralocorticoid receptor, eplerenone, beta blocker, loop diuretic, furosemide,
        digoxin, sglt2, cardiac resynchronis, cardiac resynchroniz,
        ventricular assist, transplantation, inotrope infusion,
        hypertension, blood pressure, antihypertensive, hypertensive, calcium channel
        blocker, amlodipine, thiazide, hydrochlorothiazide, ramipril, perindopril,
        secondary hypertension, renal artery stenosis, pheochromocytoma, white coat,
        congenital heart, ventricular septal defect, atrial septal defect, patent ductus,
        tetralogy, coarctation, transposition, cyanotic, acyanotic, left-to-right shunt,
        right-to-left shunt, eisenmenger, pediatric cardiology, congenital""",
    5: u"""arrhythmia, dysrhythmia, reentry, reentrant, ectopic beat, premature beat,
        bradycardia, sinus bradycardia, heart block, first degree block, second degree,
        mobitz, wenckebach, complete heart block, sick sinus, escape rhythm,
        pacemaker implant, permanent pacemaker,
        syncope, presyncope, vasovagal, neurocardiogenic, orthostatic hypotension,
        tilt table, tachycardia, sinus tachycardia, supraventricular tachycardia, svt,
        avnrt, avrt, accessory pathway, wolff-parkinson-white, pre-excitation,
        atrial flutter, atrial fibrillation, rate control, rhythm control,
        anticoagulation, chads, warfarin, doac, stroke prevention,
        ventricular tachycardia, ventricular fibrillation, torsades, long qt,
        defibrillat, cardioversion, ablation, antiarrhythmic, vaughan williams,
        amiodarone, adenosine, flecainide, sotalol, implantable cardioverter""",
    6: u"""pneumocyte, surfactant, alveolar macrophage, ciliated, goblet cell,
        respiratory epithelium, bronchiole, terminal bronchiole, acinus, lung histology,
        thoracic cage, intercostal, diaphragm, pleural anatomy, hilum, lung lobe, fissure,
        upper respiratory anatomy, nasal cavity, turbinate, nasal septum, paranasal,
        ventilation, tidal volume, residual volume, functional residual capacity,
        vital capacity, total lung capacity, lung compliance, elastic recoil,
        airway resistance, dead space, minute ventilation, work of breathing,
        pulmonary function test, spirometry, fev1, fvc, flow-volume loop,
        bronchodilator response, methacholine, peak flow,
        obstructive lung disease, asthma, copd, emphysema, chronic bronchitis, wheeze,
        bronchospasm, inhaler, metered dose, beta-2 agonist, salbutamol, ipratropium,
        anticholinergic bronchodilator, inhaled corticosteroid, montelukast, theophylline,
        allergic rhinitis, atopy, rhinitis, antihistamine, sinusitis, rhinosinusitis,
        chronic sinusitis, nasal polyp, nasal congestion""",
    7: u"""gas exchange, diffusion capacity, dlco, alveolar-arterial, a-a gradient,
        alveolar gas equation, hypoxemia, hypoxia, hypoxaemia, oxygen delivery,
        oxyhemoglobin, oxygen dissociation curve, oxygen saturation, shunt fraction,
        ventilation-perfusion, v/q mismatch, hypercapnia, hypercarbia, carbon dioxide
        retention, arterial blood gas, blood gas, respiratory acidosis,
        respiratory alkalosis, metabolic acidosis, metabolic alkalosis, anion gap,
        bicarbonate, compensation, pulmonary hypertension, cor pulmonale,
        pulmonary vascular resistance, pulmonary embolism, interstitial lung disease,
        pulmonary fibrosis, idiopathic pulmonary fibrosis, sarcoidosis,
        hypersensitivity pneumonitis, asbestosis, silicosis, crackles, clubbing,
        ards, acute respiratory distress, obstructive sleep apnea, sleep apnea,
        apnea-hypopnea, polysomnography, cpap, daytime somnolence, chest radiograph,
        chest x-ray, computed tomography chest, silhouette sign""",
    8: u"""hemoptysis, massive hemoptysis, pneumonia, community-acquired, nosocomial,
        hospital-acquired, aspiration pneumonia, consolidation, lobar, bronchopneumonia,
        curb-65, sputum, empyema, lung abscess, streptococcus pneumoniae, legionella,
        mycoplasma, tuberculosis, mycobacterium, latent tuberculosis, tuberculin,
        acid-fast, ziehl, caseating, isoniazid, rifampin, nontuberculous,
        pulmonary nodule, solitary pulmonary nodule, lung mass, lung cancer,
        bronchogenic, adenocarcinoma, squamous cell carcinoma, small cell lung,
        non-small cell, paraneoplastic, mesothelioma, pancoast,
        pleural effusion, transudate, exudate, light's criteria, thoracentesis,
        pneumothorax, tension pneumothorax, chest tube, mediastinal mass, thymoma,
        pediatric asthma, cystic fibrosis, cftr, bronchiectasis, sweat chloride""",
    9: u"",
    10: u"""gastrointestinal motility, peristalsis, migrating motor complex, sphincter,
        lower esophageal sphincter, upper esophageal sphincter, swallowing,
        oropharyngeal dysphagia, esophageal dysphagia, dysphagia, odynophagia, achalasia,
        esophageal spasm, esophageal web, schatzki, stricture, eosinophilic esophagitis,
        barrett, gastroesophageal reflux, gerd, reflux, heartburn, regurgitation,
        peptic ulcer, duodenal ulcer, gastric ulcer, helicobacter, h. pylori, gastritis,
        dyspepsia, proton pump inhibitor, omeprazole, h2 receptor antagonist, ranitidine,
        antacid, misoprostol, gastric acid, parietal cell, chief cell, gastrin,
        intrinsic factor, pepsinogen, saliva, salivary, gastric secretion,
        nausea, vomiting, emesis, gastroparesis, antiemetic, ondansetron, metoclopramide,
        chemoreceptor trigger zone, foregut, greater omentum, lesser omentum, peritoneum,
        anterior abdominal wall, rectus sheath, inguinal canal, inguinal hernia,
        gut rotation, foregut development, barium swallow, upper endoscopy""",
    11: u"""digestion, absorption, brush border, villus, microvilli, enterocyte,
        lactase, lactose intolerance, disaccharidase, bile salt, micelle, chylomicron,
        celiac, gluten, malabsorption, steatorrhea, fat-soluble vitamin, b12 absorption,
        diarrhea, osmotic diarrhea, secretory diarrhea, chronic diarrhea,
        infectious diarrhea, gastroenteritis, clostridioides, clostridium difficile,
        salmonella, shigella, campylobacter, escherichia coli, giardia, traveller's
        diarrhea, travellers diarrhea, norovirus, food poisoning,
        constipation, laxative, fibre, irritable bowel, functional gut, bloating,
        crohn, ulcerative colitis, inflammatory bowel disease, mesalamine, azathioprine,
        biologic therapy, toxic megacolon, colorectal cancer, colon cancer, colonoscopy,
        adenomatous polyp, polyp, fecal immunochemical, screening colonoscopy,
        small bowel tumour, carcinoid, upper gastrointestinal bleed, lower
        gastrointestinal bleed, hematochezia, melena, angiodysplasia,
        loperamide, prokinetic, antidiarrheal, midgut, hindgut, superior mesenteric,
        inferior mesenteric, mesentery, cecum, jejunum, ileum""",
    12: u"""liver, hepatic, hepatocyte, hepatomegaly, liver mass, hepatic adenoma,
        focal nodular hyperplasia, hemangioma, hepatocellular carcinoma, liver metastas,
        liver enzyme, transaminase, alt, ast, alkaline phosphatase, ggt, bilirubin,
        conjugated bilirubin, unconjugated, jaundice, icterus, cholestasis,
        gilbert, hemolytic jaundice, hepatitis, viral hepatitis, hepatitis a,
        hepatitis b, hepatitis c, autoimmune hepatitis, alcoholic hepatitis, steatosis,
        fatty liver, cirrhosis, portal hypertension, ascites, esophageal varices,
        hepatic encephalopathy, spontaneous bacterial peritonitis, child-pugh,
        hemochromatosis, wilson disease, alpha-1 antitrypsin, primary biliary,
        primary sclerosing, gallbladder, gallstone, cholelithiasis, cholecystitis,
        choledocholithiasis, cholangitis, biliary colic, murphy, ercp, cholecystectomy,
        pancreatitis, acute pancreatitis, chronic pancreatitis, lipase, amylase,
        pancreatic cancer, pancreatic mass, courvoisier, whipple,
        nutrition, malnutrition, vitamin deficiency, parenteral nutrition, refeeding,
        portal vein, hepatic artery, biliary tree, porta hepatis""",
    13: u"""abdominal pain, acute abdomen, peritonitis, rebound tenderness, guarding,
        rigidity, referred pain, visceral pain, abdominal distension, abdominal mass,
        bowel obstruction, small bowel obstruction, large bowel obstruction, ileus,
        adhesion, volvulus, intussusception, incarcerated hernia, strangulated,
        obstipation, air-fluid level, nasogastric decompression,
        appendicitis, mcburney, rovsing, psoas sign, appendectomy,
        diverticulitis, diverticulosis, diverticular, perforation,
        anorectal, hemorrhoid, anal fissure, anal fistula, perianal abscess, pilonidal,
        rectal prolapse, anal cancer, pruritus ani,
        pediatric diarrhea, infantile, dehydration in children, oral rehydration,
        pediatric constipation, encopresis, hirschsprung, pyloric stenosis,
        meckel, malrotation, necrotizing enterocolitis""",
    14: u"""nephron, glomerulus, glomerular, bowman, juxtaglomerular, macula densa,
        podocyte, proximal tubule, loop of henle, distal convoluted tubule,
        collecting duct, countercurrent, tubuloglomerular, renal blood flow,
        filtration fraction, glomerular filtration rate, gfr, filtration barrier,
        reabsorption, tubular secretion, transport maximum, glucose reabsorption,
        sodium handling, sodium balance, aldosterone, renin, angiotensin,
        natriuresis, enac, sodium-potassium-chloride, water handling, free water,
        antidiuretic hormone, adh, vasopressin, aquaporin, urine osmolality,
        plasma osmolality, hyponatremia, hypernatremia, siadh, diabetes insipidus,
        potassium handling, hyperkalemia, hypokalemia, acid-base disturbance,
        metabolic acidosis, metabolic alkalosis, anion gap, bicarbonate reabsorption,
        renal tubular acidosis, intravenous fluid, normal saline, ringer's lactate,
        crystalloid, colloid, maintenance fluid, edema, volume status, volume depletion,
        third spacing, retroperitoneum, retroperitoneal, ureter anatomy, adrenal gland,
        renal artery, urinary tract development, horseshoe kidney""",
    15: u"""serum creatinine, creatinine clearance, estimated gfr, egfr, cockcroft,
        cystatin, urinalysis, urine dipstick, hematuria, microscopic hematuria,
        proteinuria, albuminuria, albumin-creatinine ratio, urine sediment, casts,
        red cell cast, nephrotic syndrome, nephritic syndrome, glomerulonephritis,
        minimal change, focal segmental, membranous, iga nephropathy, lupus nephritis,
        acute kidney injury, prerenal, intrinsic renal, postrenal, acute tubular necrosis,
        contrast nephropathy, interstitial nephritis, oliguria, anuria,
        fractional excretion, chronic kidney disease, ckd, uremia, renal osteodystrophy,
        secondary hyperparathyroidism, anemia of chronic kidney, erythropoietin,
        diabetic nephropathy, diabetic kidney, microalbuminuria,
        kidney transplant, transplantation, allograft, rejection, immunosuppression,
        calcineurin, tacrolimus, diuretic, thiazide diuretic, loop diuretic,
        carbonic anhydrase, acetazolamide, potassium-sparing, bony pelvis, pelvic floor""",
    16: u"""urinary tract infection, cystitis, pyelonephritis, dysuria, urinary frequency,
        urgency, urine culture, nitrite, leukocyte esterase, pyuria, catheter-associated,
        urinary tract obstruction, hydronephrosis, obstructive uropathy,
        benign prostatic hyperplasia, bph, prostate, prostatic, lower urinary tract
        symptoms, alpha blocker, tamsulosin, finasteride, transurethral resection,
        prostate cancer, prostate-specific antigen, psa, gleason, digital rectal,
        prostatitis, scrotal pain, scrotal mass, testicular torsion, epididymitis,
        epididymo-orchitis, varicocele, hydrocele, spermatocele, testicular cancer,
        seminoma, renal mass, renal cell carcinoma, angiomyolipoma, renal cyst, bosniak,
        wilms, nephroblastoma, urothelial carcinoma, bladder cancer, transitional cell,
        painless hematuria, cystoscopy, vesicoureteral reflux, posterior urethral valve,
        undescended testis, cryptorchidism, hypospadias, pediatric urology,
        pediatric nephrology, nephrotic syndrome in children, henoch""",
    17: u"""incontinence, urinary incontinence, stress incontinence, urge incontinence,
        overflow incontinence, overactive bladder, detrusor, voiding dysfunction,
        urodynamic, post-void residual, intermittent catheterisation,
        intermittent catheterization, anticholinergic bladder, oxybutynin, mirabegron,
        pelvic floor exercise, nephrolithiasis, kidney stone, renal stone, urolithiasis,
        renal colic, calcium oxalate, struvite, uric acid stone, cystine stone,
        staghorn, lithotripsy, ureteroscopy, stone passage, stent placement,
        renal replacement therapy, dialysis, hemodialysis, haemodialysis,
        peritoneal dialysis, arteriovenous fistula, dialysis access, ultrafiltration,
        dialysis initiation, conservative management""",
}

CHAPTER_NAME = dict((k, n) for k, n, _s, _sl, _w in CHAPTERS)
CHAPTER_WEEKS = dict((k, w) for k, _n, _s, _sl, w in CHAPTERS)
CHAPTER_SLUG = dict((k, sl) for k, _n, _s, sl, _w in CHAPTERS)

META = (u"The Pre-Clerkship Workbook, 2023 edition - the student bank handed down "
        u"through the Schulich classes of 2015 to 2025. Its %s chapter. The workbook "
        u"files by organ system rather than by week, so the week here is inferred from "
        u"the question's own wording against that block's lecture titles; the block it "
        u"belongs to is the workbook's own.")


def _entries(text):
    return [e.strip() for e in re.split(u"\\s*,\\s*", re.sub(u"\\s+", u" ", text)) if e.strip()]


_ALL = dict((w, _entries(t)) for w, t in WEEK_TERMS.items())
_PHRASES = dict((w, [e for e in v if u" " in e]) for w, v in _ALL.items())
_TERMS = dict((w, sorted([e for e in v if u" " not in e], key=len, reverse=True))
              for w, v in _ALL.items())


def score_week(chapter, body):
    """-> (week, confidence). Confidence is the winner's margin over the runner-up.

    A one-week chapter settles itself. Otherwise longer terms count for more:
    "nephrolithiasis" is evidence, "renal" is not.
    """
    weeks = CHAPTER_WEEKS[chapter]
    if len(weeks) == 1:
        return weeks[0], 1.0
    text = body.lower()
    hits = {}
    for w in weeks:
        n = 0.0
        for ph in _PHRASES[w]:
            if ph in text:
                n += 1.5 * len(ph)
        for t in _TERMS[w]:
            if len(t) < 4:
                continue
            if re.search(u"\\b%s" % re.escape(t), text):
                n += float(len(t))
        hits[w] = n
    ranked = sorted(weeks, key=lambda w: (-hits[w], w))
    best = ranked[0]
    if hits[best] <= 0:
        return best, 0.0
    second = hits[ranked[1]] if len(ranked) > 1 else 0.0
    return best, (hits[best] - second) / hits[best]


def fig_html(img):
    src = question_figures.write_asset("pom1", img["bytes"], img.get("ext") or "png")
    return (u'<figure><img loading="lazy" src="%s" '
            u'alt="Figure from the Pre-Clerkship Workbook, page %d"></figure>'
            % (src, img["page"]))


def _expand_ranges(keys):
    """One answer written for a run of questions becomes that answer for each.

    The Cardiology chapter ends "119-122. Answer: AS = ..., AR = ..., MR = ...,
    MS = ...": one key covering four questions. NUM_RE matches its first number
    and leaves the "-122." in the text, which is what this reads.
    """
    for num in sorted(keys):
        m = RANGE_RE.match(plain(keys[num][0]))
        if not m:
            continue
        last = int(m.group(1))
        keys[num][0] = RANGE_RE.sub(u"", keys[num][0], count=1)
        for n in range(num + 1, last + 1):
            if n not in keys:
                keys[n] = list(keys[num])
    return keys


def read():
    """-> {chapter_key: [(section label, questions, keys), ...]}

    The FoM walker's idea of a question number is swapped for this file's for
    the duration - these chapters print decimals in tables and a range in their
    answer key, and neither appears in the FoM chapters. The module is loaded
    under its own name, so the swap cannot reach FoM's own parse.
    """
    doc = pymupdf.open(WORKBOOK)
    was, fom.NUM_RE = fom.NUM_RE, NUM_RE
    try:
        out = {}
        for key, _name, sections, _slug, _weeks in CHAPTERS:
            out[key] = [(label,
                         parse_questions(doc, qa, qb),
                         _expand_ranges(parse_answers(doc, aa, ab)))
                        for label, (qa, qb), (aa, ab) in sections]
    finally:
        fom.NUM_RE = was
        doc.close()
    return out


def build_blocks(week_label):
    """-> ({slug: [question dicts]}, filing report)."""
    out, report = {}, []
    for chapter, sections in read().items():
        slug = CHAPTER_SLUG[chapter]
        for si, (label, qs, keys) in enumerate(sections):
            for q in qs:
                stem = join(q.stem)
                opts = [{"letter": l, "html": join(p)} for l, p in q.opts]
                parts = keys.get(q.num)
                letters, rationale = parse_key(parts) if parts else ([], u"")

                body = u" ".join([plain(stem)] + [plain(o["html"]) for o in opts] +
                                 [plain(rationale)])
                week, conf = score_week(chapter, body)

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
                                  "html": u"<p>Left out of the accuracy figures on "
                                          u"purpose.</p>"})
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

                if conf < 0.25 and len(CHAPTER_WEEKS[chapter]) > 1:
                    flags.append({
                        "type": "note", "title": "Filed by best guess",
                        "html": u"<p>The workbook files by organ system, not by week, and "
                                u"nothing in this question matched the vocabulary of any "
                                u"week in the block strongly enough to place it. It is "
                                u"parked in week %d. The block it sits in is the "
                                u"workbook&rsquo;s own.</p>" % week})

                name = CHAPTER_NAME[chapter] + ((u" \u2014 " + label) if label else u"")
                out.setdefault(slug, []).append({
                    "qid": u"%s-wb-%s%d-q%d" % (slug, chapter, si, q.num),
                    "num": u"%d" % q.num,
                    "week": week,
                    "weekLabel": week_label[week],
                    "retired": False,
                    "family": "workbook",
                    "source": "workbook",
                    "sourceLabel": u"Pre-Clerkship Workbook",
                    "lecture": name,
                    "lectureMeta": META % CHAPTER_NAME[chapter],
                    "tags": sorted(set(q.subjects)),
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
        out[slug].sort(key=lambda q: (q["week"], q["lecture"], int(q["num"])))
    return out, report


if __name__ == "__main__":
    for key, sections in read().items():
        for label, qs, ks in sections:
            noopt = [q.num for q in qs if not q.opts]
            nokey = [q.num for q in qs if q.num not in ks]
            print("%-7s %-15s questions=%-4d answers=%-4d figures=%d"
                  % (key, label or "(main)", len(qs), len(ks),
                     sum(len(q.imgs) for q in qs)))
            print("        no options: %d %s" % (len(noopt), noopt[:12]))
            print("        no key    : %d %s" % (len(nokey), nokey[:12]))
    print("skipped: %s" % SKIPPED)
