/* 価値タグの儀式。ED の前に、今年やったことへ「来年も大事にしたい価値」をひとつ付ける。付かないものは手放す。
   最後に、いちばん多いタグを「来年の方針」の巻物にする */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text, G = NT.Gfx, I = NT.Input, TX = function () { return NT.DATA.TEXT.tags; };

  /* タグを付ける対象：実行済みの項目、宣言、教訓 */
  function collect(st) {
    var items = [];
    NT.DATA.QUEST_ORDER.forEach(function (id) {
      var def = NT.DATA.QUESTS[id], q = st.quests[id] || {};
      NT.Quests.lists(def).forEach(function (L) {
        (q[L.kind] || []).forEach(function (e) {
          var marked = (def.exec && def.exec.commands || []).some(function (c) { return e[(c.flag || "done") + "Key"]; }) || L.kind === "attempts";
          if (marked) items.push({ id: e.id, text: def.num + " " + e.text });
        });
      });
      if (q.declared) items.push({ id: id + ":declared", text: def.num + " " + q.declared.text + "（宣言）" });
      if (q.lesson) items.push({ id: id + ":lesson", text: def.num + " 教訓：" + q.lesson });
    });
    return items.slice(0, 24);
  }

  NT.SceneTags = function (onDone) {
    var st = NT.State.cur, items = collect(st), i = 0, t = 0, phase = "intro", counts = {}, policy = "";
    st.valueTags = st.valueTags || {};
    function tagsMenuItems() { return NT.DATA.VALUE_TAGS.map(function (v) { return { label: v[1], value: v[0] }; }); }
    function next() {
      if (i >= items.length) { finish(); return; }
      var it = items[i];
      NT.Scenes.push(NT.Menu({ title: "来年も 大事にしたい 価値は？", w: 200, x: 60, y: 110, items: tagsMenuItems(), index: 0, cancelable: false,
        onSelect: function (sel) {
          st.valueTags[it.id] = sel.value;
          if (sel.value !== "letgo") counts[sel.value] = (counts[sel.value] || 0) + 1;
          NT.State.touch();
          NT.Scenes.pop(); i++; next();
        } }));
    }
    function finish() {
      var best = null;
      Object.keys(counts).forEach(function (k) { if (!best || counts[k] > counts[best]) best = k; });
      var label = best ? NT.DATA.VALUE_TAGS.filter(function (v) { return v[0] === best; })[0][1] : "";
      policy = best ? (st.year + 1) + "年は「" + label + "」の年に する" : (st.year + 1) + "年は 身軽に はじめる";
      st.policy = policy; NT.State.touch();
      phase = "scroll"; t = 0; NT.Audio.play("bloom");
    }
    var scene = {
      id: "TAGS", opaque: true,
      enter: function () { t = 0; },
      update: function (dt) {
        t += dt;
        if (phase === "intro") { if (I.pressed("ok") || I.clicks().length) { I.consume("ok"); if (!items.length) finish(); else { phase = "tag"; next(); } } return; }
        if (phase === "scroll") { if (t > 600 && (I.pressed("ok") || I.clicks().length)) { I.consume("ok"); NT.Scenes.pop(); if (onDone) onDone(); } }
      },
      draw: function (ctx) {
        NT.Screen.clear("#0a0a16");
        T.drawCenter(ctx, TX().title, NT.W / 2, 14, "#f4d03f", { head: true, size: 16 });
        if (phase === "intro") {
          T.drawLines(ctx, T.wrap(TX().lead, 280), 20, 50, "#f4f1e8");
          T.drawCenter(ctx, items.length + " 件", NT.W / 2, 120, "#9aa0b4");
          if ((t % 1000) < 500) T.drawCenter(ctx, "Z で はじめる", NT.W / 2, NT.H - 30, "#f4d03f");
          return;
        }
        if (phase === "tag") {
          var it = items[i];
          T.drawCenter(ctx, (i + 1) + " / " + items.length, NT.W / 2, 40, "#9aa0b4");
          if (it) T.drawLines(ctx, T.wrap(it.text, 280), 20, 64, "#f4f1e8");
          return;
        }
        /* 巻物 */
        G.frame(ctx, 24, 50, 272, 130, { fill: "#fff6d6", border: "#d08a4f", innerColor: "#e8c9a0" });
        T.drawCenter(ctx, TX().scroll, NT.W / 2, 62, "#6e3b1f", { head: true, size: 16 });
        T.drawLines(ctx, T.wrap(policy, 240), 40, 92, "#2e1a0b");
        var ks = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; });
        ks.slice(0, 4).forEach(function (k, j) { var lbl = NT.DATA.VALUE_TAGS.filter(function (v) { return v[0] === k; })[0][1]; T.draw(ctx, lbl + "　" + "■".repeat(Math.min(10, counts[k])), 40, 124 + j * 14, "#6e3b1f"); });
        T.drawCenter(ctx, TX().done + "　Z で つづける", NT.W / 2, NT.H - 30, "#f4d03f");
      },
      state: function () { return { phase: phase, i: i, n: items.length, policy: policy }; }
    };
    return scene;
  };
})();
