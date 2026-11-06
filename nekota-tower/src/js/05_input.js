/* 入力。KeyboardEvent.code でキー配列に依存しない。IME 合成中と入力欄上は無視する */
(function () {
  "use strict";
  var NT = window.NT;
  var I = NT.Input = {};
  var MAP = {
    ok: ["KeyZ", "Enter", "Space", "NumpadEnter"],
    cancel: ["KeyX", "Escape", "Backspace"],
    menu: ["KeyC", "Tab"],
    up: ["ArrowUp", "KeyW"],
    down: ["ArrowDown", "KeyS"],
    left: ["ArrowLeft", "KeyA"],
    right: ["ArrowRight", "KeyD"],
    dash: ["ShiftLeft", "ShiftRight"]
  };
  var codeToAction = {};
  Object.keys(MAP).forEach(function (a) { MAP[a].forEach(function (c) { codeToAction[c] = a; }); });

  var held = {};      // action -> true
  var pressed = {};   // action -> true（このフレームで押された）
  var anyKeyFlag = false;
  var clicks = [];    // {x,y}（内部解像度）
  var repeatTimers = {};
  I.typing = false;   // 22_inputbox が入力欄を開いている間 true
  I.lastDevice = "key";
  var listeners = [];

  function isTypingTarget(e) {
    var t = e.target;
    if (!t) return false;
    var tag = (t.tagName || "").toLowerCase();
    return tag === "input" || tag === "textarea" || t.isContentEditable;
  }

  function onKeyDown(e) {
    if (I.typing || isTypingTarget(e) || e.isComposing || e.keyCode === 229) return;
    var a = codeToAction[e.code];
    I.lastDevice = "key";
    if (e.code === "Tab" || e.code === "Backspace" || e.code === "Space" || /^Arrow/.test(e.code)) e.preventDefault();
    if (!e.repeat) { anyKeyFlag = true; }
    if (!a) return;
    if (!e.repeat) {
      if (!held[a]) { pressed[a] = true; repeatTimers[a] = 0; }
      held[a] = true;
    }
    listeners.forEach(function (fn) { fn(a, e); });
  }
  function onKeyUp(e) {
    var a = codeToAction[e.code];
    if (!a) return;
    held[a] = false;
    delete repeatTimers[a];
  }
  function reset() { held = {}; pressed = {}; repeatTimers = {}; }

  I.install = function (canvas) {
    window.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("keyup", onKeyUp, true);
    window.addEventListener("blur", reset);
    document.addEventListener("visibilitychange", function () { if (document.hidden) reset(); });
    canvas.addEventListener("pointerdown", function (e) {
      I.lastDevice = "pointer";
      anyKeyFlag = true;
      var r = canvas.getBoundingClientRect();
      var x = (e.clientX - r.left) / r.width * NT.W;
      var y = (e.clientY - r.top) / r.height * NT.H;
      clicks.push({ x: Math.floor(x), y: Math.floor(y), button: e.button });
      if (!I.typing) { try { canvas.focus({ preventScroll: true }); } catch (err) { canvas.focus(); } }
      e.preventDefault();
    });
    canvas.addEventListener("contextmenu", function (e) { e.preventDefault(); });
  };

  /* フレーム末に呼ぶ。pressed を消し、長押しリピートを作る（メニュー移動用） */
  I.endFrame = function (dt) {
    pressed = {};
    clicks.length = 0;
    anyKeyFlag = false;
    ["up", "down", "left", "right"].forEach(function (a) {
      if (!held[a]) return;
      repeatTimers[a] = (repeatTimers[a] || 0) + dt;
      if (repeatTimers[a] > 320) { pressed[a] = true; repeatTimers[a] = 320 - 90; }
    });
  };
  I.pressed = function (a) { return !!pressed[a]; };
  I.held = function (a) { return !!held[a]; };
  I.anyKey = function () { return anyKeyFlag; };
  I.clicks = function () { return clicks; };
  I.consume = function (a) { pressed[a] = false; };
  I.onKey = function (fn) { listeners.push(fn); };
  I.reset = reset;
  /* 方向入力を -1/0/1 で返す */
  I.axis = function () {
    var x = (held.right ? 1 : 0) - (held.left ? 1 : 0);
    var y = (held.down ? 1 : 0) - (held.up ? 1 : 0);
    return { x: x, y: y };
  };
  /* テスト用：仮想押下 */
  I.press = function (a) { pressed[a] = true; anyKeyFlag = true; };
  I.click = function (x, y) { clicks.push({ x: x, y: y, button: 0 }); anyKeyFlag = true; };
})();
