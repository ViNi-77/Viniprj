/* ⑧〜② の見せ方。コマンドや条件は data/quests.js の定義と 53_scene_quest.js の汎用処理で動く */
(function () {
  "use strict";
  var NT = window.NT;
  var Q = function () { return NT.Quests; };
  NT.QuestImpl = NT.QuestImpl || {};

  NT.QuestImpl.q8 = {
    execStatus: function (q) {
      var sorted = Q().withFlag(q, "*:sorted", Q().def("q8")).length;
      return ["ランキングは じゅんび で。整理したい予定や関係を えらんで「整理する」", "整理した：" + sorted + "件" + (q.extras.relation ? "　歩みたい関係：" + q.extras.relation : "")];
    },
    execHint: "惰性の予定・関係を ひとつ 整理する。相手を 責める必要は ない"
  };

  NT.QuestImpl.q7 = {
    execStatus: function (q) {
      var ok = ["support", "knowledge", "pastLesson"].filter(function (k) { return q.extras[k]; }).length;
      return ["3要素（頼る人・知識・教訓）：" + ok + "/3　そろえてから 再開", "完走は いらない。再開した事実が 大事"];
    },
    execHint: "挫折の原因は 実力ではなく、頼れなかったこと。まず 人に 頼る"
  };

  NT.QuestImpl.q6 = {
    execStatus: function (q) {
      var n = Q().withFlag(q, "wants:done", Q().def("q6")).length;
      return ["手を付けた：" + n + "件。年末ぎりぎりに できたことは 来年の 習慣になりやすい"];
    },
    execHint: "とりあえず 手を付けてみてから 判断する。義務感のないものを"
  };

  NT.QuestImpl.q5 = {
    execStatus: function (q) {
      var lines = [];
      if (q.extras.goal) lines.push("変えたいこと：" + q.extras.goal);
      (q.steps || []).forEach(function (s, i) { lines.push("　" + "↓".repeat(i + 1) + " " + s.text); });
      if (!q.declared) lines.push(q.steps && q.steps.length >= 3 ? "いちばん下を えらんで 宣言しよう" : "じゅんび で 3段階まで 小さくする");
      else {
        lines.push("宣言：" + q.declared.text + "　" + NT.Util.fmt(NT.DATA.TEXT.quest.streak, { n: Q().streak(q) }));
        lines.push(NT.DATA.TEXT.quest.charm + "　" + NT.Util.fmt(NT.DATA.TEXT.quest.charmLeft, { n: q.charms || 0 }));
      }
      return lines;
    },
    execHint: "はるかに 小さく。腕立て1回の 大きさで、変わりながら つづける"
  };

  NT.QuestImpl.q4 = {
    execStatus: function (q) {
      var def = Q().def("q4");
      var c = Q().withFlag(q, "people:contacted", def).length, s = Q().withFlag(q, "people:scheduled", def);
      var lines = ["連絡した：" + c + "人　予定が決まった：" + s.length + "件"];
      if (s.length) lines.push("仲間：" + s.map(function (e) { return e.text; }).join("、"));
      lines.push("断られても 気にしない。連絡は 思っているより 喜ばれる");
      return lines;
    },
    execHint: "自分から 誘う。「どこかで ごはん 行きましょう」で じゅうぶん"
  };

  NT.QuestImpl.q3 = {
    execStatus: function (q) {
      var def = Q().def("q3"), planned = Q().withFlag(q, "places:planned", def);
      if (!planned.length) return ["行きたい場所を えらんで、来年の 日付を 入れる"];
      var today = Q().today(), soonest = null;
      planned.forEach(function (e) { if (e.date && (!soonest || e.date < soonest.date)) soonest = e; });
      var days = soonest ? NT.Time.diffDays(today, soonest.date) : 0;
      return ["予定：" + planned.length + "件　いちばん近い：" + soonest.text + "（" + NT.Time.mmdd(soonest.date).replace("-", "/") + "）", "待つ時間：あと " + days + "日。楽しみに 待つ あいだが いちばん 幸福"];
    },
    execHint: "予定を 先に 立てると、それを 待つ時間ごと 幸せになる"
  };

  NT.QuestImpl.q2 = {
    execStatus: function (q) {
      var lines = [];
      lines.push("できたこと：" + (q.extras.did || "（未記入）"));
      lines.push("いまの記録：" + (q.extras.record || "―") + "　ちょい上の目標：" + (q.extras.target || "―"));
      var best = null;
      (q.attempts || []).forEach(function (a) { var v = Q().num(a.text); if (!isNaN(v) && (best === null || v > best)) best = v; });
      if (best !== null) lines.push("挑戦の ベスト：" + best + (Q().newRecord(q) ? "　★ NEW RECORD" : ""));
      return lines;
    },
    execHint: "締切の力。小さくても「ちょい上」が どこかを 知るのが ポイント"
  };

  NT.QuestImpl.q1 = {
    execStatus: function (q) {
      var n = (q.blocks || []).length, t = q.timerDone || 0;
      var lines = ["空白の 予約：" + n + "/3　なにもしない 完走：" + t + "回"];
      if (q.extras.detox) lines.push("離れるもの：" + q.extras.detox);
      lines.push("1F の 奥の部屋でも はじめられる。さわると ボスが 回復する");
      return lines;
    },
    execHint: "空白は 目的のある 時間。ダラダラとは ちがう。10分、なにも しない"
  };
})();
