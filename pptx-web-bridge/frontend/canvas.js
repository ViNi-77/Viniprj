/**
 * 編集キャンバス。サーバが描いたスライド断片（web_renderer.slide_html）を同一オリジンの div に注入し、
 * その上に選択枠・ハンドルを重ねてドラッグ／リサイズする。
 *
 * - 座標系: .slide の内側は 1pt = 1px。画面上は transform: scale(s) で拡縮するため、ポインタ座標は /s で pt に戻す。
 * - ドラッグ中は DOM の style だけを動かし（楽観更新）、確定時に adapter.commit() へ枠を渡す。
 * - スナップ: 余白線・中央線・他要素の辺と中心・4pt グリッド。Alt で無効。Shift はリサイズ時に縦横比を保つ。
 * - 「何を動かすか」はアダプタで差し替える。既定はスライドの要素（PWB.core の状態）、テンプレート作成画面では部品の枠。
 *   PWB.canvas         … 既定インスタンス（init / mount / setSelection …）
 *   PWB.canvas.create  … 別のアダプタで新しいインスタンスを作る
 */
window.PWB = window.PWB || {};
PWB.canvas = (function () {
  "use strict";
  var HANDLE_DIRS = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
  var MIN_SIZE = 8;
  var instanceSeq = 0;

  function core() { return PWB.core; }
  function cssEscape(s) { return String(s).replace(/["'\\]/g, "\\$&"); }
  function round1(v) { return Math.round(v * 10) / 10; }

  /** 既定アダプタ: 選択中スライドの要素を動かす。 */
  var slideAdapter = {
    items: function () { var st = core().state; var s = st.presentation && st.presentation.slides[st.selectedSlide]; return s ? s.elements : []; },
    snapshot: function () { return JSON.stringify(core().state.presentation); },
    commit: function (boxes, before, opts) {
      var st = core().state, s = st.presentation && st.presentation.slides[st.selectedSlide];
      if (!s) return;
      var ids = [];
      Object.keys(boxes).forEach(function (id) {
        for (var i = 0; i < s.elements.length; i++) {
          if (s.elements[i].id !== id) continue;
          var b = boxes[id];
          s.elements[i].bbox = { x: round1(b.x), y: round1(b.y), w: round1(Math.max(MIN_SIZE, b.w)), h: round1(Math.max(MIN_SIZE, b.h)) };
          s.elements[i].user_bbox = true;
          ids.push(id);
        }
      });
      core().changed({ index: st.selectedSlide, before: JSON.parse(before), elementIds: ids, coalesce: opts && opts.coalesce });
    },
    onSelectionChanged: function (ids) { core().onSelectionChanged(ids); },
    onDoubleClick: function (id) { core().focusInspector(id); },
    onDelete: function (ids) { core().deleteElements(ids); },
    onDuplicate: function (ids) { core().duplicateElements(ids); },
    onReorder: function (ids, dir) { core().reorderZ(ids, dir); },
    margin: function () { var c = core().state.config; return (c && c.layout && c.layout.margin_pt) || 36; },
    isActive: function () { return !document.querySelector(".modal:not([hidden])"); },
    showAll: false
  };

  function createCanvas(adapter) {
    var area = null, stage = null, overlay = null, guides = null, styleEl = null;
    var canvasW = 960, canvasH = 540, scale = 1;
    var selection = [];
    var drag = null;
    var uniq = "cs-" + (++instanceSeq);

    function items() { return adapter.items() || []; }
    function itemById(id) { var list = items(); for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i]; return null; }
    function margin() { return adapter.margin ? adapter.margin() : 36; }

    // ---------------------------------------------------------------- 描画
    function init(areaEl) {
      area = areaEl;
      stage = document.createElement("div");
      stage.className = "canvas-stage " + uniq;
      overlay = document.createElement("div");
      overlay.className = "sel-overlay";
      guides = document.createElement("div");
      guides.className = "snap-guides";
      styleEl = document.createElement("style");
      document.head.appendChild(styleEl);
      area.innerHTML = "";
      area.appendChild(stage);
      stage.appendChild(overlay);
      stage.appendChild(guides);
      stage.addEventListener("pointerdown", onPointerDown);
      stage.addEventListener("dblclick", function (e) { var el = e.target.closest(".el"); if (el && el.id && itemById(el.id) && adapter.onDoubleClick) adapter.onDoubleClick(el.id); });
      window.addEventListener("resize", fit);
      document.addEventListener("keydown", onKey);
      if (adapter === slideAdapter) { stage.id = "canvas-stage"; overlay.id = "sel-overlay"; guides.id = "snap-guides"; styleEl.id = "theme-css"; }
    }

    /** サーバの断片を差し込む。themeCss は :root{...} をこのステージ限定に書き換えて適用する。 */
    function mount(html, w, h, themeCss) {
      canvasW = w || canvasW; canvasH = h || canvasH;
      if (themeCss) styleEl.textContent = themeCss.replace(/:root\s*\{/, ".canvas-stage." + uniq + "{");
      var old = stage.querySelector(".slide-wrap");
      if (old) old.remove();
      var tmp = document.createElement("div");
      tmp.innerHTML = html || "";
      var wrap = tmp.querySelector(".slide-wrap");
      if (wrap) stage.insertBefore(wrap, overlay);
      fit();
      renderSelection();
    }
    function clear() { var old = stage.querySelector(".slide-wrap"); if (old) old.remove(); selection = []; renderSelection(); }

    function fit() {
      if (!area) return;
      var availW = Math.max(100, area.clientWidth - 32);
      var availH = Math.max(100, area.clientHeight - 32);
      scale = Math.min(availW / canvasW, availH / canvasH);
      if (!isFinite(scale) || scale <= 0) scale = 1;
      var wrap = stage.querySelector(".slide-wrap");
      var slide = stage.querySelector(".slide");
      stage.style.width = (canvasW * scale) + "px";
      stage.style.height = (canvasH * scale) + "px";
      if (wrap) { wrap.style.width = (canvasW * scale) + "px"; wrap.style.height = (canvasH * scale) + "px"; wrap.style.margin = "0"; }
      if (slide) slide.style.transform = "scale(" + scale + ")";
      renderSelection();
    }

    function renderSelection() {
      if (!overlay) return;
      overlay.innerHTML = "";
      var list = items();
      selection = selection.filter(function (id) { return itemById(id); });
      if (adapter.showAll) {
        list.forEach(function (it) {
          if (!it.bbox || selection.indexOf(it.id) >= 0) return;
          var box = document.createElement("div");
          box.className = "sel-box all";
          box.setAttribute("data-el", it.id);
          placeBox(box, it.bbox);
          if (adapter.labelOf) { var tag = document.createElement("div"); tag.className = "sel-tag"; tag.textContent = adapter.labelOf(it); box.appendChild(tag); }
          overlay.appendChild(box);
        });
      }
      selection.forEach(function (id) {
        var it = itemById(id);
        if (!it || !it.bbox) return;
        var box = document.createElement("div");
        box.className = "sel-box" + (selection.length === 1 ? " primary" : "");
        box.setAttribute("data-el", id);
        placeBox(box, it.bbox);
        if (selection.length === 1) {
          HANDLE_DIRS.forEach(function (d) { var hd = document.createElement("div"); hd.className = "sel-handle h-" + d; hd.setAttribute("data-dir", d); box.appendChild(hd); });
          var label = document.createElement("div");
          label.className = "sel-label";
          label.textContent = labelFor(it.bbox);
          box.appendChild(label);
        }
        if (adapter.labelOf) { var tag = document.createElement("div"); tag.className = "sel-tag"; tag.textContent = adapter.labelOf(it); box.appendChild(tag); }
        overlay.appendChild(box);
      });
      if (adapter.onSelectionChanged) adapter.onSelectionChanged(selection.slice());
    }
    function placeBox(box, b) { box.style.left = (b.x * scale) + "px"; box.style.top = (b.y * scale) + "px"; box.style.width = (b.w * scale) + "px"; box.style.height = (b.h * scale) + "px"; }
    function labelFor(b) { return "x " + Math.round(b.x) + "  y " + Math.round(b.y) + "   " + Math.round(b.w) + " × " + Math.round(b.h) + " pt"; }

    function setSelection(ids) { selection = (ids || []).slice(); renderSelection(); }
    function getSelection() { return selection.slice(); }

    // ---------------------------------------------------------------- ポインタ操作
    function toSlide(e) {
      var slide = stage.querySelector(".slide");
      var r = slide ? slide.getBoundingClientRect() : stage.getBoundingClientRect();
      return { x: (e.clientX - r.left) / scale, y: (e.clientY - r.top) / scale };
    }

    function onPointerDown(e) {
      if (e.button !== 0) return;
      var handle = e.target.closest(".sel-handle");
      var box = e.target.closest(".sel-box");
      var elDom = e.target.closest(".el");
      var id = handle ? handle.parentNode.getAttribute("data-el") : (box ? box.getAttribute("data-el") : (elDom && elDom.id));
      if (id && !itemById(id)) id = null;
      if (!id) { if (!e.shiftKey) setSelection([]); return; }
      if (!handle) {
        if (e.shiftKey) { if (selection.indexOf(id) < 0) selection.push(id); else selection.splice(selection.indexOf(id), 1); }
        else if (selection.indexOf(id) < 0) selection = [id];
        renderSelection();
      }
      if (!selection.length) return;
      e.preventDefault();
      stage.setPointerCapture(e.pointerId);
      var p = toSlide(e);
      drag = {
        mode: handle ? "resize" : "move",
        dir: handle ? handle.getAttribute("data-dir") : null,
        start: p,
        ids: handle ? [id] : selection.slice(),
        orig: {},
        moved: false,
        before: adapter.snapshot ? adapter.snapshot() : null
      };
      drag.ids.forEach(function (i) { var it = itemById(i); if (it && it.bbox) drag.orig[i] = { x: it.bbox.x, y: it.bbox.y, w: it.bbox.w, h: it.bbox.h }; });
      stage.addEventListener("pointermove", onPointerMove);
      stage.addEventListener("pointerup", onPointerUp);
      stage.addEventListener("pointercancel", onPointerUp);
    }

    function onPointerMove(e) {
      if (!drag) return;
      var p = toSlide(e);
      var dx = p.x - drag.start.x, dy = p.y - drag.start.y;
      if (!drag.moved && Math.abs(dx) * scale < 3 && Math.abs(dy) * scale < 3) return;
      drag.moved = true;
      var snapOn = !e.altKey;
      var boxes = {};
      if (drag.mode === "move") {
        var lead = drag.orig[drag.ids[0]];
        var nx = lead.x + dx, ny = lead.y + dy;
        if (snapOn) { var sn = snapMove(nx, ny, lead.w, lead.h, drag.ids); nx = sn.x; ny = sn.y; showGuides(sn.guides); }
        var ddx = nx - lead.x, ddy = ny - lead.y;
        drag.ids.forEach(function (i) { var o = drag.orig[i]; if (o) boxes[i] = { x: o.x + ddx, y: o.y + ddy, w: o.w, h: o.h }; });
      } else {
        var o = drag.orig[drag.ids[0]];
        boxes[drag.ids[0]] = resizeBox(o, drag.dir, dx, dy, e.shiftKey, snapOn, drag.ids[0]);
      }
      drag.live = boxes;
      Object.keys(boxes).forEach(function (i) { applyLive(i, boxes[i]); });
    }

    function onPointerUp(e) {
      stage.removeEventListener("pointermove", onPointerMove);
      stage.removeEventListener("pointerup", onPointerUp);
      stage.removeEventListener("pointercancel", onPointerUp);
      try { stage.releasePointerCapture(e.pointerId); } catch (err) { /* 無視 */ }
      hideGuides();
      var d = drag; drag = null;
      if (!d || !d.moved || !d.live) return;
      var boxes = {};
      Object.keys(d.live).forEach(function (i) { var b = d.live[i]; boxes[i] = { x: round1(b.x), y: round1(b.y), w: round1(Math.max(MIN_SIZE, b.w)), h: round1(Math.max(MIN_SIZE, b.h)) }; });
      adapter.commit(boxes, d.before, {});
    }

    function applyLive(id, b) {
      var dom = stage.querySelector(".el[id='" + cssEscape(id) + "']");
      if (dom) { dom.style.left = b.x + "px"; dom.style.top = b.y + "px"; dom.style.width = b.w + "px"; dom.style.height = b.h + "px"; }
      var box = overlay.querySelector(".sel-box[data-el='" + cssEscape(id) + "']");
      if (box) { placeBox(box, b); var lb = box.querySelector(".sel-label"); if (lb) lb.textContent = labelFor(b); }
    }

    function resizeBox(o, dir, dx, dy, keepAspect, snapOn, id) {
      var x = o.x, y = o.y, w = o.w, h = o.h;
      if (dir.indexOf("e") >= 0) w = o.w + dx;
      if (dir.indexOf("s") >= 0) h = o.h + dy;
      if (dir.indexOf("w") >= 0) { x = o.x + dx; w = o.w - dx; }
      if (dir.indexOf("n") >= 0) { y = o.y + dy; h = o.h - dy; }
      if (keepAspect && o.w > 0 && o.h > 0 && dir.length === 2) {
        var ratio = o.w / o.h;
        if (Math.abs(w / ratio - h) < Math.abs(h * ratio - w)) h = w / ratio; else w = h * ratio;
        if (dir.indexOf("w") >= 0) x = o.x + o.w - w;
        if (dir.indexOf("n") >= 0) y = o.y + o.h - h;
      }
      if (w < MIN_SIZE) { if (dir.indexOf("w") >= 0) x = o.x + o.w - MIN_SIZE; w = MIN_SIZE; }
      if (h < MIN_SIZE) { if (dir.indexOf("n") >= 0) y = o.y + o.h - MIN_SIZE; h = MIN_SIZE; }
      if (snapOn) {
        var g = guideLines([id]);
        var t = 6 / scale;
        var right = x + w, bottom = y + h, gl = [];
        if (dir.indexOf("e") >= 0) { var s1 = nearest(right, g.v, t); if (s1 !== null) { w = s1 - x; gl.push({ v: s1 }); } }
        if (dir.indexOf("w") >= 0) { var s2 = nearest(x, g.v, t); if (s2 !== null) { w = right - s2; x = s2; gl.push({ v: s2 }); } }
        if (dir.indexOf("s") >= 0) { var s3 = nearest(bottom, g.h, t); if (s3 !== null) { h = s3 - y; gl.push({ h: s3 }); } }
        if (dir.indexOf("n") >= 0) { var s4 = nearest(y, g.h, t); if (s4 !== null) { h = bottom - s4; y = s4; gl.push({ h: s4 }); } }
        showGuides(gl);
      }
      return { x: x, y: y, w: w, h: h };
    }

    // ---------------------------------------------------------------- スナップ
    function guideLines(excludeIds) {
      var m = margin();
      var v = [m, canvasW - m, canvasW / 2], h = [m, canvasH - m, canvasH / 2];
      items().forEach(function (it) {
        if (!it.bbox || excludeIds.indexOf(it.id) >= 0) return;
        v.push(it.bbox.x, it.bbox.x + it.bbox.w, it.bbox.x + it.bbox.w / 2);
        h.push(it.bbox.y, it.bbox.y + it.bbox.h, it.bbox.y + it.bbox.h / 2);
      });
      return { v: v, h: h };
    }
    function nearest(value, lines, t) {
      var best = null, bd = t;
      lines.forEach(function (l) { var d = Math.abs(l - value); if (d <= bd) { bd = d; best = l; } });
      return best;
    }
    function snapMove(x, y, w, h, ids) {
      var g = guideLines(ids);
      var t = 6 / scale;
      var res = { x: x, y: y, guides: [] };
      var cands = [[x, 0], [x + w, w], [x + w / 2, w / 2]];
      for (var i = 0; i < cands.length; i++) { var s = nearest(cands[i][0], g.v, t); if (s !== null) { res.x = s - cands[i][1]; res.guides.push({ v: s }); break; } }
      var candh = [[y, 0], [y + h, h], [y + h / 2, h / 2]];
      for (var j = 0; j < candh.length; j++) { var sh = nearest(candh[j][0], g.h, t); if (sh !== null) { res.y = sh - candh[j][1]; res.guides.push({ h: sh }); break; } }
      if (!res.guides.length) { res.x = Math.round(res.x / 4) * 4; res.y = Math.round(res.y / 4) * 4; }
      return res;
    }
    function showGuides(list) {
      guides.innerHTML = "";
      (list || []).forEach(function (g) {
        var d = document.createElement("div");
        if (g.v !== undefined) { d.className = "snap-line v"; d.style.left = (g.v * scale) + "px"; }
        else { d.className = "snap-line h"; d.style.top = (g.h * scale) + "px"; }
        guides.appendChild(d);
      });
    }
    function hideGuides() { guides.innerHTML = ""; }

    // ---------------------------------------------------------------- キーボード
    function onKey(e) {
      if (e.target && /input|textarea|select/i.test(e.target.tagName)) return;
      if (adapter.isActive && !adapter.isActive()) return;
      if (!selection.length) return;
      var step = e.shiftKey ? 10 : 1;
      var d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
      if (d) {
        e.preventDefault();
        var before = adapter.snapshot ? adapter.snapshot() : null;
        var boxes = {};
        selection.forEach(function (id) { var it = itemById(id); if (it && it.bbox) boxes[id] = { x: round1(it.bbox.x + d[0]), y: round1(it.bbox.y + d[1]), w: it.bbox.w, h: it.bbox.h }; });
        adapter.commit(boxes, before, { coalesce: "nudge" });
        return;
      }
      if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); if (adapter.onDelete) adapter.onDelete(selection.slice()); return; }
      if ((e.ctrlKey || e.metaKey) && (e.key === "d" || e.key === "D")) { e.preventDefault(); if (adapter.onDuplicate) adapter.onDuplicate(selection.slice()); return; }
      if ((e.ctrlKey || e.metaKey) && (e.key === "]" || e.key === "[")) { e.preventDefault(); if (adapter.onReorder) adapter.onReorder(selection.slice(), e.key === "]" ? 1 : -1); return; }
      if (e.key === "Escape") { setSelection([]); }
    }

    return { init: init, mount: mount, clear: clear, fit: fit, setSelection: setSelection, getSelection: getSelection, refreshSelection: renderSelection, scale: function () { return scale; }, adapter: adapter };
  }

  var main = createCanvas(slideAdapter);
  main.create = createCanvas;
  return main;
})();
