/* Web図解ビューア。ページ送り・目次・全画面・縦読み切替・ノート表示。外部依存なし。 */
(function () {
  "use strict";
  var body = document.body;
  var stage = document.querySelector(".stage");
  var wraps = Array.prototype.slice.call(document.querySelectorAll(".slide-wrap"));
  var tocItems = Array.prototype.slice.call(document.querySelectorAll(".toc li"));
  var counter = document.querySelector(".counter");
  var canvasW = parseFloat(body.getAttribute("data-canvas-w")) || 960;
  var canvasH = parseFloat(body.getAttribute("data-canvas-h")) || 540;
  var breakpoint = parseFloat(body.getAttribute("data-flow-breakpoint")) || 720;
  var current = 0;
  var userMode = null; // null = 自動 / "slide" / "flow"

  function readHash() {
    var m = /^#s(\d+)$/.exec(location.hash);
    if (m) { var n = parseInt(m[1], 10) - 1; if (n >= 0 && n < wraps.length) current = n; }
  }

  function isFlow() {
    if (userMode) return userMode === "flow";
    return window.innerWidth < breakpoint;
  }

  function applyMode() {
    var flow = isFlow();
    body.classList.toggle("flow-mode", flow);
    body.classList.toggle("slide-mode", !flow);
    var btn = document.getElementById("btn-mode");
    if (btn) btn.textContent = flow ? "スライド表示" : "縦読み表示";
    fit();
  }

  function fit() {
    if (body.classList.contains("flow-mode")) {
      wraps.forEach(function (w) { w.style.width = ""; w.style.height = ""; var s = w.querySelector(".slide"); if (s) s.style.transform = ""; });
      return;
    }
    var availW = stage.clientWidth - 32;
    var availH = stage.clientHeight - 32;
    var scale = Math.min(availW / canvasW, availH / canvasH);
    if (!isFinite(scale) || scale <= 0) scale = 1;
    wraps.forEach(function (w) {
      var s = w.querySelector(".slide");
      s.style.transform = "scale(" + scale + ")";
      w.style.width = (canvasW * scale) + "px";
      w.style.height = (canvasH * scale) + "px";
    });
  }

  function show(n, updateHash) {
    if (n < 0) n = 0;
    if (n >= wraps.length) n = wraps.length - 1;
    current = n;
    wraps.forEach(function (w, i) { w.classList.toggle("current", i === n); });
    tocItems.forEach(function (li, i) { li.classList.toggle("active", i === n); });
    if (counter) counter.textContent = (n + 1) + " / " + wraps.length;
    if (updateHash !== false) { try { history.replaceState(null, "", "#s" + (n + 1)); } catch (e) { /* file:// では失敗しても無視 */ } }
    if (body.classList.contains("flow-mode")) { var w = wraps[n]; if (w) w.scrollIntoView({ behavior: "smooth", block: "start" }); }
  }

  function bind(id, fn) { var el = document.getElementById(id); if (el) el.addEventListener("click", fn); }
  bind("btn-prev", function () { show(current - 1); });
  bind("btn-next", function () { show(current + 1); });
  bind("btn-toc", function () { var t = document.querySelector(".toc"); if (t) t.classList.toggle("hidden"); fit(); });
  bind("btn-full", function () {
    var el = document.documentElement;
    if (document.fullscreenElement) { document.exitFullscreen(); }
    else if (el.requestFullscreen) { el.requestFullscreen(); }
  });
  bind("btn-mode", function () { userMode = isFlow() ? "slide" : "flow"; applyMode(); show(current); });
  bind("btn-notes", function () { body.classList.toggle("show-notes"); fit(); });
  bind("btn-print", function () { window.print(); });
  tocItems.forEach(function (li, i) { li.addEventListener("click", function () { show(i); }); });

  document.addEventListener("keydown", function (e) {
    if (e.target && /input|textarea/i.test(e.target.tagName)) return;
    switch (e.key) {
      case "ArrowRight": case "PageDown": case " ": show(current + 1); e.preventDefault(); break;
      case "ArrowLeft": case "PageUp": show(current - 1); e.preventDefault(); break;
      case "Home": show(0); break;
      case "End": show(wraps.length - 1); break;
      case "f": case "F": var b = document.getElementById("btn-full"); if (b) b.click(); break;
      case "n": case "N": body.classList.toggle("show-notes"); break;
    }
  });
  window.addEventListener("resize", function () { applyMode(); });
  window.addEventListener("hashchange", function () { readHash(); show(current, false); });
  document.addEventListener("fullscreenchange", fit);

  readHash();
  applyMode();
  show(current, false);
})();
