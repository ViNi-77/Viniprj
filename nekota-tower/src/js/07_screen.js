/* 画面。320×240 の canvas を整数倍で中央に置く。既定はデバイスピクセル基準（Windows の 125%/150% でも均一なドットになる） */
(function () {
  "use strict";
  var NT = window.NT;
  var S = NT.Screen = {};
  S.canvas = null; S.ctx = null; S.stage = null; S.crt = null;
  S.scale = 2; S.cssScale = 2; S.mode = "device"; // 'device' | 'css'
  S.crtOn = true;

  S.init = function () {
    S.stage = document.getElementById("stage");
    S.canvas = document.getElementById("game");
    S.crt = document.getElementById("crt");
    S.canvas.width = NT.W; S.canvas.height = NT.H;
    S.ctx = S.canvas.getContext("2d", { alpha: false });
    S.ctx.imageSmoothingEnabled = false;
    S.fit();
    window.addEventListener("resize", S.fit);
    try {
      var mq = window.matchMedia("(resolution: " + window.devicePixelRatio + "dppx)");
      if (mq && mq.addEventListener) mq.addEventListener("change", S.fit);
    } catch (e) { /* 無視 */ }
  };

  S.fit = function () {
    var vw = document.documentElement.clientWidth || window.innerWidth;
    var vh = document.documentElement.clientHeight || window.innerHeight;
    var dpr = window.devicePixelRatio || 1;
    var cssW, cssH, n;
    if (S.mode === "device") {
      n = Math.max(1, Math.floor(Math.min(vw * dpr / NT.W, vh * dpr / NT.H)));
      cssW = NT.W * n / dpr; cssH = NT.H * n / dpr;
      S.scale = n; S.cssScale = n / dpr;
    } else {
      n = Math.max(1, Math.floor(Math.min(vw / NT.W, vh / NT.H)));
      cssW = NT.W * n; cssH = NT.H * n;
      S.scale = n * dpr; S.cssScale = n;
    }
    var root = document.documentElement.style;
    root.setProperty("--stage-w", cssW + "px");
    root.setProperty("--stage-h", cssH + "px");
    root.setProperty("--scale", String(S.cssScale));
    S.ctx.imageSmoothingEnabled = false;
  };

  S.setMode = function (m) { S.mode = m === "css" ? "css" : "device"; S.fit(); };
  S.setCRT = function (on) {
    S.crtOn = !!on;
    if (S.crt) S.crt.classList.toggle("off", !S.crtOn);
  };
  /* 内部座標 → CSS px（オーバーレイ配置用） */
  S.toCss = function (v) { return v * S.cssScale; };
  S.clear = function (color) {
    S.ctx.fillStyle = color || "#000";
    S.ctx.fillRect(0, 0, NT.W, NT.H);
  };
})();
