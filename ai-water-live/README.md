# トークンの水 — 世界でいま、AI の冷却で蒸発している淡水

生成 AI のトークン処理で消える電力と、データセンターの冷却・発電で蒸発する淡水を、3D の地球儀の上で
リアルタイムに見せる Web アプリ。「100 億トークン使った人は何リットル消したか」も計算できる。

- **地球儀**: 代表的なデータセンター拠点 20 か所が脈打ち、トークンの流れが弧になって集まり、拠点から水の粒が立ち上って消える。
- **世界ティッカー**: トークン/秒、平均電力、蒸発する水/秒、開いてからの累計（毎フレーム更新。足し込まず経過秒から計算）。
- **あなたのトークン**: トークン数（1 億 / 10 億 / 100 億 / 1 兆 のプリセット、「1 日あたり」も可）× モデルの級（軽量 / 標準 / 最上位 / 上限。例は 2026-10 時点の現行モデル）× 地域 → 電力・水・換算・共有カード PNG。
- **前提**: 低 / 中 / 高 のプリセットと 4 本のスライダー（Wh/1,000 トークン、施設内 WUE、発電側の水、世界の倍率）。出典 ID 付き。
- **方法**: `src/data/model.ts` から自動で描く出典と計算式（`methodology.html`）。
- **ボトル**（上部の「地球 | ボトル」）: 3D の 500 mL ボトルに、あなたの応答ごとに水が注がれ、満ちたボトルが棚に並ぶ。縮尺の目盛り（いま / 7 日 / 1 年換算 / 世界の 1 日）で、浴槽・プール・東京ドームまでカメラが引く。
- **映像**（「▶ 45 秒」）: 同じ話を 45 秒で。`python scripts/render_film.py --mp4 scripts/out/film.mp4` で MP4 にできる（絵コンテと指示文は `docs/05`）。

## あなたの水（自分の実ログ）

Claude Code の利用記録からトークン数だけを読み、自分が蒸発させた水を数える。本文は読まない・送らない。

```bash
python scripts/water_meter.py --summary        # 直近 7 日の表（低 / 中 / 高、ボトル本数、キャッシュ無しなら何 L）
python scripts/install_statusline.py           # Claude Code のステータス行に「💧今日 12.4 L ▕███▍    ▏24本 · 会話 … · 節水 …」（数字は表示の例）
python scripts/install_statusline.py --uninstall
```

`scripts/serve.py` から開くと、地球儀の左下に「あなたの今日」が出て、自分の地域（既定 東京）から強調色の柱が立ち上る。
静的に配った版（GitHub Pages など）では出ない（案内が 1 行出る）。

## 開く

ブラウザの制約で `index.html` のダブルクリックでは動きません（module と fetch が `file://` で落ちる）。

```bash
npm install
npm run build          # dist/ を作る
python scripts/serve.py  # 空きポートでサーバーを立ててブラウザを開く（Windows は start_windows.bat）
```

GitHub Pages に置くなら `dist/` をそのまま配置する（`base: './'` で相対パス）。開発中は `npm run dev`。

## 検査

```bash
npm test                      # 計算式の代表値（100 億トークン → 低 450 L / 中 4.9 万 L / 高 16 万 L など）
python scripts/ui_smoke.py    # ビルド → 3 視口 + reduced-motion + 静的配信で画面検査、scripts/out/ にスクリーンショット
python -m unittest scripts/test_water_meter.py   # 実ログの集計とステータス行の導入
```

Playwright の Python パッケージが要る。ブラウザは `$PLAYWRIGHT_BROWSERS_PATH` から探す（`playwright install` はしない）。

## 構成

```
src/data/params.json  数値の唯一の置き場（画面と water_meter.py が共有）
src/data/model.ts     出典・計算式
src/data/hubs.ts      拠点 20 か所（位置と想定シェア）
src/data/land-points.json  陸地の点群（npm run data で world-atlas から生成）
src/globe/            Three.js: 陸・拠点・弧・粒・蒸発・ループ
src/ui/               ティッカー・あなたのトークン・前提・方法・共有カード・整形
docs/                 要件・モデルと出典・設計・受入・引き継ぎ・意思決定ログ
```

## 注意

- すべて推計。拠点とシェアは仮定。出典 ID のない数字は画面に出さない。
- 自分の実ログは手元でだけ読む（`~/.claude/projects` と `~/.cache/ai-water`）。リポジトリには入れない。映像と「手で注ぐ」は作例（仮の数字）を使う。
- CDN は使わない（依存はすべて npm で入れてバンドル）。社名・個人情報・認証情報を含めない。
