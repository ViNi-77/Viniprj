/* 起動画面。NETTA の肉球 → NETTA BOY → 本体チェック。約4秒、いつでもスキップ可 */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text, G = NT.Gfx, I = NT.Input;

  NT.SceneBoot = function (opts) {
    opts = opts || {};
    var t = 0, stage = 0, powered = false, finished = false, typed = 0;
    var LINES = ["PAW CHECK ........ OK", "MEMORY  3 SLOT ... OK", "MEMORY CARD ...... ---", "", "LICENSED BY NETTA GAME-BU", "(C) 2026 NETTA GAME-BU"];
    var rng = NT.Util.rng(7);
    var noise = [];
    for (var i = 0; i < 200; i++) noise.push([Math.floor(rng() * NT.W), Math.floor(rng() * NT.H)]);
    var sfxBoot = false, sfxBrand = false, sfxCart = false;

    function finish() {
      if (finished) return;
      finished = true;
      if (opts.onDone) opts.onDone();
    }
    return {
      id: "BOOT", opaque: true,
      enter: function () { t = 0; },
      update: function (dt) {
        if (!powered) {
          if (I.anyKey()) { powered = true; NT.Audio.unlock(); t = 0; }
          return;
        }
        t += dt;
        if (I.anyKey() && t > 200) { finish(); return; }
        if (t > 150 && !sfxBoot) { sfxBoot = true; NT.Audio.play("boot"); }
        if (t > 1300 && !sfxBrand) { sfxBrand = true; NT.Audio.play("open"); }
        if (t > 2600) typed = Math.min(LINES.join("\n").length, Math.floor((t - 2600) / 14));
        if (t > 4300 && !sfxCart) { sfxCart = true; NT.Audio.play("cart"); }
        if (t > 4700) finish();
      },
      draw: function (ctx) {
        NT.Screen.clear("#000");
        var reduce = NT.Settings.get("reduceMotion");
        if (!powered) {
          /* 電源待ち：暗い画面に PRESS ANY KEY */
          ctx.fillStyle = "#07070b"; ctx.fillRect(0, 0, NT.W, NT.H);
          if ((Math.floor(performance.now() / 600) % 2) === 0 || reduce) T.drawCenter(ctx, "PRESS ANY KEY", NT.W / 2, 128, "#9aa0b4");
          T.drawCenter(ctx, "でんげんを いれる", NT.W / 2, 148, "#5b5a66");
          G.paw(ctx, NT.W / 2, 96, 1.4, "#3a3444");
          return;
        }
        /* 段階1：点灯の横線 → ノイズ → 肉球 + NETTA（0–1200ms） */
        if (t < 1200) {
          if (t < 160 && !reduce) {
            var h = Math.max(1, Math.round((t / 160) * NT.H));
            ctx.fillStyle = "#e8e8f0"; ctx.fillRect(0, (NT.H - h) / 2, NT.W, h);
            return;
          }
          if (t < 300 && !reduce) {
            ctx.fillStyle = "#101014"; ctx.fillRect(0, 0, NT.W, NT.H);
            ctx.fillStyle = "#9aa0b4";
            for (var i = 0; i < noise.length; i++) { var p = noise[(i + Math.floor(t)) % noise.length]; ctx.fillRect(p[0], (p[1] + Math.floor(t * 3)) % NT.H, 2, 1); }
            return;
          }
          var k = NT.Util.clamp((t - 300) / 500, 0, 1), e = NT.Util.easeOut(k);
          var py = reduce ? 96 : Math.round(-30 + (96 + 30) * e);
          G.paw(ctx, NT.W / 2, py, 2.2, "#f4d03f");
          if (t > 700) T.drawCenter(ctx, "NETTA", NT.W / 2, 134, "#f4f1e8", { head: true, size: 16 });
          return;
        }
        /* 段階2：ブランドマーク（1200–2600ms） */
        if (t < 2600) {
          var k2 = NT.Util.clamp((t - 1200) / 400, 0, 1);
          drawHeadphoneCat(ctx, NT.W / 2, 84, k2);
          var label = "NETTA BOY";
          var n = Math.floor(label.length * NT.Util.clamp((t - 1500) / 400, 0, 1));
          T.drawCenter(ctx, label, NT.W / 2, 150, "#f4f1e8", { head: true, size: 16, limit: n });
          if (t > 2100) T.drawCenter(ctx, "MAX 10 MEGA QUEST SPEC", NT.W / 2, 176, "#9aa0b4");
          if (t > 2300) T.drawCenter(ctx, "GAME-BU", NT.W / 2, 194, "#f4d03f");
          return;
        }
        /* 段階3：本体チェックのタイプ表示（2600–4700ms） */
        var all = LINES.join("\n"), shown = all.slice(0, typed).split("\n");
        for (var li = 0; li < shown.length; li++) T.draw(ctx, shown[li], 40, 60 + li * 18, li >= 4 ? "#9aa0b4" : "#7dffb0");
        if ((Math.floor(t / 250) % 2) === 0 && typed < all.length) { var lastLine = shown[shown.length - 1] || ""; ctx.fillStyle = "#7dffb0"; ctx.fillRect(40 + T.measure(lastLine), 60 + (shown.length - 1) * 18, 6, 12); }
        if (t > 4300) G.fade(ctx, (t - 4300) / 400, "255,255,255");
      },
      skip: finish,
      power: function () { if (!powered) { powered = true; NT.Audio.unlock(); t = 0; } }
    };
  };

  /* ヘッドホンの猫（ゲーム部ロゴの簡略版） */
  function drawHeadphoneCat(ctx, cx, cy, k) {
    var r = 26 * k;
    if (r < 1) return;
    ctx.fillStyle = "#cdbdec";
    ctx.beginPath(); ctx.ellipse(cx, cy, r, r * 0.86, 0, 0, Math.PI * 2); ctx.fill();
    /* 耳 */
    ctx.beginPath(); ctx.moveTo(cx - r * 0.85, cy - r * 0.3); ctx.lineTo(cx - r * 0.6, cy - r * 1.25); ctx.lineTo(cx - r * 0.2, cy - r * 0.75); ctx.closePath(); ctx.fill();
    ctx.beginPath(); ctx.moveTo(cx + r * 0.85, cy - r * 0.3); ctx.lineTo(cx + r * 0.6, cy - r * 1.25); ctx.lineTo(cx + r * 0.2, cy - r * 0.75); ctx.closePath(); ctx.fill();
    /* ヘッドホン */
    ctx.strokeStyle = "#2ef2ff"; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.arc(cx, cy - r * 0.1, r * 1.05, Math.PI * 1.1, Math.PI * 1.9); ctx.stroke();
    ctx.fillStyle = "#2ef2ff";
    ctx.fillRect(cx - r * 1.2, cy - r * 0.35, r * 0.3, r * 0.7); ctx.fillRect(cx + r * 0.9, cy - r * 0.35, r * 0.3, r * 0.7);
    /* 目と口 */
    ctx.fillStyle = "#1d1b2e";
    ctx.fillRect(cx - r * 0.45, cy - r * 0.1, r * 0.22, r * 0.3); ctx.fillRect(cx + r * 0.23, cy - r * 0.1, r * 0.22, r * 0.3);
    ctx.fillRect(cx - r * 0.1, cy + r * 0.3, r * 0.2, r * 0.08);
    ctx.fillStyle = "#f4afc4"; ctx.fillRect(cx - r * 0.7, cy + r * 0.2, r * 0.2, r * 0.1); ctx.fillRect(cx + r * 0.5, cy + r * 0.2, r * 0.2, r * 0.1);
    /* 肉球 */
    G.paw(ctx, cx + r * 1.5, cy + r * 0.7, 0.9 * k, "#78ff9a");
  }
})();
