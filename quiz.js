/* The questions half of a course block page.
   Each block page sets window.QUIZ_BLOCK and calls POM2_QUIZ.boot() when the
   Questions tab is first opened - the block JSON runs to hundreds of kilobytes,
   so nothing is fetched until it is asked for.

   This file is shared by every course in the portal, so the two things that
   differ between them arrive in QUIZ_BLOCK rather than being written here:

     store     the localStorage prefix, so one course cannot read or overwrite
               another's progress even though they are served from one origin
     families  the question sets shown in the rail, in the order they appear

   Both fall back to the PoM 2 values, which is what the pages carried before
   the portal held more than one course. */

(function () {
  "use strict";

  var BLOCK = window.QUIZ_BLOCK;
  var STORE_PREFIX = BLOCK.store || "nsq.v1.";
  var STORE_KEY = STORE_PREFIX + BLOCK.slug;

  /* every family the course has is listed, empty ones included: an empty family
     is a visible gap in coverage, which is the point. */
  var FAMILIES = BLOCK.families || [
    {
      key: "module",
      name: "Course modules",
      blurb: "The Elentra module knowledge checks and the concept checks on the lecture slides. Cases live under Meds 2029 instead, wherever they came from."
    },
    {
      key: "weekly",
      name: "Weekly quizzes",
      blurb: "The weekly quizzes, both the Microsoft Forms ones and the ones sat in Elentra. Kept whole as their own set, so a week's quiz can be drilled the way it was written."
    },
    {
      key: "workbook",
      name: "Pre-Clerkship Workbook",
      blurb: "The Pre-Clerkship Workbook (2023 edition), the student bank passed down through the Schulich classes of 2015-2025. It has a written key, but the key is peer-written and contains real errors. Every one found is flagged on the question."
    },
    {
      key: "meds2029",
      name: "Meds 2029",
      blurb: "Questions built from patient cases in the modules, DSSGs and in-class lectures, since exams tend to recycle similar cases."
    },
    {
      key: "reviews",
      name: "Schulich Reviews",
      blurb: "The Schulich Reviews sessions, both their practice questions and their summary content. TBD."
    }
  ];

  var QUESTIONS = [];
  var QMAP = Object.create(null);
  var progress = Object.create(null);
  var filters = { status: "all", family: null, week: "all", tag: "all" };

  /* View and Mode are two axes, deliberately independent. VIEW is how the
     questions are laid out; MODE is when the answer is allowed to appear. The
     pair that matters is paged + test - a block with a boundary and a submit -
     but neither implies the other: browsing one at a time and scrolling a
     tutor stream are both things people actually do. */
  var VIEW = "stream";          /* "stream" | "paged" */
  var MODE = "tutor";           /* "tutor"  | "test"  */
  var pageIdx = 0;

  /* A sat block is a lifecycle, not a toggle: drawn, sat, submitted, reviewed.
     Its answers stage HERE and are only written to the store on submit, so
     abandoning a block half-done leaves no trace - which is right, because you
     did not answer those questions. Drawing a block never erases what you
     already had. */
  var TEST = { size: 20, ids: null, picks: Object.create(null),
               submitted: false, poolN: 0, asked: 0 };

  /* label and total lookups, filled in by buildBar: the applied-filter line
     needs a filter's human name, and a family's block total is what tells an
     empty coverage gap ("none") apart from one the filters emptied ("0"). */
  var FAM_TOTAL = Object.create(null);
  var FAM_NAME = Object.create(null);
  var WEEK_LABEL = Object.create(null);
  var TAG_LABEL = Object.create(null);
  var STATUS_LABEL = Object.create(null);
  var RESET_SHOWN_IDLE = null;
  var storeWritable = true;

  function byId(id) { return document.getElementById(id); }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  /* ---------- the store ---------- */

  function sanitize(qid, data) {
    var q = QMAP[qid];
    if (!q || !data || typeof data !== "object") return null;
    return {
      qid: qid,
      source: q.source,
      family: q.family,
      lecture: q.lecture,
      week: q.week === null ? 0 : q.week,
      status: (data.status === "correct" || data.status === "wrong") ? data.status : null,
      flagged: data.flagged === true,
      firstTryCorrect: typeof data.firstTryCorrect === "boolean" ? data.firstTryCorrect : null,
      attempts: Array.isArray(data.attempts)
        ? data.attempts.filter(function (a) { return a && typeof a === "object"; }).slice(-50)
        : [],
      lastTs: typeof data.lastTs === "number" ? data.lastTs : 0
    };
  }

  function load() {
    var raw = null;
    try { raw = window.localStorage.getItem(STORE_KEY); }
    catch (e) { storeWritable = false; return; }
    if (!raw) return;
    var parsed;
    try { parsed = JSON.parse(raw); }
    catch (e) { return; }
    if (!parsed || typeof parsed !== "object") return;
    Object.keys(parsed).forEach(function (qid) {
      var rec = sanitize(qid, parsed[qid]);
      if (rec) progress[qid] = rec;
    });
  }

  function save() {
    if (!storeWritable) return;
    try { window.localStorage.setItem(STORE_KEY, JSON.stringify(progress)); }
    catch (e) {
      storeWritable = false;
      note("Progress could not be saved - the browser refused to write to local storage. Every question still works, but nothing is being kept.");
    }
  }

  function note(text) {
    var n = byId("storenote");
    n.hidden = false;
    n.textContent = text;
  }

  /* ---------- progress model ---------- */

  function rec(qid) { return progress[qid] || null; }

  function stateOf(qid) {
    var r = rec(qid);
    if (!r || (r.status !== "correct" && r.status !== "wrong")) return "unseen";
    return r.status;
  }

  function isStarred(qid) { var r = rec(qid); return !!(r && r.flagged === true); }

  function attemptsOf(qid) {
    var r = rec(qid);
    return (r && Array.isArray(r.attempts)) ? r.attempts : [];
  }

  function chosenOf(qid) {
    var a = attemptsOf(qid);
    if (!a.length) return null;
    var c = a[a.length - 1].chosen;
    return typeof c === "string" ? c.split("+").filter(Boolean) : null;
  }

  function persist(qid, patch) {
    var prev = progress[qid] || {}, q = QMAP[qid];
    var next = {
      qid: qid,
      source: q.source,
      family: q.family,
      lecture: q.lecture,
      week: q.week === null ? 0 : q.week,
      status: patch.status !== undefined ? patch.status : (prev.status || null),
      flagged: patch.flagged !== undefined ? patch.flagged : (prev.flagged === true),
      firstTryCorrect: (typeof prev.firstTryCorrect === "boolean") ? prev.firstTryCorrect : null,
      attempts: Array.isArray(prev.attempts) ? prev.attempts.slice(-49) : [],
      lastTs: Date.now()
    };
    if (patch.attempt) {
      if (next.firstTryCorrect === null) next.firstTryCorrect = patch.attempt.correct;
      next.attempts = next.attempts.concat([patch.attempt]);
    }
    progress[qid] = next;
    save();
    paintQuestion(qid);
    paintStats();
    setAnchor(qid);
  }

  function forget(qid) {
    delete progress[qid];
    save();
    paintQuestion(qid);
    paintStats();
    if (ANCHOR === qid) { ANCHOR = null; RESUMING = false; paintPos(); }
  }

  /* ---------- mode helpers ---------- */

  /* The single gate on showing an answer. In tutor mode an answered question
     reveals at once - that is the whole value of the written rationales. In a
     sat block the pick is held and nothing is shown until submit; revealing
     early would make it a tutor stream with extra steps. */
  function revealOk() { return MODE !== "test" || TEST.submitted; }

  /* 155 of the questions in the banks cannot be auto-marked: free text,
     matching, and the ones whose source gives no defensible key. They are
     fine in a tutor stream, where you mark yourself. A sat block that
     silently fails to score a fifth of itself is not a score, so blocks are
     drawn from the gradable ones only. */
  function gradable(q) {
    return !q.free && !q.unscorable &&
           Array.isArray(q.correct) && q.correct.length > 0;
  }

  function testChosen(qid) {
    var v = TEST.picks[qid];
    return Array.isArray(v) ? v : [];
  }

  function staging() { return MODE === "test" && !TEST.submitted; }

  /* ---------- build one question ---------- */

  var KIND_LABEL = { matching: "matching", short: "short answer", broken: "unscorable" };

  function buildQuestion(q) {
    var art = el("article", "q");
    art.id = "q-" + q.qid;
    art.dataset.qid = q.qid;
    art.dataset.kind = q.kind;

    var head = el("div", "qhead");
    head.appendChild(el("span", "qnum", "Q" + q.num));
    head.appendChild(el("span", "tag", q.sourceLabel));
    if (!q.keyed) head.appendChild(el("span", "tag reasoned", "no official key"));
    if (KIND_LABEL[q.kind]) head.appendChild(el("span", "tag kind", KIND_LABEL[q.kind]));
    if (q.multi) head.appendChild(el("span", "tag multi", "select " + q.correct.length));
    if (q.retired) head.appendChild(el("span", "tag retired", "retired"));
    var hasErr = (q.flags || []).some(function (f) {
      return f.type === "bug" || f.type === "red" ||
             (f.type === "warning" && f.title !== "No explanation in the module");
    });
    if (hasErr) head.appendChild(el("span", "tag errflag", "source error flagged"));
    head.appendChild(el("span", "spacer"));

    var star = el("button", "star-btn", "★");
    star.type = "button";
    star.title = "Star for review";
    star.setAttribute("aria-label", "Star question " + q.num);
    star.setAttribute("aria-pressed", "false");
    star.addEventListener("click", function () {
      persist(q.qid, { flagged: !isStarred(q.qid) });
    });
    head.appendChild(star);
    art.appendChild(head);

    if (q.preamble) {
      var pre = el("div", "preamble");
      pre.appendChild(el("span", "pt", q.preamble.title || "Instructions"));
      var pb = el("div");
      pb.innerHTML = q.preamble.html;
      pre.appendChild(pb);
      art.appendChild(pre);
    }

    var stem = el("div", "stem");
    stem.innerHTML = q.stem;
    art.appendChild(stem);

    if (q.options.length) {
      var list = el("ul", "opts");
      q.options.forEach(function (o) {
        var li = document.createElement("li");
        var b = el("button", "opt");
        b.type = "button";
        b.dataset.letter = o.letter;
        b.appendChild(el("span", "L", o.letter));
        var t = el("span", "t");
        t.innerHTML = o.html;
        b.appendChild(t);
        b.appendChild(el("span", "verdict"));
        if (q.unscorable) b.disabled = true;
        else b.addEventListener("click", function () { pick(q, art, o.letter); });
        li.appendChild(b);
        list.appendChild(li);
      });
      art.appendChild(list);
    }

    if (q.unscorable) {
      var bn = el("div", "banner pre");
      bn.appendChild(el("b", null, "Not scored"));
      bn.appendChild(document.createTextNode(
        "The source gives no defensible answer for this one, so it is left out of the accuracy figures. Read why, then move on."));
      art.appendChild(bn);
      var a1 = el("div", "actions");
      var sh = el("button", "btn ghost", "Show the problem");
      sh.type = "button";
      sh.addEventListener("click", function () { art.classList.add("revealed"); });
      a1.appendChild(sh);
      art.appendChild(a1);
    } else if (q.free) {
      var a2 = el("div", "actions");
      var show = el("button", "btn", "Show answer");
      show.type = "button";
      show.addEventListener("click", function () { art.classList.add("revealed"); });
      var got = el("button", "btn ghost", "I had it");
      got.type = "button";
      got.addEventListener("click", function () {
        art.classList.add("revealed");
        persist(q.qid, {
          status: "correct",
          attempt: { ts: Date.now(), chosen: "self", correct: true }
        });
      });
      var mis = el("button", "btn ghost", "I missed it");
      mis.type = "button";
      mis.addEventListener("click", function () {
        art.classList.add("revealed");
        persist(q.qid, {
          status: "wrong",
          attempt: { ts: Date.now(), chosen: "self", correct: false }
        });
      });
      a2.appendChild(show);
      a2.appendChild(got);
      a2.appendChild(mis);
      art.appendChild(a2);
    } else if (q.multi) {
      var a3 = el("div", "actions");
      var check = el("button", "btn", "Check answer");
      check.type = "button";
      check.dataset.role = "check";
      check.disabled = true;
      check.addEventListener("click", function () { submitMulti(q, art); });
      a3.appendChild(check);
      a3.appendChild(el("span", "hint", "select " + q.correct.length + ", then check"));
      art.appendChild(a3);
    }

    var ans = el("div", "answer");
    if (!q.keyed) {
      var nk = el("div", "banner");
      nk.appendChild(el("b", null, "No official answer key"));
      nk.appendChild(document.createTextNode(
        "Reasoned from the lecture content, not transcribed from a key. Verify before relying on it."));
      ans.appendChild(nk);
    }
    ans.appendChild(el("p", "ans-h", q.keyed ? (q.answerTitle || "Answer") : "Reasoned answer"));
    var ab = el("div", "ans-body");
    ab.innerHTML = q.answer;
    ans.appendChild(ab);
    (q.flags || []).forEach(function (f) {
      var c = el("div", "callout k-" + (/^[a-z]+$/.test(f.type) ? f.type : "note"));
      c.appendChild(el("span", "ct", f.title || "Note"));
      var cb = el("div");
      cb.innerHTML = f.html;
      c.appendChild(cb);
      ans.appendChild(c);
    });
    art.appendChild(ans);

    var foot = el("div", "qfoot");
    foot.appendChild(el("span", "qid", q.qid));
    foot.appendChild(el("span", "qid attempts"));
    var rst = el("button", "reset-q", "reset");
    rst.type = "button";
    rst.hidden = true;
    rst.addEventListener("click", function () { forget(q.qid); });
    foot.appendChild(rst);
    art.appendChild(foot);
    return art;
  }

  function pick(q, art, letter) {
    /* While a block is being sat, a pick is held in memory rather than
       written through: nothing reaches localStorage until submit. */
    if (staging()) {
      var cur = testChosen(q.qid);
      if (q.multi) {
        var at = cur.indexOf(letter);
        if (at === -1) cur = cur.concat([letter]);
        else cur = cur.slice(0, at).concat(cur.slice(at + 1));
      } else {
        cur = (cur.length === 1 && cur[0] === letter) ? [] : [letter];
      }
      TEST.picks[q.qid] = cur;
      paintQuestion(q.qid);
      paintTest();
      return;
    }
    if (q.multi) {
      if (art.classList.contains("revealed")) return;
      var btn = art.querySelector('.opt[data-letter="' + letter + '"]');
      btn.dataset.pick = btn.dataset.pick === "on" ? "" : "on";
      art.querySelector('[data-role="check"]').disabled =
        art.querySelectorAll('.opt[data-pick="on"]').length === 0;
      return;
    }
    var correct = q.correct.indexOf(letter) !== -1;
    persist(q.qid, {
      status: correct ? "correct" : "wrong",
      attempt: { ts: Date.now(), chosen: letter, correct: correct }
    });
  }

  function submitMulti(q, art) {
    if (staging()) return;
    var picked = [].slice.call(art.querySelectorAll('.opt[data-pick="on"]'))
      .map(function (b) { return b.dataset.letter; })
      .sort();
    var correct = picked.join("+") === q.correct.slice().sort().join("+");
    persist(q.qid, {
      status: correct ? "correct" : "wrong",
      attempt: { ts: Date.now(), chosen: picked.join("+"), correct: correct }
    });
  }

  function paintQuestion(qid) {
    var art = byId("q-" + qid);
    if (!art) return;
    var q = QMAP[qid], st = stateOf(qid), done = st !== "unseen";

    /* A staged block answers from TEST.picks, not from the store, and reveals
       nothing: no verdict, no state stripe, options still live so the answer
       can be changed right up to the submit. */
    var chosen, reveal;
    if (staging()) {
      chosen = testChosen(qid);
      done = chosen.length > 0;
      reveal = false;
    } else {
      chosen = chosenOf(qid) || [];
      reveal = done && revealOk();
    }

    art.dataset.state = reveal ? st : "unseen";
    if (!q.unscorable) art.classList.toggle("revealed", reveal);
    art.querySelector(".star-btn").setAttribute("aria-pressed", isStarred(qid) ? "true" : "false");

    [].forEach.call(art.querySelectorAll(".opt"), function (b) {
      if (q.unscorable) return;
      var L = b.dataset.letter;
      b.disabled = reveal;
      b.dataset.pick = (!reveal && chosen.indexOf(L) !== -1) ? "on" : "";
      var v = b.querySelector(".verdict");
      v.textContent = "";
      b.dataset.mark = "";
      if (!reveal) return;
      var isKey = q.correct.indexOf(L) !== -1, wasPicked = chosen.indexOf(L) !== -1;
      if (wasPicked && isKey) { b.dataset.mark = "hit"; v.textContent = "your pick · correct"; }
      else if (wasPicked) { b.dataset.mark = "miss"; v.textContent = "your pick"; }
      else if (isKey) { b.dataset.mark = "key"; v.textContent = "correct"; }
    });

    /* nothing to "check" while staging - the pick IS the answer until submit */
    var check = art.querySelector('[data-role="check"]');
    if (check) check.hidden = reveal || staging();

    var atts = attemptsOf(qid);
    art.querySelector(".attempts").textContent = atts.length > 1 ? atts.length + " attempts" : "";
    art.querySelector(".reset-q").hidden = staging() || (!reveal && !isStarred(qid));
  }

  /* ---------- filters ---------- */

  /* One predicate per filter group rather than one combined test: a facet's
     own count has to honour the other two groups and ignore itself, which is
     what makes "Week 3" read as "3 of the questions you are looking at". */
  function famOk(q) { return !filters.family || q.family === filters.family; }

  function weekOk(q) { return filters.week === "all" || weekKey(q) === filters.week; }

  /* Tags cut across the other three: the anatomy strand is taught in one block
     but its questions arrive as modules and as workbook chapters, so neither
     the family row nor the week chip can gather them. A question carries none
     unless it was tagged, and most carry none. */
  function tagsOf(q) { return Array.isArray(q.tags) ? q.tags : []; }

  function tagOk(q) {
    return filters.tag === "all" || tagsOf(q).indexOf(filters.tag) !== -1;
  }

  function statusOk(q) {
    var st = stateOf(q.qid);
    switch (filters.status) {
      case "unseen":  return st === "unseen";
      case "wrong":   return st === "wrong";
      case "correct": return st === "correct";
      case "starred": return isStarred(q.qid);
      default:        return true;
    }
  }

  function matches(qid) {
    var q = QMAP[qid];
    return famOk(q) && weekOk(q) && tagOk(q) && statusOk(q);
  }

  // qids currently passing the filters that actually have something to clear
  function shownWithProgress() {
    return QUESTIONS.filter(function (q) { return progress[q.qid] && matches(q.qid); })
                    .map(function (q) { return q.qid; });
  }

  /* The qids in play, in bank order. In a sat block that is the block; in a
     tutor stream it is whatever the filters match. Bank order either way -
     the draw decides WHICH questions, never what order you meet them in, so
     a block still reads week by week. */
  function inPlayIds() {
    if (MODE === "test" && TEST.ids) {
      var set = Object.create(null);
      TEST.ids.forEach(function (id) { set[id] = 1; });
      return QUESTIONS.filter(function (q) { return set[q.qid]; })
                      .map(function (q) { return q.qid; });
    }
    return QUESTIONS.filter(function (q) { return matches(q.qid); })
                    .map(function (q) { return q.qid; });
  }

  /* Paging is the filter trick with a narrower predicate: the stream already
     builds every question once and hides what is out of play, so one at a
     time is "hide all but one" and every other part of the engine - progress,
     stars, the keyboard steps, the resume point - carries over untouched. */
  function applyFilters() {
    var ids = inPlayIds(), live = Object.create(null);
    if (VIEW === "paged" && ids.length) {
      if (pageIdx >= ids.length) pageIdx = ids.length - 1;
      if (pageIdx < 0) pageIdx = 0;
      live[ids[pageIdx]] = 1;
    } else {
      ids.forEach(function (id) { live[id] = 1; });
    }

    var shown = 0;
    QUESTIONS.forEach(function (q) {
      var art = byId("q-" + q.qid);
      /* buildStream only renders questions whose family is declared on the
         block, so a bank carrying a family portal.py does not list yet has
         no node here. Before this guard that was a null dereference that
         took the whole questions tab down - one stray family, blank page. */
      if (!art) return;
      var ok = !!live[q.qid];
      art.hidden = !ok;
      if (ok) shown++;
    });
    // a heading survives only while a question under it is still visible
    [].forEach.call(document.querySelectorAll(".lecbar"), function (h) {
      var any = false, n = h.nextElementSibling;
      while (n && n.classList.contains("q")) {
        if (!n.hidden) { any = true; break; }
        n = n.nextElementSibling;
      }
      h.hidden = !any;
    });
    [].forEach.call(document.querySelectorAll(".weekbar"), function (h) {
      var any = false, n = h.nextElementSibling;
      while (n && !n.classList.contains("weekbar")) {
        if (n.classList.contains("q") && !n.hidden) { any = true; break; }
        n = n.nextElementSibling;
      }
      h.hidden = !any;
    });

    var narrowed = filters.status !== "all" || filters.week !== "all" ||
                   filters.tag !== "all";
    [].forEach.call(document.querySelectorAll(".family"), function (f) {
      if (filters.family && f.dataset.family !== filters.family) { f.hidden = true; return; }
      if (f.dataset.count === "0") { f.hidden = !!narrowed; return; }
      f.hidden = !f.querySelector(".q:not([hidden])");
    });
    /* the empty state belongs to the filters, not to the page you are on */
    byId("empty").hidden = ids.length > 0;
    indexVisible();
    paintPos();
    paintBar();
    paintTest();
    paintPagebar(ids);
  }

  /* Changing a filter while a block is being sat draws a new block. The
     alternative - quietly editing the block under you - would make the score
     mean nothing. */
  function afterFilterChange() {
    pageIdx = 0;
    if (MODE === "test") { redrawBlock(); return; }
    applyFilters();
  }

  function setStatus(s) { filters.status = s; afterFilterChange(); }
  function setWeek(w) { filters.week = w; afterFilterChange(); }
  function setTag(t) { filters.tag = t; afterFilterChange(); }

  /* ---------- view + mode ---------- */

  function syncSegs() {
    [].forEach.call(document.querySelectorAll("#view-seg button"), function (b) {
      b.setAttribute("aria-pressed", b.dataset.view === VIEW ? "true" : "false");
    });
    [].forEach.call(document.querySelectorAll("#mode-seg button"), function (b) {
      b.setAttribute("aria-pressed", b.dataset.mode === MODE ? "true" : "false");
    });
  }

  function setView(v) {
    if ((v !== "stream" && v !== "paged") || VIEW === v) return;
    VIEW = v;
    if (v === "paged") {
      /* land on the question you were already looking at rather than the top
         of the bank - the anchor is what the resume point is built on */
      var ids = inPlayIds(), at = ANCHOR ? ids.indexOf(ANCHOR) : -1;
      pageIdx = at === -1 ? 0 : at;
    }
    syncSegs();
    applyFilters();
    if (v === "paged") toTop();
  }

  function setMode(m) {
    if ((m !== "tutor" && m !== "test") || MODE === m) return;
    MODE = m;
    if (m === "test") {
      drawTest();
    } else {
      TEST.ids = null;
      TEST.picks = Object.create(null);
      TEST.submitted = false;
      pageIdx = 0;
    }
    syncSegs();
    applyFilters();
    /* reveal is a global condition, so every card has to be repainted */
    QUESTIONS.forEach(function (q) { paintQuestion(q.qid); });
    toTop();
  }

  /* ---------- the sat block ---------- */

  function drawTest() {
    var pool = QUESTIONS.filter(function (q) {
      return matches(q.qid) && gradable(q);
    }).map(function (q) { return q.qid; });

    /* Fisher-Yates. Drawn in bank order, a block would be the same block every
       time, and the first twenty questions of week 1 are not a rehearsal. */
    for (var i = pool.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1)), t = pool[i];
      pool[i] = pool[j]; pool[j] = t;
    }
    TEST.poolN = pool.length;
    TEST.asked = TEST.size;
    TEST.ids = pool.slice(0, Math.min(TEST.size, pool.length));
    TEST.picks = Object.create(null);
    TEST.submitted = false;
    pageIdx = 0;
  }

  function submitTest() {
    if (!TEST.ids || TEST.submitted) return;
    /* flipped before the writes so persist() paints a revealed card, not a
       staged one */
    TEST.submitted = true;
    TEST.ids.forEach(function (qid) {
      var q = QMAP[qid], picked = testChosen(qid);
      if (!picked.length) return;         /* left blank stays left blank */
      var correct = picked.slice().sort().join("+") === q.correct.slice().sort().join("+");
      persist(qid, {
        status: correct ? "correct" : "wrong",
        /* tagged, so "what is my accuracy when nothing tells me I am right"
           stays an answerable question later */
        attempt: { ts: Date.now(), chosen: picked.join("+"), correct: correct, mode: "test" }
      });
    });
    pageIdx = 0;
    applyFilters();
    TEST.ids.forEach(paintQuestion);
    toTop();
  }

  /* Repaint only the cards that changed hands. This runs on every keystroke
     in the block-size field, and a blanket repaint of a 581-question bank
     there is a visible stutter for no gain. */
  function redrawBlock() {
    var before = TEST.ids || [];
    drawTest();
    applyFilters();
    var touched = Object.create(null);
    before.concat(TEST.ids || []).forEach(function (id) { touched[id] = 1; });
    Object.keys(touched).forEach(paintQuestion);
  }

  function clearResult() {
    var r = byId("tb-result");
    if (r && r.parentNode) r.parentNode.removeChild(r);
  }

  /* The one number a sat block exists to produce, and the grouping that a
     tutor stream structurally cannot show you: which SOURCE you are losing
     marks to, visible only because forty were marked at once. */
  function paintResult() {
    clearResult();
    if (MODE !== "test" || !TEST.submitted || !TEST.ids) return;
    var n = TEST.ids.length, right = 0, blank = 0, missed = [];
    TEST.ids.forEach(function (qid) {
      if (!testChosen(qid).length) { blank++; return; }
      if (stateOf(qid) === "correct") right++; else missed.push(QMAP[qid]);
    });

    var box = el("div", "tb-result");
    box.id = "tb-result";
    box.appendChild(el("h3", null, "Block submitted"));
    box.appendChild(el("div", "big", right + " / " + n));
    box.appendChild(el("p", null,
      (n ? Math.round(right / n * 100) : 0) + "% on this block" +
      (blank ? " \u00b7 " + blank + " left blank" : "") + "."));

    if (missed.length) {
      var bySrc = Object.create(null);
      missed.forEach(function (q) {
        bySrc[q.sourceLabel] = (bySrc[q.sourceLabel] || 0) + 1;
      });
      var ul = document.createElement("ul");
      Object.keys(bySrc).forEach(function (k) {
        ul.appendChild(el("li", null, bySrc[k] + " missed from " + k));
      });
      box.appendChild(ul);
    }
    var stream = byId("stream");
    stream.parentNode.insertBefore(box, stream);
  }

  function paintTest() {
    var shell = byId("panel-questions");
    if (shell) {
      shell.dataset.view = VIEW;
      shell.dataset.mode = MODE;
      shell.dataset.submitted = TEST.submitted ? "true" : "false";
    }
    var bar = byId("testbar");
    if (!bar) return;
    bar.textContent = "";
    if (MODE !== "test") { bar.hidden = true; clearResult(); return; }
    bar.hidden = false;

    var ids = TEST.ids || [];
    var answered = ids.filter(function (id) { return testChosen(id).length; }).length;

    var head = el("span");
    head.appendChild(el("b", null, "Block of " + ids.length));
    head.appendChild(document.createTextNode(TEST.submitted
      ? " \u00b7 submitted \u00b7 reviewing"
      : " \u00b7 " + answered + " of " + ids.length +
        " answered \u00b7 no feedback until you submit"));
    bar.appendChild(head);

    var sf = el("div", "tb-size");
    var lab = document.createElement("label");
    lab.setAttribute("for", "tb-count");
    lab.textContent = "How many?";
    var inp = document.createElement("input");
    inp.type = "number";
    inp.id = "tb-count";
    inp.min = "1";
    inp.step = "1";
    inp.value = String(TEST.size);
    /* repainting the bar rebuilds this field, so the caret has to be put back
       or it jumps out on every keystroke */
    inp.addEventListener("input", function () {
      var v = parseInt(inp.value, 10);
      if (isNaN(v) || v < 1) return;
      TEST.size = v;
      redrawBlock();
      var back = byId("tb-count");
      if (back) {
        back.focus();
        try { back.setSelectionRange(back.value.length, back.value.length); }
        catch (e) { /* number inputs refuse this in some browsers */ }
      }
    });
    sf.appendChild(lab);
    sf.appendChild(inp);
    bar.appendChild(sf);

    var btn = el("button", "tb-btn", TEST.submitted ? "New block" : "Submit block");
    btn.type = "button";
    btn.addEventListener("click", function () {
      if (TEST.submitted) { redrawBlock(); toTop(); } else submitTest();
    });
    bar.appendChild(btn);

    /* A block shrunk to fit the pool says so, here, beside the count. Clamping
       in silence is indistinguishable from a control that does nothing. */
    if (TEST.asked > ids.length) {
      bar.appendChild(el("span", "tb-note",
        "You asked for " + TEST.asked + ". These filters match " + TEST.poolN +
        " auto-markable question" + (TEST.poolN === 1 ? "" : "s") +
        ", so the block is " + ids.length + ". Widen the filters for a longer one."));
    }
    paintResult();
  }

  function paintPagebar(ids) {
    var bar = byId("pagebar");
    if (!bar) return;
    bar.textContent = "";
    if (VIEW !== "paged" || !ids.length) { bar.hidden = true; return; }
    bar.hidden = false;
    /* the position bar and the pager say the same thing; one of them goes */
    var pb = byId("posbar");
    if (pb) pb.hidden = true;

    var prev = el("button", "pg-btn", "\u2190 Previous");
    prev.type = "button";
    prev.disabled = pageIdx === 0;
    prev.addEventListener("click", function () { pageIdx--; applyFilters(); toTop(); });
    bar.appendChild(prev);

    bar.appendChild(el("span", "pg-pos", (pageIdx + 1) + " of " + ids.length));

    var atEnd = pageIdx === ids.length - 1;
    if (MODE === "test" && !TEST.submitted && atEnd) {
      var sub = el("button", "pg-btn primary", "Submit block");
      sub.type = "button";
      sub.addEventListener("click", submitTest);
      bar.appendChild(sub);
    } else {
      var next = el("button", "pg-btn", "Next \u2192");
      next.type = "button";
      next.disabled = atEnd;
      next.addEventListener("click", function () { pageIdx++; applyFilters(); toTop(); });
      bar.appendChild(next);
    }
  }

  /* ---------- where you are in the stream ---------- */

  /* The stream runs from the first question to the last in one scroll - 279 of
     them in endo - so the bar pinned to the bottom of the viewport is the only
     thing that says where you are, and the only way back to the question you
     were on before you scrolled off to check something.

     Position is read from an IntersectionObserver rather than measured on
     scroll. Asking this many nodes where they are on every scroll event costs
     frames, and a hidden question is not rendered and so never intersects,
     which means the filters fall out of it for free. */

  var VISIBLE = [];                  // qids passing the filters, in stream order
  var VINDEX = Object.create(null);  // qid -> its place in VISIBLE
  var inView = Object.create(null);  // qids currently crossing the sight line
  var CURRENT = null;                // the question at the top of the viewport
  var ANCHOR = null;                 // the question to offer a way back to
  var RESUMING = false;              // showing the reopen offer, not the marker
  var posReady = false;
  var scrollQueued = false;

  /* read off the DOM, not off QUESTIONS: the stream is built family by family,
     so its order is not the order the JSON happens to arrive in */
  function indexVisible() {
    VISIBLE = [];
    VINDEX = Object.create(null);
    [].forEach.call(document.querySelectorAll("#stream .q"), function (art) {
      if (art.hidden) return;
      VINDEX[art.dataset.qid] = VISIBLE.length;
      VISIBLE.push(art.dataset.qid);
    });
  }

  function topmostInView() {
    var best = null, bestAt = Infinity;
    Object.keys(inView).forEach(function (qid) {
      var i = VINDEX[qid];
      if (i !== undefined && i < bestAt) { bestAt = i; best = qid; }
    });
    return best;
  }

  function onIntersect(entries) {
    entries.forEach(function (e) {
      var qid = e.target.dataset.qid;
      if (e.isIntersecting) inView[qid] = true;
      else delete inView[qid];
    });
    var top = topmostInView();
    if (top) CURRENT = top;   // between two questions, the last one still holds
    paintPos();
  }

  /* the stream runs to hundreds of questions, so the bar owes you the way
     out of it as well as the way around it. It hides itself once you land. */
  function toTop() {
    var still = window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    try { window.scrollTo({ top: 0, behavior: still ? "auto" : "smooth" }); }
    catch (e) { window.scrollTo(0, 0); }
  }

  function goTo(qid) {
    var art = byId("q-" + qid);
    if (!art) return;
    var top = art.getBoundingClientRect().top + window.pageYOffset - 16;
    var still = window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    try { window.scrollTo({ top: top, behavior: still ? "auto" : "smooth" }); }
    catch (e) { window.scrollTo(0, top); }
    CURRENT = qid;
    paintPos();
  }

  function step(delta) {
    if (!VISIBLE.length) return;
    var i = (CURRENT && VINDEX[CURRENT] !== undefined) ? VINDEX[CURRENT] : 0;
    var j = i + delta;
    if (j < 0 || j >= VISIBLE.length) return;
    goTo(VISIBLE[j]);
  }

  function setAnchor(qid) {
    ANCHOR = qid;
    RESUMING = false;
    paintPos();
  }

  /* lastTs has been written on every answer all along and read by nothing, so
     the question you last touched costs no new storage and already rides along
     in the JSON backup */
  function resumePoint() {
    var best = null, bestTs = 0;
    Object.keys(progress).forEach(function (qid) {
      if (QMAP[qid] && progress[qid].lastTs > bestTs) {
        bestTs = progress[qid].lastTs;
        best = qid;
      }
    });
    return best;
  }

  function paintMark(at) {
    var mk = byId("pb-mark");
    if (RESUMING && ANCHOR && QMAP[ANCHOR]) {
      mk.hidden = false;
      mk.textContent = "Resume at Q" + QMAP[ANCHOR].num +
                       " \u00b7 " + QMAP[ANCHOR].lecture;
      return;
    }
    // no anchor, filtered away, or near enough that a button would be noise
    if (!ANCHOR || VINDEX[ANCHOR] === undefined || at === null) {
      mk.hidden = true;
      return;
    }
    var away = VINDEX[ANCHOR] - at;
    if (Math.abs(away) < 2) { mk.hidden = true; return; }
    mk.hidden = false;
    mk.textContent = (away < 0 ? "\u2191" : "\u2193") +
                     " back to Q" + QMAP[ANCHOR].num;
  }

  function paintPos() {
    if (!posReady) return;
    var bar = byId("posbar");
    /* out of the way until you are actually into the stream, except when there
       is a spot to reopen at - that offer has to be visible from the top */
    if (!VISIBLE.length || !(RESUMING || window.pageYOffset > 400)) {
      bar.hidden = true;
      return;
    }
    bar.hidden = false;

    if (!CURRENT || VINDEX[CURRENT] === undefined) {
      CURRENT = topmostInView() || VISIBLE[0];
    }
    var at = VINDEX[CURRENT] === undefined ? null : VINDEX[CURRENT];
    var q = QMAP[CURRENT];

    byId("pb-where").textContent = q ? (q.weekLabel + " \u00b7 " + q.lecture) : "";
    byId("pb-count").textContent = (at === null ? "\u2013" : String(at + 1)) +
      " / " + VISIBLE.length +
      ((filters.status !== "all" || filters.family ||
         filters.week !== "all" || filters.tag !== "all") ? " shown" : "");
    byId("pb-prev").disabled = at === null || at === 0;
    byId("pb-next").disabled = at === null || at === VISIBLE.length - 1;
    paintMark(at);
  }

  function onScroll() {
    if (scrollQueued) return;
    scrollQueued = true;
    window.requestAnimationFrame(function () {
      scrollQueued = false;
      // scrolling in is answer enough: the offer gives way to the live marker
      if (RESUMING && window.pageYOffset > 240) RESUMING = false;
      paintPos();
    });
  }

  function onKey(e) {
    if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
    if (byId("panel-questions").hidden) return;
    var t = e.target;
    if (t && (t.isContentEditable ||
              /^(input|textarea|select)$/i.test(t.tagName || ""))) return;
    if (e.key === "j") { e.preventDefault(); step(1); }
    else if (e.key === "k") { e.preventDefault(); step(-1); }
    else if (e.key === "b" && ANCHOR) {
      e.preventDefault();
      RESUMING = false;
      goTo(ANCHOR);
    }
  }

  /* a browser without IntersectionObserver gets the stream exactly as it was,
     which is better than a bar that cannot say where it is */
  function initPos() {
    if (!window.IntersectionObserver) return;
    posReady = true;

    // the sight line is the top fifth of the viewport
    var obs = new window.IntersectionObserver(onIntersect,
      { rootMargin: "0px 0px -80% 0px" });
    [].forEach.call(document.querySelectorAll("#stream .q"), function (art) {
      obs.observe(art);
    });

    byId("pb-top").addEventListener("click", toTop);
    byId("pb-prev").addEventListener("click", function () { step(-1); });
    byId("pb-next").addEventListener("click", function () { step(1); });
    byId("pb-mark").addEventListener("click", function () {
      if (!ANCHOR) return;
      RESUMING = false;
      goTo(ANCHOR);
    });
    window.addEventListener("scroll", onScroll, { passive: true });
    document.addEventListener("keydown", onKey);

    var r = resumePoint();
    if (r && matches(r)) { ANCHOR = r; RESUMING = true; }
    paintPos();
  }

  /* ---------- rail ---------- */

  var STATUS_DEFS = [
    { k: "all", label: "All" },
    { k: "unseen", label: "Unseen" },
    { k: "wrong", label: "Wrong", cls: "wrongish" },
    { k: "correct", label: "Correct" },
    { k: "starred", label: "Starred", cls: "starish" }
  ];

  /* Weeks come off the questions rather than off BLOCK.weeks: that is a
     display string ("1–3"), and a block can carry off-curriculum questions
     that belong to no week at all. Numbers, not labels - the same week is
     labelled differently by each family, so the labels would split it. */
  function weekKey(q) { return q.week === null ? "off" : String(q.week); }

  function weekDefs() {
    var n = Object.create(null), order = [];
    QUESTIONS.forEach(function (q) {
      var k = weekKey(q);
      if (n[k] === undefined) { n[k] = 0; order.push(k); }
      n[k]++;
    });
    order.sort(function (a, b) {
      if (a === "off") return 1;
      if (b === "off") return -1;
      return Number(a) - Number(b);
    });
    var defs = [{ k: "all", label: "All", n: QUESTIONS.length }];
    order.forEach(function (k) {
      defs.push({ k: k, label: k === "off" ? "Off-curriculum" : "Week " + k, n: n[k] });
    });
    return defs;
  }

  /* Spelled out here rather than derived from the tag, so a chip can be worded
     independently of the tag every question carries. An unknown tag still
     renders, capitalised. */
  var TAG_NAMES = { anatomy: "Anatomy" };

  function tagTitle(k) {
    return TAG_NAMES[k] || (k.charAt(0).toUpperCase() + k.slice(1));
  }

  /* Empty for a block with nothing tagged, which is what hides the group:
     endo has the anatomy strand, the other four have nothing yet. */
  function tagDefs() {
    var n = Object.create(null), order = [];
    QUESTIONS.forEach(function (q) {
      tagsOf(q).forEach(function (k) {
        if (n[k] === undefined) { n[k] = 0; order.push(k); }
        n[k]++;
      });
    });
    if (!order.length) return [];
    order.sort();
    var defs = [{ k: "all", label: "All", n: QUESTIONS.length }];
    order.forEach(function (k) { defs.push({ k: k, label: tagTitle(k), n: n[k] }); });
    return defs;
  }

  /* Every tally below skips its own group and applies the other three, in one
     pass. Before this, the numbers went wrong the moment a second filter was
     on: picking Wrong still offered "Week 1 195" when only a handful of those
     were wrong, and the week counts were written once at build and never
     repainted at all. */
  function facetCounts() {
    var fam = Object.create(null), week = Object.create(null);
    var tag = Object.create(null);
    var status = { all: 0, unseen: 0, wrong: 0, correct: 0, starred: 0 };
    var famAll = 0, weekAll = 0, tagAll = 0, shown = 0;
    QUESTIONS.forEach(function (q) {
      var f = famOk(q), w = weekOk(q), t = tagOk(q), sOk = statusOk(q), wk, st;
      if (w && t && sOk) {
        fam[q.family] = (fam[q.family] || 0) + 1;
        famAll++;
      }
      if (f && t && sOk) {
        wk = weekKey(q);
        week[wk] = (week[wk] || 0) + 1;
        weekAll++;
      }
      if (f && w && sOk) {
        /* a question with two tags counts under each, so these never sum to
           tagAll - the same way the week chips are a partition and these are
           not */
        tagsOf(q).forEach(function (k) { tag[k] = (tag[k] || 0) + 1; });
        tagAll++;
      }
      if (f && w && t) {
        st = stateOf(q.qid);
        status.all++;
        if (st === "unseen") status.unseen++;
        else if (st === "wrong") status.wrong++;
        else status.correct++;
        if (isStarred(q.qid)) status.starred++;
      }
      if (f && w && t && sOk) shown++;
    });
    return {
      fam: fam, famAll: famAll,
      week: week, weekAll: weekAll,
      tag: tag, tagAll: tagAll,
      status: status, shown: shown
    };
  }

  /* Four independent filters and, without this, nothing anywhere saying which
     of them emptied the stream - the answer had to be hunted across all four
     groups. It matters more now than it did in the rail: a closed dropdown
     hides its count, so this row is the only thing standing between you and a
     filtered view that looks unfiltered. */
  function paintApplied(shown) {
    var box = byId("applied");
    if (!box) return;          // a page cached from before this shipped

    var live = [];
    if (filters.family) {
      live.push({
        label: FAM_NAME[filters.family] || filters.family,
        clear: function () { filters.family = null; }
      });
    }
    if (filters.week !== "all") {
      live.push({
        label: WEEK_LABEL[filters.week] || ("Week " + filters.week),
        clear: function () { filters.week = "all"; }
      });
    }
    if (filters.tag !== "all") {
      live.push({
        label: TAG_LABEL[filters.tag] || filters.tag,
        clear: function () { filters.tag = "all"; }
      });
    }
    if (filters.status !== "all") {
      live.push({
        label: STATUS_LABEL[filters.status] || filters.status,
        clear: function () { filters.status = "all"; }
      });
    }

    box.hidden = live.length === 0;
    box.textContent = "";
    if (!live.length) return;

    var head = el("div", "applied-h");
    head.appendChild(el("span", null, "Active filters"));
    head.appendChild(el("span", "res", shown + (shown === 1 ? " question" : " questions")));
    box.appendChild(head);

    var list = el("div", "applied-list");
    live.forEach(function (item) {
      var b = el("button", "fchip");
      b.type = "button";
      b.setAttribute("aria-label", "Remove the " + item.label + " filter");
      b.appendChild(el("span", null, item.label));
      b.appendChild(el("span", "x", "\u00d7"));
      b.addEventListener("click", function () { item.clear(); applyFilters(); });
      list.appendChild(b);
    });

    var ca = el("button", "clear-all", "Clear all");
    ca.type = "button";
    ca.addEventListener("click", function () {
      filters.family = null;
      filters.week = "all";
      filters.tag = "all";
      filters.status = "all";
      applyFilters();
    });
    list.appendChild(ca);

    box.appendChild(list);
  }

  /* An option worth zero is disabled rather than left live, which is what the
     family rows have always done and the chips never did. The one exception is
     the option currently selected: disabling that would trap you in it. */
  function paintBar() {
    var c = facetCounts();

    function paintSel(id, countFor, cur) {
      var sel = byId(id);
      if (!sel) return;
      [].forEach.call(sel.options, function (o) {
        var n = countFor(o.value);
        o.textContent = o.dataset.base + " \u00b7 " + n;
        o.disabled = o.value !== "all" && n === 0 && o.value !== cur;
      });
      sel.value = cur;
    }

    paintSel("f-status", function (k) { return c.status[k] || 0; }, filters.status);
    paintSel("f-week", function (k) {
      return k === "all" ? c.weekAll : (c.week[k] || 0);
    }, filters.week);
    paintSel("f-tag", function (k) {
      return k === "all" ? c.tagAll : (c.tag[k] || 0);
    }, filters.tag);

    /* the family select is the one that cannot just print its count: a family
       the block has none of says "none" for good, because that is a coverage
       gap, and one the filters emptied says 0 */
    var fsel = byId("f-family"), fcur = filters.family || "all";
    if (fsel) {
      [].forEach.call(fsel.options, function (o) {
        var k = o.value, n = (k === "all") ? c.famAll : (c.fam[k] || 0);
        var gap = k !== "all" && FAM_TOTAL[k] === 0;
        o.textContent = o.dataset.base + " \u00b7 " + (gap ? "none" : n);
        o.disabled = k !== "all" && n === 0 && k !== fcur;
      });
      fsel.value = fcur;
    }

    paintApplied(c.shown);
    if (RESET_SHOWN_IDLE) RESET_SHOWN_IDLE();
  }

  function paintStats() {
    var attempted = 0, wrong = 0, starred = 0, ok = 0;
    QUESTIONS.forEach(function (q) {
      var st = stateOf(q.qid);
      if (st !== "unseen") {
        attempted++;
        if (st === "wrong") wrong++; else ok++;
      }
      if (isStarred(q.qid)) starred++;
    });
    byId("sc-done").textContent = attempted;
    byId("sc-first").textContent = attempted ? Math.round(ok / attempted * 100) + "%" : "–";
    byId("sc-wrong").textContent = wrong;
    byId("sc-star").textContent = starred;
    byId("review-wrong").disabled = wrong === 0;
    byId("review-n").textContent = wrong;
    paintBar();
  }

  /* ---------- boot ---------- */

  /* the eyebrow is written by pom2.js instead - it has to be right even when
     the page opens on the notes tab and none of this has run */
  function buildMasthead() {
    byId("sc-of").textContent = "/" + QUESTIONS.length;
  }

  /* One <select> per facet, options built once. Their labels carry the live
     counts, rewritten by paintBar, so a count still rides on the option the
     way it used to ride on the chip - the one real thing a dropdown hides. */
  function buildSelect(id, defs, onPick) {
    var sel = byId(id);
    if (!sel) return null;
    defs.forEach(function (d) {
      var o = document.createElement("option");
      o.value = d.k;
      o.dataset.base = d.label;
      o.textContent = d.label;
      sel.appendChild(o);
    });
    sel.addEventListener("change", function () { onPick(sel.value); });
    return sel;
  }

  function buildBar() {
    var famCount = {};
    QUESTIONS.forEach(function (q) { famCount[q.family] = (famCount[q.family] || 0) + 1; });

    var famDefs = [{ k: "all", label: "All question sets" }];
    FAMILIES.forEach(function (f) {
      FAM_TOTAL[f.key] = famCount[f.key] || 0;
      FAM_NAME[f.key] = f.name;
      famDefs.push({ k: f.key, label: f.name });
    });
    STATUS_DEFS.forEach(function (d) { STATUS_LABEL[d.k] = d.label; });

    buildSelect("f-family", famDefs, function (v) {
      filters.family = (v === "all") ? null : v;
      afterFilterChange();
    });

    var wd = weekDefs();
    wd.forEach(function (d) { WEEK_LABEL[d.k] = d.label; });
    buildSelect("f-week", wd.map(function (d) {
      return { k: d.k, label: d.k === "all" ? "All weeks" : d.label };
    }), setWeek);

    /* The topic group only earns its slot where something is tagged, so the
       dropdown ships hidden and the block's own data is what reveals it. */
    var td = tagDefs();
    if (td.length) {
      td.forEach(function (d) { TAG_LABEL[d.k] = d.label; });
      buildSelect("f-tag", td.map(function (d) {
        return { k: d.k, label: d.k === "all" ? "All topics" : d.label };
      }), setTag);
      if (byId("f-tag-wrap")) byId("f-tag-wrap").hidden = false;
    }

    buildSelect("f-status", STATUS_DEFS.map(function (d) {
      return { k: d.k, label: d.k === "all" ? "Any status" : d.label };
    }), setStatus);

    /* "wrong only" means every wrong answer in the block, so it clears what
       else is narrowing the stream rather than handing back an empty list.
       It is a review action, so it drops you out of a sat block. */
    byId("review-wrong").addEventListener("click", function () {
      filters.family = null;
      filters.week = "all";
      filters.tag = "all";
      filters.status = "wrong";
      if (MODE === "test") { setMode("tutor"); return; }
      afterFilterChange();
    });

    [].forEach.call(document.querySelectorAll("#view-seg button"), function (b) {
      b.addEventListener("click", function () { setView(b.dataset.view); });
    });
    [].forEach.call(document.querySelectorAll("#mode-seg button"), function (b) {
      b.addEventListener("click", function () { setMode(b.dataset.mode); });
    });
    syncSegs();

    // reset only what is on screen right now
    var rs = byId("reset-shown"), rsArmed = false, rsTimer = null;
    function rsIdle() {
      rsArmed = false;
      rs.classList.remove("armed");
      rs.textContent = "Reset the questions shown (" + shownWithProgress().length + ")";
      rs.disabled = shownWithProgress().length === 0;
    }
    rs.addEventListener("click", function () {
      var hit = shownWithProgress();
      if (!hit.length) return;
      if (!rsArmed) {
        rsArmed = true;
        rs.classList.add("armed");
        rs.textContent = "Clear these " + hit.length + ", click to confirm";
        rsTimer = setTimeout(rsIdle, 5000);
        return;
      }
      clearTimeout(rsTimer);
      hit.forEach(forget);
      rsIdle();
    });
    RESET_SHOWN_IDLE = rsIdle;

    var ra = byId("reset-all"), armed = false, timer = null;
    function raIdle() {
      armed = false;
      ra.classList.remove("armed");
      ra.textContent = "Reset all progress";
    }
    ra.addEventListener("click", function () {
      if (!armed) {
        armed = true;
        ra.classList.add("armed");
        ra.textContent = "Erase every answer in " + BLOCK.name + ", click to confirm";
        timer = setTimeout(raIdle, 5000);
        return;
      }
      clearTimeout(timer);
      raIdle();
      Object.keys(progress).slice().forEach(forget);
    });

    buildBackup();
  }

  /* localStorage is per-browser and the browser can clear it, so the progress
     has to be liftable out of here by hand. One file carries every block: the
     browser keeps all of them under the same key prefix, and a page that can
     read its own key can read its neighbours' just as well. */

  var SLUG_OK = /^[a-z0-9][a-z0-9_-]*$/i;

  function readStored(slug) {
    var raw = null;
    try { raw = window.localStorage.getItem(STORE_PREFIX + slug); }
    catch (e) { return null; }
    if (!raw) return null;
    var parsed;
    try { parsed = JSON.parse(raw); }
    catch (e) { return null; }
    return (parsed && typeof parsed === "object") ? parsed : null;
  }

  /* every block this browser has answered anything in, read off the keys rather
     than a list - the block list stays in tools/, and five stays unspecial */
  function everyBlock() {
    var out = {}, i, key, slug, data;
    try {
      for (i = 0; i < window.localStorage.length; i++) {
        key = window.localStorage.key(i);
        if (!key || key.indexOf(STORE_PREFIX) !== 0) continue;
        slug = key.slice(STORE_PREFIX.length);
        data = readStored(slug);
        if (data) out[slug] = data;
      }
    } catch (e) { /* the scan was refused; the open block still lands below */ }
    out[BLOCK.slug] = progress;   // what is in memory is at least as new
    return out;
  }

  /* a restore adds and advances, it never erases: a record older than the one
     already here loses. That is what makes restoring a stale file safe, and
     what makes it safe to restore onto a machine already part way through. */
  function newer(have, inc) {
    var a = (have && typeof have.lastTs === "number") ? have.lastTs : -1;
    var b = (inc && typeof inc.lastTs === "number") ? inc.lastTs : 0;
    return b > a;
  }

  function buildBackup() {
    byId("export-progress").addEventListener("click", function () {
      var payload = {
        store: "nsq",
        version: 2,
        exported: new Date().toISOString(),
        blocks: everyBlock()
      };
      var url = URL.createObjectURL(
        new Blob([JSON.stringify(payload, null, 1)], { type: "application/json" }));
      var a = document.createElement("a");
      a.href = url;
      /* dated, because the browser otherwise stacks these up as (1), (2) and
         there is no telling them apart from the outside */
      a.download = (BLOCK.course || "pom2").toLowerCase().replace(/[^a-z0-9]+/g, "-") + "-progress-" + new Date().toISOString().slice(0, 10) + ".json";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    });

    var file = byId("import-file");
    byId("import-progress").addEventListener("click", function () { file.click(); });
    file.addEventListener("change", function () {
      var f = file.files && file.files[0];
      if (!f) return;
      var reader = new FileReader();
      reader.onload = function () { restore(String(reader.result)); };
      reader.readAsText(f);
      file.value = "";
    });
  }

  /* a v2 file holds every block at once. A v1 file held one, named beside it -
     those still restore, they just restore the one. */
  function blocksInFile(parsed) {
    if (!parsed || typeof parsed !== "object") return null;
    if (parsed.blocks && typeof parsed.blocks === "object") return parsed.blocks;
    if (parsed.progress && typeof parsed.progress === "object") {
      var one = {};
      one[typeof parsed.block === "string" ? parsed.block : BLOCK.slug] = parsed.progress;
      return one;
    }
    return null;
  }

  function restore(text) {
    var parsed;
    try { parsed = JSON.parse(text); }
    catch (e) { note("That file is not valid JSON, so nothing was imported."); return; }

    var incoming = blocksInFile(parsed);
    if (!incoming) { note("No progress records found in that file."); return; }

    var here = 0, away = 0, elsewhere = [];

    Object.keys(incoming).forEach(function (slug) {
      var set = incoming[slug];
      if (!SLUG_OK.test(slug) || !set || typeof set !== "object") return;

      if (slug === BLOCK.slug) {
        Object.keys(set).forEach(function (qid) {
          var r = sanitize(qid, set[qid]);
          if (r && newer(progress[qid], r)) { progress[qid] = r; here++; }
        });
        return;
      }

      /* another block's records go to storage unchecked. Its own page sanitizes
         everything it loads against its own question list, so nothing
         unrecognised can reach the screen, and this page has no list to check
         them against without fetching a second question file. */
      var store = readStored(slug) || {}, n = 0;
      Object.keys(set).forEach(function (qid) {
        var inc = set[qid];
        if (!inc || typeof inc !== "object") return;
        if (newer(store[qid], inc)) { store[qid] = inc; n++; }
      });
      if (!n) return;
      try { window.localStorage.setItem(STORE_PREFIX + slug, JSON.stringify(store)); }
      catch (e) { return; }
      away += n;
      elsewhere.push(slug);
    });

    if (!here && !away) {
      note("Nothing in that file was newer than what is already here, so nothing changed.");
      return;
    }

    save();
    QUESTIONS.forEach(function (q) { paintQuestion(q.qid); });
    paintStats();
    applyFilters();

    var msg = here + " question" + (here === 1 ? "" : "s") + " restored in " + BLOCK.name + ".";
    if (away) {
      msg += " Another " + away + " in " + elsewhere.join(", ") +
             ", which appear when you open those blocks.";
    }
    note(msg);
  }

  function buildStream() {
    var stream = byId("stream"), frag = document.createDocumentFragment();
    FAMILIES.forEach(function (f) {
      var mine = QUESTIONS.filter(function (q) { return q.family === f.key; });
      var sec = el("section", "family");
      sec.dataset.family = f.key;
      sec.dataset.count = String(mine.length);

      var head = el("div", "fam-head");
      head.appendChild(el("p", "fam-meta",
        mine.length ? mine.length + " questions" : "nothing transcribed yet"));
      head.appendChild(el("h2", null, f.name));
      head.appendChild(el("p", null, f.blurb));
      sec.appendChild(head);

      if (!mine.length) {
        sec.appendChild(el("p", "fam-empty",
          "No " + f.name.toLowerCase() + " questions exist for this block yet. When they are written, they appear here."));
      }

      var lastWeek = null, lastLecture = null;
      mine.forEach(function (q) {
        if (q.weekLabel !== lastWeek) {
          lastWeek = q.weekLabel;
          lastLecture = null;
          var wb = el("div", "weekbar");
          wb.appendChild(el("h3", null, q.weekLabel));
          sec.appendChild(wb);
        }
        if (q.lecture !== lastLecture) {
          lastLecture = q.lecture;
          var lb = el("div", "lecbar");
          lb.appendChild(el("h4", null, q.lecture));
          /* lectureMeta is provenance - which deck, which pages, keyed or
             reasoned - and it stays in the bank and in the vault note. It is
             not shown here: on the page it sat between the lecture name and
             the first question as a paragraph of housekeeping, which is not
             what you are there to read. */
          sec.appendChild(lb);
        }
        sec.appendChild(buildQuestion(q));
      });
      frag.appendChild(sec);
    });
    var empty = el("div", "empty", "Nothing matches that filter.");
    empty.id = "empty";
    empty.hidden = true;
    frag.appendChild(empty);
    stream.innerHTML = "";
    stream.appendChild(frag);
  }

  function start(data) {
    QUESTIONS = data;
    QUESTIONS.forEach(function (q) { QMAP[q.qid] = q; });
    load();
    buildMasthead();
    buildBar();
    buildStream();
    paintStats();
    applyFilters();
    QUESTIONS.forEach(function (q) { paintQuestion(q.qid); });
    initPos();
    if (!storeWritable) {
      note("This browser will not let the page use local storage, so answers cannot be saved. Every question still works.");
    }
  }

  /* the tab strip calls this the first time Questions is opened; a second call
     is a no-op so switching tabs never refetches or rebuilds the stream */
  var booted = false;

  window.POM2_QUIZ = {
    boot: function () {
      if (booted) return;
      booted = true;
      fetch("data/questions/" + BLOCK.slug + ".json" +
            /* build_pages.py stamps the file's content hash here. Without it this
               one fetch was the only thing on the page with no cache busting, so a
               browser could keep serving the previous deploy's bank however hard
               you refreshed. Older pages carry no hash and simply go without. */
            (BLOCK.qv ? "?v=" + BLOCK.qv : ""))
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .then(start)
        .catch(function () {
          byId("stream").innerHTML = "";
          var e = el("div", "empty",
            "The question set could not be loaded. If you are opening this file straight from disk, serve the folder over HTTP instead - browsers block local fetches.");
          byId("stream").appendChild(e);
        });
    }
  };
})();
