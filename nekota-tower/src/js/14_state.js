/* ゲーム状態。セーブはこの state を丸ごと JSON にしたもの */
(function () {
  "use strict";
  var NT = window.NT;
  var S = NT.State = { cur: null, dirty: false, playMs: 0, seq: 0, slot: 0, loadedFrom: null };
  var listeners = [];

  S.TITLES = [[10, "人生最高の余暇"], [8, "けんじゃ"], [5, "ゆうしゃ"], [3, "ぼうけんしゃ"], [1, "みならい"], [0, "たびびと"]];
  S.titleFor = function (n) { for (var i = 0; i < S.TITLES.length; i++) if (n >= S.TITLES[i][0]) return S.TITLES[i][1]; return "たびびと"; };

  S.newGame = function (name) {
    var key = NT.Time.jstKey();
    var quests = {};
    Object.keys(NT.DATA.QUESTS || {}).forEach(function (id) { quests[id] = { status: "offered" }; });
    S.cur = {
      name: name || "ねこ太のともだち",
      startedKey: key, lastKey: key, year: NT.Time.yearOf(key),
      pos: null, floor: 10,
      flags: { prologueDone: false, doorOpen: false, clockSuspect: false, resultShown: false, tutorialDone: false },
      clears: [], marks: 0, title: "たびびと",
      flowers: {},
      quests: quests,
      lessons: [], log: [],
      lap: 1
    };
    S.playMs = 0; S.seq = 0; S.dirty = false; S.slot = 0; S.loadedFrom = "new";
    S.recompute();
    return S.cur;
  };

  S.load = function (rec, slot) {
    S.cur = rec.state;
    S.playMs = rec.playMs || 0;
    S.seq = rec.seq || 0;
    S.slot = slot || 0;
    S.dirty = false;
    S.loadedFrom = "slot";
    if (!S.cur.flags) S.cur.flags = {};
    if (!S.cur.quests) S.cur.quests = {};
    Object.keys(NT.DATA.QUESTS || {}).forEach(function (id) { if (!S.cur.quests[id]) S.cur.quests[id] = { status: "offered" }; });
    if (NT.Time.clockSuspect(rec)) S.cur.flags.clockSuspect = true;
    S.recompute();
    return S.cur;
  };

  /* 2周目：教訓・仲間・来年の予定を引き継ぎ、年を +1 して塔を作り直す */
  S.newLap = function () {
    var old = S.cur; if (!old) return null;
    var carry = { lessons: (old.lessons || []).slice(), friends: [], plans: [], lastYear: old.year, lastMarks: old.marks, lastTitle: old.title, excuses: (old.excuses || []).length };
    var q4 = old.quests.q4 || {}, q3 = old.quests.q3 || {};
    (q4.people || []).forEach(function (p) { if (p.scheduledKey) carry.friends.push({ text: p.text, date: p.date || "" }); });
    (q3.places || []).forEach(function (p) { if (p.plannedKey) carry.plans.push({ text: p.text, date: p.date || "" }); });
    (old.carry && old.carry.friends || []).forEach(function (f) { if (!carry.friends.some(function (x) { return x.text === f.text; })) carry.friends.push(f); });
    var quests = {};
    Object.keys(NT.DATA.QUESTS || {}).forEach(function (id) { quests[id] = { status: "offered" }; });
    var key = NT.Time.jstKey();
    S.cur = {
      name: old.name, startedKey: key, lastKey: key, year: Math.max(old.year + 1, NT.Time.yearOf(key)),
      pos: null, floor: 10,
      flags: { prologueDone: true, doorOpen: false, clockSuspect: false, resultShown: false, tutorialDone: true, lapIntro: false },
      clears: [], marks: 0, title: "たびびと",
      flowers: {}, quests: quests,
      lessons: [], log: [], excuses: [],
      lap: (old.lap || 1) + 1, carry: carry
    };
    S.recompute();
    S.setDirty(true);
    return S.cur;
  };

  S.toRecord = function () {
    S.seq++;
    return {
      v: NT.SAVE_VERSION, app: NT.APP, build: NT.BUILD,
      savedAt: new Date(NT.Time.now()).toISOString(),
      seq: S.seq, playMs: Math.round(S.playMs),
      state: NT.Util.deepClone(S.cur)
    };
  };

  S.setDirty = function (v) {
    var was = S.dirty;
    S.dirty = v !== false;
    if (was !== S.dirty) listeners.forEach(function (f) { f(S.dirty); });
  };
  S.onDirty = function (f) { listeners.push(f); };
  S.touch = function () { S.setDirty(true); };

  S.clearCount = function () { return S.cur ? S.cur.clears.length : 0; };
  S.recompute = function () {
    var c = S.cur; if (!c) return;
    c.marks = c.clears.length;
    c.title = S.titleFor(c.marks);
    c.doorWasOpen = c.flags.doorOpen;
    c.flags.doorOpen = c.marks >= 3;
    var today = NT.Time.jstKey();
    if (today > (c.lastKey || "")) c.lastKey = today;
  };
  S.addLog = function (ev, text) {
    if (!S.cur) return;
    S.cur.log.push({ t: new Date(NT.Time.now()).toISOString(), k: NT.Time.jstKey(), ev: ev, text: text || "" });
    if (S.cur.log.length > 400) S.cur.log.shift();
    S.touch();
  };
  S.addLesson = function (q, text) {
    if (!S.cur || !text) return;
    S.cur.lessons.push({ q: q, text: text, k: NT.Time.jstKey() });
    S.touch();
  };
  S.tick = function (dt) { if (S.cur) S.playMs += dt; };
  S.playTimeText = function (ms) {
    ms = ms === undefined ? S.playMs : ms;
    var s = Math.floor(ms / 1000), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    return h + ":" + NT.Util.pad2(m) + ":" + NT.Util.pad2(s % 60);
  };
  S.phase = function () { return NT.Time.phase(NT.Time.jstKey(), S.cur ? S.cur.year : undefined); };
  S.daysLeft = function () { return NT.Time.daysLeft(NT.Time.jstKey(), S.cur ? S.cur.year : undefined); };
  S.feelDays = function () { return NT.Time.feelDays(NT.Time.jstKey(), S.cur ? S.cur.year : undefined); };
})();
