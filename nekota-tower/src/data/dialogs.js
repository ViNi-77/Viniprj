/* 会話スクリプト。形式は 20_dialog.js 冒頭を参照。{name} はプレイヤー名、{daysLeft} は残り日数 */
(function () {
  "use strict";
  var NT = window.NT = window.NT || {}; NT.DATA = NT.DATA || {};
  var ELDER = "としのせの長老", NEKO = "ねこ太";
  NT.DATA.DIALOGS = {
    /* プロローグ（はじめから の直後） */
    "d.prologue": [
      { set: { prologueDone: true } },
      { who: ELDER, text: "……来たか、{name}。ここは「十二月の塔」。年の瀬にだけ 扉がひらく。" },
      { who: ELDER, text: "いまの世は あまりに 余裕のない者が多い。数秒の待ち時間に いらだち、すきまを すべて 画面で うめてしまう。" },
      { who: NEKO, text: "ぼくも、気づいたら スマホを 見ちゃうんだ……。" },
      { who: ELDER, text: "この塔の 十の階には、それぞれ「年内に やり切りたいこと」を かかえた者がいる。話を聞き、現実で 手を動かし、ここへ 報告せよ。" },
      { who: ELDER, text: "三つの しるしで 合格。十の しるしを そろえた者だけが、一番下の 扉の先を 見られる。" },
      { who: ELDER, text: "十二月は うまく使えば 三か月ぶんの 重さがある。残りは {daysLeft}日。いそがず、あなどらず。" },
      { who: NEKO, text: "いこう、{name}。まずは この階の 右のほうに 困っている子が いるみたい。" }
    ],
    "d.elder": [
      { if: "flag:prologueDone", else: "d.prologue" },
      { if: "clears>=10", goto: "d.elder.true" },
      { if: "quest:q1:cleared", goto: "d.elder.final" },
      { if: "clears>=3", goto: "d.elder.pass" },
      { if: "clears>=8", goto: "d.elder.8" },
      { if: "clears>=5", goto: "d.elder.5" },
      { who: ELDER, text: "しるしは {marks}つ。三つで 合格じゃ。階は どこから 回ってもよい。" },
      { who: ELDER, text: "入力したことは 静かに 記録される。ほんとうに 祝うのは、現実で やりとげて ここへ 報告したときだけ。" },
      { choice: [
        { label: "塔のことを きく", goto: "d.elder.help" },
        { label: "しるしのことを きく", goto: "d.elder.marks" },
        { label: "もどる", end: true }
      ] }
    ],
    "d.elder.8": [
      { who: ELDER, text: "しるし {marks}つ。けんじゃの 域じゃ。残りは 焦らず、ひとつずつ。" },
      { goto: "d.elder.menu" }
    ],
    "d.elder.5": [
      { who: ELDER, text: "しるし {marks}つ。ゆうしゃ じゃな。合格は もう 済んでおる。ここからは 遊びじゃ。" },
      { goto: "d.elder.menu" }
    ],
    "d.elder.menu": [
      { choice: [
        { label: "塔のことを きく", goto: "d.elder.help" },
        { label: "しるしのことを きく", goto: "d.elder.marks" },
        { label: "もどる", end: true }
      ] }
    ],
    "d.elder.help": [
      { who: ELDER, text: "階段で 下へ。左はしの 扉は エレベーターじゃ。石碑に ふれれば きろくを のこせる。" },
      { who: ELDER, text: "きろくは 本体メモリに のこるが、ファイルを 動かすと 見えなくなることがある。だいじな きろくは メモリーカードへ。" },
      { end: true }
    ],
    "d.elder.marks": [
      { who: ELDER, text: "しるしは 階ごとの 依頼を やりとげた あかし。三つで 合格、五つで 勇者、十で ……まあ、来てみれば わかる。" },
      { who: ELDER, text: "多ければ よいわけではない。ひとつでも、何年も できなかったことなら、それは 大きい。" },
      { end: true }
    ],
    "d.elder.pass": [
      { who: ELDER, text: "三つの しるし……合格じゃ、{name}。一番下の 扉が ひらいた。" },
      { who: ELDER, text: "だが 最後の階は、これまでと 逆のことを 求める。「なにもしない」を やりとげよ。" },
      { end: true }
    ],
    "d.elder.all": [
      { who: ELDER, text: "十の しるし。おぬしの 年の瀬は、もう おぬしのものじゃ。" },
      { end: true }
    ],
    "d.elder.true": [
      { who: ELDER, text: "十の しるし。{name}、おぬしは 年の瀬を 自分の手に 取りもどした。" },
      { who: NEKO, text: "来年の 予定も、もう 手の中に あるね。" },
      { choice: [
        { label: "白い朝を 見る（トゥルーエンディング）", call: "ending.true" },
        { label: "塔の 景色を 見る（エンディング）", call: "ending.normal" },
        { label: "まだ 塔に のこる", end: true }
      ] }
    ],
    "d.lap2": [
      { who: ELDER, text: "……また 来たか、{name}。去年は しるし {lastMarks}つ、「{lastTitle}」で 終えた。" },
      { who: ELDER, text: "去年の 教訓と、会う約束と、行く予定は 引き継いである。塔は 新しく 組み直した。" },
      { who: NEKO, text: "去年の 自分からの 手紙、ぼくが 持ってるよ。最初の 教訓は──「{firstLesson}」。" },
      { who: ELDER, text: "三つで 合格、十で 白い朝。いそがず、あなどらず。" }
    ],
    "d.elder.final": [
      { who: ELDER, text: "……なにもしない を やりとげたか。しるしは {marks}つ。塔は、おぬしに ひとつの 景色を 見せる用意が ある。" },
      { who: NEKO, text: "いつでも 戻ってこられるよ。残りの階も、年が 明けるまでは そのまま。" },
      { choice: [
        { label: "塔の 景色を 見る（エンディング）", call: "ending.normal" },
        { label: "まだ 塔に のこる", end: true }
      ] }
    ],

    /* ❿ すてる */
    "d.q10": [
      { if: "quest:q10:cleared", goto: "d.q10.after" },
      { if: "quest:q10:!offered", goto: "d.q10.progress" },
      { who: "アライのグマ", text: "あっ、{name}……この箱、見える？ 何年も すてられない物で いっぱいなんだ。" },
      { who: "アライのグマ", text: "すてるべき物は もう すてた。残ってるのは「すてづらい物」。大きくて、場所を取って、いつも 目に入ってる やつ。" },
      { who: NEKO, text: "高かった服、使ってない機械、スマホの中の アプリや サブスクも 入るね。" },
      { who: "アライのグマ", text: "ひとつでいい。できれば 大きい物を。そして「なんで 買ったんだろう」を ひとこと 書いてほしい。それが 教訓になる。" },
      { choice: [{ label: "うける", goto: "d.q10.accept" }, { label: "あとで", end: true }] }
    ],
    "d.q10.accept": [
      { call: "quest.accept", arg: "q10" },
      { who: "アライのグマ", text: "ありがとう！ じゅんびの欄に、いつ・どこで・どうやって を 書いておくと、手が 動きやすいよ。" },
      { call: "quest.open", arg: "q10" }
    ],
    "d.q10.progress": [
      { who: "アライのグマ", text: "どう？ すてづらい物ほど、「なんで 買ったんだろう」が 思い出しやすいんだ。" },
      { choice: [
        { label: "クエストを ひらく", call: "quest.open", arg: "q10" },
        { label: "ほうこくする", call: "quest.report", arg: "q10", if: "reportable:q10" },
        { label: "もどる", end: true }
      ] }
    ],
    "d.q10.after": [
      { who: "アライのグマ", text: "部屋が 広くなった。古い物を かかえたままじゃ、人は 変われないんだね。" },
      { choice: [{ label: "クエストを ひらく", call: "quest.open", arg: "q10" }, { label: "もどる", end: true }] }
    ],

    /* ❾ やめる */
    "d.q9": [
      { if: "quest:q9:cleared", goto: "d.q9.after" },
      { if: "quest:q9:!offered", goto: "d.q9.progress" },
      { who: "ハムの助", text: "……ぽりぽり。あ、{name}。やめたいのに やめられないことって、ない？" },
      { who: "ハムの助", text: "言い訳を 考えてる時間が、いちばん 頭を つかれさせるんだ。" },
      { who: NEKO, text: "だから「年末のあいだだけ やめてみる」。期間限定なら、はじめやすい。" },
      { who: "ハムの助", text: "やめたいことを 書いて、ひとつ 宣言して、きょうも やめた、を 3日。「今年 やらなければ よかった理由」も 書いてね。" },
      { who: "ハムの助", text: "休みたい日は「おやすみのお守り」を 2つまで つかえる。つづきは 切れないよ。" },
      { choice: [{ label: "うける", goto: "d.q9.accept" }, { label: "あとで", end: true }] }
    ],
    "d.q9.accept": [
      { call: "quest.accept", arg: "q9" },
      { who: "ハムの助", text: "よし。じゃあ まず、やめたいことを 書き出そう。" },
      { call: "quest.open", arg: "q9" }
    ],
    "d.q9.progress": [
      { who: "ハムの助", text: "きょうは どう？ 1日 1回、「きょうも やめた」を 押すだけで いいんだ。" },
      { choice: [
        { label: "クエストを ひらく", call: "quest.open", arg: "q9" },
        { label: "ほうこくする", call: "quest.report", arg: "q9", if: "reportable:q9" },
        { label: "もどる", end: true }
      ] }
    ],
    "d.q9.after": [
      { who: "ハムの助", text: "この期間に やめられたことは、つづきやすいんだって。ぽりぽりは……ちょっと 減ったよ。" },
      { choice: [{ label: "クエストを ひらく", call: "quest.open", arg: "q9" }, { label: "もどる", end: true }] }
    ],

    /* ⑧ 切れなかった人を 切る */
    "d.q8": [
      { if: "quest:q8:cleared", goto: "d.q8.after" },
      { if: "quest:q8:!offered", goto: "d.q8.progress" },
      { who: "フクロウ先生", text: "ほう、{name}か。今年の 予定を すべて 見返したことは あるかね。" },
      { who: "フクロウ先生", text: "「行かなくて良かった予定ランキング」を 作るのじゃ。プライベートと 仕事、両方な。" },
      { who: NEKO, text: "ランキングにすると、特定の 条件や 人が 浮かんでくるんだって。" },
      { who: "フクロウ先生", text: "惰性で 会っている関係を ひとつ 整理する。相手を 責める必要は ない。時間を 自分に 返すだけじゃ。" },
      { who: "フクロウ先生", text: "最後に「この先 どんな関係を 歩みたいか」を ひとこと。それが この階の 依頼じゃ。" },
      { choice: [{ label: "うける", goto: "d.q8.accept" }, { label: "あとで", end: true }] }
    ],
    "d.q8.accept": [
      { call: "quest.accept", arg: "q8" },
      { who: "フクロウ先生", text: "よろしい。他人に 使っている時間は、思うより 多く、長く、むだが 多い。" },
      { call: "quest.open", arg: "q8" }
    ],
    "d.q8.progress": [
      { who: "フクロウ先生", text: "ランキングは できたかね。上位ほど、来年 断る 候補じゃ。" },
      { choice: [
        { label: "クエストを ひらく", call: "quest.open", arg: "q8" },
        { label: "ほうこくする", call: "quest.report", arg: "q8", if: "reportable:q8" },
        { label: "もどる", end: true }
      ] }
    ],
    "d.q8.after": [
      { who: "フクロウ先生", text: "誰と会うかで 人生は 決まる。会いたい人とだけ 会う人生を、少しずつ。" },
      { choice: [{ label: "クエストを ひらく", call: "quest.open", arg: "q8" }, { label: "もどる", end: true }] }
    ],

    /* ⑦ 挫折したモノを 再開する */
    "d.q7": [
      { if: "quest:q7:cleared", goto: "d.q7.after" },
      { if: "quest:q7:!offered", goto: "d.q7.progress" },
      { who: "カメ吉", text: "……このギター、途中で やめちゃってさ。{name}にも、そういうの ある？" },
      { who: "カメ吉", text: "人生を ふりかえって、挫折TOP5を 作ってほしい。上のほうから ひとつ、再開してみる。コンプリートは いらない。" },
      { who: NEKO, text: "挫折したのは 実力不足じゃなくて、頼れる人・足りない知識・前回の教訓の どれかが 欠けてたから、なんだって。" },
      { who: "カメ吉", text: "だから 3つを そろえてから 再開する。ひとりで やろうとしないこと。それが この階の 依頼。" },
      { choice: [{ label: "うける", goto: "d.q7.accept" }, { label: "あとで", end: true }] }
    ],
    "d.q7.accept": [
      { call: "quest.accept", arg: "q7" },
      { who: "カメ吉", text: "ありがとう。人に 頼むのは 甘えじゃなくて、相手も 成長する 機会なんだって。" },
      { call: "quest.open", arg: "q7" }
    ],
    "d.q7.progress": [
      { who: "カメ吉", text: "3つ そろった？ そろったら、ほんの 少しでいいから 再開してみて。" },
      { choice: [
        { label: "クエストを ひらく", call: "quest.open", arg: "q7" },
        { label: "ほうこくする", call: "quest.report", arg: "q7", if: "reportable:q7" },
        { label: "もどる", end: true }
      ] }
    ],
    "d.q7.after": [
      { who: "カメ吉", text: "挑戦は 一度きりじゃ もったいない。自分の 挑戦の実績を、もっと 大事に しよう。" },
      { choice: [{ label: "クエストを ひらく", call: "quest.open", arg: "q7" }, { label: "もどる", end: true }] }
    ],

    /* ⑥ 手を付けなかったコトに 手を付ける */
    "d.q6": [
      { if: "quest:q6:cleared", goto: "d.q6.after" },
      { if: "quest:q6:!offered", goto: "d.q6.progress" },
      { who: "うさ子", text: "この手紙、ずっと 封を切れなくて。{name}にも「やりたかったのに 手を付けなかったこと」って あるでしょ？" },
      { who: "うさ子", text: "TOP5を 作って、なるべく 多く 手を付ける。とりあえず 手を付けてみてから 判断するの。" },
      { who: NEKO, text: "年末ぎりぎりに できたことは、来年の 習慣に なりやすいんだって。" },
      { who: "うさ子", text: "義務感のないものを えらんでね。やれなかったのは 戦略不足。時間と お金と 人と、自分の気持ちの 使い方。" },
      { choice: [{ label: "うける", goto: "d.q6.accept" }, { label: "あとで", end: true }] }
    ],
    "d.q6.accept": [
      { call: "quest.accept", arg: "q6" },
      { who: "うさ子", text: "うん。手を付けないと、来年も やらないから。" },
      { call: "quest.open", arg: "q6" }
    ],
    "d.q6.progress": [
      { who: "うさ子", text: "ひとつでも 手を付けた？ 「やってみてから 判断する」だよ。" },
      { choice: [
        { label: "クエストを ひらく", call: "quest.open", arg: "q6" },
        { label: "ほうこくする", call: "quest.report", arg: "q6", if: "reportable:q6" },
        { label: "もどる", end: true }
      ] }
    ],
    "d.q6.after": [
      { who: "うさ子", text: "封を 切ったよ。中身は……来年の 楽しみに なった。" },
      { choice: [{ label: "クエストを ひらく", call: "quest.open", arg: "q6" }, { label: "もどる", end: true }] }
    ],

    /* ⑤ 変えられなかったコトを 小さく変える */
    "d.q5": [
      { if: "quest:q5:cleared", goto: "d.q5.after" },
      { if: "quest:q5:!offered", goto: "d.q5.progress" },
      { who: "でんでん", text: "……ぼくらは 習慣の 奴隷。良い習慣も 悪い習慣も、急には 変えられない。" },
      { who: "でんでん", text: "だから 小さく 変えるしかない。近道は ない。変えたいことを 3段階、はるかに 小さくする。" },
      { who: NEKO, text: "筋トレしたい → 週3回 → 1日1回の 腕立て、みたいに？" },
      { who: "でんでん", text: "そう。いちばん小さい形で 3日。がむしゃらに 続けるより、変わりながら 続けるのが 大事。" },
      { choice: [{ label: "うける", goto: "d.q5.accept" }, { label: "あとで", end: true }] }
    ],
    "d.q5.accept": [
      { call: "quest.accept", arg: "q5" },
      { who: "でんでん", text: "……ゆっくりで いい。ハードルは、めっちゃ 下げて。" },
      { call: "quest.open", arg: "q5" }
    ],
    "d.q5.progress": [
      { who: "でんでん", text: "いちばん小さい形、見つかった？ 1日1回で いいんだよ。" },
      { choice: [
        { label: "クエストを ひらく", call: "quest.open", arg: "q5" },
        { label: "ほうこくする", call: "quest.report", arg: "q5", if: "reportable:q5" },
        { label: "もどる", end: true }
      ] }
    ],
    "d.q5.after": [
      { who: "でんでん", text: "小さく 変わりながら 続ける。それが 良い習慣を 形作る、たったひとつの 方法。" },
      { choice: [{ label: "クエストを ひらく", call: "quest.open", arg: "q5" }, { label: "もどる", end: true }] }
    ],

    /* ④ もっと一緒にいたかった人に 連絡する */
    "d.q4": [
      { if: "quest:q4:cleared", goto: "d.q4.after" },
      { if: "quest:q4:!offered", goto: "d.q4.progress" },
      { who: "ポッポ", text: "くるっぽ。{name}、今年 もっと 一緒に 時間を 過ごしたかった人、いる？" },
      { who: "ポッポ", text: "来年 もっと会いたい人 TOP10を 作って、自分から 連絡する。「どこかで ごはん 行きましょう」で いい。" },
      { who: NEKO, text: "断られても 気にしないこと。連絡は、こっちが 思っているより ずっと 喜ばれるんだって。" },
      { who: "ポッポ", text: "ひとつ 予定が 決まったら、それは 来年の 楽しみ。先の予定を 立てると、行動が 変わる。" },
      { choice: [{ label: "うける", goto: "d.q4.accept" }, { label: "あとで", end: true }] }
    ],
    "d.q4.accept": [
      { call: "quest.accept", arg: "q4" },
      { who: "ポッポ", text: "会いたい人に 会うと、話を 聞く力も 上がる。人間関係も、想像力も。" },
      { call: "quest.open", arg: "q4" }
    ],
    "d.q4.progress": [
      { who: "ポッポ", text: "連絡した？ 3人に 送って、ひとつ 日付が 決まれば じゅうぶん。" },
      { choice: [
        { label: "クエストを ひらく", call: "quest.open", arg: "q4" },
        { label: "ほうこくする", call: "quest.report", arg: "q4", if: "reportable:q4" },
        { label: "もどる", end: true }
      ] }
    ],
    "d.q4.after": [
      { who: "ポッポ", text: "誰と会うかで 人生が 決まる。来年は、会いたい人と 会う年に。" },
      { choice: [{ label: "クエストを ひらく", call: "quest.open", arg: "q4" }, { label: "もどる", end: true }] }
    ],

    /* ③ 行きたかった場所に 行く予定を入れる */
    "d.q3": [
      { if: "quest:q3:cleared", goto: "d.q3.after" },
      { if: "quest:q3:!offered", goto: "d.q3.progress" },
      { who: "ペン太郎", text: "スーツケース、もう 用意してあるんだ。{name}には、行きたいのに 行けなかった場所、ある？" },
      { who: "ペン太郎", text: "来年の 日付で 予定を 入れる。それだけで、待っている あいだずっと 幸福が 上がる。" },
      { who: NEKO, text: "修学旅行の 前の日に 眠れない、あの感じだね。" },
      { who: "ペン太郎", text: "そう。後ろに 何が 控えているかで、途中の 経験が 変わる。言い訳ばかりの 人生に、ここで 終止符。" },
      { choice: [{ label: "うける", goto: "d.q3.accept" }, { label: "あとで", end: true }] }
    ],
    "d.q3.accept": [
      { call: "quest.accept", arg: "q3" },
      { who: "ペン太郎", text: "予定の 先取りで、来年を それ前提の 年に できる。" },
      { call: "quest.open", arg: "q3" }
    ],
    "d.q3.progress": [
      { who: "ペン太郎", text: "日付、入れた？ 入れた瞬間から、待つ時間が はじまる。" },
      { choice: [
        { label: "クエストを ひらく", call: "quest.open", arg: "q3" },
        { label: "ほうこくする", call: "quest.report", arg: "q3", if: "reportable:q3" },
        { label: "もどる", end: true }
      ] }
    ],
    "d.q3.after": [
      { who: "ペン太郎", text: "自分の人生を 自分で 決めている感じ。それが いちばん 簡単な 幸福の 上げ方。" },
      { choice: [{ label: "クエストを ひらく", call: "quest.open", arg: "q3" }, { label: "もどる", end: true }] }
    ],

    /* ② 出来たコトの 新記録に挑戦する */
    "d.q2": [
      { if: "quest:q2:cleared", goto: "d.q2.after" },
      { if: "quest:q2:!offered", goto: "d.q2.progress" },
      { who: "ケロ吉", text: "ケロ！ {name}、今年 できたことを ひとつ 言ってみて。" },
      { who: "ケロ吉", text: "その ちょい上を 目標にして、年内に 1回 挑戦する。締切の力を あなどるな。" },
      { who: NEKO, text: "限界の ちょっと先に 行くときだけ、人は 成長するんだって。筋トレと おなじ。" },
      { who: "ケロ吉", text: "小さくていい。「ちょい上」が どこかを 知ることが ポイントだ。" },
      { choice: [{ label: "うける", goto: "d.q2.accept" }, { label: "あとで", end: true }] }
    ],
    "d.q2.accept": [
      { call: "quest.accept", arg: "q2" },
      { who: "ケロ吉", text: "いまの記録と 目標を 書いて、挑戦したら 記録を 入れる。それだけ！" },
      { call: "quest.open", arg: "q2" }
    ],
    "d.q2.progress": [
      { who: "ケロ吉", text: "挑戦した？ 年末ブーストは、あなどれないぞ。" },
      { choice: [
        { label: "クエストを ひらく", call: "quest.open", arg: "q2" },
        { label: "ほうこくする", call: "quest.report", arg: "q2", if: "reportable:q2" },
        { label: "もどる", end: true }
      ] }
    ],
    "d.q2.after": [
      { who: "ケロ吉", text: "習慣の アップグレード、完了。来年の 基準が ひとつ 上がった。" },
      { choice: [{ label: "クエストを ひらく", call: "quest.open", arg: "q2" }, { label: "もどる", end: true }] }
    ],

    /* ① 最高のホワイトタイムを 過ごす */
    "d.q1": [
      { if: "quest:q1:cleared", goto: "d.q1.after" },
      { if: "quest:q1:!offered", goto: "d.q1.progress" },
      { who: "しろくまさん", text: "……ぐう。ああ、{name}。ここまで 来たんだね。最後の階は、これまでと 逆のことを 頼む。" },
      { who: "しろくまさん", text: "空白の時間を 3つ 予約して、10分、なにも しない。スマホも 置いて。" },
      { who: NEKO, text: "ダラダラと 空白は ちがうんだよね。空白は、目的のある 時間。" },
      { who: "しろくまさん", text: "1年の 疲れを 置いて、新年に 備える。奥の部屋に、なにも しない ための 相手が いる。さわらないことが、勝ち方。" },
      { choice: [{ label: "うける", goto: "d.q1.accept" }, { label: "あとで", end: true }] }
    ],
    "d.q1.accept": [
      { call: "quest.accept", arg: "q1" },
      { who: "しろくまさん", text: "いそがしい年末だからこそ、「あえて なにもしない」が いちばん むずかしくて、いちばん 価値がある。……ぐう。" },
      { call: "quest.open", arg: "q1" }
    ],
    "d.q1.progress": [
      { who: "しろくまさん", text: "予約は できた？ 奥の部屋で、10分。手を はなすだけ。" },
      { choice: [
        { label: "クエストを ひらく", call: "quest.open", arg: "q1" },
        { label: "なにもしない を はじめる", call: "white.start" },
        { label: "ほうこくする", call: "quest.report", arg: "q1", if: "reportable:q1" },
        { label: "もどる", end: true }
      ] }
    ],
    "d.q1.after": [
      { who: "しろくまさん", text: "よく 来たね。空白の時間は、新しい挑戦の 準備と、1年の ふりかえりを 可能にする「心のスペース」。" },
      { who: "しろくまさん", text: "キリがいい タイミングは、人が いちばん 変われる チャンス。ここまで 来られたなら、きっと わかる。" },
      { choice: [{ label: "クエストを ひらく", call: "quest.open", arg: "q1" }, { label: "もどる", end: true }] }
    ],
    "d.boss": [
      { if: "quest:q1:cleared", goto: "d.boss.after" },
      { if: "quest:q1:offered", goto: "d.boss.hint" },
      { who: "？？？", text: "……………。" },
      { who: NEKO, text: "なにも 言わないね。ここは、なにも しない場所。さわらないことが、勝ち方なんだって。" },
      { choice: [{ label: "なにもしない を はじめる（10分）", call: "white.start" }, { label: "もどる", end: true }] }
    ],
    "d.boss.hint": [
      { who: "？？？", text: "……………。" },
      { who: NEKO, text: "しろくまさんから 依頼を 受けてから、だね。" }
    ],
    "d.boss.after": [
      { who: NEKO, text: "……しずかだ。ボスは もう いない。ここには、空白だけが 残った。" }
    ],

    /* 仕掛け */
    "d.door": [
      { who: NEKO, text: "扉が しまってる。「三つの しるしが いる」って 書いてある。" }
    ],
    "d.shelf": [
      { who: NEKO, text: "本棚だ。『WHITE SPACE』『より少ない家大全』『人に頼む技術』……。年末に 読み切ったら 人生 変わる、って 帯に ある。" }
    ],
    "d.window": [
      { if: "phase:over", goto: "d.window.over" },
      { if: "phase:final", goto: "d.window.final" },
      { if: "phase:dec", goto: "d.window.dec" },
      { who: NEKO, text: "窓の外は まだ 秋の色。のこり {daysLeft}日。じゅんびの あいだ。" }
    ],
    "d.window.over": [{ who: NEKO, text: "年が あけた。窓の外は しずかだ。" }],
    "d.window.final": [{ who: NEKO, text: "窓の外、町が そわそわしてる。のこり {daysLeft}日。きょうの ひと押しは 1か月ぶんだよ。" }],
    "d.window.dec": [{ who: NEKO, text: "窓の外は もう 暗い。のこり {daysLeft}日。12月は 2か月ぶんの 重さが あるんだって。" }],
    "d.pot": [
      { who: NEKO, text: "空の 植木鉢。この階の 依頼を やりとげると、花が 咲くらしい。" }
    ],
    "d.flower": [
      { who: NEKO, text: "花が 咲いてる。{name}が やりとげた あかしだ。" }
    ],
    "d.power": [
      { who: NEKO, text: "セーブしてないけど とじますか？" }
    ]
  };
})();
