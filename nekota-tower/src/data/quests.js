/* クエスト定義（⑩〜①）。ロジックは 50_quests.js / 53_scene_quest.js / 54_quest_impls.js。
   prep.fields  … if-then の共通欄（いつ・どこで・どうやって・じゃまするもの）
   prep.lists   … リスト（複数可）。{kind, label, min, max, itemLabel, tags?, extra?}
   prep.extras  … 自由記述欄。{key, label, maxLen, multiline?}。値は q.extras[key]
   exec.commands… 項目に対するコマンド。{id, label, flag, weight, sfx, log, input?:{field,title,kind:'text'|'date'|'number',maxLen}}
                  実行すると entry[flag+'Key'] に当日の日付キーが入る（60 秒以内なら とりけし 可）
   exec.declare / daily / charms … 宣言と日次チェック（⑨⑤）
   exec.white   … 10 分なにもしない（①）
   clear / bonus … [atom, 引数1, 引数2, 表示名]。atom は 50_quests.js の条件表 */
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
        lists: [{
          kind: "entries", label: "すてる物", min: 1, max: 10, itemLabel: "すてる物の なまえ",
          tags: [["big", "大きい"], ["space", "場所を取る"], ["sight", "いつも目に入る"], ["app", "アプリ・サブスク"], ["pricey", "高かった"], ["none", "とくになし"]],
          extra: [["why", "なぜ 買った？（ひとこと）"]]
        }]
      },
      exec: { commands: [{ id: "discard", label: "すてる", flag: "done", mark: "●", weight: 6, sfx: "item", log: "{text}を すてた！" }] },
      clear: [["flagCount", "entries:done", 1, "ひとつ すてる"], ["lesson", null, null, "教訓を ひとこと 書く"]],
      bonus: [["doneTag", "big", null, "大きい物を すてた"], ["flagCount", "entries:done", 3, "3つ以上 すてた"]],
      report: { lesson: true, lessonPrompt: "なぜ 買ったのか、ひとこと（教訓）" }
    },
    q9: {
      id: "q9", floor: 9, num: "⑨", title: "やめられなかったコトを やめる", npc: "npc9", implemented: true,
      summary: "年末のあいだだけ ひとつ やめてみる。3日 つづいたら クリア",
      prep: {
        fields: PLAN,
        lists: [{ kind: "candidates", label: "やめたいこと", min: 1, max: 5, itemLabel: "やめたいこと", extra: [["reason", "今年 やらなければ よかった 理由"]] }]
      },
      exec: { declare: true, declareLabel: "これを 年末限定で やめると 宣言する", checkLabel: "きょうも やめた", daily: true, streakNeeded: 3, charms: 2, commands: [] },
      clear: [["declared", null, null, "やめることを 宣言する"], ["streak", ">=", 3, "3日 つづける"], ["reason", null, null, "理由を 書く"]],
      bonus: [["streakThrough", "12-31", null, "12月31日まで つづけた"]],
      report: { lesson: true, lessonPrompt: "やめてみて わかったこと（教訓）" }
    },
    q8: {
      id: "q8", floor: 8, num: "⑧", title: "切れなかった人を 切る", npc: "npc8", implemented: true,
      summary: "「行かなくて良かった予定ランキング」を プライベートと仕事で作り、惰性の関係を ひとつ 整理する",
      prep: {
        fields: PLAN,
        lists: [
          { kind: "privateRank", label: "行かなくて良かった予定（プライベート）", min: 3, max: 5, itemLabel: "予定の なまえ（1位から）", extra: [["why", "なぜ 行かなくて よかった？"]] },
          { kind: "workRank", label: "行かなくて良かった予定（仕事）", min: 3, max: 5, itemLabel: "予定の なまえ（1位から）", extra: [["why", "なぜ 行かなくて よかった？"]] }
        ],
        extras: [{ key: "relation", label: "この先 どんな関係を 歩みたいか（ひとこと）", maxLen: 60 }]
      },
      exec: { commands: [{ id: "sort", label: "この予定・関係を 整理する", flag: "sorted", mark: "●", weight: 6, sfx: "item", log: "「{text}」を 整理した" }] },
      clear: [["listCount", "privateRank", 3, "プライベートの ランキングを 3つ以上"], ["listCount", "workRank", 3, "仕事の ランキングを 3つ以上"], ["flagCount", "*:sorted", 1, "ひとつ 整理する"], ["extra", "relation", null, "歩みたい関係を ひとこと"]],
      bonus: [["listCount", "privateRank", 5, "プライベートを 5つ"], ["listCount", "workRank", 5, "仕事を 5つ"]],
      report: { lesson: true, lessonPrompt: "ランキングを 作って 見えた 条件や 人（教訓）" }
    },
    q7: {
      id: "q7", floor: 7, num: "⑦", title: "挫折したモノを 再開する", npc: "npc7", implemented: true,
      summary: "挫折TOP5から ひとつ 選び、頼る人・足りなかった知識・前回の教訓を そろえて 再開する。完走は いらない",
      prep: {
        fields: PLAN,
        lists: [{ kind: "failed", label: "挫折TOP5（上から順に）", min: 3, max: 5, itemLabel: "挫折したこと" }],
        extras: [
          { key: "support", label: "頼れる人（だれに なにを 頼む？）", maxLen: 60 },
          { key: "knowledge", label: "足りなかった知識（なにを 調べる？）", maxLen: 60 },
          { key: "pastLesson", label: "前回の 失敗から 学んだこと", maxLen: 60 }
        ]
      },
      exec: { commands: [{ id: "resume", label: "これを 再開した", flag: "resumed", mark: "●", weight: 6, sfx: "item", log: "「{text}」を 再開した！" }, { id: "asked", label: "頼る人に 連絡した", flag: "asked", mark: "★", weight: 4, sfx: "tap", log: "「{text}」のことで 人に 頼った" }] },
      clear: [["listCount", "failed", 3, "挫折TOP5を 3つ以上"], ["extrasAll", ["support", "knowledge", "pastLesson"], null, "頼る人・知識・教訓を そろえる"], ["flagCount", "failed:resumed", 1, "ひとつ 再開する"]],
      bonus: [["flagCount", "failed:asked", 1, "頼る人に 実際に 連絡した"]],
      report: { lesson: true, lessonPrompt: "再開してみて わかったこと（教訓）" }
    },
    q6: {
      id: "q6", floor: 6, num: "⑥", title: "手を付けなかったコトに 手を付ける", npc: "npc6", implemented: true,
      summary: "やりたかったのに 手を付けなかったこと TOP5。ひとつでいい、とりあえず 手を付ける",
      prep: {
        fields: PLAN,
        lists: [{ kind: "wants", label: "やりたかったのに 手を付けなかったこと TOP5", min: 3, max: 5, itemLabel: "やりたかったこと", extra: [["whyNot", "なぜ 手を付けなかった？（ひとこと）"]] }]
      },
      exec: { commands: [{ id: "touch", label: "てをつけた", flag: "done", mark: "●", weight: 6, sfx: "item", log: "「{text}」に 手を付けた！" }] },
      clear: [["listCount", "wants", 3, "TOP5を 3つ以上"], ["flagCount", "wants:done", 1, "ひとつ 手を付ける"]],
      bonus: [["flagCount", "wants:done", 3, "3つ以上 手を付けた"]],
      report: { lesson: true, lessonPrompt: "手を付けてみて わかったこと。来年の 習慣に なりそうか" }
    },
    q5: {
      id: "q5", floor: 5, num: "⑤", title: "変えられなかったコトを 小さく変える", npc: "npc5", implemented: true,
      summary: "変えたいことを 3段階 小さくして、いちばん小さい形で 3日 つづける",
      prep: {
        fields: PLAN,
        extras: [{ key: "goal", label: "変えたいこと（大きいまま 書く）", maxLen: 40 }],
        lists: [{ kind: "steps", label: "小さくする（3段階。下に行くほど 小さく）", min: 3, max: 3, itemLabel: "もっと 小さくすると？" }]
      },
      exec: { declare: true, declareFrom: "steps", declareLast: true, declareLabel: "いちばん小さい形で はじめると 宣言する", checkLabel: "きょうも やった", daily: true, streakNeeded: 3, charms: 2, commands: [] },
      clear: [["extra", "goal", null, "変えたいことを 書く"], ["listCount", "steps", 3, "3段階まで 小さくする"], ["declared", null, null, "いちばん小さい形を 宣言する"], ["streak", ">=", 3, "3日 つづける"]],
      bonus: [["streakThrough", "12-31", null, "12月31日まで つづけた"]],
      report: { lesson: true, lessonPrompt: "小さくしてみて わかったこと（教訓）" }
    },
    q4: {
      id: "q4", floor: 4, num: "④", title: "もっと一緒にいたかった人に 連絡する", npc: "npc4", implemented: true,
      summary: "来年 もっと会いたい人 TOP10。自分から 連絡して、ひとつ 予定を決める。断られても 気にしない",
      prep: {
        fields: PLAN,
        lists: [{ kind: "people", label: "来年 もっと会いたい人 TOP10", min: 3, max: 10, itemLabel: "会いたい人（よびかた）", extra: [["topic", "なにを 話したい？（ひとこと）"]] }]
      },
      exec: {
        commands: [
          { id: "contact", label: "連絡した", flag: "contacted", mark: "●", weight: 5, sfx: "item", log: "{text}に 連絡した！" },
          { id: "schedule", label: "予定が 決まった（日付を入れる）", flag: "scheduled", mark: "★", weight: 8, sfx: "accept", log: "{text}と {date}に 会う！", input: { field: "date", kind: "date", title: "会う日（例 1/20 や 2027-01-20）" } }
        ]
      },
      clear: [["listCount", "people", 3, "会いたい人を 3人以上"], ["flagCount", "people:contacted", 3, "3人に 連絡する"], ["flagCount", "people:scheduled", 1, "ひとつ 予定を 決める"]],
      bonus: [["flagCount", "people:scheduled", 3, "3つ以上 予定が 決まった"]],
      report: { lesson: true, lessonPrompt: "連絡してみて どうだった（教訓）" }
    },
    q3: {
      id: "q3", floor: 3, num: "③", title: "行きたかった場所に 行く予定を入れる", npc: "npc3", implemented: true,
      summary: "行きたかったのに 行けなかった場所に、来年の 日付で 予定を 入れる。待つ時間が 幸福を 上げる",
      prep: {
        fields: PLAN,
        lists: [{ kind: "places", label: "行きたかったのに 行けなかった場所", min: 1, max: 10, itemLabel: "場所の なまえ", extra: [["withWho", "だれと？（ひとりでも よい）"]] }]
      },
      exec: {
        commands: [
          { id: "plan", label: "予定を 入れた（日付を入れる）", flag: "planned", mark: "★", weight: 8, sfx: "accept", log: "{date}に {text}へ 行く！", input: { field: "date", kind: "date", title: "行く日（例 3/15 や 2027-03-15）" } }
        ]
      },
      clear: [["listCount", "places", 1, "行きたかった場所を 書く"], ["flagCount", "places:planned", 1, "ひとつ 予定を 入れる"]],
      bonus: [["flagCount", "places:planned", 3, "3つ以上 予定を 入れた"]],
      report: { lesson: true, lessonPrompt: "予定を 入れてみて どんな気持ちか（教訓）" }
    },
    q2: {
      id: "q2", floor: 2, num: "②", title: "出来たコトの 新記録に挑戦する", npc: "npc2", implemented: true,
      summary: "今年できたことの ちょい上を 目標にして、年内に 1回 挑戦する。締切の力を つかう",
      prep: {
        fields: PLAN,
        extras: [
          { key: "did", label: "今年 できたこと", maxLen: 40 },
          { key: "record", label: "いまの記録（数字が あれば 数字で）", maxLen: 20 },
          { key: "target", label: "ちょい上の 目標（数字が あれば 数字で）", maxLen: 20 }
        ],
        lists: [{ kind: "attempts", label: "挑戦の 記録", min: 1, max: 10, itemLabel: "きょうの 記録（数字 か ひとこと）" }]
      },
      exec: { commands: [], attemptsAreActions: true },
      clear: [["extrasAll", ["did", "record", "target"], null, "できたこと・記録・目標を 書く"], ["listCount", "attempts", 1, "1回 挑戦する"]],
      bonus: [["newRecord", null, null, "新記録を 出した"]],
      report: { lesson: true, lessonPrompt: "ちょい上に 挑戦して わかったこと（教訓）" }
    },
    q1: {
      id: "q1", floor: 1, num: "①", title: "最高のホワイトタイムを 過ごす", npc: "npc1", implemented: true, final: true,
      summary: "空白の時間を 3つ 予約し、10分 なにもしない。ダラダラと 空白は ちがう",
      prep: {
        fields: PLAN,
        lists: [{ kind: "blocks", label: "空白の 予約（いつ・どれくらい）", min: 3, max: 5, itemLabel: "いつ・どれくらい（例 12/29 午前 1時間）" }],
        extras: [{ key: "detox", label: "そのあいだ 離れるもの（スマホ など）", maxLen: 40 }]
      },
      exec: { commands: [], white: true, whiteSeconds: 600 },
      clear: [["listCount", "blocks", 3, "空白を 3つ 予約する"], ["timer", null, 1, "10分 なにもしない を やりとげる"], ["extra", "reflect", null, "ふりかえりを ひとこと"]],
      bonus: [["timer", null, 2, "2回以上 やりとげた"]],
      report: { lesson: true, lessonPrompt: "空白の時間で 気づいたこと（教訓）", reflectKey: "reflect", reflectLabel: "ふりかえり（1行）" }
    }
  };
  NT.DATA.QUEST_ORDER = ["q10", "q9", "q8", "q7", "q6", "q5", "q4", "q3", "q2", "q1"];
})();
