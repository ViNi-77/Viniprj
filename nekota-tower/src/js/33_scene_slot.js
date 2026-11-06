/* きろく（セーブスロット）の選択。mode: 'load' | 'save' | 'new' */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text, G = NT.Gfx, I = NT.Input, TX = function () { return NT.DATA.TEXT.slot; };

  NT.SceneSlot = function (opts) {
    var mode = opts.mode, index = 0, slots = [], suspend = null, askedSuspend = false, note = null;
    function readAll() {
      slots = [];
      for (var n = 1; n <= 3; n++) {
        var r = NT.Storage.readSlot(n);
        slots.push(r && r.rec ? r.rec : null);
      }
      var s = NT.Storage.readSuspend();
      suspend = s && s.rec ? s.rec : null;
    }
    function rowY(i) { return 40 + i * 52; }
    function pick(i) {
      var rec = slots[i], n = i + 1;
      if (mode === "load") {
        if (!rec) { NT.Audio.play("error"); return; }
        NT.Audio.play("decide");
        NT.Scenes.pop({ slot: n, rec: rec });
        if (opts.onPick) opts.onPick(n, rec);
        return;
      }
      /* save / new：上書き確認 */
      var go = function () { NT.Scenes.pop({ slot: n }); if (opts.onPick) opts.onPick(n, rec); };
      if (rec) { NT.Audio.play("decide"); NT.Scenes.push(NT.Confirm(NT.Util.fmt(TX().overwrite, { n: n }), go, null, { y: 150 })); }
      else { NT.Audio.play("decide"); go(); }
    }
    var scene = {
      id: "SLOT", opaque: true,
      enter: function () {
        readAll();
        if (mode === "load") { for (var i = 0; i < 3; i++) if (slots[i]) { index = i; break; } }
        if (mode === "save" && NT.State.slot) index = NT.State.slot - 1;
        if (mode === "load" && suspend && !askedSuspend) {
          askedSuspend = true;
          NT.Scenes.push(NT.Confirm(TX().suspend, function () {
            NT.Scenes.pop({ slot: 0, rec: suspend });
            if (opts.onPick) opts.onPick(0, suspend);
          }, function () { NT.Storage.clearSuspend(); suspend = null; }, { y: 150 }));
        }
        if (!NT.Storage.available) note = NT.DATA.TEXT.save.fail;
      },
      resume: function () { readAll(); },
      update: function () {
        if (I.pressed("up")) { index = (index + 2) % 3; NT.Audio.play("cursor"); }
        if (I.pressed("down")) { index = (index + 1) % 3; NT.Audio.play("cursor"); }
        if (I.pressed("ok")) { I.consume("ok"); pick(index); return; }
        if (I.pressed("cancel")) { I.consume("cancel"); NT.Audio.play("cancel"); NT.Scenes.pop(null); if (opts.onCancel) opts.onCancel(); return; }
        var cl = I.clicks();
        for (var k = 0; k < cl.length; k++) for (var i = 0; i < 3; i++) if (cl[k].y >= rowY(i) && cl[k].y < rowY(i) + 46) { index = i; pick(i); return; }
      },
      draw: function (ctx) {
        NT.Screen.clear("#070716");
        T.drawCenter(ctx, TX().title, NT.W / 2, 14, "#f4d03f");
        for (var i = 0; i < 3; i++) {
          var y = rowY(i), rec = slots[i];
          G.frame(ctx, 16, y, 288, 46, { innerColor: i === index ? "#f4d03f" : "#3a3444" });
          T.draw(ctx, "きろく " + (i + 1), 30, y + 8, "#9aa0b4");
          if (rec) {
            var st = rec.state;
            T.draw(ctx, st.name, 92, y + 8, "#f4f1e8");
            T.draw(ctx, st.title, 92 + T.measure(st.name) + 8, y + 8, "#f4afc4");
            T.draw(ctx, TX().marks + " " + st.marks + "/10", 30, y + 26, "#f4d03f");
            T.draw(ctx, TX().play + " " + NT.State.playTimeText(rec.playMs || 0), 130, y + 26, "#9aa0b4");
            T.drawRight(ctx, (rec.savedAt || "").slice(0, 10), 292, y + 26, "#5b5a66");
            T.drawRight(ctx, st.floor ? st.floor + "F" : "", 292, y + 8, "#9aa0b4");
          } else {
            T.draw(ctx, TX().empty, 92, y + 8, "#5b5a66");
          }
          if (i === index) G.cursor(ctx, 20, y + 10, "#f4d03f");
        }
        var ml = T.wrap(note || NT.DATA.TEXT.save.memoryNote, 296);
        T.drawLines(ctx, ml, 12, 202, note ? "#f4afc4" : "#5b5a66", undefined, 14);
      }
    };
    return scene;
  };
})();
