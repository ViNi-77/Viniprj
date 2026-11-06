/* ① ホワイトタイム：10分 なにもしない。操作すると ボスが 回復する（＝残り時間が戻る）。X / Esc で中断（失敗ではない） */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text, G = NT.Gfx, I = NT.Input;

  NT.SceneWhite = function (id) {
    var def = NT.Quests.def(id), total = (NT.query.white ? +NT.query.white : (def.exec && def.exec.whiteSeconds) || 600) * 1000;
    var remain = total, t = 0, heal = 0, healMsg = 0, done = false, dawn = 0, touches = 0, started = false;
    function finish() {
      if (done) return;
      done = true;
      NT.Quests.whiteDone(id, Math.round(total / 1000));
      NT.Audio.play("bloom");
      NT.Scenes.push(NT.Notice("10分、なにも しなかった。ボスは しずかに 消えた", function () { NT.Scenes.pop(); }, { color: "#f4d03f" }));
    }
    function quit() {
      NT.Scenes.push(NT.Confirm("ここで やめますか？（失敗には ならない。また いつでも）", function () { NT.Scenes.pop(); }, null, { y: 150 }));
    }
    var scene = {
      id: "WHITE", opaque: true,
      enter: function () { NT.Audio.stopMusic(); t = 0; },
      update: function (dt) {
        if (done) { dawn = Math.min(1, dawn + dt / 1500); return; }
        t += dt;
        if (!started) { started = true; return; }
        if (I.pressed("cancel")) { I.consume("cancel"); quit(); return; }
        /* さわると回復 */
        var touched = I.anyKey() || I.clicks().length;
        if (touched && t > 400) {
          touches++;
          var back = Math.min(total - remain, 30000);
          remain += back; heal = 600; healMsg = 2600;
          NT.Audio.play("error");
        }
        if (heal > 0) heal -= dt;
        if (healMsg > 0) healMsg -= dt;
        remain -= dt;
        if (remain <= 0) { remain = 0; finish(); }
      },
      draw: function (ctx) {
        var p = 1 - remain / total;
        /* 深い色から 夜明けへ */
        var r = Math.round(10 + 40 * p + 200 * dawn), g = Math.round(10 + 30 * p + 180 * dawn), b = Math.round(22 + 60 * p + 150 * dawn);
        ctx.fillStyle = "rgb(" + r + "," + g + "," + b + ")"; ctx.fillRect(0, 0, NT.W, NT.H);
        /* 星が少しずつ消える */
        var rng = NT.Util.rng(11);
        for (var i = 0; i < 40; i++) { var sx = Math.floor(rng() * NT.W), sy = Math.floor(rng() * 150); if (rng() > p * 0.9) { ctx.fillStyle = "rgba(244,241,232," + (0.5 - dawn * 0.5) + ")"; ctx.fillRect(sx, sy, 1, 1); } }
        /* ボス：息をする雲。回復中は赤く */
        var breathe = Math.sin(t / 900) * 3, size = 1 - p * 0.6 - dawn;
        if (size > 0) {
          var cx = NT.W / 2, cy = 110 + breathe;
          ctx.fillStyle = heal > 0 ? "rgba(244,175,196," + size + ")" : "rgba(255,255,255," + (0.85 * size) + ")";
          [[0, 0, 28], [-22, 6, 18], [22, 6, 18], [-10, -12, 16], [12, -12, 16]].forEach(function (c) {
            ctx.beginPath(); ctx.ellipse(cx + c[0], cy + c[1], c[2] * (0.6 + size * 0.4), c[2] * 0.8 * (0.6 + size * 0.4), 0, 0, Math.PI * 2); ctx.fill();
          });
          ctx.fillStyle = "rgba(29,27,46," + size + ")";
          ctx.fillRect(cx - 12, cy - 2, 7, 2); ctx.fillRect(cx + 5, cy - 2, 7, 2);
        }
        /* ねこ太は すわっている */
        if (NT.Sprites.ready && dawn < 1) NT.Sprites.draw(ctx, "nekota:up:0", NT.W / 2, 196);
        /* 文字は最小限 */
        var mm = Math.floor(remain / 60000), ss = Math.floor((remain % 60000) / 1000);
        var dim = "rgba(244,241,232," + (0.35 + 0.3 * (1 - p)) + ")";
        if (!done) {
          T.drawCenter(ctx, "なにも しない", NT.W / 2, 40, dim);
          T.drawCenter(ctx, mm + ":" + NT.Util.pad2(ss), NT.W / 2, NT.H - 30, dim);
          if (healMsg > 0) T.drawCenter(ctx, "さわると ボスが 回復する", NT.W / 2, 60, "#f4afc4");
          if (t < 4000) T.drawCenter(ctx, "手を はなして。X で やめられる", NT.W / 2, NT.H - 14, "rgba(244,241,232,.35)");
        } else {
          T.drawCenter(ctx, "夜が あけた", NT.W / 2, 40, "#f4f1e8", { head: true, size: 16 });
        }
      },
      state: function () { return { remain: Math.round(remain / 1000), touches: touches, done: done }; }
    };
    return scene;
  };
  NT.Flow = NT.Flow || {};
  NT.Flow.openWhite = function (id) {
    var q = NT.Quests.state(id || "q1");
    if (q.status === "offered") NT.Quests.accept(id || "q1");
    NT.Scenes.push(NT.SceneWhite(id || "q1"));
  };
})();
