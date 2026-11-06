/* エンディング。mode: 'result'（年が明けたときの結果発表。3未満ならバッド→CONTINUE）| 'normal'（スタッフロール）| 'true'（10/10。スタッフロールの後に NEXT QUEST） */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text, G = NT.Gfx, I = NT.Input, TX = function () { return NT.DATA.TEXT.ending; };

  function buildRoll(st) {
    var lines = [];
    var push = function (s, c) { lines.push({ s: s, c: c || "#f4f1e8" }); };
    push(NT.DATA.TEXT.title, "#f4d03f"); push(""); push("― " + st.name + " の " + st.year + "年の 年の瀬 ―" + (st.lap > 1 ? "（" + st.lap + "しゅうめ）" : ""), "#9aa0b4"); push(""); push("");
    NT.DATA.QUEST_ORDER.forEach(function (id) {
      var def = NT.DATA.QUESTS[id], q = st.quests[id] || {};
      var cleared = q.status === "cleared";
      push(def.num + " " + def.title, cleared ? "#f4d03f" : "#9aa0b4");
      NT.Quests.lists(def).forEach(function (L) {
        (q[L.kind] || []).forEach(function (e) {
          var marked = (def.exec && def.exec.commands || []).some(function (c) { return e[(c.flag || "done") + "Key"]; }) || (L.kind === "attempts");
          var tag = st.valueTags && st.valueTags[e.id] ? "〔" + tagLabel(st.valueTags[e.id]) + "〕" : "";
          push("　" + (marked ? "● " : "○ ") + e.text + (e.date ? "（" + NT.Time.mmdd(e.date).replace("-", "/") + "）" : "") + tag, marked ? "#f4f1e8" : "#9aa0b4");
        });
      });
      Object.keys(q.extras || {}).forEach(function (k) { if (q.extras[k]) push("　" + q.extras[k], "#9aa0b4"); });
      if (q.declared) push("　★ " + q.declared.text + "　" + NT.Quests.streak(q) + "日", "#f4f1e8");
      if (q.timerDone) push("　なにもしない　" + q.timerDone + "回", "#f4f1e8");
      if (q.lesson) push("　教訓：" + q.lesson, "#f4afc4");
      if (q.reportText) push("　「" + q.reportText + "」", "#9aa0b4");
      push("");
    });
    if (st.excuses && st.excuses.length) {
      push("いいわけ の 記録", "#f4afc4");
      st.excuses.forEach(function (x) { push("　" + (x.fought ? "● " : "○ ") + x.text + (x.action ? " → " + x.action : ""), x.fought ? "#f4f1e8" : "#9aa0b4"); });
      push("");
    }
    if (st.policy) { push(NT.DATA.TEXT.tags.scroll + "：" + st.policy, "#f4d03f"); push(""); }
    push(""); push(TX().title + "　" + st.title, "#f4d03f"); push(TX().marks + "　" + st.marks + "/10", "#f4afc4"); push("");
    push(TX().thanks, "#f4f1e8"); push(""); push(""); push("NETTA BOY", "#5b5a66"); push("(C) 2026 NETTA GAME-BU", "#5b5a66");
    var out = [];
    lines.forEach(function (l) { T.wrap(l.s, 288).forEach(function (w) { out.push({ s: w, c: l.c }); }); });
    return out;
  }
  function tagLabel(id) { var t = (NT.DATA.VALUE_TAGS || []).filter(function (x) { return x[0] === id; })[0]; return t ? t[1] : id; }

  /* 来年の予定（④の人、③の場所）を日付順に */
  function nextQuests(st) {
    var out = [];
    ((st.quests.q4 || {}).people || []).forEach(function (p) { if (p.scheduledKey && p.date) out.push({ date: p.date, text: p.text + " と 会う" }); });
    ((st.quests.q3 || {}).places || []).forEach(function (p) { if (p.plannedKey && p.date) out.push({ date: p.date, text: p.text + " へ 行く" }); });
    out.sort(function (a, b) { return a.date < b.date ? -1 : 1; });
    return out;
  }

  NT.SceneEnding = function (mode) {
    var st = NT.State.cur, roll = [], y = 0, t = 0, finished = false, resultStep = 0, page = 0, nexts = [];
    var isBad = mode === "result" && st.marks < 3;
    function startLap() {
      NT.State.newLap();
      NT.Scenes.pop();
      if (NT.State.slot) NT.Save.writeTo(NT.State.slot);
      NT.Flow.startGame(false);
    }
    function afterResult() {
      if (isBad) {
        NT.Scenes.push(NT.Confirm(TX().badSub, startLap, function () { NT.Scenes.pop(); }, { yesLabel: TX().cont, noLabel: TX().stay, defaultYes: true, y: 170 }));
      } else {
        NT.Scenes.push(NT.Menu({ title: st.year + "年の 塔", w: 220, cancelable: false, items: [
          { label: TX().again, value: "lap" },
          { label: TX().stay, value: "stay" }
        ], onSelect: function (it) { NT.Scenes.pop(); if (it.value === "lap") startLap(); else NT.Scenes.pop(); } }));
      }
    }
    var scene = {
      id: "ENDING", opaque: true,
      enter: function () {
        roll = buildRoll(st); y = NT.H; t = 0; nexts = nextQuests(st);
        if (mode !== "result" && NT.DATA.SONGS) NT.Audio.startMusic(NT.DATA.SONGS.ending);
        st.flags.resultShown = true;
        if (mode === "true") { st.flags.trueEndSeen = true; NT.State.touch(); }
        if (isBad) NT.Audio.play("error");
      },
      exit: function () { NT.Audio.stopMusic(); },
      update: function (dt) {
        t += dt;
        if (mode === "result") {
          if (I.pressed("ok") || I.clicks().length) { I.consume("ok"); if (resultStep < 2) { resultStep++; NT.Audio.play("decide"); } else afterResult(); }
          return;
        }
        var speed = (I.held("ok") || I.held("down")) ? 0.22 : 0.03;
        if (!finished) {
          y -= dt * speed;
          if (y + roll.length * 16 < NT.H / 2) { finished = true; if (mode === "true") NT.Audio.play("rank"); }
        } else if (I.pressed("ok") || I.pressed("cancel") || I.clicks().length) {
          I.consume("ok"); I.consume("cancel");
          if (mode === "true" && page === 0) { page = 1; NT.Audio.play("decide"); return; }
          NT.Scenes.pop();
        }
      },
      draw: function (ctx) {
        NT.Screen.clear(mode === "true" && finished ? "#fff6d6" : "#000");
        if (mode === "result") {
          T.drawCenter(ctx, TX().result, NT.W / 2, 24, "#f4d03f", { head: true, size: 16 });
          T.drawCenter(ctx, st.year + "年の 塔は とじました", NT.W / 2, 52, "#9aa0b4");
          if (resultStep >= 0) T.drawCenter(ctx, TX().marks + "　" + st.marks + "/10", NT.W / 2, 90, "#f4afc4");
          if (resultStep >= 1) T.drawCenter(ctx, TX().title + "　" + st.title, NT.W / 2, 112, "#f4d03f");
          if (resultStep >= 2) {
            if (isBad) {
              T.drawLines(ctx, T.wrap(TX().bad, 280), 20, 134, "#f4afc4");
              T.draw(ctx, "しるしは あと " + (3 - st.marks) + "つ。教訓と 予定は 2しゅうめへ", 20, 150, "#f4f1e8");
            } else {
              T.drawLines(ctx, T.wrap("合格。塔の中は 来年まで あるける。2しゅうめ へ 進むと、年が ひとつ 進み、教訓・仲間・来年の予定を 引き継ぐ", 280), 20, 140, "#f4f1e8");
            }
          }
          if ((t % 1000) < 500) G.nextMark(ctx, NT.W - 20, NT.H - 14, "#f4d03f");
          return;
        }
        if (mode === "true" && finished) {
          /* 白い朝。NEXT QUEST */
          var ink = "#2e1a0b";
          if (page === 0) {
            T.drawCenter(ctx, TX().trueEnd, NT.W / 2, 60, ink, { head: true, size: 16 });
            T.drawCenter(ctx, TX().trueSub, NT.W / 2, 90, "#6e3b1f");
            if (NT.Sprites.ready) NT.Sprites.draw(ctx, "nekota:down:0:wave", NT.W / 2, 170);
            T.drawCenter(ctx, "Z で NEXT QUEST", NT.W / 2, NT.H - 20, "#9a7a5a");
          } else {
            T.drawCenter(ctx, TX().next, NT.W / 2, 16, ink, { head: true, size: 16 });
            ctx.fillStyle = "#d08a4f"; ctx.fillRect(40, 36, 240, 1);
            if (!nexts.length) T.drawCenter(ctx, "（来年の 予定は まだ 空いている。それも 自由）", NT.W / 2, 100, "#6e3b1f");
            nexts.slice(0, 9).forEach(function (n, i) {
              T.draw(ctx, n.date.slice(0, 4) + "/" + NT.Time.mmdd(n.date).replace("-", "/"), 40, 46 + i * 18, "#6e3b1f");
              T.draw(ctx, n.text, 130, 46 + i * 18, ink);
            });
            T.drawCenter(ctx, "― おわり ―", NT.W / 2, NT.H - 36, ink, { head: true, size: 16 });
            T.drawCenter(ctx, "Z で 塔に もどる", NT.W / 2, NT.H - 16, "#9a7a5a");
          }
          return;
        }
        for (var i = 0; i < roll.length; i++) {
          var ly = Math.round(y + i * 16);
          if (ly < -16 || ly > NT.H) continue;
          T.draw(ctx, roll[i].s, 16, ly, roll[i].c);
        }
        if (finished) T.drawCenter(ctx, "― おわり ―", NT.W / 2, NT.H / 2, "#f4d03f", { head: true, size: 16 });
        if (!finished) T.drawRight(ctx, "Z で はやおくり", NT.W - 8, NT.H - 14, "#5b5a66");
      },
      state: function () { return { mode: mode, finished: finished, page: page, isBad: isBad, nexts: nexts.length }; },
      skipRoll: function () { if (mode !== "result") { y = NT.H / 2 - roll.length * 16 - 1; } }
    };
    return scene;
  };
  /* 価値タグの儀式を経てから ED へ */
  function openEnding(mode) {
    NT.State.cur.flags.endingSeen = true; NT.State.touch();
    NT.Scenes.push(NT.SceneTags(function () { NT.Scenes.push(NT.SceneEnding(mode)); }));
  }
  NT.Dialog.hooks["ending.normal"] = function () { openEnding("normal"); return "stop"; };
  NT.Dialog.hooks["ending.true"] = function () { openEnding("true"); return "stop"; };
})();
