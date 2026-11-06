/* カメラ。主人公を中央に置き、マップの端で止める。エレベーターは縦にパンする */
(function () {
  "use strict";
  var NT = window.NT;
  var C = NT.Camera = { x: 0, y: 0 };
  var tween = null;
  C.HUD = 16; /* 上部 HUD の高さ（px）*/

  C.clamp = function () {
    C.x = NT.Util.clamp(C.x, 0, Math.max(0, NT.Tilemap.pxW - NT.W));
    C.y = NT.Util.clamp(C.y, -C.HUD, Math.max(-C.HUD, NT.Tilemap.pxH - NT.H + 0));
  };
  C.center = function (px, py) {
    C.x = Math.round(px - NT.W / 2);
    C.y = Math.round(py - (NT.H + C.HUD) / 2);
    C.clamp();
  };
  C.follow = function (px, py) {
    if (tween) return;
    C.center(px, py);
  };
  C.panTo = function (px, py, ms, onDone) {
    var sx = C.x, sy = C.y;
    var tx = Math.round(px - NT.W / 2), ty = Math.round(py - (NT.H + C.HUD) / 2);
    tx = NT.Util.clamp(tx, 0, Math.max(0, NT.Tilemap.pxW - NT.W));
    ty = NT.Util.clamp(ty, -C.HUD, Math.max(-C.HUD, NT.Tilemap.pxH - NT.H));
    tween = { sx: sx, sy: sy, tx: tx, ty: ty, t: 0, ms: ms || 600, onDone: onDone };
  };
  C.update = function (dt) {
    if (!tween) return;
    tween.t += dt;
    var k = NT.Util.easeInOut(NT.Util.clamp(tween.t / tween.ms, 0, 1));
    C.x = Math.round(NT.Util.lerp(tween.sx, tween.tx, k));
    C.y = Math.round(NT.Util.lerp(tween.sy, tween.ty, k));
    if (tween.t >= tween.ms) { var cb = tween.onDone; tween = null; if (cb) cb(); }
  };
  C.busy = function () { return !!tween; };
})();
