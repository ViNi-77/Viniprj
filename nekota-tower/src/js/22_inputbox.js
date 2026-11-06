/* 日本語入力。canvas 上に本物の input/textarea を重ねる（IME を正しく扱うため）
   NT.InputBox.open({x,y,w,h, value, maxLen, multiline, placeholder, title, onDone(value|null)}) */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text, G = NT.Gfx;
  var B = NT.InputBox = { active: null };

  function ensureOverlay() { return document.getElementById("overlay"); }

  B.open = function (o) {
    if (B.active) B.close(null);
    var ov = ensureOverlay();
    var el = document.createElement(o.multiline ? "textarea" : "input");
    el.className = o.multiline ? "nt-textarea" : "nt-input";
    if (!o.multiline) { el.type = "text"; el.autocomplete = "off"; el.autocapitalize = "off"; el.spellcheck = false; }
    el.value = o.value || "";
    el.placeholder = o.placeholder || "";
    el.setAttribute("aria-label", o.title || "入力");
    var maxLen = o.maxLen || 40;
    var composing = false, lastCompEnd = 0;
    var top = o.title ? 26 : 10, inputH = o.multiline ? 16 * (o.rows || 3) : 16;
    var frame = { x: o.x, y: o.y, w: o.w, h: o.h || (top + inputH + 30) };
    var inner = { x: frame.x + 12, y: frame.y + top, w: frame.w - 24, h: inputH };
    function place() {
      var s = NT.Screen.cssScale;
      el.style.left = (inner.x * s) + "px"; el.style.top = (inner.y * s) + "px";
      el.style.width = (inner.w * s) + "px"; el.style.height = (inner.h * s) + "px";
    }
    place();
    ov.appendChild(el);
    NT.Input.typing = true;
    var done = false;
    function finish(v) {
      if (done) return; done = true;
      NT.Input.typing = false;
      if (el.parentNode) el.parentNode.removeChild(el);
      B.active = null;
      try { NT.Screen.canvas.focus({ preventScroll: true }); } catch (e) { /* 無視 */ }
      window.removeEventListener("resize", place);
      if (o.onDone) o.onDone(v);
    }
    function clampLen() {
      var g = NT.Util.graphemes(el.value);
      if (g.length > maxLen) { el.value = g.slice(0, maxLen).join(""); }
    }
    el.addEventListener("compositionstart", function () { composing = true; });
    el.addEventListener("compositionend", function () { composing = false; lastCompEnd = performance.now(); clampLen(); });
    el.addEventListener("input", function () { if (!composing) clampLen(); });
    el.addEventListener("keydown", function (e) {
      e.stopPropagation();
      if (e.isComposing || e.keyCode === 229 || composing) return;
      if (performance.now() - lastCompEnd < 50 && e.key === "Enter") return; /* Safari の順序対策 */
      if (e.key === "Enter" && !(o.multiline && e.shiftKey)) { e.preventDefault(); NT.Audio.play("decide"); finish(el.value.normalize("NFC").trim()); }
      else if (e.key === "Escape") { e.preventDefault(); NT.Audio.play("cancel"); finish(null); }
      else if (e.key === "Tab") { e.preventDefault(); }
    });
    el.addEventListener("keyup", function (e) { e.stopPropagation(); });
    window.addEventListener("resize", place);
    B.active = { el: el, frame: frame, inner: inner, title: o.title, maxLen: maxLen, finish: finish, hint: o.hint };
    setTimeout(function () { try { el.focus({ preventScroll: true }); } catch (e) { el.focus(); } }, 0);
    return B.active;
  };
  B.close = function (v) { if (B.active) B.active.finish(v); };
  B.setValue = function (v) { if (B.active) { B.active.el.value = v; } };
  B.submit = function () { if (B.active) B.active.finish(B.active.el.value.normalize("NFC").trim()); };
  /* 枠と残り文字数を canvas に描く（シーン側の draw から呼ぶ） */
  B.draw = function (ctx) {
    var a = B.active; if (!a) return;
    G.frame(ctx, a.frame.x, a.frame.y, a.frame.w, a.frame.h);
    if (a.title) T.draw(ctx, a.title, a.frame.x + 12, a.frame.y + 8, "#f4d03f");
    var n = NT.Util.gLen(a.el.value);
    T.drawRight(ctx, n + "/" + a.maxLen, a.frame.x + a.frame.w - 12, a.frame.y + a.frame.h - 20, "#9aa0b4");
    var hint = a.hint || (a.el.tagName === "TEXTAREA" ? "Enter できめる　Shift+Enter で改行　Esc でやめる" : "Enter できめる　Esc でやめる");
    T.draw(ctx, hint, a.frame.x + 12, a.frame.y + a.frame.h - 20, "#5b5a66");
  };
})();
