# 補完機 — 生成AIの中身を、動く機械で見る

生成AIは考える機械ではなく、**届いた手紙の続きを一語ずつ埋める機械**。
それを本当に机の上の機械として描き、ボタンで工程を 1 つずつ動かせる研修教材にした。
単体 HTML、ライブラリなし、通信なし。

最初に「ですます調で」と頼んだのに、途中からタメ口になる。前提を伝えたはずなのに後半で無視される。
仕組みを知らないと「AIが壊れた」で終わるが、机が有限で紙が落ちるところを自分の手で見れば、
「話題が変わったら新しいチャット」が自然にできるようになる。

## 使い方

`completion-machine.html` をダブルクリックして開く（明テーマは `completion-machine-light.html`）。

| 工程 | 機械で起きること |
|---|---|
| ① 手紙を書く | 今回の頼み・材料・見本の紙が投入口に積まれる |
| ② 前のやり取りを綴じる | 綴じ器が下りて、前の会話の束が同じ手紙に綴じられる（毎回はじめまして） |
| ③ 机に広げる | 手紙の紙が机の 20 枠に並ぶ。机に載ったものしか AI には見えない |
| ④ 次の一語を選ぶ | 読み取りヘッドが机を読み、候補ダイヤルが回って一語をテープに印字する |
| ⑤ 続きを埋める | 同じことを繰り返して 8 語の文になる |
| ⑥ 往復を重ねる | 机があふれ、最初の紙が受け皿に落ちる（壁①: 机の広さ） |
| ⑦ 条件を積む | 条件ピンが立ち、注意力メーターの針が下がる（壁②: 指示の積みすぎ） |
| ⑧ 机を片付ける | レバーで机が空になる（話題が変わったら新しいチャット） |

左の列で押せるのは次の工程だけ。「自動」にすると 1 周（46 秒）して止まる。Space / Enter で次へ、Home で最初から。

### 動画版

```bash
python scripts/render_film.py --mp4 scripts/out/film.mp4   # 30 fps、46 秒、無音
```

絵コンテは `docs/05_映像設計.md`。

## 開発

```bash
node build.mjs                       # completion-machine.html を生成（自己チェック値を表示）
node build.mjs --light               # 明テーマ
node build.mjs --audit               # 幾何の監査（重なり・浮き・描画順）
export CHROME_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome   # 環境に合わせる
node vendor/anatomy/scripts/lines.mjs completion-machine.html --out scripts/out/lines.png   # 線の端
python scripts/ui_smoke.py           # 3 視口 + reduced-motion + 明テーマ + render
python scripts/render_film.py --check
```

Node 20 以上と、`playwright` の Python パッケージ（`pip install playwright`）が要る。ブラウザは `$PLAYWRIGHT_BROWSERS_PATH` または `CHROME_PATH` から探すので `playwright install` は不要（この環境では実行しない）。
`pip` で Pillow を入れると `--stills` が一覧表を作る。

- 数値は `js/data.js` にだけ書き、出典は `docs/03_数値の根拠.md` と一致させる。画面には「トークン」という語を出さない。
- 描画は [anatomy](https://github.com/wheresryan22/anatomy) のキット（MIT）を `vendor/anatomy/` に複製して使う。
- 設計は `docs/02_設計.md`、受入は `docs/04_受入試験.md`、判断は `docs/99_意思決定ログ.md`。

## 注意

- 机の枚数・手紙の枚数・条件の数は、説明のための架空の量（例示値）。本物の机の広さは公開資料の値で、画面には % だけ出す。
- 「注意力の取り分 = 100 ÷ 条件数」は研修の比喩を数にしたもので、モデルの内部をこの式で説明しているわけではない。
- 社名・個人情報・認証情報を含めない（public 前提）。
