/* 起動配線と画面間の流れ（NT.Flow）。デバッグ用の窓口 window.__NEKOTA もここ */
(function () {
  "use strict";
  var NT = window.NT;
  var F = NT.Flow = NT.Flow || {};
  var T = NT.Text, G = NT.Gfx, I = NT.Input;

  function banner(msg) {
    var b = document.getElementById("banner");
    if (!b) { b = document.createElement("div"); b.id = "banner"; document.body.appendChild(b); }
    b.textContent = msg; b.classList.add("show");
  }

  /* ---- 画面の流れ ---- */
  F.toTitle = function () { NT.Scenes.reset(NT.SceneTitle()); };

  F.newGame = function () {
    NT.Scenes.push(NT.SceneName({
      onDone: function (name) {
        NT.Scenes.push(NT.SceneSlot({ mode: "new", onPick: function (n) {
          NT.State.newGame(name);
          NT.State.slot = n;
          NT.Save.writeTo(n);
          F.startGame(true);
        } }));
      }
    }));
  };
  F.openSlots = function () {
    NT.Scenes.push(NT.SceneSlot({ mode: "load", onPick: function (n, rec) {
      NT.State.load(rec, n);
      if (n === 0) NT.State.setDirty(true); /* ちゅうだんデータは未保存扱い */
      F.startGame(false);
    } }));
  };
  F.startGame = function (fresh) {
    NT.Scenes.reset(NT.SceneMap());
    var st = NT.State.cur;
    if (NT.State.phase() === "over" && !st.flags.resultShown) { NT.Scenes.push(NT.SceneEnding("result")); return; }
    if (fresh || !st.flags.prologueDone) NT.Dialog.open("d.prologue");
    else if (st.lap > 1 && !st.flags.lapIntro) { st.flags.lapIntro = true; NT.Dialog.open("d.lap2"); }
    else if (st.flags.clockSuspect) NT.Scenes.push(NT.Notice(NT.DATA.TEXT.quest.frozen));
  };
  F.openQuest = function (id, tab) {
    var open = function () { NT.Scenes.push(NT.SceneQuest(id, tab)); };
    if (NT.Excuse && NT.Excuse.shouldAppear(id)) NT.Scenes.push(NT.SceneExcuse(id, open)); else open();
  };
  F.openQuestList = function () {
    var items = NT.DATA.QUEST_ORDER.map(function (id) {
      var def = NT.DATA.QUESTS[id], st = NT.Quests.state(id);
      var note = !def.implemented ? "" : st.status === "cleared" ? "クリア" : st.status === "offered" ? "" : NT.Quests.progressText(id);
      return { label: def.num + " " + def.title, value: id, note: note, disabled: !def.implemented || st.status === "offered", color: st.status === "cleared" ? "#7dffb0" : undefined };
    });
    items.push({ label: NT.DATA.TEXT.menu.back, value: null });
    NT.Scenes.push(NT.Menu({ x: 8, y: 20, w: 304, title: "クエスト", items: items, lh: 16, onSelect: function (it) { NT.Scenes.pop(); if (it.value) F.openQuest(it.value, "prep"); } }));
  };
  F.openElevator = function () {
    var cur = NT.Tilemap.floorAt(NT.Player.y);
    var items = [];
    for (var f = 10; f >= 1; f--) {
      var locked = f === 1 && !NT.State.cur.flags.doorOpen;
      items.push({ label: NT.Util.fmt(NT.DATA.TEXT.elevator.floor, { n: f }), value: f, disabled: f === cur || locked, note: locked ? "とざされている" : (f === cur ? "いまここ" : "") });
    }
    items.push({ label: NT.DATA.TEXT.menu.back, value: 0 });
    NT.Audio.play("open");
    NT.Scenes.push(NT.Menu({ x: 200, y: 24, w: 112, title: NT.DATA.TEXT.elevator.title, items: items, index: Math.max(0, 10 - cur + (cur === 10 ? 1 : -1)),
      onSelect: function (it) {
        NT.Scenes.pop();
        if (!it.value) { NT.Player.tryMove(1, 0); return; }
        var spot = NT.DATA.MAP.elevatorSpot(it.value);
        NT.Player.locked = true;
        NT.Audio.play("elevator");
        NT.Camera.panTo(spot.x * NT.TILE + 8, spot.y * NT.TILE + 8, 700, function () {
          NT.Player.place(spot.x, spot.y, "right");
          NT.Player.locked = false;
          NT.State.touch();
          var m = NT.Scenes.find("MAP"); if (m) m.toast(it.value + "F");
        });
      },
      onCancel: function () { NT.Scenes.pop(); NT.Player.tryMove(1, 0); }
    }));
  };
  F.openSettings = function () {
    var S = NT.Settings, tx = NT.DATA.TEXT.settings;
    function items() {
      var sp = S.SPEEDS[S.get("msgSpeed")] || S.SPEEDS[1];
      return [
        { label: tx.msgSpeed, value: "msgSpeed", note: sp.label },
        { label: tx.sfx, value: "sfx", note: S.get("sfx") ? tx.on : tx.off },
        { label: tx.crt, value: "crt", note: S.get("crt") ? tx.on : tx.off },
        { label: tx.scale, value: "scaleMode", note: S.get("scaleMode") === "device" ? tx.scaleDevice : tx.scaleCss },
        { label: tx.motion, value: "reduceMotion", note: S.get("reduceMotion") ? tx.reduce : tx.on },
        { label: NT.DATA.TEXT.menu.back, value: "back" }
      ];
    }
    var m = NT.Menu({ x: 40, y: 50, w: 240, title: tx.title, items: items(), onSelect: function (it, idx, menu) {
      if (it.value === "back") { NT.Scenes.pop(); return; }
      if (it.value === "msgSpeed") S.set("msgSpeed", (S.get("msgSpeed") + 1) % S.SPEEDS.length);
      else if (it.value === "scaleMode") S.set("scaleMode", S.get("scaleMode") === "device" ? "css" : "device");
      else S.set(it.value, !S.get(it.value));
      menu.items = items();
    } });
    m.id = "SETTINGS";
    NT.Scenes.push(m);
  };
  F.powerOff = function () {
    var go = function () {
      NT.Audio.play("close");
      NT.Interlock.disarm();
      NT.State.cur = null; NT.State.setDirty(false);
      F.toTitle();
    };
    if (NT.State.dirty) NT.Scenes.push(NT.Confirm(NT.DATA.TEXT.power.confirm, go, null, {}));
    else go();
  };

  /* ---- 起動 ---- */
  function boot() {
    NT.Screen.init();
    NT.Storage.probe();
    NT.Settings.load();
    NT.Input.install(NT.Screen.canvas);
    NT.Tilemap.init();
    NT.Entities.init();
    NT.Interlock.install();
    if (!NT.Storage.available) banner(NT.DATA.TEXT.sys.storageFail);
    NT.Fonts.load().then(function () { if (!NT.Fonts.ok) console.warn("fonts:", NT.DATA.TEXT.sys.fontFail); });
    NT.Sprites.load();
    var bootScene = NT.SceneBoot({ onDone: function () {
      Promise.all([NT.Fonts.load(), NT.Sprites.load()]).then(function () { F.toTitle(); });
    } });
    NT.Scenes.reset(bootScene);
    if (NT.query.fast) { bootScene.power(); bootScene.skip(); }
    NT.Loop.start();
    try { NT.Screen.canvas.focus({ preventScroll: true }); } catch (e) { /* 無視 */ }
    window.addEventListener("error", function (ev) { if (NT.debug) banner("エラー: " + (ev.message || ev)); });
  }

  /* ---- デバッグ・テスト用の窓口 ---- */
  window.__NEKOTA = {
    build: NT.BUILD,
    state: function () { return NT.State.cur; },
    dirty: function () { return NT.State.dirty; },
    scene: function () { return NT.Scenes.top() ? NT.Scenes.top().id : null; },
    scenes: function () { return NT.Scenes.ids(); },
    todayKey: function () { return NT.Time.jstKey(); },
    phase: function () { return NT.State.phase(); },
    skipBoot: function () { var s = NT.Scenes.find("BOOT"); if (s) { s.power(); s.skip(); } },
    startTitle: function () { var s = NT.Scenes.find("TITLE"); if (s && s.start) s.start(); },
    setClears: function (n) {
      var st = NT.State.cur; if (!st) return;
      st.clears = NT.DATA.QUEST_ORDER.slice(0, n);
      st.clears.forEach(function (id) { NT.Quests.state(id).status = "cleared"; });
      NT.State.recompute(); NT.State.touch();
    },
    press: function (a) { NT.Input.press(a); },
    click: function (x, y) { NT.Input.click(x, y); },
    step: function (n) { NT.Loop.stepManual(n); },
    player: function () { return { x: NT.Player.x, y: NT.Player.y, dir: NT.Player.dir, floor: NT.Tilemap.floorAt(NT.Player.y) }; },
    teleport: function (x, y) { NT.Player.place(x, y); NT.Camera.center(NT.Player.px + 8, NT.Player.py + 8); },
    dialog: function () { var d = NT.Scenes.find("DIALOG"); return d ? d.state() : null; },
    endDialog: function () { var d = NT.Scenes.find("DIALOG"); if (d) d.end(); },
    choose: function (i) { var d = NT.Scenes.find("DIALOG"); if (d) d.choose(i); },
    inputbox: function () { return NT.InputBox.active ? { title: NT.InputBox.active.title, value: NT.InputBox.active.el.value } : null; },
    typeInput: function (v) { NT.InputBox.setValue(v); NT.InputBox.submit(); },
    cardStatus: function () { var c = NT.Scenes.find("CARD"); return c ? c.status() : null; },
    lastExport: function () { return NT.Card.lastExport; },
    importText: function (t) { NT.Card.importFile(new File([t], "card.csv", { type: "text/csv" })); },
    storage: function () { return { available: NT.Storage.available, reason: NT.Storage.reason }; },
    fonts: function () { return { ready: NT.Fonts.ready, ok: NT.Fonts.ok, check: NT.Fonts.check() }; },
    sprites: function () { return { ready: NT.Sprites.ready, failed: NT.Sprites.failed }; },
    screen: function () { return { scale: NT.Screen.scale, cssScale: NT.Screen.cssScale, mode: NT.Screen.mode }; },
    quests: function () { return NT.Quests; },
    goto: function (id) { if (id === "ending") NT.Scenes.push(NT.SceneEnding("normal")); if (id === "true") NT.Scenes.push(NT.SceneEnding("true")); if (id === "result") NT.Scenes.push(NT.SceneEnding("result")); if (id === "bar") NT.Flow.openBar(); if (id === "tags") NT.Scenes.push(NT.SceneTags(function () {})); },
    newLap: function () { NT.State.newLap(); },
    excuse: function (id) { NT.Scenes.push(NT.SceneExcuse(id || "q10", function () {})); },
    top: function () { var s = NT.Scenes.top(); return s && s.state ? s.state() : null; },
    skipRoll: function () { var s = NT.Scenes.find("ENDING"); if (s && s.skipRoll) s.skipRoll(); },
    NT: NT
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
