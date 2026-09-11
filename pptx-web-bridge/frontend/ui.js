/**
 * 画面の共通部品（素の JavaScript、ビルド無し）。
 *
 * - モーダルは HTML 標準の <dialog> を使う（焦点の閉じ込め・Esc・背景はブラウザ任せ）。
 *   既存コードと Playwright の検査は `hidden` 属性で開閉を見ているので、open/close と同期させる。
 * - 3 ペインの幅は Split.js（frontend/vendor/split.min.js）に任せ、最小幅を割らないようにする。
 */
(function () {
  "use strict";
  window.PWB = window.PWB || {};

  function openModal(el) {
    if (!el) return;
    el.hidden = false;
    if (typeof el.showModal === "function" && !el.open) {
      try { el.showModal(); } catch (e) { el.setAttribute("open", ""); }
    }
  }
  function closeModal(el) {
    if (!el) return;
    if (typeof el.close === "function" && el.open) el.close();
    el.removeAttribute("open");
    el.hidden = true;
  }
  function isOpen(el) { return !!el && !el.hidden && (el.open || el.hasAttribute("open")); }

  /**
   * <dialog> の標準イベントと `hidden` を同期させる。
   * onCancel が false を返すと Esc で閉じない（キャンバスの選択解除に Esc を使う画面向け）。
   */
  function bindModal(el, opts) {
    opts = opts || {};
    el.addEventListener("cancel", function (e) {
      e.preventDefault();  // 既定の close は hidden を戻さないので自前で閉じる
      if (opts.onCancel && opts.onCancel() === false) return;
      closeModal(el);
      if (opts.onClose) opts.onClose();
    });
    el.addEventListener("close", function () { el.hidden = true; if (opts.onClose) opts.onClose(); });
    if (opts.backdropCloses) {
      el.addEventListener("click", function (e) { if (e.target === el) { closeModal(el); if (opts.onClose) opts.onClose(); } });
    }
  }

  var PANES_KEY = "pptx_web_bridge.panes.v2";
  var STACK_BELOW = 900;  // これより狭い画面は縦積み（Split は使わない）
  var splitInstance = null;

  /** 3 ペインの幅（%）を Split.js で管理する。保存値は割合で持ち、最小幅で必ずクランプされる。 */
  function initPanes(ids, opts) {
    opts = opts || {};
    var els = ids.map(function (id) { return document.getElementById(id); });
    if (els.some(function (e) { return !e; }) || typeof window.Split !== "function") return null;
    var sizes = null;
    try { sizes = JSON.parse(localStorage.getItem(PANES_KEY) || "null"); } catch (e) { sizes = null; }
    if (!Array.isArray(sizes) || sizes.length !== ids.length || sizes.some(function (v) { return !(v > 0); })) sizes = opts.sizes || [22, 24, 54];
    function create() {
      if (splitInstance) return;
      splitInstance = window.Split(els, {
        sizes: sizes,
        minSize: opts.minSize || [220, 200, 420],
        expandToMin: true,
        gutterSize: 8,
        snapOffset: 0,
        onDrag: function () { if (opts.onResize) opts.onResize(); },
        onDragEnd: function (s) { sizes = s; try { localStorage.setItem(PANES_KEY, JSON.stringify(s)); } catch (e) { /* 保存できなくても動く */ } if (opts.onResize) opts.onResize(); }
      });
    }
    function destroy() {
      if (!splitInstance) return;
      splitInstance.destroy();
      splitInstance = null;
      els.forEach(function (e) { e.style.width = ""; });
    }
    function sync() {
      var stacked = window.innerWidth < STACK_BELOW;
      document.body.classList.toggle("stacked", stacked);
      if (stacked) destroy(); else create();
    }
    sync();
    window.addEventListener("resize", sync);
    return {
      reset: function () { destroy(); sizes = opts.sizes || [22, 24, 54]; try { localStorage.removeItem(PANES_KEY); } catch (e) { /* noop */ } sync(); },
      instance: function () { return splitInstance; }
    };
  }

  window.PWB.ui = { openModal: openModal, closeModal: closeModal, isOpen: isOpen, bindModal: bindModal, initPanes: initPanes };
})();
