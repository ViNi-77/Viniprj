/* クエスト定義。❿❾は完全実装、❽〜❶は依頼文のみ（PR 2 以降で実装）。
   clear/bonus の条件は 50_quests.js の条件表で評価する（eval は使わない） */
(function () {
  "use strict";
  var NT = window.NT = window.NT || {}; NT.DATA = NT.DATA || {};
  var PLAN = ["when", "where", "how", "obstacle"];
  NT.DATA.QUESTS = {
    q10: {
      id: "q10", floor: 10, num: "⑩", title: "すてられなかった物を すてる", npc: "npc10", implemented: true,
      summary: "何年も すてられなかった物を ひとつ すてる。大きい物ほど よい",
      prep: {
        fields: PLAN,
        list: {
          kind: "entries", label: "すてる物", min: 1, max: 10, itemLabel: "すてる物の なまえ",
          tags: [["big", "大きい"], ["space", "場所を取る"], ["sight", "いつも目に入る"], ["app", "アプリ・サブスク"], ["pricey", "高かった"], ["none", "とくになし"]],
          extra: [["why", "なぜ 買った？（ひとこと）"]]
        }
      },
      exec: { commands: [{ id: "discard", label: "すてる", weight: 6, sfx: "item", log: "{text}を すてた！" }] },
      clear: [["doneCount", ">=", 1, "ひとつ すてる"], ["lesson", "nonempty", null, "教訓を ひとこと 書く"]],
      bonus: [["doneTag", "big", null, "大きい物を すてた"], ["doneCount", ">=", 3, "3つ以上 すてた"]],
      report: { lesson: true, lessonPrompt: "なぜ 買ったのか、ひとこと（教訓）" }
    },
    q9: {
      id: "q9", floor: 9, num: "⑨", title: "やめられなかったコトを やめる", npc: "npc9", implemented: true,
      summary: "年末のあいだだけ ひとつ やめてみる。3日 つづいたら クリア",
      prep: {
        fields: PLAN,
        list: {
          kind: "candidates", label: "やめたいこと", min: 1, max: 5, itemLabel: "やめたいこと",
          extra: [["reason", "今年 やらなければ よかった 理由"]]
        }
      },
      exec: {
        declare: true, daily: true, streakNeeded: 3, charms: 2,
        commands: [
          { id: "declare", label: "年末限定で やめると 宣言する", once: true, weight: 6, sfx: "accept" },
          { id: "check", label: "きょうも やめた", daily: true, weight: 4, sfx: "item" },
          { id: "charm", label: "おやすみのお守りを つかう", limit: 2 }
        ]
      },
      clear: [["declared", null, null, "やめることを 宣言する"], ["streak", ">=", 3, "3日 つづける"], ["reason", "nonempty", null, "理由を 書く"]],
      bonus: [["streakThrough", "12-31", null, "12月31日まで つづけた"]],
      report: { lesson: true, lessonPrompt: "やめてみて わかったこと（教訓）" }
    },
    q8: { id: "q8", floor: 8, num: "⑧", title: "切れなかった人を 切る", npc: "npc8", implemented: false, summary: "「行かなくて良かった予定ランキング」を作り、惰性の関係を ひとつ 整理する" },
    q7: { id: "q7", floor: 7, num: "⑦", title: "挫折したモノを 再開する", npc: "npc7", implemented: false, summary: "挫折TOP5から ひとつ 選び、頼る人・足りなかった知識・教訓を そろえて 再開する" },
    q6: { id: "q6", floor: 6, num: "⑥", title: "手を付けなかったコトに 手を付ける", npc: "npc6", implemented: false, summary: "やりたかったTOP5を作り、ひとつでも 手を付ける" },
    q5: { id: "q5", floor: 5, num: "⑤", title: "変えられなかったコトを 小さく変える", npc: "npc5", implemented: false, summary: "変えたいことを 3段階 小さくして、3日 つづける" },
    q4: { id: "q4", floor: 4, num: "④", title: "もっと一緒にいたかった人に 連絡する", npc: "npc4", implemented: false, summary: "来年 もっと会いたい人TOP10を作り、3人に 連絡して ひとつ 予定を決める" },
    q3: { id: "q3", floor: 3, num: "③", title: "行きたかった場所に 行く予定を入れる", npc: "npc3", implemented: false, summary: "行きたかった場所を書き出し、来年の 日付で ひとつ 予定を入れる" },
    q2: { id: "q2", floor: 2, num: "②", title: "出来たコトの 新記録に挑戦する", npc: "npc2", implemented: false, summary: "今年できたことの ちょい上を 目標にして、1回 挑戦する" },
    q1: { id: "q1", floor: 1, num: "①", title: "最高のホワイトタイムを 過ごす", npc: "npc1", implemented: false, summary: "空白の時間を 予約し、10分 なにもしない", final: true }
  };
  NT.DATA.QUEST_ORDER = ["q10", "q9", "q8", "q7", "q6", "q5", "q4", "q3", "q2", "q1"];
})();
