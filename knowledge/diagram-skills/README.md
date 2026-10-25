# 図解スキルのナレッジ（archify / diagram-design / anatomy）

AI エージェントに入れて図を作らせるスキル 3 つの要点と使い分けをまとめたもの。いずれも MIT ライセンスの外部リポジトリで、このフォルダにはコードを入れず、読んだ結果と使った結果だけを置く。

- **構造を正確に伝える** → [archify](archify.md)
- **資料に貼る図を整える** → [diagram-design](diagram-design.md)
- **仕組みを触って体験させる** → [anatomy](anatomy.md)（手順書: [anatomy-guide.md](anatomy-guide.md)）

確認日は 2026-10-24。archify と diagram-design はリポジトリを読んだだけで、動かしていない。anatomy は実際に 2 台の機械図解を作った（[anatomy.md の「実践で分かったこと」](anatomy.md#実践で分かったこと)）。

## 1. 基本情報

| | archify | diagram-design | anatomy |
|---|---|---|---|
| リポジトリ | [tt-a1i/archify](https://github.com/tt-a1i/archify) | [cathrynlavery/diagram-design](https://github.com/cathrynlavery/diagram-design) | [wheresryan22/anatomy](https://github.com/wheresryan22/anatomy) |
| 確認した版 | v3.2.0（commit `25cf370`、2026-10-19） | v2.6.120（commit `0b9b10c`、2026-10-24） | commit `1482e84`（2026-10-18） |
| 規模 | 約 1,170 ファイル（重い） | 約 690 ファイル | 約 170 ファイル |
| 必要なもの | Node 18 以上、ブラウザ（表示の自動確認） | Python 3（PNG / SVG 書き出し時のみ） | Node 20.10 以上、Chrome / Chromium（自動検査）。動画にするなら ffmpeg |
| 導入 | `npx skills add tt-a1i/archify -g` | `npx skills add cathrynlavery/diagram-design` | `npx skills add wheresryan22/anatomy -g -a claude-code` |

## 2. 何を作るか

| | archify | diagram-design | anatomy |
|---|---|---|---|
| 一言で | 正確な構造図 | 資料に貼れる整った図 | 触って分かる機械の図解 |
| 見た目 | 箱と矢印。拡大縮小・経路のハイライト・検索ができる HTML | 箱と矢印やグラフ。静的な SVG | 斜め上から見た立体の機械。部品は数十〜百個 |
| 図の種類 | 10 種類 + 1 ページ解説 | 45 種類（グラフを含む） | 決まっていない。概念ごとに機械を考え出す |
| 出力 | 単体 HTML、画像、SVG、動画（WebM） | 単体 HTML、PNG、SVG | 単体 HTML、動画（mp4） |
| 制作時間 | 数分 | 数分 | 1 時間〜数時間 |
| 中心の考え方 | 見栄えより正確さ。書かれていない関係は描かない | 減らすのが一番の改善 | 物そのものが説明 |

## 3. 強みと弱み

| | archify | diagram-design | anatomy |
|---|---|---|---|
| 強み | コードを読み、特定の commit に固定したソースリンク付きの図にできる。出力前に自動検査。Mermaid を読み込める | ブランドの色とフォントを読み取って登録できる。スライド用の 16:9 / 4:3 の型。draw.io / Mermaid / Excalidraw を読み込める | 数値をすべて 1 つの計算式から出すので表示が食い違わない。部品の重なり・浮き・線の端・描画順を自動検査。印象に残る |
| 弱み | 数値グラフは対象外。重い。操作画面（ボタン等）に日本語版がない | 操作できない。正確さの自動検査は弱い。A4 横の型がない | 時間と使用量が大きい。PowerPoint にはそのまま入らない（ブラウザで見せるか動画にする） |
| 外部通信 | 新しい版の有無を確認する通信あり（自動更新はしない） | 図を開くと Google Fonts を読み込む。`--system-fonts` で止められる | 生成物には外部 URL なし（実際に作って確認） |

## 4. Viniprj での使い道

| ツール | 使い方 | 守ること |
|---|---|---|
| `pptx-web-bridge/` | 取り込まない。diagram-design のルール集（要素は 9 個まで、強調色は 1〜2 か所、影なし、描く前に種類と削る物を宣言）と、anatomy の「図 1 枚に伝えることは 1 つ」を、Copilot への指示文の「型ごとの作り方」に書き写す | このアプリは図を描かない（CLAUDE.md 9 章）。取り入れたら `docs/99` に 1 行残す |
| `ai-water-footprint/` | anatomy で「1 回の質問で ◯ mL が蒸発する」を冷却塔の機械として見せる案が一番合う。数値を `js/data.js` だけに置く今の決まりと、anatomy の「計算式は 1 つ」が同じ考え方 | ビルドなし・依存なしの決まりがあるので、生成物の単体 HTML だけを置く。キットを使うなら `vendor/` に複製し、取得元 commit を記録する |
| 研修・説明資料（リポジトリ外） | 図をスライドに貼るなら diagram-design。触れる教材や動画なら anatomy。システムの引き継ぎ図なら archify | 非公開のコードや資料から作った図は、このリポジトリに置かない |

## 5. 入れるときの注意

- 外部リポジトリのスキルなので、業務環境で使う前に中身を読む。
- この環境では CDN が塞がれている。HTML に外部のスクリプトやフォントの読み込みが残っていないかを確かめる（diagram-design は既定で Google Fonts を読む）。
- 日本語: diagram-design は日本語フォントを同梱せず PC 側のフォントに頼る。archify の操作画面は英語・中国語など（日本語の README はある）。anatomy は日本語ラベルが表示できることを確認済み（[anatomy.md](anatomy.md)）。
- archify の README にはスポンサー広告が載っているが、スキル本体とは関係ない。
