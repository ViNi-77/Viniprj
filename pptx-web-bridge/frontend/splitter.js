/**
 * 3 ペインの境界をドラッグして幅を変える。幅は CSS 変数 --col-left / --col-center に入れ、localStorage に保持する。
 */
window.PWB = window.PWB || {};
PWB.splitter = (function () {
  "use strict";
  var KEY = "pptx_web_bridge.panes";
  var MIN = 220;

  function apply(widths) {
    var root = document.documentElement;
    if (widths.left) root.style.setProperty("--col-left", widths.left + "px");
    if (widths.center) root.style.setProperty("--col-center", widths.center + "px");
  }
  function load() { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; } }
  function save(widths) { try { localStorage.setItem(KEY, JSON.stringify(widths)); } catch (e) { /* 無視 */ } }

  function init() {
    var widths = load();
    apply(widths);
    document.querySelectorAll(".splitter").forEach(function (bar) {
      var which = bar.getAttribute("data-splitter"); // "left" | "center"
      bar.addEventListener("pointerdown", function (e) {
        e.preventDefault();
        bar.setPointerCapture(e.pointerId);
        var pane = document.querySelector(which === "left" ? ".pane-left" : ".pane-center");
        var startX = e.clientX;
        var startW = pane.getBoundingClientRect().width;
        var maxW = window.innerWidth - MIN * 2;
        function move(ev) {
          var w = Math.max(MIN, Math.min(maxW, startW + (ev.clientX - startX)));
          widths[which] = Math.round(w);
          apply(widths);
          window.dispatchEvent(new Event("resize"));
        }
        function up(ev) {
          bar.removeEventListener("pointermove", move);
          bar.removeEventListener("pointerup", up);
          bar.removeEventListener("pointercancel", up);
          try { bar.releasePointerCapture(ev.pointerId); } catch (err) { /* 無視 */ }
          save(widths);
        }
        bar.addEventListener("pointermove", move);
        bar.addEventListener("pointerup", up);
        bar.addEventListener("pointercancel", up);
      });
      bar.addEventListener("dblclick", function () { delete widths[which]; document.documentElement.style.removeProperty("--col-" + which); save(widths); window.dispatchEvent(new Event("resize")); });
    });
  }
  return { init: init };
})();
