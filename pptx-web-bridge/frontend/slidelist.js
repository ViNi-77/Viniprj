/**
 * スライド一覧。サムネイル（サーバ描画の断片を縮小表示）、題名の直接編集、ドラッグ＆ドロップの並べ替え、↑↓⧉✕。
 * サムネイルの HTML はスライド ID をキーに保持し、並べ替えでも再取得しない。
 */
window.PWB = window.PWB || {};
PWB.slidelist = (function () {
  "use strict";
  var list = null;
  var thumbs = {}; // slide id → html 断片
  var THUMB_MAX = 132, THUMB_MIN = 64;
  var lastThumbW = 0;
  function thumbWidth() {
    // 一覧の幅の 35% を目安に、64〜132px の間で決める（狭いペインでも題名の欄が残る）
    var w = list ? list.clientWidth : 0;
    return w ? Math.max(THUMB_MIN, Math.min(THUMB_MAX, Math.round(w * 0.35))) : THUMB_MAX;
  }
  var core = function () { return PWB.core; };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };

  function init(el) {
    list = el;
    if (typeof ResizeObserver === "function") {
      new ResizeObserver(function () { if (list && core().state.presentation && Math.abs(thumbWidth() - lastThumbW) >= 8) render(); }).observe(list);
    }
    list.addEventListener("dragstart", function (e) {
      var li = e.target.closest(".slide-item");
      if (!li || e.target.tagName === "INPUT") { e.preventDefault(); return; }
      e.dataTransfer.setData("text/plain", li.getAttribute("data-slide"));
      e.dataTransfer.effectAllowed = "move";
      li.classList.add("dragging");
    });
    list.addEventListener("dragend", function (e) { var li = e.target.closest(".slide-item"); if (li) li.classList.remove("dragging"); list.querySelectorAll(".drop-before, .drop-after").forEach(function (x) { x.classList.remove("drop-before", "drop-after"); }); });
    list.addEventListener("dragover", function (e) {
      var li = e.target.closest(".slide-item");
      if (!li) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      var r = li.getBoundingClientRect();
      var after = e.clientY > r.top + r.height / 2;
      list.querySelectorAll(".drop-before, .drop-after").forEach(function (x) { x.classList.remove("drop-before", "drop-after"); });
      li.classList.add(after ? "drop-after" : "drop-before");
    });
    list.addEventListener("drop", function (e) {
      var li = e.target.closest(".slide-item");
      if (!li) return;
      e.preventDefault();
      var from = parseInt(e.dataTransfer.getData("text/plain"), 10);
      var to = parseInt(li.getAttribute("data-slide"), 10);
      var r = li.getBoundingClientRect();
      if (e.clientY > r.top + r.height / 2) to += 1;
      if (!isNaN(from) && !isNaN(to)) core().moveSlide(from, to);
    });
  }

  function slideTitle(s) {
    if (s.title) return s.title;
    var els = s.elements || [];
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (el.type === "text" || el.type === "shape") {
        var t = (el.paragraphs || []).map(function (p) { return (p.runs || []).map(function (r) { return r.text; }).join(""); }).join("\n").trim();
        if (t) return t.split("\n")[0].slice(0, 40);
      }
    }
    return "スライド " + (s.index + 1);
  }

  function render() {
    if (!list) return;
    var st = core().state;
    list.innerHTML = "";
    if (!st.presentation) return;
    var pres = st.presentation;
    var cw = pres.canvas.width_pt, ch = pres.canvas.height_pt;
    var THUMB_W = thumbWidth();
    lastThumbW = THUMB_W;
    var scale = THUMB_W / cw;
    pres.slides.forEach(function (s, i) {
      var li = document.createElement("li");
      li.className = "slide-item" + (i === st.selectedSlide ? " selected" : "");
      li.setAttribute("data-slide", i);
      li.setAttribute("draggable", "true");
      var warnCount = (s.warnings || []).length;
      var thumb = thumbs[s.id];
      li.innerHTML = '<span class="num">' + (i + 1) + "</span>" +
        '<div class="thumb" style="width:' + THUMB_W + "px;height:" + Math.round(ch * scale) + 'px"><div class="thumb-inner" style="transform:scale(' + scale + ")\">" + (thumb || "") + "</div></div>" +
        '<div class="slide-main"><input class="title-input" type="text" data-slide-title="' + i + '" value="' + esc(slideTitle(s)) + '" title="スライド題名">' +
        '<div class="meta">' + esc(s.layout || "") + " / 要素 " + (s.elements || []).length + (s.continuation_of ? ' / <span class="pill">続き</span>' : "") + (warnCount ? ' / <span class="warn">警告 ' + warnCount + "</span>" : "") + "</div></div>" +
        '<div class="col"><button class="small secondary" data-slide-act="up" data-slide="' + i + '" title="上へ">↑</button><button class="small secondary" data-slide-act="down" data-slide="' + i + '" title="下へ">↓</button><button class="small secondary" data-slide-act="dup" data-slide="' + i + '" title="複製">⧉</button><button class="small secondary" data-slide-act="del" data-slide="' + i + '" title="削除">✕</button></div>';
      list.appendChild(li);
    });
    var sel = list.querySelector(".slide-item.selected");
    if (sel && sel.scrollIntoView) sel.scrollIntoView({ block: "nearest" });
  }

  /** サムネイルの断片を差し替える（描画 API の結果から）。 */
  function setThumb(slideId, html) {
    thumbs[slideId] = html;
    if (!list) return;
    var st = core().state;
    var idx = -1;
    st.presentation.slides.forEach(function (s, i) { if (s.id === slideId) idx = i; });
    var inner = idx >= 0 ? list.querySelector('.slide-item[data-slide="' + idx + '"] .thumb-inner') : null;
    if (inner) inner.innerHTML = html;
  }
  function clearThumbs() { thumbs = {}; }
  function hasThumb(slideId) { return !!thumbs[slideId]; }

  return { init: init, render: render, setThumb: setThumb, clearThumbs: clearThumbs, hasThumb: hasThumb, slideTitle: slideTitle };
})();
