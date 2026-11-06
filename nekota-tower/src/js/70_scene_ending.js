/* エンディングの骨格。mode: 'result'（年が明けたときの結果発表）| 'normal'（ノーマルED：本人の入力が流れる） */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text, G = NT.Gfx, I = NT.Input, TX = function () { return NT.DATA.TEXT.ending; };

  function buildRoll(st) {
    var lines = [];
    var push = function (s, c) { lines.push({ s: s, c: c || "#f4f1e8" }); };
    push(NT.DATA.TEXT.title, "#f4d03f"); push(""); push("― " + st.name + " の 年の瀬 ―", "#9aa0b4"); push(""); push("");
    NT.DATA.QUEST_ORDER.forEach(function (id) {
      var def = NT.DATA.QUESTS[id], q = st.quests[id] || {};
      var cleared = q.status === "cleared";
      push(def.num + " " + def.title, cleared ? "#f4d03f" : "#9aa0b4");
      if (!def.implemented) { push("　（じゅんびちゅう）", "#5b5a66"); push(""); return; }
      (q.entries || []).forEach(function (e) { push("　" + (e.doneKey ? "● " : "○ ") + e.text, e.doneKey ? "#f4f1e8" : "#9aa0b4"); });
      if (q.declared) push("　★ " + q.declared.text + "　" + NT.Quests.streak(q) + "日", "#f4f1e8");
      if (q.lesson) push("　教訓：" + q.lesson, "#f4afc4");
      if (q.reportText) push("　「" + q.reportText + "」", "#9aa0b4");
      push("");
    });
    push(""); push(TX().title + "　" + st.title, "#f4d03f"); push(TX().marks + "　" + st.marks + "/10", "#f4afc4"); push("");
    push(TX().thanks, "#f4f1e8"); push(""); push(""); push("NETTA BOY", "#5b5a66"); push("(C) 2026 NETTA GAME-BU", "#5b5a66");
    var out = [];
    lines.forEach(function (l) { T.wrap(l.s, 288).forEach(function (w, i) { out.push({ s: w, c: l.c }); }); });
    return out;
  }

  NT.SceneEnding = function (mode) {
    var st = NT.State.cur, roll = [], y = 0, t = 0, finished = false, resultStep = 0;
    var scene = {
      id: "ENDING", opaque: true,
      enter: function () {
        roll = buildRoll(st); y = NT.H; t = 0;
        if (mode === "normal" && NT.DATA.SONGS) NT.Audio.startMusic(NT.DATA.SONGS.ending);
        st.flags.resultShown = true;
      },
      exit: function () { NT.Audio.stopMusic(); },
      update: function (dt) {
        t += dt;
        if (mode === "result") {
          if (I.pressed("ok") || I.clicks().length) { I.consume("ok"); if (resultStep < 2) { resultStep++; NT.Audio.play("decide"); } else { NT.Scenes.pop(); } }
          return;
        }
        var speed = (I.held("ok") || I.held("down")) ? 0.09 : 0.03;
        if (!finished) {
          y -= dt * speed;
          if (y + roll.length * 16 < NT.H / 2) finished = true;
        } else if (I.pressed("ok") || I.pressed("cancel") || I.clicks().length) { I.consume("ok"); NT.Scenes.pop(); }
      },
      draw: function (ctx) {
        NT.Screen.clear("#000");
        if (mode === "result") {
          T.drawCenter(ctx, TX().result, NT.W / 2, 24, "#f4d03f", { head: true, size: 16 });
          T.drawCenter(ctx, st.year + "年の 塔は とじました", NT.W / 2, 52, "#9aa0b4");
          if (resultStep >= 0) { T.drawCenter(ctx, TX().marks + "　" + st.marks + "/10", NT.W / 2, 90, "#f4afc4"); }
          if (resultStep >= 1) { T.drawCenter(ctx, TX().title + "　" + st.title, NT.W / 2, 112, "#f4d03f"); }
          if (resultStep >= 2) {
            var msg = st.marks >= 3 ? "合格。塔の中は 来年まで あるけます" : "しるしは あと " + (3 - st.marks) + "つ。来年の 塔で また";
            T.drawLines(ctx, T.wrap(msg, 280), 20, 140, "#f4f1e8");
            T.drawCenter(ctx, "（2しゅうめ・トゥルーED は つぎの版で）", NT.W / 2, 190, "#5b5a66");
          }
          if ((t % 1000) < 500) G.nextMark(ctx, NT.W - 20, NT.H - 14, "#f4d03f");
          return;
        }
        for (var i = 0; i < roll.length; i++) {
          var ly = Math.round(y + i * 16);
          if (ly < -16 || ly > NT.H) continue;
          T.draw(ctx, roll[i].s, 16, ly, roll[i].c);
        }
        if (finished) T.drawCenter(ctx, "― おわり ―", NT.W / 2, NT.H / 2, "#f4d03f", { head: true, size: 16 });
        if (!finished) T.drawRight(ctx, "Z で はやおくり", NT.W - 8, NT.H - 14, "#5b5a66");
      }
    };
    return scene;
  };
})();
