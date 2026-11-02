// Swan dashboard: every minute fetch the page again and swap the changed blocks of <main> in place (no page reload,
// so scroll, selection, hover and open sections survive). Sections you opened stay open across visits (this browser only).
// Falls back to location.reload() when fetch is unavailable or after MAXFAIL failed refreshes in a row.
(function () {
  var KEY = "swan-open", EVERY = 60000, MAXFAIL = 2, TIMEOUT = 30000;
  var open = {};
  try { open = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { open = {}; }
  if (typeof open !== "object") open = {};

  function has(k) { return Object.prototype.hasOwnProperty.call(open, k); }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(open)); } catch (e) {} }
  function list(nodes) { return Array.prototype.slice.call(nodes); }
  function kids(el) { return list(el.children); }
  function summaryText(d) { var s = d.querySelector("summary"); return s ? s.textContent : ""; }

  // 'toggle' does not bubble, so listen in the capture phase on document: swapped-in nodes need no re-binding.
  document.addEventListener("toggle", function (e) {
    var d = e.target;
    if (d && d.tagName === "DETAILS" && d.id) { open[d.id] = d.open; save(); }
  }, true);

  list(document.querySelectorAll("details[id]")).forEach(function (d) { if (has(d.id)) d.open = open[d.id]; });

  // Every <details> in root, root itself included: querySelectorAll skips the root, and most sections ARE a top-level
  // block (Activity, Bot, Score & targets, Blue...), so without this they were reset to the server's closed default.
  function allDetails(root) {
    var a = list(root.querySelectorAll("details"));
    if (root.tagName === "DETAILS") a.unshift(root);
    return a;
  }

  // Copy the open/closed state of the <details> in oldRoot onto the matching ones in newRoot (by id; ones without an id
  // by position and summary text), else the remembered state for that id, else leave the new markup's default.
  function carry(oldRoot, newRoot) {
    var olds = allDetails(oldRoot), news = allDetails(newRoot), byId = {};
    olds.forEach(function (d) { if (d.id) byId[d.id] = d; });
    news.forEach(function (d, i) {
      var o = null, st;
      if (d.id) o = byId[d.id] || null;
      else if (olds.length === news.length && !olds[i].id && summaryText(olds[i]) === summaryText(d)) o = olds[i];
      if (o) st = o.open; else if (d.id && has(d.id)) st = open[d.id]; else return;
      if (d.open !== st) d.open = st;
    });
  }

  function selectionIn(node) {
    var s = window.getSelection ? window.getSelection() : null;
    if (!s || s.isCollapsed || !s.rangeCount) return false;
    var r = s.getRangeAt(0);
    try { return r.intersectsNode(node); } catch (e) { return node.contains(r.startContainer) || node.contains(r.endContainer); }
  }

  // Which <details> in `block` has keyboard focus on its <summary> (index), so focus can follow to the new copy.
  function focusedDetails(block) {
    var a = document.activeElement;
    if (!a || a.tagName !== "SUMMARY" || !block.contains(a)) return -1;
    return allDetails(block).indexOf(a.parentNode);
  }
  function refocus(block, idx) {
    if (idx < 0) return;
    var d = allDetails(block)[idx], s = d && d.querySelector("summary");
    try { if (s) s.focus({ preventScroll: true }); } catch (e) {}
  }

  var prev = null;       // outerHTML of each top-level block of <main> as last applied from the server

  // Apply fetched page text. Returns true if handled (including "nothing to do"), false if the page looks wrong.
  function apply(html) {
    var doc = new DOMParser().parseFromString(html, "text/html");
    var nm = doc.querySelector("main"), main = document.querySelector("main");
    if (!nm || !main) return false;
    if (doc.title) document.title = doc.title;
    var nk = kids(nm), ok = kids(main), src = nk.map(function (n) { return n.outerHTML; });
    if (prev && prev.length === src.length && prev.every(function (s, i) { return s === src[i]; })) return true;   // identical

    var x = window.pageXOffset, y = window.pageYOffset;
    if (nk.length === ok.length) {                         // normal case: swap only the blocks that changed
      var next = [];
      nk.forEach(function (n, i) {
        if (prev && prev[i] === src[i]) { next[i] = src[i]; return; }
        if (selectionIn(ok[i])) { next[i] = prev ? prev[i] : undefined; return; }   // leave it; try again next minute
        var f = focusedDetails(ok[i]), copy = document.importNode(n, true);
        carry(ok[i], copy);
        main.replaceChild(copy, ok[i]);
        refocus(copy, f);
        next[i] = src[i];
      });
      prev = next;
    } else {                                               // layout changed (blocks added or removed): swap everything
      if (selectionIn(main)) return true;
      var frag = document.createDocumentFragment();
      list(nm.childNodes).forEach(function (n) { frag.appendChild(document.importNode(n, true)); });
      carry(main, frag);
      while (main.firstChild) main.removeChild(main.firstChild);
      main.appendChild(frag);
      prev = src;
    }
    if (y > 0 && window.pageYOffset === 0) window.scrollTo(x, y);   // browsers normally keep it; this undoes a reset to top
    return true;
  }

  return;   // frozen final page (2 Nov): nothing to refresh, so keep only the open-sections memory above

  if (!window.fetch || !window.DOMParser || !window.Promise) {      // very old browser: the old behaviour
    setTimeout(function () { location.reload(); }, EVERY);
    return;
  }

  var timer = null, busy = false, fails = 0, last = Date.now();
  function schedule(ms) {
    if (timer) clearTimeout(timer);
    timer = document.hidden ? null : setTimeout(load, ms);
  }
  function load() {
    if (timer) clearTimeout(timer);
    timer = null;
    if (busy || document.hidden) return;
    busy = true;
    var ctl = window.AbortController ? new AbortController() : null;
    var guard = ctl ? setTimeout(function () { ctl.abort(); }, TIMEOUT) : null;
    var opts = { cache: "no-store", credentials: "same-origin" };
    if (ctl) opts.signal = ctl.signal;
    fetch(location.href, opts).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.text();
    }).then(function (t) {
      if (!apply(t)) throw new Error("no <main>");
      fails = 0;
      last = Date.now();
    }).catch(function () {
      if (++fails >= MAXFAIL) location.reload();                   // keep the old page until then
    }).then(function () {
      if (guard) clearTimeout(guard);
      busy = false;
      schedule(EVERY);
    });
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) { if (timer) { clearTimeout(timer); timer = null; } return; }
    var age = Date.now() - last;
    if (age >= EVERY) load(); else schedule(EVERY - age);
  });
  schedule(EVERY);
})();
