/* 酒場。メモリーカードを持ちよって、みんなの達成を並べる。加算だけで順位は付けない。本体メモリの きろく も並ぶ */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text, G = NT.Gfx, I = NT.Input, TX = function () { return NT.DATA.TEXT.bar; };

  NT.SceneBar = function () {
    var rows = [], status = "", busy = false, scroll = 0, t = 0;
    function addRec(rec, source) {
      var st = rec.state; if (!st) return;
      var cleared = {};
      NT.DATA.QUEST_ORDER.forEach(function (id) { cleared[id] = !!(st.quests && st.quests[id] && st.quests[id].status === "cleared") || (st.clears || []).indexOf(id) >= 0; });
      var row = { name: st.name, title: st.title, marks: st.marks || 0, cleared: cleared, savedAt: (rec.savedAt || "").slice(0, 10), year: st.year, source: source };
      var i = rows.findIndex(function (r) { return r.name === row.name && r.year === row.year; });
      if (i >= 0) { if (rows[i].savedAt <= row.savedAt) rows[i] = row; } else rows.push(row);
      rows.sort(function (a, b) { return a.name < b.name ? -1 : a.name > b.name ? 1 : 0; });
    }
    function loadLocal() { for (var n = 1; n <= 3; n++) { var r = NT.Storage.readSlot(n); if (r && r.rec) addRec(r.rec, "きろく" + n); } }
    function onFileText(text) {
      busy = true;
      NT.Codec.decodeCard(text).then(function (entries) {
        busy = false;
        entries.forEach(function (e) { var m = NT.Storage.migrate(e.record); if (m && m.rec) addRec(m.rec, "カード"); });
        status = entries.length + " 件 よみこんだ"; NT.Audio.play("save");
      }).catch(function (err) {
        busy = false;
        if (err && err.code === "auth") {
          NT.InputBox.open({ x: 24, y: 70, w: 272, maxLen: 32, title: NT.DATA.TEXT.card.passPrompt, onDone: function (pw) {
            if (!pw) { status = NT.DATA.TEXT.card.bad; return; }
            busy = true;
            NT.Codec.decodeCard(text, { password: pw }).then(function (entries) { busy = false; entries.forEach(function (e) { var m = NT.Storage.migrate(e.record); if (m && m.rec) addRec(m.rec, "カード"); }); status = entries.length + " 件 よみこんだ"; NT.Audio.play("save"); })
              .catch(function () { busy = false; status = NT.DATA.TEXT.card.bad; NT.Audio.play("error"); });
          } });
          return;
        }
        status = NT.DATA.TEXT.card.bad; NT.Audio.play("error");
      });
    }
    var scene = {
      id: "BAR", opaque: true,
      enter: function () { NT.Card.installDrop(); loadLocal(); },
      update: function (dt) {
        t += dt;
        if (I.pressed("cancel")) { I.consume("cancel"); NT.Audio.play("close"); NT.Scenes.pop(); return; }
        if (I.pressed("ok")) { I.consume("ok"); if (!busy) NT.Card.pickFile(); return; }
        if (I.pressed("down")) scroll = Math.min(Math.max(0, rows.length * 18 - 110), scroll + 18);
        if (I.pressed("up")) scroll = Math.max(0, scroll - 18);
        var cl = I.clicks();
        if (cl.length && cl[0].y > NT.H - 20) { NT.Scenes.pop(); return; }
        if (cl.length && cl[0].y < 40) NT.Card.pickFile();
      },
      draw: function (ctx) {
        NT.Screen.clear("#1a1008");
        ctx.fillStyle = "#2e1a0b"; ctx.fillRect(0, 0, NT.W, 28);
        T.draw(ctx, TX().title, 10, 6, "#f4d03f", { head: true, size: 16 });
        T.drawRight(ctx, "Z: " + TX().load, NT.W - 10, 8, "#d08a4f");
        /* 見出し行 */
        var y0 = 36;
        T.draw(ctx, "なまえ", 12, y0, "#9aa0b4");
        for (var c = 0; c < 10; c++) T.draw(ctx, String(10 - c === 10 ? "⑩" : ["①","②","③","④","⑤","⑥","⑦","⑧","⑨"][10 - c - 1]), 110 + c * 16, y0, "#9aa0b4");
        T.drawRight(ctx, TX().cols, NT.W - 12, y0, "#9aa0b4");
        ctx.fillStyle = "#6e3b1f"; ctx.fillRect(8, y0 + 14, NT.W - 16, 1);
        ctx.save(); ctx.beginPath(); ctx.rect(0, y0 + 16, NT.W, NT.H - y0 - 16 - 40); ctx.clip();
        if (!rows.length) T.drawLines(ctx, T.wrap(TX().empty, 280), 20, y0 + 30, "#9aa0b4");
        rows.forEach(function (r, i) {
          var y = y0 + 20 + i * 18 - scroll;
          var nm = r.name; while (T.measure(nm) > 84 && nm.length) nm = nm.slice(0, -1);
          T.draw(ctx, nm, 12, y, "#f4f1e8");
          NT.DATA.QUEST_ORDER.forEach(function (id, c) { T.draw(ctx, r.cleared[id] ? "●" : "○", 110 + c * 16, y, r.cleared[id] ? "#f4d03f" : "#5b5a66"); });
          T.drawRight(ctx, r.marks + "/10", NT.W - 12, y, "#f4afc4");
        });
        ctx.restore();
        ctx.fillStyle = "#2e1a0b"; ctx.fillRect(0, NT.H - 40, NT.W, 40);
        T.drawLines(ctx, T.wrap(status || TX().lead, 280), 12, NT.H - 36, "#d08a4f", undefined, 14);
        T.drawRight(ctx, "X:とじる", NT.W - 8, NT.H - 14, "#9a7a5a");
        if (busy) T.drawCenter(ctx, NT.DATA.TEXT.sys.loading + "…", NT.W / 2, 100, "#f4f1e8");
        NT.InputBox.draw(ctx);
      },
      onFileText: onFileText,
      rows: function () { return rows.map(function (r) { return { name: r.name, marks: r.marks, source: r.source }; }); },
      status: function () { return status; }
    };
    return scene;
  };
  NT.Flow = NT.Flow || {};
  NT.Flow.openBar = function () { NT.Scenes.push(NT.SceneBar()); };
})();
