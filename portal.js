/* Tab strip for a course block page, and the boot for the question bank.

   Notes and Anki are two views of the same week and share a page. Questions
   are not: they live on the course's one qbank.html, where a block is a filter
   value rather than a page, so the third tab is a link out rather than a panel.
   It carries the block in its hash, so arriving there lands pre-filtered.

   The tab lives in the hash, so a link can point straight at the notes and the
   back button steps between them. An old #questions link still works: it is
   redirected to the qbank, filtered to this block. */

(function () {
  "use strict";

  var BLOCK = window.QUIZ_BLOCK;

  var TABS = {
    notes: {
      tab: "tab-notes",
      panel: "panel-notes",
      board: "sb-notes",
      boot: function () { if (window.POM2_NOTES) window.POM2_NOTES.boot(); }
    },
    anki: {
      tab: "tab-anki",
      panel: "panel-anki",
      board: null,          /* the scoreboard counts answers; a deck has none */
      boot: function () {}
    }
  };

  /* Where this block's questions went. One place builds it, so the link in the
     tab strip and the redirect below cannot drift apart. */
  function qbankUrl() {
    return "qbank.html#block=" + BLOCK.slug;
  }

  /* A bookmark or an old link pointing at this block's questions still means
     something; it just means somewhere else now. Replace rather than assign,
     so Back goes where the reader came from instead of bouncing off a redirect.

     Checked on load AND on hashchange, because #questions arriving from a link
     on the page is a same-document navigation: nothing reloads, init never
     runs again, and a load-time check alone would sit there doing nothing. */
  function leftForQbank() {
    if ((window.location.hash || "") !== "#questions") return false;
    window.location.replace(qbankUrl());
    return true;
  }

  function byId(id) { return document.getElementById(id); }

  /* Notes come first when there are any - they are what you read before you
     test yourself. A block with none of them written yet would otherwise open
     on a page of nothing but gaps, so it falls through to the questions. */
  function fallback() {
    var tc = byId("tc-notes");
    var written = tc ? parseInt(tc.textContent, 10) : 0;
    /* Notes first where any are written - they are what you read before you
       test yourself. A block with none of them falls through to Anki rather
       than to questions, which are no longer on this page at all. */
    return written > 0 ? "notes" : "anki";
  }

  function wanted() {
    var h = (window.location.hash || "").replace("#", "");
    return TABS[h] ? h : fallback();
  }

  /* How many of this block's questions have been answered, read straight out
     of the store. The bank itself is 44 to 269 KB and lives on another page;
     the answer to "how far in am I" is already here, in a record per question
     carrying its own status, so it costs one localStorage read and no fetch. */
  function answeredHere() {
    var raw = null;
    try { raw = window.localStorage.getItem((BLOCK.store || "nsq.v1.") + BLOCK.slug); }
    catch (e) { return 0; }
    if (!raw) return 0;
    var parsed;
    try { parsed = JSON.parse(raw); }
    catch (e) { return 0; }
    if (!parsed || typeof parsed !== "object") return 0;
    var n = 0;
    Object.keys(parsed).forEach(function (qid) {
      var r = parsed[qid];
      if (r && (r.status === "correct" || r.status === "wrong")) n++;
    });
    return n;
  }

  function paintDone() {
    var el = byId("qb-done"), n = answeredHere();
    if (!el) return;
    el.hidden = n === 0;
    el.textContent = n + " done";
  }

  function show(key) {
    /* the stylesheet reads this: the questions tab is a working view and drops
       the block's blurb from the masthead, where the notes tab keeps it */
    document.body.dataset.tab = key;
    Object.keys(TABS).forEach(function (k) {
      var t = TABS[k], on = k === key;
      byId(t.tab).setAttribute("aria-selected", on ? "true" : "false");
      byId(t.panel).hidden = !on;
      if (t.board) byId(t.board).hidden = !on;
    });
    if (!TABS[key].board) {
      Object.keys(TABS).forEach(function (k) {
        if (TABS[k].board) byId(TABS[k].board).hidden = true;
      });
    }
    TABS[key].boot();
  }

  function init() {
    /* The question bank has one panel and therefore no tab strip. It says its
       own eyebrow in QUIZ_BLOCK, because "Block 3 · Weeks 7–11" is not a true
       thing to say about a page that is every block at once. */
    if (BLOCK.blocks && BLOCK.blocks.length) {
      byId("m-eyebrow").textContent =
        "Schulich " + (BLOCK.course || "PoM 2") + " · " +
        (BLOCK.eyebrow || "Every block");
      /* not "questions": that value hides the masthead blurb, which the block
         pages can afford because their notes tab carries it and this page,
         having no other tab, cannot */
      document.body.dataset.tab = "qbank";
      if (window.POM2_QUIZ) window.POM2_QUIZ.boot();
      return;
    }

    /* quiz.js used to write this, but it only runs once questions are booted -
       landing on the notes tab would have left the masthead blank */
    byId("m-eyebrow").textContent =
      "Schulich " + (BLOCK.course || "PoM 2") + " · Block " + BLOCK.n +
      " · Weeks " + BLOCK.weeks;

    if (leftForQbank()) return;

    Object.keys(TABS).forEach(function (k) {
      byId(TABS[k].tab).addEventListener("click", function () {
        if (wanted() === k) { show(k); return; }
        window.location.hash = k;   // hashchange does the rest, and history keeps it
      });
    });

    paintDone();
    window.addEventListener("hashchange", function () {
      if (leftForQbank()) return;
      show(wanted());
    });
    show(wanted());
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
