/* クエスト画面。タブ：じゅんび / じっこう / ほうこく。入力は InputBox、選択は Menu を重ねる。
   定義（data/quests.js）から汎用に組み立て、個別の見せ方だけ NT.QuestImpl[id] で上書きする */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text, G = NT.Gfx, I = NT.Input, Q = NT.Quests, U = NT.Util;
  var TX = function () { return NT.DATA.TEXT.quest; };
  var TABS = ["prep", "exec", "report"];
  var LIST_X = 16, LIST_W = 288;
  var BOX = { x: 24, y: 70, w: 272 };

  NT.SceneQuest = function (id, tab) {
    var def = Q.def(id), impl = NT.QuestImpl[id] || {}, ex = def.exec || {};
    var tabIndex = Math.max(0, TABS.indexOf(tab || "prep"));
    var cursor = 0, scroll = 0, flash = 0;
    var FIELD_LABELS = { when: TX().when, where: TX().where, how: TX().how, obstacle: TX().obstacle };

    function q() { return Q.state(id); }
    function lists() { return Q.lists(def); }
    function list(L) { var st = q(); st[L.kind] = st[L.kind] || []; return st[L.kind]; }
    function extras() { return (def.prep && def.prep.extras) || []; }
    function isDeclaredEntry(e) { return !!(q().declared && q().declared.text === e.text); }

    /* 項目の 1 行表示 */
    function entryLine(e, L) {
      if (impl.entryLine) return impl.entryLine(e, q(), L);
      var mark = "○ ";
      (ex.commands || []).forEach(function (c) { if (e[(c.flag || "done") + "Key"]) mark = (c.mark || "●") + " "; });
      if (isDeclaredEntry(e)) mark = "★ ";
      var suffix = e.date ? "（" + NT.Time.mmdd(e.date).replace("-", "/") + "）" : "";
      if (L && L.tags && e.tag && e.tag !== "none") { var tg = L.tags.filter(function (t) { return t[0] === e.tag; })[0]; if (tg) suffix += "〔" + tg[1] + "〕"; }
      return mark + e.text + suffix;
    }

    /* 各タブの行を組み立てる */
    function rows() {
      var out = [], st = q();
      if (TABS[tabIndex] === "prep") {
        out.push({ kind: "head", label: TX().plan });
        (def.prep.fields || []).forEach(function (f) {
          var v = (st.plan && st.plan[f]) || "";
          out.push({ kind: "field", field: f, label: FIELD_LABELS[f] + "：" + (v || "（未記入）"), dim: !v });
        });
        extras().forEach(function (xd) {
          if (xd.key === (def.report && def.report.reflectKey)) return;
          var v = st.extras[xd.key] || "";
          out.push({ kind: "extra", extra: xd, label: xd.label + "：" + (v || "（未記入）"), dim: !v });
        });
        lists().forEach(function (L) {
          if (ex.attemptsAreActions && L.kind === "attempts") return;
          var l = list(L);
          out.push({ kind: "head", label: L.label + "（" + l.length + "/" + L.max + "）" });
          l.forEach(function (e, i) { out.push({ kind: "entry", entry: e, L: L, index: i, label: entryLine(e, L) }); });
          if (l.length < L.max) out.push({ kind: "add", L: L, label: TX().add });
        });
      } else if (TABS[tabIndex] === "exec") {
        var status = impl.execStatus ? impl.execStatus(st, def) : defaultExecStatus(st);
        status.forEach(function (l) { out.push({ kind: "info", label: l }); });
        if (ex.declare) {
          dailyCommands(st).forEach(function (c) { out.push({ kind: "daily", cmd: c, label: c.label, dim: c.disabled }); });
        }
        if (ex.white) out.push({ kind: "white", label: "10分 なにもしない を はじめる" });
        if (ex.attemptsAreActions) {
          var La = Q.listDef(def, "attempts"), la = list(La);
          out.push({ kind: "head", label: La.label + "（" + la.length + "）" });
          la.forEach(function (e, i) { out.push({ kind: "entry", entry: e, L: La, index: i, label: "● " + e.text + "　" + (e.k || "") }); });
          if (la.length < La.max) out.push({ kind: "add", L: La, label: "＋ 挑戦した（記録を入れる）" });
        }
        lists().forEach(function (L) {
          if (ex.attemptsAreActions && L.kind === "attempts") return;
          var l = list(L);
          out.push({ kind: "head", label: L.label });
          if (!l.length) out.push({ kind: "info", label: "（じゅんび で 書き出す）" });
          l.forEach(function (e, i) { out.push({ kind: "entry", entry: e, L: L, index: i, label: entryLine(e, L) }); });
        });
      } else {
        out.push({ kind: "head", label: TX().condition });
        Q.conditions(id).forEach(function (c) { out.push({ kind: "info", label: (c.ok ? "● " : "○ ") + c.label, color: c.ok ? "#7dffb0" : "#f4f1e8" }); });
        var bs = Q.bonuses(id);
        if (bs.length) { out.push({ kind: "head", label: TX().bonus }); bs.forEach(function (b) { out.push({ kind: "info", label: (b.ok ? "★ " : "○ ") + b.label, color: b.ok ? "#f4d03f" : "#9aa0b4" }); }); }
        if (def.report && def.report.reflectKey) {
          var rv = st.extras[def.report.reflectKey] || "";
          out.push({ kind: "extra", extra: { key: def.report.reflectKey, label: def.report.reflectLabel || "ふりかえり", maxLen: 60 }, label: (def.report.reflectLabel || "ふりかえり") + "：" + (rv || "（未記入）"), dim: !rv });
        }
        if (def.report && def.report.lesson) out.push({ kind: "lesson", label: TX().lesson + "：" + (st.lesson || "（未記入）"), dim: !st.lesson });
        if (st.status === "cleared") out.push({ kind: "info", label: TX().cleared + "　" + (st.clearedKey || ""), color: "#f4d03f" });
        else out.push({ kind: "report", label: "長老に ほうこくする", dim: !Q.isReportable(id) });
      }
      return out;
    }
    function defaultExecStatus(st) {
      var lines = [];
      if (ex.declare) {
        if (!st.declared) lines.push(ex.declareFrom ? "じゅんび で 書いたものから えらんで 宣言しよう" : "候補を えらんで 宣言しよう");
        else {
          lines.push("宣言：" + st.declared.text);
          lines.push(U.fmt(TX().streak, { n: Q.streak(st) }) + "（" + st.declared.startKey.slice(5).replace("-", "/") + "〜）");
          lines.push(TX().charm + "　" + U.fmt(TX().charmLeft, { n: st.charms || 0 }));
        }
      }
      return lines;
    }
    function dailyCommands(st) {
      if (!st.declared) return [];
      var can = Q.canCheckToday(st);
      return [
        { label: ex.checkLabel || "きょうも やった", value: "check", disabled: !can.ok },
        { label: "おやすみのお守りを つかう", value: "charm", disabled: !(st.charms > 0) || !can.ok }
      ];
    }
    function selectable(r) { return r.kind !== "head" && r.kind !== "info"; }
    function clampCursor(rs) {
      if (!rs.length) { cursor = 0; return; }
      cursor = U.clamp(cursor, 0, rs.length - 1);
      var guard = 0;
      while (!selectable(rs[cursor]) && guard++ < rs.length) cursor = (cursor + 1) % rs.length;
    }
    function moveCursor(rs, d) {
      if (!rs.length) return;
      var i = cursor, guard = 0;
      do { i = (i + d + rs.length) % rs.length; guard++; } while (!selectable(rs[i]) && guard <= rs.length);
      if (selectable(rs[i])) { cursor = i; NT.Audio.play("cursor"); }
    }

    /* ---- 入力 ---- */
    function ask(title, value, maxLen, multiline, cb) {
      NT.InputBox.open({ x: BOX.x, y: BOX.y, w: BOX.w, maxLen: maxLen || 40, title: title, value: value || "", multiline: !!multiline, rows: multiline ? 2 : 1, onDone: cb });
    }
    function editField(f) {
      var st = q();
      ask(FIELD_LABELS[f], st.plan[f], 40, false, function (v) { if (v !== null) { st.plan[f] = v; NT.State.touch(); } });
    }
    function editExtra(xd) {
      var st = q();
      ask(xd.label, st.extras[xd.key], xd.maxLen || 40, !!xd.multiline, function (v) { if (v !== null) { st.extras[xd.key] = v; NT.State.touch(); } });
    }
    function addEntry(L) {
      ask(L.itemLabel, "", 30, false, function (text) {
        if (!text) return;
        var e = { id: U.uid(), text: text };
        afterText(e, L, function () {
          list(L).push(e); NT.State.touch();
          if (ex.attemptsAreActions && L.kind === "attempts") onAttempt(e); else NT.Audio.play("tap");
        });
      });
    }
    function afterText(e, L, done) {
      var steps = [];
      if (L.tags) steps.push(function (next) {
        NT.Scenes.push(NT.Menu({ title: "どんな物？", w: 200, items: L.tags.map(function (t) { return { label: t[1], value: t[0] }; }), cancelable: false,
          onSelect: function (it) { e.tag = it.value; NT.Scenes.pop(); next(); } }));
      });
      (L.extra || []).forEach(function (exd) {
        steps.push(function (next) { ask(exd[1], e[exd[0]], 60, false, function (v) { if (v !== null) e[exd[0]] = v; next(); }); });
      });
      var i = 0;
      (function run() { if (i < steps.length) steps[i++](run); else done(); })();
    }
    /* ② 挑戦の記録：追加そのものが実行 */
    function onAttempt(e) {
      var st = q();
      e.k = Q.today();
      st.status = "doing";
      var rec = Q.num(st.extras.record), v = Q.num(e.text), tgt = Q.num(st.extras.target);
      var isNew = !isNaN(rec) && !isNaN(v) && v > rec;
      NT.State.addLog(id + ".attempt", e.text);
      NT.Audio.play(isNew ? "clear" : "item"); NT.Loop.freeze(isNew ? 12 : 6); flash = 180;
      var msg = isNew ? "NEW RECORD！　" + e.text + "（いままで " + st.extras.record + "）" : (!isNaN(tgt) && !isNaN(v) && v >= tgt ? "目標に とどいた！　" + e.text : "挑戦を 記録した　" + e.text);
      NT.Scenes.push(NT.Notice(msg, null, { color: isNew ? "#f4d03f" : "#f4f1e8" }));
    }
    function editEntry(e, L) {
      ask(L.itemLabel, e.text, 30, false, function (text) {
        if (!text) return;
        if (isDeclaredEntry(e)) q().declared.text = text;
        e.text = text;
        afterText(e, L, function () { NT.State.touch(); });
      });
    }
    function canDeclareFrom(e, L) {
      if (!ex.declare || q().declared) return false;
      if (ex.declareFrom && L.kind !== ex.declareFrom) return false;
      if (ex.declareLast) { var l = list(L); return l.length >= (L.min || 1) && l[l.length - 1] === e; }
      return true;
    }
    function entryMenu(e, L) {
      var items;
      if (impl.entryCommands) items = impl.entryCommands(q(), e, L);
      else {
        items = [];
        (ex.commands || []).forEach(function (c) { if (!e[(c.flag || "done") + "Key"]) items.push({ label: c.label, value: "cmd", cmd: c }); });
        if (e.undoUntil > NT.Loop.elapsed && e[(e.undoFlag || "done") + "Key"]) items.push({ label: TX().undo, value: "undo" });
        if (canDeclareFrom(e, L)) items.push({ label: ex.declareLabel || "これを 宣言する", value: "declare" });
        items.push({ label: TX().edit, value: "edit" });
        if (!isDeclaredEntry(e) && !(ex.attemptsAreActions && L.kind === "attempts")) items.push({ label: TX().remove, value: "remove" });
        items.push({ label: NT.DATA.TEXT.menu.back, value: "back" });
      }
      NT.Scenes.push(NT.Menu({ title: e.text, w: 260, items: items, onSelect: function (it) {
        NT.Scenes.pop();
        if (it.value === "cmd" || it.value === "do") runCommand(e, it.cmd);
        else if (it.value === "undo") { Q.undo(id, e); NT.State.touch(); }
        else if (it.value === "edit") editEntry(e, L);
        else if (it.value === "remove") { var l = list(L); l.splice(l.indexOf(e), 1); NT.State.touch(); NT.Audio.play("cancel"); }
        else if (it.value === "declare") {
          var go = function (reason) { Q.declare(id, e.text, reason); flash = 180; };
          if (ex.declareFrom || e.reason) go(e.reason);
          else ask(TX().reasonPrompt, "", 60, false, function (v) { if (v === null) return; e.reason = v; go(v); });
        }
      } }));
    }
    function runCommand(e, cmd) {
      if (cmd.input) {
        var inp = cmd.input;
        ask(inp.title, e[inp.field] || "", inp.maxLen || 20, false, function (v) {
          if (v === null || v === "") return;
          if (inp.kind === "date") {
            var key = Q.parseDate(v);
            if (!key) { NT.Audio.play("error"); NT.Scenes.push(NT.Notice("日付が 読めなかった。例：1/20 や 2027-01-20")); return; }
            if (key < Q.today()) { NT.Audio.play("error"); NT.Scenes.push(NT.Notice("きょうより あとの 日付を 入れてね")); return; }
            v = key;
          }
          Q.markFlag(id, e, cmd, v); flash = 180;
        });
        return;
      }
      NT.Scenes.push(NT.Confirm(U.fmt(TX().confirmDone, { text: e.text }), function () { Q.markFlag(id, e, cmd); flash = 180; }, null, { defaultYes: true }));
    }
    function daily(c) {
      if (c.value === "check") {
        var r = Q.checkToday(id);
        if (!r.ok) { NT.Audio.play("error"); NT.Scenes.push(NT.Notice(r.why)); return; }
        flash = 180;
        NT.Scenes.push(NT.Notice(U.fmt(TX().streak, { n: r.streak })));
      } else if (c.value === "charm") {
        var r2 = Q.useCharm(id);
        if (!r2.ok) { NT.Audio.play("error"); NT.Scenes.push(NT.Notice(r2.why)); return; }
        NT.Scenes.push(NT.Notice(TX().charmUsed));
      }
    }
    function editLesson() {
      ask(def.report.lessonPrompt || TX().lessonPrompt, q().lesson, 60, true, function (v) { if (v !== null) { q().lesson = v; NT.State.touch(); } });
    }
    function report() {
      if (!Q.isReportable(id)) { NT.Audio.play("error"); NT.Scenes.push(NT.Notice(TX().needMore)); return; }
      ask(TX().reportText, "", 60, true, function (v) {
        if (v === null) return;
        NT.Scenes.push(NT.Confirm(TX().confirmReport, function () {
          NT.Scenes.remove(scene);
          Q.clear(id, v);
        }, null, { defaultYes: true }));
      });
    }
    function activate(r) {
      if (r.kind === "field") editField(r.field);
      else if (r.kind === "extra") editExtra(r.extra);
      else if (r.kind === "add") addEntry(r.L);
      else if (r.kind === "entry") entryMenu(r.entry, r.L);
      else if (r.kind === "daily") { if (r.cmd.disabled) { NT.Audio.play("error"); var can = Q.canCheckToday(q()); NT.Scenes.push(NT.Notice(can.why || TX().needMore)); } else daily(r.cmd); }
      else if (r.kind === "white") NT.Flow.openWhite(id);
      else if (r.kind === "lesson") editLesson();
      else if (r.kind === "report") report();
    }

    var scene = {
      id: "QUEST", opaque: true,
      enter: function () { if (q().status === "offered") Q.accept(id); if (NT.Excuse) NT.Excuse.touch(id); clampCursor(rows()); },
      exit: function () { if (NT.Excuse) NT.Excuse.touch(id); },
      resume: function () { clampCursor(rows()); },
      update: function (dt) {
        NT.State.tick(dt);
        if (flash > 0) flash -= dt;
        var rs = rows();
        if (!rs[cursor] || !selectable(rs[cursor])) clampCursor(rs);
        if (I.pressed("left")) { tabIndex = (tabIndex + 2) % 3; cursor = 0; scroll = 0; clampCursor(rows()); NT.Audio.play("cursor"); return; }
        if (I.pressed("right")) { tabIndex = (tabIndex + 1) % 3; cursor = 0; scroll = 0; clampCursor(rows()); NT.Audio.play("cursor"); return; }
        if (I.pressed("up")) moveCursor(rs, -1);
        if (I.pressed("down")) moveCursor(rs, 1);
        if (I.pressed("ok")) { I.consume("ok"); if (rs[cursor] && selectable(rs[cursor])) { NT.Audio.play("decide"); activate(rs[cursor]); } return; }
        if (I.pressed("cancel") || I.pressed("menu")) { I.consume("cancel"); I.consume("menu"); NT.Audio.play("close"); NT.Scenes.pop(); return; }
        var cl = I.clicks();
        for (var k = 0; k < cl.length; k++) {
          var c = cl[k];
          if (c.y >= 30 && c.y < 46) { var ti = Math.floor((c.x - LIST_X) / 84); if (ti >= 0 && ti < 3) { tabIndex = ti; cursor = 0; scroll = 0; clampCursor(rows()); NT.Audio.play("cursor"); } return; }
          if (c.y >= NT.H - 18) { NT.Scenes.pop(); return; }
          var ri = Math.floor((c.y - 52 + scroll) / 16);
          if (ri >= 0 && ri < rs.length && selectable(rs[ri])) { cursor = ri; NT.Audio.play("decide"); activate(rs[ri]); return; }
        }
        var top = cursor * 16, viewH = NT.H - 52 - 22;
        if (top - scroll > viewH - 16) scroll = top - (viewH - 16);
        if (top - scroll < 0) scroll = top;
      },
      draw: function (ctx) {
        NT.Screen.clear("#0a0a16");
        var st = q();
        ctx.fillStyle = "#15152a"; ctx.fillRect(0, 0, NT.W, 28);
        T.draw(ctx, def.num + " " + def.title, 10, 6, "#f4d03f", { head: true, size: 16 });
        var statusTxt = st.status === "cleared" ? TX().cleared : Q.progressText(id);
        T.drawRight(ctx, statusTxt, NT.W - 10, 8, st.status === "cleared" ? "#7dffb0" : "#9aa0b4");
        for (var i = 0; i < 3; i++) {
          var tx = LIST_X + i * 84, label = [TX().prep, TX().exec, TX().report][i];
          var on = i === tabIndex;
          ctx.fillStyle = on ? "#f4d03f" : "#2a2a3e"; ctx.fillRect(tx, 30, 80, 16);
          T.draw(ctx, label, tx + 6, 32, on ? "#000" : "#9aa0b4");
        }
        T.draw(ctx, "◀▶", NT.W - 40, 32, "#5b5a66");
        var rs = rows();
        ctx.save(); ctx.beginPath(); ctx.rect(0, 50, NT.W, NT.H - 50 - 20); ctx.clip();
        for (var r = 0; r < rs.length; r++) {
          var row = rs[r], y = 52 + r * 16 - scroll;
          if (y < 36 || y > NT.H - 20) continue;
          var color = row.color || (row.kind === "head" ? "#f4afc4" : row.dim ? "#6e6a7a" : "#f4f1e8");
          var x = row.kind === "head" ? LIST_X : LIST_X + 12;
          var lbl = row.label;
          if (T.measure(lbl) > LIST_W - 16) { while (T.measure(lbl + "…") > LIST_W - 16 && lbl.length) lbl = lbl.slice(0, -1); lbl += "…"; }
          T.draw(ctx, lbl, x, y, color);
          if (r === cursor && selectable(row)) G.cursor(ctx, LIST_X + 2, y + 1, flash > 0 ? "#7dffb0" : "#f4d03f");
        }
        ctx.restore();
        ctx.fillStyle = "#15152a"; ctx.fillRect(0, NT.H - 20, NT.W, 20);
        var hint = TABS[tabIndex] === "exec" && impl.execHint ? impl.execHint : TABS[tabIndex] === "prep" ? def.summary : "条件が そろったら 長老に ほうこく";
        var hl = T.wrap(hint, NT.W - 70);
        T.draw(ctx, hl[0], 8, NT.H - 16, "#9aa0b4");
        T.drawRight(ctx, "X:とじる", NT.W - 8, NT.H - 16, "#5b5a66");
        NT.InputBox.draw(ctx);
      },
      /* テスト用 */
      rows: function () { return rows().map(function (r) { return { kind: r.kind, label: r.label }; }); },
      setTab: function (i) { tabIndex = i; cursor = 0; scroll = 0; clampCursor(rows()); },
      cursorTo: function (pred) { var rs = rows(); for (var i = 0; i < rs.length; i++) if (selectable(rs[i]) && pred(rs[i])) { cursor = i; return true; } return false; },
      activateCursor: function () { var rs = rows(); if (rs[cursor] && selectable(rs[cursor])) activate(rs[cursor]); }
    };
    return scene;
  };
})();
