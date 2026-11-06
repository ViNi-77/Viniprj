/* クエストエンジン。状態の遷移、条件の評価、クリアの儀式 */
(function () {
  "use strict";
  var NT = window.NT;
  var Q = NT.Quests = {};
  var TX = function () { return NT.DATA.TEXT.quest; };

  Q.def = function (id) { return NT.DATA.QUESTS[id]; };
  Q.state = function (id) {
    var st = NT.State.cur;
    if (!st.quests[id]) st.quests[id] = { status: "offered" };
    return st.quests[id];
  };
  Q.status = function (id) { return Q.state(id).status; };

  Q.accept = function (id) {
    var q = Q.state(id);
    if (q.status !== "offered") return false;
    q.status = "accepted";
    q.acceptedKey = NT.Time.jstKey();
    q.plan = q.plan || { when: "", where: "", how: "", obstacle: "" };
    var def = Q.def(id);
    if (def.prep && def.prep.list) q[def.prep.list.kind] = q[def.prep.list.kind] || [];
    if (def.exec && def.exec.charms) q.charms = def.exec.charms;
    q.checks = q.checks || []; q.charmUsed = q.charmUsed || [];
    NT.State.addLog(id + ".accept", def.title);
    return true;
  };

  /* ---- 条件表 ---- */
  Q.today = function () { return NT.Time.jstKey(); };
  Q.doneEntries = function (q) { return (q.entries || []).filter(function (e) { return e.doneKey; }); };
  /* 連続日数。きょう（またはきのう）から さかのぼる。お守りの日も数える */
  Q.streak = function (q) {
    var set = {};
    (q.checks || []).forEach(function (k) { set[k] = true; });
    (q.charmUsed || []).forEach(function (k) { set[k] = true; });
    var k = Q.today();
    if (!set[k]) k = NT.Time.prevKey(k);
    var n = 0, guard = 0;
    while (set[k] && guard++ < 400) { n++; k = NT.Time.prevKey(k); }
    return n;
  };
  Q.streakThrough = function (q, mmdd) {
    var year = NT.State.cur.year, end = year + "-" + mmdd;
    if (Q.today() < end) return false;
    var set = {};
    (q.checks || []).concat(q.charmUsed || []).forEach(function (k) { set[k] = true; });
    if (!q.declared) return false;
    var k = q.declared.startKey;
    var guard = 0;
    while (k <= end && guard++ < 400) { if (!set[k]) return false; k = NT.Time.nextKey(k); }
    return true;
  };
  var ATOMS = {
    doneCount: function (q, op, v) { return cmp(Q.doneEntries(q).length, op, v); },
    doneTag: function (q, tag) { return Q.doneEntries(q).some(function (e) { return e.tag === tag; }); },
    lesson: function (q) { return !!(q.lesson && q.lesson.trim()); },
    declared: function (q) { return !!q.declared; },
    streak: function (q, op, v) { return cmp(Q.streak(q), op, v); },
    reason: function (q) { return !!(q.declared && q.declared.reason && q.declared.reason.trim()); },
    streakThrough: function (q, mmdd) { return Q.streakThrough(q, mmdd); }
  };
  function cmp(a, op, b) { return op === ">=" ? a >= b : op === ">" ? a > b : op === "==" ? a === b : op === "<=" ? a <= b : a < b; }
  Q.evalCond = function (q, c) {
    var fn = ATOMS[c[0]];
    if (!fn) return false;
    return !!fn(q, c[1], c[2]);
  };
  /* [{label, ok}] */
  Q.conditions = function (id) {
    var def = Q.def(id), q = Q.state(id);
    return (def.clear || []).map(function (c) { return { label: c[3] || c[0], ok: Q.evalCond(q, c) }; });
  };
  Q.bonuses = function (id) {
    var def = Q.def(id), q = Q.state(id);
    return (def.bonus || []).map(function (c) { return { label: c[3] || c[0], ok: Q.evalCond(q, c) }; });
  };
  Q.isReportable = function (id) {
    var def = Q.def(id);
    if (!def || !def.implemented) return false;
    var q = Q.state(id);
    if (q.status === "cleared" || q.status === "offered") return false;
    return Q.conditions(id).every(function (c) { return c.ok; });
  };
  Q.progressText = function (id) {
    var q = Q.state(id), def = Q.def(id);
    if (!def.implemented) return TX().preparing;
    if (q.status === "cleared") return TX().cleared;
    if (q.status === "offered") return "";
    var cs = Q.conditions(id), n = cs.filter(function (c) { return c.ok; }).length;
    return n + "/" + cs.length;
  };

  /* ---- 実行コマンド ---- */
  Q.canCheckToday = function (q) {
    var st = NT.State.cur;
    if (st.flags.clockSuspect) return { ok: false, why: TX().frozen };
    if (!q.declared) return { ok: false, why: TX().needMore };
    var k = Q.today();
    if ((q.checks || []).indexOf(k) >= 0 || (q.charmUsed || []).indexOf(k) >= 0) return { ok: false, why: TX().checked };
    if (q.declared.startKey && k < q.declared.startKey) return { ok: false, why: TX().needMore };
    return { ok: true };
  };
  Q.checkToday = function (id) {
    var q = Q.state(id), can = Q.canCheckToday(q);
    if (!can.ok) return can;
    q.checks.push(Q.today());
    q.status = "doing";
    NT.State.addLog(id + ".check", Q.def(id).title);
    NT.Audio.play("item"); NT.Loop.freeze(4);
    return { ok: true, streak: Q.streak(q) };
  };
  Q.useCharm = function (id) {
    var q = Q.state(id);
    if (!q.declared) return { ok: false, why: TX().needMore };
    if (!(q.charms > 0)) return { ok: false, why: NT.Util.fmt(TX().charmLeft, { n: 0 }) };
    var k = Q.today();
    if (q.checks.indexOf(k) >= 0 || q.charmUsed.indexOf(k) >= 0) return { ok: false, why: TX().checked };
    q.charms--; q.charmUsed.push(k);
    NT.State.addLog(id + ".charm", "");
    NT.Audio.play("save");
    return { ok: true };
  };
  Q.declare = function (id, text, reason) {
    var q = Q.state(id);
    q.declared = { text: text, reason: reason || "", startKey: Q.today() };
    q.status = "doing";
    NT.State.addLog(id + ".declare", text);
    NT.Audio.play("accept"); NT.Loop.freeze(6);
  };
  Q.markDone = function (id, entry, cmd) {
    var q = Q.state(id);
    entry.doneKey = Q.today();
    entry.undoUntil = NT.Loop.elapsed + 60000;
    q.status = "doing";
    NT.State.addLog(id + ".done", NT.Util.fmt(cmd.log || "{text}", { text: entry.text }));
    NT.Audio.play(cmd.sfx || "item"); NT.Loop.freeze(cmd.weight || 6);
    if (NT.Scenes.find("MAP")) NT.Scenes.find("MAP").toast(NT.Util.fmt(cmd.log || "{text}", { text: entry.text }));
  };
  Q.undo = function (id, entry) {
    if (!entry.doneKey) return false;
    entry.doneKey = null; entry.undoUntil = 0;
    NT.State.addLog(id + ".undo", entry.text);
    NT.Audio.play("cancel");
    return true;
  };

  /* ---- クリアの儀式 ---- */
  Q.clear = function (id, reportText) {
    var st = NT.State.cur, q = Q.state(id), def = Q.def(id);
    if (!Q.isReportable(id)) return false;
    q.status = "cleared"; q.clearedKey = Q.today();
    if (reportText) q.reportText = reportText;
    if (st.clears.indexOf(id) < 0) st.clears.push(id);
    var prevTitle = st.title;
    q.bonusResult = Q.bonuses(id).filter(function (b) { return b.ok; }).map(function (b) { return b.label; });
    if (q.lesson) NT.State.addLesson(id, q.lesson);
    NT.State.recompute();
    /* 花 */
    var pots = NT.Tilemap.potsOf(def.floor), fl = st.flowers[def.floor] = st.flowers[def.floor] || [];
    var bandY = NT.Tilemap.bandY(def.floor);
    for (var i = 0; i < pots.length; i++) {
      var p = [pots[i][0], bandY + pots[i][1]];
      if (!fl.some(function (x) { return x[0] === p[0] && x[1] === p[1]; })) { fl.push(p); break; }
    }
    NT.State.addLog(id + ".clear", def.title);
    NT.State.touch();
    NT.Audio.play("clear"); NT.Loop.freeze(20); NT.Loop.shake(2, 120);
    var titleChanged = prevTitle !== st.title;
    var msgs = [TX().cleared + "　" + def.num + " " + def.title, TX().mark + "（" + st.marks + "/10）", TX().flower];
    if (q.bonusResult.length) msgs.push(TX().bonus + "：" + q.bonusResult.join("、"));
    if (titleChanged) msgs.push(NT.Util.fmt(TX().title, { t: st.title }));
    if (st.marks === 3) msgs.push("1F の 扉が ひらいた");
    Q.ceremony(msgs, titleChanged);
    return true;
  };
  Q.ceremony = function (msgs, titleChanged) {
    var i = 0;
    function next() {
      if (i >= msgs.length) return;
      var m = msgs[i++];
      if (titleChanged && i === msgs.length) NT.Audio.play("rank");
      if (i === 3) NT.Audio.play("bloom");
      NT.Scenes.push(NT.Notice(m, next, { color: i === 1 ? "#f4d03f" : "#f4f1e8" }));
    }
    next();
  };

  /* ---- 会話からのフック ---- */
  NT.Dialog.hooks["quest.accept"] = function (id) { Q.accept(id); };
  NT.Dialog.hooks["quest.open"] = function (id) { NT.Flow.openQuest(id, "prep"); return "stop"; };
  NT.Dialog.hooks["quest.report"] = function (id) { NT.Flow.openQuest(id, "report"); return "stop"; };
  NT.Dialog.hooks["scene.save"] = function () { NT.Flow.openSave(); return "stop"; };
})();
