/* クエストエンジン。状態の遷移、条件の評価、クリアの儀式 */
(function () {
  "use strict";
  var NT = window.NT;
  var Q = NT.Quests = {};
  var TX = function () { return NT.DATA.TEXT.quest; };

  Q.def = function (id) { return NT.DATA.QUESTS[id]; };
  /* 定義のリスト一覧（lists 優先、無ければ list を 1 件として扱う） */
  Q.lists = function (def) { return def.prep ? (def.prep.lists || (def.prep.list ? [def.prep.list] : [])) : []; };
  Q.listDef = function (def, kind) { var ls = Q.lists(def); for (var i = 0; i < ls.length; i++) if (ls[i].kind === kind) return ls[i]; return null; };
  Q.state = function (id) {
    var st = NT.State.cur;
    if (!st.quests[id]) st.quests[id] = { status: "offered" };
    var q = st.quests[id];
    if (!q.extras) q.extras = {};
    return q;
  };
  Q.status = function (id) { return Q.state(id).status; };

  Q.accept = function (id) {
    var q = Q.state(id);
    if (q.status !== "offered") return false;
    q.status = "accepted";
    q.acceptedKey = NT.Time.jstKey();
    q.plan = q.plan || { when: "", where: "", how: "", obstacle: "" };
    var def = Q.def(id);
    Q.lists(def).forEach(function (L) { q[L.kind] = q[L.kind] || []; });
    if (def.exec && def.exec.charms) q.charms = def.exec.charms;
    q.checks = q.checks || []; q.charmUsed = q.charmUsed || [];
    q.extras = q.extras || {};
    NT.State.addLog(id + ".accept", def.title);
    return true;
  };

  /* ---- 条件表 ---- */
  Q.today = function () { return NT.Time.jstKey(); };
  Q.entriesOf = function (q, kind, def) {
    if (kind === "*" ) { var all = []; Q.lists(def).forEach(function (L) { all = all.concat(q[L.kind] || []); }); return all; }
    return q[kind] || [];
  };
  Q.withFlag = function (q, spec, def) {
    var parts = spec.split(":"), kind = parts[0], flag = parts[1];
    return Q.entriesOf(q, kind, def).filter(function (e) { return !!e[flag + "Key"]; });
  };
  /* 旧データ互換：doneKey を持つ entries */
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
  Q.num = function (s) { if (s == null) return NaN; var m = String(s).replace(/,/g, "").match(/-?\d+(\.\d+)?/); return m ? parseFloat(m[0]) : NaN; };
  Q.newRecord = function (q) {
    var rec = Q.num(q.extras && q.extras.record);
    if (isNaN(rec)) return false;
    return (q.attempts || []).some(function (a) { var v = Q.num(a.text); return !isNaN(v) && v > rec; });
  };
  var ATOMS = {
    doneCount: function (q, op, v) { return cmp(Q.doneEntries(q).length, op, v); },
    doneTag: function (q, tag) { return Q.doneEntries(q).some(function (e) { return e.tag === tag; }); },
    lesson: function (q) { return !!(q.lesson && q.lesson.trim()); },
    declared: function (q) { return !!q.declared; },
    streak: function (q, op, v) { return cmp(Q.streak(q), op, v); },
    reason: function (q) { return !!(q.declared && q.declared.reason && q.declared.reason.trim()); },
    streakThrough: function (q, mmdd) { return Q.streakThrough(q, mmdd); },
    flagCount: function (q, spec, n, def) { return Q.withFlag(q, spec, def).length >= n; },
    listCount: function (q, kind, n, def) { return Q.entriesOf(q, kind, def).length >= n; },
    extra: function (q, key) { return !!(q.extras && q.extras[key] && String(q.extras[key]).trim()); },
    extrasAll: function (q, keys) { return (keys || []).every(function (k) { return !!(q.extras && q.extras[k] && String(q.extras[k]).trim()); }); },
    timer: function (q, _, n) { return (q.timerDone || 0) >= n; },
    newRecord: function (q) { return Q.newRecord(q); }
  };
  function cmp(a, op, b) { return op === ">=" ? a >= b : op === ">" ? a > b : op === "==" ? a === b : op === "<=" ? a <= b : a < b; }
  Q.evalCond = function (q, c, def) {
    var fn = ATOMS[c[0]];
    if (!fn) return false;
    return !!fn(q, c[1], c[2], def);
  };
  /* [{label, ok}] */
  Q.conditions = function (id) {
    var def = Q.def(id), q = Q.state(id);
    return (def.clear || []).map(function (c) { return { label: c[3] || c[0], ok: Q.evalCond(q, c, def) }; });
  };
  Q.bonuses = function (id) {
    var def = Q.def(id), q = Q.state(id);
    return (def.bonus || []).map(function (c) { return { label: c[3] || c[0], ok: Q.evalCond(q, c, def) }; });
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
  /* 項目に印を付ける（汎用）。cmd.flag が 'done' なら doneKey */
  Q.markFlag = function (id, entry, cmd, value) {
    var q = Q.state(id), flag = cmd.flag || "done";
    entry[flag + "Key"] = Q.today();
    entry.undoUntil = NT.Loop.elapsed + 60000;
    entry.undoFlag = flag;
    if (cmd.input && cmd.input.field && value !== undefined) entry[cmd.input.field] = value;
    q.status = "doing";
    var vars = { text: entry.text, date: entry.date ? NT.Time.mmdd(entry.date).replace("-", "/") : "", value: value || "" };
    var msg = NT.Util.fmt(cmd.log || "{text}", vars);
    NT.State.addLog(id + "." + flag, msg);
    NT.Audio.play(cmd.sfx || "item"); NT.Loop.freeze(cmd.weight || 6);
    var m = NT.Scenes.find("MAP"); if (m) m.toast(msg);
    return msg;
  };
  Q.markDone = function (id, entry, cmd) { return Q.markFlag(id, entry, cmd, undefined); };
  Q.undo = function (id, entry) {
    var flag = entry.undoFlag || "done";
    if (!entry[flag + "Key"]) return false;
    entry[flag + "Key"] = null; entry.undoUntil = 0;
    NT.State.addLog(id + ".undo", entry.text);
    NT.Audio.play("cancel");
    return true;
  };
  /* 10分なにもしない の完了 */
  Q.whiteDone = function (id, seconds) {
    var q = Q.state(id);
    q.timerDone = (q.timerDone || 0) + 1;
    q.status = "doing";
    q.whiteLog = q.whiteLog || [];
    q.whiteLog.push({ k: Q.today(), sec: seconds });
    NT.State.addLog(id + ".white", seconds + "秒 なにもしなかった");
    NT.State.touch();
  };
  /* 日付の読み取り：'YYYY-MM-DD' / 'YYYY/M/D' / 'M/D'（きょうより前なら来年） */
  Q.parseDate = function (s) {
    s = String(s || "").trim().replace(/[０-９]/g, function (c) { return String.fromCharCode(c.charCodeAt(0) - 0xFEE0); }).replace(/[年月]/g, "/").replace(/日/g, "");
    var m, y, mo, d, today = Q.today();
    if ((m = /^(\d{4})[-\/](\d{1,2})[-\/](\d{1,2})$/.exec(s))) { y = +m[1]; mo = +m[2]; d = +m[3]; }
    else if ((m = /^(\d{1,2})[-\/](\d{1,2})$/.exec(s))) {
      mo = +m[1]; d = +m[2]; y = NT.Time.yearOf(today);
      var cand = y + "-" + NT.Util.pad2(mo) + "-" + NT.Util.pad2(d);
      if (cand < today) y++;
    } else return null;
    if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
    var key = y + "-" + NT.Util.pad2(mo) + "-" + NT.Util.pad2(d);
    var chk = new Date(NT.Time.keyToUTC(key));
    if (chk.getUTCMonth() + 1 !== mo) return null;
    return key;
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
    if (st.marks === 10) msgs.push("十の しるしが そろった。長老に 会いに いこう");
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
  NT.Dialog.hooks["white.start"] = function () { NT.Flow.openWhite("q1"); return "stop"; };
})();
