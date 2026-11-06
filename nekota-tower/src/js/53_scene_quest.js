/* クエスト画面。タブ：じゅんび / じっこう / ほうこく。入力は InputBox、選択は Menu を重ねる */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text, G = NT.Gfx, I = NT.Input, Q = NT.Quests, U = NT.Util;
  var TX = function () { return NT.DATA.TEXT.quest; };
  var TABS = ["prep", "exec", "report"];
  var LIST_X = 16, LIST_W = 288;

  NT.SceneQuest = function (id, tab) {
    var def = Q.def(id), impl = NT.QuestImpl[id] || {};
    var tabIndex = Math.max(0, TABS.indexOf(tab || "prep"));
    var cursor = 0, scroll = 0, flash = 0;
    var FIELD_LABELS = { when: TX().when, where: TX().where, how: TX().how, obstacle: TX().obstacle };

    function q() { return Q.state(id); }
    function listKind() { return def.prep && def.prep.list ? def.prep.list.kind : null; }
    function list() { var k = listKind(); if (!k) return []; q()[k] = q()[k] || []; return q()[k]; }

    /* 各タブの行を組み立てる。row: {label, value, kind, ...} */
    function rows() {
      var out = [], st = q();
      if (TABS[tabIndex] === "prep") {
        out.push({ kind: "head", label: TX().plan });
        (def.prep.fields || []).forEach(function (f) {
          var v = (st.plan && st.plan[f]) || "";
          out.push({ kind: "field", field: f, label: FIELD_LABELS[f] + "：" + (v || "（未記入）"), dim: !v });
        });
        if (def.prep.list) {
          out.push({ kind: "head", label: def.prep.list.label + "（" + list().length + "/" + def.prep.list.max + "）" });
          list().forEach(function (e, i) { out.push({ kind: "entry", entry: e, index: i, label: impl.entryLine ? impl.entryLine(e, st) : "○ " + e.text }); });
          if (list().length < def.prep.list.max) out.push({ kind: "add", label: TX().add });
        }
      } else if (TABS[tabIndex] === "exec") {
        if (impl.execStatus) impl.execStatus(st).forEach(function (l) { out.push({ kind: "info", label: l }); });
        if (impl.dailyCommands) impl.dailyCommands(st).forEach(function (c) { out.push({ kind: "daily", cmd: c, label: c.label, dim: c.disabled }); });
        if (def.prep.list) {
          out.push({ kind: "head", label: def.prep.list.label });
          if (!list().length) out.push({ kind: "info", label: "（じゅんび で 書き出す）" });
          list().forEach(function (e, i) { out.push({ kind: "entry", entry: e, index: i, label: impl.entryLine ? impl.entryLine(e, st) : "○ " + e.text }); });
        }
      } else {
        out.push({ kind: "head", label: TX().condition });
        Q.conditions(id).forEach(function (c) { out.push({ kind: "info", label: (c.ok ? "● " : "○ ") + c.label, color: c.ok ? "#7dffb0" : "#f4f1e8" }); });
        var bs = Q.bonuses(id);
        if (bs.length) { out.push({ kind: "head", label: TX().bonus }); bs.forEach(function (b) { out.push({ kind: "info", label: (b.ok ? "★ " : "○ ") + b.label, color: b.ok ? "#f4d03f" : "#9aa0b4" }); }); }
        if (def.report && def.report.lesson) out.push({ kind: "lesson", label: TX().lesson + "：" + (st.lesson || "（未記入）"), dim: !st.lesson });
        if (st.status === "cleared") out.push({ kind: "info", label: TX().cleared + "　" + (st.clearedKey || ""), color: "#f4d03f" });
        else out.push({ kind: "report", label: "長老に ほうこくする", dim: !Q.isReportable(id) });
      }
      return out;
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

    /* ---- 操作 ---- */
    function editField(f) {
      var st = q();
      NT.InputBox.open({ x: 24, y: 70, w: 272, maxLen: 40, title: FIELD_LABELS[f], value: st.plan[f] || "",
        onDone: function (v) { if (v !== null) { st.plan[f] = v; NT.State.touch(); } } });
    }
    function addEntry() {
      var L = def.prep.list;
      NT.InputBox.open({ x: 24, y: 70, w: 272, maxLen: 30, title: L.itemLabel, onDone: function (text) {
        if (!text) return;
        var e = { id: U.uid(), text: text };
        afterText(e, function () { list().push(e); NT.State.touch(); NT.Audio.play("tap"); });
      } });
    }
    function afterText(e, done) {
      var L = def.prep.list;
      var steps = [];
      if (L.tags) steps.push(function (next) {
        NT.Scenes.push(NT.Menu({ title: "どんな物？", w: 200, items: L.tags.map(function (t) { return { label: t[1], value: t[0] }; }), cancelable: false,
          onSelect: function (it) { e.tag = it.value; NT.Scenes.pop(); next(); } }));
      });
      (L.extra || []).forEach(function (ex) {
        steps.push(function (next) {
          NT.InputBox.open({ x: 24, y: 70, w: 272, maxLen: 60, title: ex[1], value: e[ex[0]] || "", onDone: function (v) { if (v !== null) e[ex[0]] = v; next(); } });
        });
      });
      var i = 0;
      (function run() { if (i < steps.length) steps[i++](run); else done(); })();
    }
    function editEntry(e) {
      NT.InputBox.open({ x: 24, y: 70, w: 272, maxLen: 30, title: def.prep.list.itemLabel, value: e.text, onDone: function (text) {
        if (!text) return;
        if (q().declared && q().declared.text === e.text) q().declared.text = text;
        e.text = text;
        afterText(e, function () { NT.State.touch(); });
      } });
    }
    function entryMenu(e) {
      var items = impl.entryCommands ? impl.entryCommands(q(), e) : [{ label: NT.DATA.TEXT.menu.back, value: "back" }];
      NT.Scenes.push(NT.Menu({ title: e.text, w: 240, items: items, onSelect: function (it) {
        NT.Scenes.pop();
        if (it.value === "do") {
          NT.Scenes.push(NT.Confirm(U.fmt(TX().confirmDone, { text: e.text }), function () { Q.markDone(id, e, it.cmd); flash = 180; }, null, { defaultYes: true }));
        } else if (it.value === "undo") { Q.undo(id, e); NT.State.touch(); }
        else if (it.value === "edit") editEntry(e);
        else if (it.value === "remove") { var l = list(); l.splice(l.indexOf(e), 1); NT.State.touch(); NT.Audio.play("cancel"); }
        else if (it.value === "declare") {
          var go = function (reason) { Q.declare(id, e.text, reason); flash = 180; };
          if (e.reason) go(e.reason);
          else NT.InputBox.open({ x: 24, y: 70, w: 272, maxLen: 60, title: TX().reasonPrompt, onDone: function (v) { if (v === null) return; e.reason = v; go(v); } });
        }
      } }));
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
      NT.InputBox.open({ x: 24, y: 70, w: 272, maxLen: 60, title: def.report.lessonPrompt || TX().lessonPrompt, value: q().lesson || "", multiline: true, rows: 2,
        onDone: function (v) { if (v !== null) { q().lesson = v; NT.State.touch(); } } });
    }
    function report() {
      if (!Q.isReportable(id)) { NT.Audio.play("error"); NT.Scenes.push(NT.Notice(TX().needMore)); return; }
      NT.InputBox.open({ x: 24, y: 70, w: 272, maxLen: 60, title: TX().reportText, multiline: true, rows: 2, onDone: function (v) {
        if (v === null) return;
        NT.Scenes.push(NT.Confirm(TX().confirmReport, function () {
          /* クエスト画面を閉じてから儀式 */
          NT.Scenes.remove(scene);
          Q.clear(id, v);
        }, null, { defaultYes: true }));
      } });
    }
    function activate(r) {
      if (r.kind === "field") editField(r.field);
      else if (r.kind === "add") addEntry();
      else if (r.kind === "entry") entryMenu(r.entry);
      else if (r.kind === "daily") { if (r.cmd.disabled) { NT.Audio.play("error"); var can = Q.canCheckToday(q()); NT.Scenes.push(NT.Notice(can.why || TX().needMore)); } else daily(r.cmd); }
      else if (r.kind === "lesson") editLesson();
      else if (r.kind === "report") report();
    }

    var scene = {
      id: "QUEST", opaque: true,
      enter: function () { if (q().status === "offered") Q.accept(id); clampCursor(rows()); },
      resume: function () { clampCursor(rows()); },
      update: function (dt) {
        NT.State.tick(dt);
        if (flash > 0) flash -= dt;
        var rs = rows();
        if (!rs[cursor] || !selectable(rs[cursor])) clampCursor(rs);
        if (I.pressed("left")) { tabIndex = (tabIndex + 2) % 3; cursor = 0; clampCursor(rows()); NT.Audio.play("cursor"); return; }
        if (I.pressed("right")) { tabIndex = (tabIndex + 1) % 3; cursor = 0; clampCursor(rows()); NT.Audio.play("cursor"); return; }
        if (I.pressed("up")) moveCursor(rs, -1);
        if (I.pressed("down")) moveCursor(rs, 1);
        if (I.pressed("ok")) { I.consume("ok"); if (rs[cursor] && selectable(rs[cursor])) { NT.Audio.play("decide"); activate(rs[cursor]); } return; }
        if (I.pressed("cancel") || I.pressed("menu")) { I.consume("cancel"); I.consume("menu"); NT.Audio.play("close"); NT.Scenes.pop(); return; }
        var cl = I.clicks();
        for (var k = 0; k < cl.length; k++) {
          var c = cl[k];
          if (c.y >= 30 && c.y < 46) { var ti = Math.floor((c.x - LIST_X) / 84); if (ti >= 0 && ti < 3) { tabIndex = ti; cursor = 0; clampCursor(rows()); NT.Audio.play("cursor"); } return; }
          if (c.y >= NT.H - 18) { NT.Scenes.pop(); return; }
          var ri = Math.floor((c.y - 52 + scroll) / 16);
          if (ri >= 0 && ri < rs.length && selectable(rs[ri])) { cursor = ri; NT.Audio.play("decide"); activate(rs[ri]); return; }
        }
        /* スクロール */
        var top = cursor * 16, viewH = NT.H - 52 - 22;
        if (top - scroll > viewH - 16) scroll = top - (viewH - 16);
        if (top - scroll < 0) scroll = top;
      },
      draw: function (ctx) {
        NT.Screen.clear("#0a0a16");
        var st = q();
        /* 見出し */
        ctx.fillStyle = "#15152a"; ctx.fillRect(0, 0, NT.W, 28);
        T.draw(ctx, def.num + " " + def.title, 10, 6, "#f4d03f", { head: true, size: 16 });
        var statusTxt = st.status === "cleared" ? TX().cleared : Q.progressText(id);
        T.drawRight(ctx, statusTxt, NT.W - 10, 8, st.status === "cleared" ? "#7dffb0" : "#9aa0b4");
        /* タブ */
        for (var i = 0; i < 3; i++) {
          var tx = LIST_X + i * 84, label = [TX().prep, TX().exec, TX().report][i];
          var on = i === tabIndex;
          ctx.fillStyle = on ? "#f4d03f" : "#2a2a3e"; ctx.fillRect(tx, 30, 80, 16);
          T.draw(ctx, label, tx + 6, 32, on ? "#000" : "#9aa0b4");
        }
        T.draw(ctx, "◀▶", NT.W - 40, 32, "#5b5a66");
        /* 行 */
        var rs = rows();
        ctx.save(); ctx.beginPath(); ctx.rect(0, 50, NT.W, NT.H - 50 - 20); ctx.clip();
        for (var r = 0; r < rs.length; r++) {
          var row = rs[r], y = 52 + r * 16 - scroll;
          if (y < 36 || y > NT.H - 20) continue;
          var color = row.color || (row.kind === "head" ? "#f4afc4" : row.dim ? "#6e6a7a" : "#f4f1e8");
          var x = row.kind === "head" ? LIST_X : LIST_X + 12;
          var label = row.label;
          if (T.measure(label) > LIST_W - 16) { while (T.measure(label + "…") > LIST_W - 16 && label.length) label = label.slice(0, -1); label += "…"; }
          T.draw(ctx, label, x, y, color);
          if (r === cursor && selectable(row)) G.cursor(ctx, LIST_X + 2, y + 1, flash > 0 ? "#7dffb0" : "#f4d03f");
        }
        ctx.restore();
        /* 下の帯 */
        ctx.fillStyle = "#15152a"; ctx.fillRect(0, NT.H - 20, NT.W, 20);
        var hint = TABS[tabIndex] === "exec" && impl.execHint ? impl.execHint : TABS[tabIndex] === "prep" ? def.summary : "条件が そろったら 長老に ほうこく";
        var hl = T.wrap(hint, NT.W - 70);
        T.draw(ctx, hl[0], 8, NT.H - 16, "#9aa0b4");
        T.drawRight(ctx, "X:とじる", NT.W - 8, NT.H - 16, "#5b5a66");
        NT.InputBox.draw(ctx);
      }
    };
    return scene;
  };
})();
