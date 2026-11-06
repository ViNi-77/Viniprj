/* 言い訳モンスター。受けたまま 3 日さわっていないクエストを開くと現れる。
   「たちむかう」＝きょうできる最小の行動を 1 行宣言（ゆうき +1）、「にげる」＝責めずに教訓の書へ記録。1 日 1 回まで */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text, G = NT.Gfx, I = NT.Input, TX = function () { return NT.DATA.TEXT.excuse; };
  var X = NT.Excuse = { STALE_DAYS: 3 };

  X.touch = function (id) { var q = NT.Quests.state(id); q.touchedKey = NT.Time.jstKey(); };
  X.staleDays = function (id) {
    var q = NT.Quests.state(id);
    if (q.status === "offered" || q.status === "cleared") return 0;
    var last = q.touchedKey || q.acceptedKey; if (!last) return 0;
    return NT.Time.diffDays(last, NT.Time.jstKey());
  };
  X.shouldAppear = function (id) {
    if (NT.query.noexcuse) return false;
    var q = NT.Quests.state(id), today = NT.Time.jstKey();
    if (q.excuseKey === today) return false;
    var d = X.staleDays(id);
    return d >= X.STALE_DAYS || (NT.query.excuse === "1");
  };

  NT.SceneExcuse = function (id, onDone) {
    var def = NT.Quests.def(id), q = NT.Quests.state(id), st = NT.State.cur;
    var t = 0, phase = "appear", excuse = "", wob = 0, days = X.staleDays(id), done = false;
    st.excuses = st.excuses || [];
    function finish(res) {
      if (done) return; done = true;
      q.excuseKey = NT.Time.jstKey();
      NT.State.touch();
      NT.Scenes.remove(scene);
      if (onDone) onDone(res);
    }
    function askExcuse() {
      phase = "ask";
      NT.InputBox.open({ x: 24, y: 150, w: 272, maxLen: 40, title: TX().ask, hint: "Enter で つぎへ（空でも よい）", onDone: function (v) {
        excuse = v || "（ことばに ならない）";
        phase = "choose";
        NT.Scenes.push(NT.Menu({ x: 60, y: 150, w: 200, cancelable: false, items: [{ label: TX().fight, value: "fight" }, { label: TX().run, value: "run" }], onSelect: function (it) {
          NT.Scenes.pop();
          if (it.value === "fight") {
            NT.InputBox.open({ x: 24, y: 150, w: 272, maxLen: 40, title: TX().fightAsk, onDone: function (a) {
              if (!a) { run(); return; }
              st.excuses.push({ q: id, k: NT.Time.jstKey(), text: excuse, action: a, fought: true });
              st.courage = (st.courage || 0) + 1;
              if (q.plan) q.plan.how = q.plan.how || a;
              NT.State.addLog(id + ".fight", a);
              NT.Audio.play("clear"); NT.Loop.freeze(8); NT.Loop.shake(2, 100);
              phase = "won"; t = 0;
            } });
          } else run();
        } }));
      } });
    }
    function run() {
      st.excuses.push({ q: id, k: NT.Time.jstKey(), text: excuse, fought: false });
      NT.State.addLog(id + ".run", excuse);
      NT.Audio.play("cancel");
      phase = "ran"; t = 0;
    }
    var scene = {
      id: "EXCUSE", opaque: true,
      enter: function () { t = 0; NT.Audio.play("error"); NT.Loop.shake(2, 120); },
      update: function (dt) {
        t += dt; wob += dt;
        if (phase === "appear" && t > 500 && (I.pressed("ok") || I.clicks().length)) { I.consume("ok"); askExcuse(); return; }
        if ((phase === "won" || phase === "ran") && t > 500 && (I.pressed("ok") || I.clicks().length)) { I.consume("ok"); finish(phase); }
      },
      draw: function (ctx) {
        NT.Screen.clear("#120a16");
        /* いいわけ：もやもやした影。たおすと 消える */
        var alive = phase !== "won";
        if (alive) {
          var cx = NT.W / 2 + Math.sin(wob / 300) * 4, cy = 80 + Math.cos(wob / 420) * 3;
          ctx.fillStyle = "rgba(90,60,110,.85)";
          [[0, 0, 30, 22], [-24, 8, 18, 14], [24, 8, 18, 14], [-10, -16, 16, 12], [12, -16, 16, 12]].forEach(function (c) {
            ctx.beginPath(); ctx.ellipse(cx + c[0], cy + c[1], c[2], c[3], 0, 0, Math.PI * 2); ctx.fill();
          });
          ctx.fillStyle = "#f4d03f"; ctx.fillRect(cx - 12, cy - 4, 6, 3); ctx.fillRect(cx + 6, cy - 4, 6, 3);
          ctx.fillStyle = "#1d1b2e"; ctx.fillRect(cx - 6, cy + 8, 12, 2);
        } else {
          ctx.fillStyle = "rgba(244,208,63,.6)";
          for (var k = 0; k < 8; k++) { var a = k / 8 * Math.PI * 2, r = 20 + (t / 20) % 30; ctx.fillRect(NT.W / 2 + Math.cos(a) * r, 80 + Math.sin(a) * r, 2, 2); }
        }
        if (NT.Sprites.ready) NT.Sprites.draw(ctx, "nekota:up:0", NT.W / 2, 150);
        var head = phase === "won" ? TX().fightDone : phase === "ran" ? TX().ranAway : TX().appear;
        T.drawCenter(ctx, head, NT.W / 2, 14, phase === "won" ? "#7dffb0" : "#f4afc4", { head: true, size: 16 });
        if (phase === "appear") {
          T.drawCenter(ctx, def.num + " " + def.title, NT.W / 2, 40, "#9aa0b4");
          T.drawCenter(ctx, NT.Util.fmt(TX().days, { n: days }), NT.W / 2, 56, "#9aa0b4");
          if ((t % 1000) < 500) T.drawCenter(ctx, "Z", NT.W / 2, NT.H - 24, "#f4d03f");
        }
        if (phase === "ask" || phase === "choose") T.drawLines(ctx, T.wrap("いいわけ：" + (excuse || "…"), 280), 20, 110, "#f4f1e8");
        if (phase === "won") { T.drawLines(ctx, T.wrap("きょうの 一歩：" + st.excuses[st.excuses.length - 1].action, 280), 20, 110, "#f4f1e8"); T.drawCenter(ctx, "ゆうき " + (st.courage || 0), NT.W / 2, NT.H - 40, "#f4d03f"); }
        if (phase === "ran") T.drawLines(ctx, T.wrap("「" + excuse + "」　にげるのも 選択。責めない。あしたも 塔は ここに ある", 280), 20, 110, "#9aa0b4");
        NT.InputBox.draw(ctx);
      },
      state: function () { return { phase: phase, excuse: excuse, days: days }; }
    };
    return scene;
  };
})();
