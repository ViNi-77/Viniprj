/* 塔の中を歩くシーン。HUD、話しかけ、石碑、エレベーター、扉、ゲーム内メニュー */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text, G = NT.Gfx, I = NT.Input, TILE = NT.TILE, TX = function () { return NT.DATA.TEXT; };

  NT.SceneMap = function () {
    var fade = 1, fadeDir = -1, noteTimer = 0, noteText = null, lastFloor = 0, toast = null;
    var scene = {
      id: "MAP", opaque: true,
      enter: function () {
        var st = NT.State.cur;
        if (st.pos) NT.Player.place(st.pos.x, st.pos.y, st.pos.dir);
        else { var sp = NT.Tilemap.spawn; NT.Player.place(sp.x, sp.y, "down"); }
        NT.Camera.center(NT.Player.px + 8, NT.Player.py + 8);
        NT.Player.onArrive = onArrive;
        fade = 1; fadeDir = -1;
        lastFloor = NT.Tilemap.floorAt(NT.Player.y);
        showCalendarNote();
      },
      resume: function () { NT.Input.reset(); },
      update: function (dt) {
        NT.State.tick(dt);
        if (noteTimer > 0) noteTimer -= dt;
        NT.Camera.update(dt);
        if (NT.Camera.busy()) return;
        NT.Entities.update(dt);
        NT.Player.update(dt);
        NT.Camera.follow(NT.Player.px + 8, NT.Player.py + 8);
        var cl = I.clicks();
        if (cl.length && !NT.Player.locked) {
          var c = cl[0];
          if (c.y >= NT.Camera.HUD) {
            var tx = Math.floor((c.x + NT.Camera.x) / TILE), ty = Math.floor((c.y + NT.Camera.y) / TILE);
            var e = NT.Entities.at(tx, ty);
            var adj = Math.abs(tx - NT.Player.x) + Math.abs(ty - NT.Player.y) === 1;
            if (e && adj) { faceTo(tx, ty); interact(); } else NT.Player.walkTo(tx, ty);
          }
        }
        if (I.pressed("ok") && !NT.Player.moving) { I.consume("ok"); interact(); }
        if (I.pressed("menu")) { I.consume("menu"); if (!NT.Player.moving) openMenu(); }
        var f = NT.Tilemap.floorAt(NT.Player.y);
        if (f !== lastFloor) { lastFloor = f; scene.toast(f + "F"); }
      },
      draw: function (ctx) {
        NT.Screen.clear("#000");
        var cam = NT.Camera;
        NT.Tilemap.draw(ctx, cam);
        /* 描画順：y の小さい順（奥から） */
        var drawables = NT.Entities.list.filter(NT.Entities.visible).map(function (e) { return { y: e.wy, fn: function () { drawOne(ctx, cam, e); } }; });
        drawables.push({ y: NT.Player.py / TILE + 0.01, fn: function () { NT.Player.draw(ctx, cam); } });
        drawables.sort(function (a, b) { return a.y - b.y; });
        drawables.forEach(function (d) { d.fn(); });
        drawHUD(ctx);
        if (noteTimer > 0 && noteText) {
          var lines = T.wrap(noteText, 280);
          var h = lines.length * 16 + 12;
          G.frame(ctx, 8, NT.H - h - 6, 304, h, { inner: false });
          T.drawLines(ctx, lines, 20, NT.H - h, "#f4f1e8");
        }
        if (toast && toast.t > 0) { T.drawCenter(ctx, toast.text, NT.W / 2, 28, "#f4d03f", { head: true, size: 16, shadow: true }); toast.t -= 16; }
        if (fade > 0) { G.fade(ctx, fade); fade = Math.max(0, fade - 0.06); }
      },
      toast: function (text) { toast = { text: text, t: 1200 }; },
      note: function (text) { noteText = text; noteTimer = 3600; }
    };
    function drawOne(ctx, cam, e) {
      /* 43_entities.draw は一括描画なので、ここでは1体ずつ */
      var saveList = NT.Entities.list; NT.Entities.list = [e]; NT.Entities.draw(ctx, cam); NT.Entities.list = saveList;
    }
    function faceTo(tx, ty) {
      var dx = tx - NT.Player.x, dy = ty - NT.Player.y;
      NT.Player.dir = dx > 0 ? "right" : dx < 0 ? "left" : dy > 0 ? "down" : "up";
    }
    function interact() {
      var f = NT.Player.facing();
      var e = NT.Entities.at(f.x, f.y);
      if (e && NT.Entities.visible(e)) {
        e.dir = { down: "up", up: "down", left: "right", right: "left" }[NT.Player.dir];
        NT.Entities.hop(e.id);
        NT.Dialog.open(e.dialog, { npc: e });
        return;
      }
      var ch = NT.Tilemap.at(f.x, f.y);
      if (ch === "M") { NT.Flow.openSave(); return; }
      if (ch === "D" && !(NT.State.cur.flags.doorOpen)) { NT.Dialog.open("d.door"); return; }
      if (ch === "B") { NT.Dialog.open("d.shelf"); return; }
      if (ch === "W") { NT.Dialog.open("d.window"); return; }
      if (ch === "F") { NT.Dialog.open(NT.Tilemap.isFlower(f.x, f.y) && isBloomed(f.x, f.y) ? "d.flower" : "d.pot"); return; }
    }
    function isBloomed(x, y) {
      var fl = NT.State.cur.flowers || {}, f = NT.Tilemap.floorAt(y);
      return (fl[f] || []).some(function (p) { return p[0] === x && p[1] === y; });
    }
    function onArrive(x, y) {
      var ch = NT.Tilemap.at(x, y);
      if (ch === "E") { NT.Flow.openElevator(); }
      NT.State.touch();
    }
    function showCalendarNote() {
      var n = NT.Time.calendarNote();
      if (n) scene.note(n);
    }
    function drawHUD(ctx) {
      var st = NT.State.cur, hud = TX().hud;
      ctx.fillStyle = "rgba(0,0,0,.82)"; ctx.fillRect(0, 0, NT.W, 16);
      ctx.fillStyle = "#3a3444"; ctx.fillRect(0, 16, NT.W, 1);
      var f = NT.Tilemap.floorAt(NT.Player.y);
      T.draw(ctx, f + "F", 6, 2, "#f4d03f");
      var phase = NT.State.phase();
      var left = NT.State.daysLeft();
      var s = phase === "over" ? hud.over : NT.Util.fmt(hud.daysLeft, { n: left });
      T.draw(ctx, s, 34, 2, phase === "final" ? "#f4d03f" : "#f4f1e8");
      if (phase === "dec" || phase === "final") T.draw(ctx, NT.Util.fmt(hud.feel, { n: NT.State.feelDays() }), 34 + T.measure(s) + 8, 2, "#9aa0b4");
      var marks = NT.Util.fmt(hud.marks, { n: st.marks });
      T.drawRight(ctx, marks, NT.W - 18, 2, "#f4afc4");
      if (NT.State.dirty) T.draw(ctx, hud.unsaved, NT.W - 12, 2, "#f4d03f");
      if (phase === "final") { ctx.fillStyle = "#f4d03f"; ctx.fillRect(0, 17, NT.W, 1); }
    }
    function openMenu() {
      NT.Audio.play("open");
      var tx = TX();
      var items = [
        { label: "クエスト", value: "quests" },
        { label: tx.save.title, value: "save" },
        { label: tx.card.title, value: "card" },
        { label: tx.settings.title, value: "settings" },
        { label: tx.power.title, value: "power" },
        { label: tx.menu.close, value: "close" }
      ];
      NT.Scenes.push(NT.Menu({
        x: 180, y: 24, w: 132, items: items, title: NT.State.cur.name + "　" + NT.State.cur.title,
        onSelect: function (it) {
          if (it.value === "close") { NT.Scenes.pop(); return; }
          if (it.value === "quests") { NT.Scenes.pop(); NT.Flow.openQuestList(); }
          else if (it.value === "save") { NT.Scenes.pop(); NT.Flow.openSave(); }
          else if (it.value === "card") { NT.Scenes.pop(); NT.Flow.openCard(); }
          else if (it.value === "settings") { NT.Scenes.pop(); NT.Flow.openSettings(); }
          else if (it.value === "power") { NT.Scenes.pop(); NT.Flow.powerOff(); }
        }
      }));
    }
    return scene;
  };
})();
