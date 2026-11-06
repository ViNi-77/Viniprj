/* 固定ステップのゲームループ。ヒットストップは freeze(frames) で止める */
(function () {
  "use strict";
  var NT = window.NT;
  var L = NT.Loop = { running: false, frame: 0, freezeFrames: 0, elapsed: 0, fps: 0 };
  var acc = 0, last = 0, raf = 0, fpsAcc = 0, fpsN = 0;
  var hooks = { pre: [], post: [] };

  function tick(now) {
    raf = requestAnimationFrame(tick);
    if (!last) last = now;
    var dt = Math.min(now - last, NT.STEP * 5);
    last = now;
    if (document.hidden) return;
    acc += dt;
    while (acc >= NT.STEP) {
      acc -= NT.STEP;
      L.frame++;
      if (L.freezeFrames > 0) { L.freezeFrames--; continue; }
      L.elapsed += NT.STEP;
      hooks.pre.forEach(function (f) { f(NT.STEP); });
      NT.Scenes.update(NT.STEP);
      NT.Input.endFrame(NT.STEP);
      hooks.post.forEach(function (f) { f(NT.STEP); });
    }
    NT.Scenes.draw(NT.Screen.ctx);
    if (L.shakeTimer > 0) { L.shakeTimer -= dt; if (L.shakeTimer <= 0) NT.Screen.canvas.style.transform = ""; }
    fpsAcc += dt; fpsN++;
    if (fpsAcc >= 1000) { L.fps = Math.round(fpsN * 1000 / fpsAcc); fpsAcc = 0; fpsN = 0; }
  }
  L.start = function () { if (L.running) return; L.running = true; last = 0; raf = requestAnimationFrame(tick); };
  L.stop = function () { L.running = false; cancelAnimationFrame(raf); };
  L.freeze = function (frames) { L.freezeFrames = Math.max(L.freezeFrames, Math.min(24, frames | 0)); };
  L.onPre = function (f) { hooks.pre.push(f); };
  L.onPost = function (f) { hooks.post.push(f); };
  /* 画面揺れ（CSS transform。reduced-motion では無効） */
  L.shakeTimer = 0;
  L.shake = function (px, ms) {
    if (NT.Settings && NT.Settings.get("reduceMotion")) return;
    var cv = NT.Screen.canvas, s = NT.Screen.cssScale;
    cv.style.transform = "translate(" + (px * s) + "px," + (-px * s * 0.6) + "px)";
    L.shakeTimer = ms || 60;
  };
  /* テスト用：手動で n ステップ進める */
  L.stepManual = function (n) {
    for (var i = 0; i < (n || 1); i++) { NT.Scenes.update(NT.STEP); NT.Input.endFrame(NT.STEP); }
    NT.Scenes.draw(NT.Screen.ctx);
  };
})();
