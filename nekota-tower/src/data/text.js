/* 画面の文言。ここ以外に UI の日本語を書かない（フォントのサブセットはこのファイル群から文字を集める） */
(function () {
  "use strict";
  var NT = window.NT = window.NT || {}; NT.DATA = NT.DATA || {};
  NT.DATA.TEXT = {
    title: "ねこ太と十二月の塔",
    subtitle: "年末クエスト",
    menu: { newGame: "はじめから", cont: "つづきから", card: "メモリーカード", bar: "酒場", settings: "せってい", back: "もどる", yes: "はい", no: "いいえ", ok: "けってい", cancel: "やめる", close: "とじる" },
    name: { title: "なまえを いれてください", hint: "6もじまで。Enter できめる", confirm: "「{name}」で いいですか？", empty: "なまえが からっぽです" },
    slot: { title: "きろくを えらんでください", empty: "―― からっぽ ――", overwrite: "きろく {n} に うわがきしますか？", load: "きろく {n} を ひらきますか？", suspend: "ちゅうだんデータが あります。ひらきますか？", none: "きろくが ありません", marks: "しるし", days: "のこり", play: "プレイ" },
    hud: { daysLeft: "のこり{n}日", feel: "体感{n}日ぶん", marks: "しるし {n}/10", unsaved: "*", over: "年が あけました" },
    save: { title: "きろくする", done: "きろくしました", fail: "本体メモリに かきこめませんでした。メモリーカードに かきだしてください", memoryNote: "ファイルを うごかすと 本体メモリは みえなくなります。だいじな きろくは メモリーカードへ" },
    card: {
      title: "メモリーカード", export: "カードに かきだす", import: "カードから よみこむ", password: "あいことばを つかう", nopass: "あいことばなし",
      choose: "かきだす きろくを えらぶ", exported: "カードを かきだしました（{file}）", imported: "カードを よみこみました", toSlot: "どの きろくに いれますか？",
      bad: "あいことばが ちがうようです", unsupported: "この ブラウザでは メモリーカードが つかえません", drop: "ここに カードを おとす",
      passPrompt: "あいことばを いれてください（なしなら Enter）", passAgain: "もういちど いれてください", passMismatch: "あいことばが そろいません"
    },
    quest: {
      tabs: ["うける", "じゅんび", "じっこう", "ほうこく"],
      prep: "じゅんび", exec: "じっこう", report: "ほうこく", add: "＋ ついかする", edit: "なおす", remove: "けす", done: "できた", undo: "とりけす",
      when: "いつ", where: "どこで", how: "どうやって", obstacle: "じゃまするもの", plan: "いつ・どこで・どうやって", notYet: "まだ できていない",
      cleared: "クエストクリア！", mark: "しるしを てにいれた", flower: "この階に 花が さいた", title: "称号が「{t}」に なった",
      preparing: "（この階は じゅんびちゅう）", today: "きょう", streak: "{n}日 つづいている", checked: "きょうは もう チェックずみ", frozen: "とけいが みらいから もどってきたみたい。きょうの チェックは おやすみ",
      charm: "おやすみのお守り", charmLeft: "のこり {n}", charmUsed: "お守りを つかった。きょうは やすんでも つづく",
      bonus: "ボーナス", close: "とじる", lesson: "教訓", lessonPrompt: "なぜ 買ったのか、ひとこと", reasonPrompt: "今年 やらなければ よかった 理由",
      confirmDone: "「{text}」を じっこうしたことにしますか？", confirmReport: "長老に ほうこくしますか？", reportText: "ひとこと（なにを どうしたか）",
      needMore: "まだ クリアの条件が そろっていない", condition: "クリアのじょうけん"
    },
    elevator: { title: "どの階へ？", locked: "1F は 3つの しるしが いる", floor: "{n}F" },
    power: { title: "でんげんを きる", confirm: "セーブしてないけど とじますか？", bye: "また あそんでね" },
    settings: { title: "せってい", msgSpeed: "もじの はやさ", sfx: "こうかおん", crt: "テレビふう", scale: "ひょうじ", scaleDevice: "ドットきじゅん", scaleCss: "ウィンドウきじゅん", motion: "うごき", on: "オン", off: "オフ", reduce: "ひかえめ" },
    ending: { result: "けっか はっぴょう", staffroll: "スタッフロール", thanks: "ここまで きてくれて ありがとう", next: "NEXT QUEST", again: "つよくて 2しゅうめ へ", title: "称号", marks: "しるし",
      bad: "「来年も 変わらない人」に なるところだった", badSub: "でも、ここまで 来た。CONTINUE？", cont: "CONTINUE", stay: "このまま 塔に のこる", trueEnd: "人生最高の余暇", trueSub: "十の しるし。来年の 予定は もう ここに ある" },
    tags: { title: "価値タグの 儀式", lead: "今年 やったことに、来年も 大事にしたい 価値を ひとつ 付ける。付かないものは 手放す", scroll: "来年の 方針", done: "巻物が できた", letgo: "手放す" },
    excuse: { appear: "いいわけ が あらわれた！", ask: "いま 頭に うかんだ いいわけ を 1行", fight: "たちむかう（最小の 行動を 宣言する）", run: "にげる（きょうは やらない）", fightAsk: "きょう できる いちばん 小さい 行動", fightDone: "いいわけ は きえた。ゆうき +1", ranAway: "いいわけ は また 来る。教訓の書に 残した", days: "{n}日 さわっていない" },
    bar: { title: "酒場", lead: "メモリーカードを 持ちよると、みんなの 達成が ならぶ。順位は つけない", load: "カードを よみこむ", empty: "まだ だれも いない。カードを 落とすか、よみこむ", cols: "しるし", nobody: "―" },
    library: { title: "図書室", lead: "この階の 本棚", kindBook: "本", kindVideo: "動画" },
    sys: { storageFail: "本体メモリが つかえません。きろくは メモリーカードに かきだしてください", fontFail: "フォントが よみこめませんでした。べつの もじで ひょうじします", loading: "よみこみちゅう" },
    titles: { 0: "たびびと", 1: "みならい", 3: "ぼうけんしゃ", 5: "ゆうしゃ", 8: "けんじゃ", 10: "人生最高の余暇" }
  };
  /* 年末の暦の小ネタ（HUD の下に出す）。出典は docs/01 */
  NT.DATA.CALENDAR_NOTES = {
    "12-12": "きょうは「今年の漢字」の日。一字で ことしを あらわすなら？",
    "12-13": "正月事始め。むかしは きょうから すす払いを はじめた",
    "12-28": "飾りつけは きょうまでが よいとされる。あすは「苦」の日",
    "12-29": "「二重苦」の日。むりに 急がなくていい",
    "12-30": "のこり ふつか。小さいことを ひとつ",
    "12-31": "おおみそか。きょうの ひと押しは 1か月ぶん"
  };
})();
