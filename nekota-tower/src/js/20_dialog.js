/* 会話ウィンドウ。data/dialogs.js のスクリプトを解釈する
   ステップ: {text, who} | {choice:[{label, goto, end, call, arg, value}]} | {if, goto, else} | {goto} | {set:{flag:value}} | {call, arg} | {sfx} | {wait} | {end:true}
   if 条件: 'quest:<id>:<status>' | 'quest:<id>:!<status>' | 'flag:<name>' | '!flag:<name>' | 'clears>=<n>' | 'phase:<name>' | 'impl:<id>' */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text, G = NT.Gfx, I = NT.Input;
  var D = NT.Dialog = {};
  D.hooks = {};   /* call 名 → function(arg, dialog) */

  D.evalCond = function (cond) {
    var st = NT.State.cur || { flags: {}, quests: {}, clears: [] };
    var neg = false;
    if (cond[0] === "!") { neg = true; cond = cond.slice(1); }
    var r = false, m;
    if ((m = /^quest:(\w+):(!?)(\w+)$/.exec(cond))) {
      var q = st.quests[m[1]] || { status: "offered" };
      r = (q.status === m[3]); if (m[2] === "!") r = !r;
    } else if ((m = /^flag:(\w+)$/.exec(cond))) r = !!st.flags[m[1]];
    else if ((m = /^clears>=(\d+)$/.exec(cond))) r = st.clears.length >= +m[1];
    else if ((m = /^phase:(\w+)$/.exec(cond))) r = NT.State.phase() === m[1];
    else if ((m = /^impl:(\w+)$/.exec(cond))) r = !!(NT.DATA.QUESTS[m[1]] && NT.DATA.QUESTS[m[1]].implemented);
    else if ((m = /^reportable:(\w+)$/.exec(cond))) r = NT.Quests ? NT.Quests.isReportable(m[1]) : false;
    return neg ? !r : r;
  };

  D.vars = function () {
    var st = NT.State.cur || {};
    return { name: st.name || "", daysLeft: NT.State.daysLeft(), feel: NT.State.feelDays(), marks: st.marks || 0, title: st.title || "" };
  };

  /* 会話シーンを開く。id はスクリプト名、または直接ステップ配列。opts.onEnd(result) */
  D.open = function (id, opts) {
    opts = opts || {};
    var script = Array.isArray(id) ? id : (NT.DATA.DIALOGS[id] || [{ text: "（" + id + " がみつからない）" }]);
    var scene = D.scene(script, opts);
    NT.Scenes.push(scene);
    return scene;
  };

  D.scene = function (script, opts) {
    var pc = 0, result = null;
    var page = null;          // {lines, shown, total, who}
    var choice = null;        // {items, index}
    var waitMs = 0, blink = 0, done = false;
    var W = 304, H = 76, X = 8, Y = NT.H - H - 6;
    var innerW = W - 24;

    function showText(text, who) {
      var lines = T.wrap(NT.Util.fmt(text, D.vars()), innerW);
      page = { lines: lines, shown: 0, total: T.countChars(lines), who: who || null, pages: [], pi: 0 };
      var per = who ? 3 : 4;
      for (var i = 0; i < lines.length; i += per) page.pages.push(lines.slice(i, i + per));
      page.cur = page.pages[0]; page.curTotal = T.countChars(page.cur);
    }
    function nextPage() {
      page.pi++;
      if (page.pi >= page.pages.length) { page = null; return false; }
      page.cur = page.pages[page.pi]; page.curTotal = T.countChars(page.cur); page.shown = 0;
      return true;
    }
    function finish(res) {
      if (done) return;
      done = true;
      NT.Scenes.remove(scene, res);
      if (opts.onEnd) opts.onEnd(res);
    }
    function gotoLabel(label) {
      if (Array.isArray(NT.DATA.DIALOGS[label])) { script = NT.DATA.DIALOGS[label]; pc = 0; return; }
      finish(result);
    }
    function step() {
      while (!page && !choice && waitMs <= 0 && !done) {
        if (pc >= script.length) { finish(result); return; }
        var s = script[pc++];
        if (typeof s === "string") { showText(s); return; }
        if (s.text !== undefined) { showText(s.text, s.who); return; }
        if (s.choice) {
          var items = s.choice.filter(function (c) { return !c.if || D.evalCond(c.if); });
          choice = { items: items, index: 0, title: s.title || null };
          return;
        }
        if (s.if) { if (D.evalCond(s.if)) { if (s.goto) gotoLabel(s.goto); else if (s.then) { script = s.then; pc = 0; } } else if (s.else) gotoLabel(s.else); continue; }
        if (s.goto) { gotoLabel(s.goto); continue; }
        if (s.set) { for (var k in s.set) { NT.State.cur.flags[k] = s.set[k]; } NT.State.touch(); continue; }
        if (s.call) { var fn = D.hooks[s.call]; if (fn) { var r = fn(s.arg, scene); if (r === "stop") { finish(result); return; } } continue; }
        if (s.sfx) { NT.Audio.play(s.sfx); continue; }
        if (s.wait) { waitMs = s.wait; return; }
        if (s.result !== undefined) { result = s.result; continue; }
        if (s.end) { finish(result); return; }
      }
    }
    var scene = {
      id: "DIALOG", opaque: false,
      enter: function () { step(); },
      update: function (dt) {
        blink += dt;
        if (waitMs > 0) { waitMs -= dt; if (waitMs <= 0) step(); return; }
        if (choice) {
          if (I.pressed("up")) { choice.index = (choice.index + choice.items.length - 1) % choice.items.length; NT.Audio.play("cursor"); }
          if (I.pressed("down")) { choice.index = (choice.index + 1) % choice.items.length; NT.Audio.play("cursor"); }
          var cl = I.clicks();
          for (var k = 0; k < cl.length; k++) {
            var box = choiceBox();
            for (var i = 0; i < choice.items.length; i++) {
              var ry = box.y + 10 + (choice.title ? 16 : 0) + i * 16;
              if (cl[k].x >= box.x && cl[k].x < box.x + box.w && cl[k].y >= ry - 2 && cl[k].y < ry + 14) { choice.index = i; I.press("ok"); }
            }
          }
          if (I.pressed("ok")) {
            I.consume("ok");
            var c = choice.items[choice.index];
            NT.Audio.play(c.sfx || "decide");
            choice = null;
            if (c.value !== undefined) result = c.value;
            if (c.set) { for (var kk in c.set) NT.State.cur.flags[kk] = c.set[kk]; NT.State.touch(); }
            if (c.call) { var fn = D.hooks[c.call]; if (fn && fn(c.arg, scene) === "stop") { finish(result); return; } }
            if (c.end) { finish(result); return; }
            if (c.goto) gotoLabel(c.goto);
            else if (c.then) { script = c.then; pc = 0; }
            step();
          }
          return;
        }
        if (page) {
          if (page.shown < page.curTotal) {
            var per = NT.Settings.charsPerStep();
            var before = Math.floor(page.shown);
            page.shown = Math.min(page.curTotal, page.shown + per);
            if (Math.floor(page.shown) !== before && (Math.floor(page.shown) % 3 === 0)) NT.Audio.play("tap");
            if (I.pressed("ok") || I.clicks().length) { I.consume("ok"); page.shown = page.curTotal; }
            return;
          }
          if (I.pressed("ok") || I.pressed("cancel") || I.clicks().length) {
            I.consume("ok"); I.consume("cancel");
            if (!nextPage()) step();
          }
        }
      },
      draw: function (ctx) {
        if (page) {
          G.frame(ctx, X, Y, W, H);
          var ty = Y + 10;
          if (page.who) { T.draw(ctx, page.who, X + 12, ty, "#f4d03f"); ty += 16; }
          T.drawLines(ctx, page.cur, X + 12, ty, "#f4f1e8", Math.floor(page.shown));
          if (page.shown >= page.curTotal && (blink % 1000) < 500) {
            var more = page.pi < page.pages.length - 1 || pc < script.length;
            if (more) G.nextMark(ctx, X + W - 18, Y + H - 10, "#f4d03f");
          }
        }
        if (choice) {
          var box = choiceBox();
          G.frame(ctx, box.x, box.y, box.w, box.h);
          var y0 = box.y + 10;
          if (choice.title) { T.draw(ctx, choice.title, box.x + 10, y0, "#f4d03f"); y0 += 16; }
          for (var i = 0; i < choice.items.length; i++) {
            var it = choice.items[i];
            T.draw(ctx, it.label, box.x + 20, y0 + i * 16, it.disabled ? "#5b5a66" : "#f4f1e8");
            if (i === choice.index) G.cursor(ctx, box.x + 11, y0 + i * 16 + 1, "#f4d03f");
          }
        }
      },
      /* テスト・外部用 */
      skip: function () { if (page) page.shown = page.curTotal; },
      end: function () { page = null; choice = null; finish(result); },
      state: function () { return { pc: pc, page: page ? page.cur.join("\n") : null, choice: choice ? choice.items.map(function (c) { return c.label; }) : null, index: choice ? choice.index : -1 }; },
      choose: function (i) { if (choice) { choice.index = i; I.press("ok"); } }
    };
    function choiceBox() {
      var maxW = 0;
      choice.items.forEach(function (it) { maxW = Math.max(maxW, T.measure(it.label)); });
      if (choice.title) maxW = Math.max(maxW, T.measure(choice.title) - 10);
      var w = maxW + 40, h = choice.items.length * 16 + 20 + (choice.title ? 16 : 0);
      var x = X + W - w - 4, y = Y - h - 2;
      if (!page) { x = Math.round((NT.W - w) / 2); y = Math.round((NT.H - h) / 2); }
      return { x: x, y: y, w: w, h: h };
    }
    return scene;
  };
})();
