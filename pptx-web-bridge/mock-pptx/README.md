# mock-pptx: 匿名化 12 枚模擬 PPTX

「匿名化スライド仕様書」「模擬PPTX生成指示書」に従い、双方向変換アプリの受入試験に使う模擬 PowerPoint を生成する。
実在の会社名・部署名・氏名・ロゴ・テンプレートは含まない。数値はすべて架空（「仮」「例示」「サンプル」を明記）。

## 採用技術と理由
| 候補 | 判断 | 理由 |
|---|---|---|
| Node.js + TypeScript + PptxGenJS（第一候補） | 見送り | 変換アプリ本体が Python（FastAPI + python-pptx）であり、Node ランタイムを追加すると再現手順が二重になる。生成物の再読込検査も python-pptx で行うため、同じライブラリで生成・検査する方が差分を追いやすい |
| **Python 3 + python-pptx + Pillow（代替候補）** | **採用** | 編集可能なテキスト・表・図形・画像・コネクターを生成でき、`python -m pytest` で構造検査まで一気通貫にできる。依存はアプリ本体の `requirements.txt` と共通 |

## 構成
```
mock-pptx/
├── src/
│   ├── theme.py                 テーマ定数（色・フォント・余白・フッター）
│   ├── generate_mock_pptx.py    12 枚を生成し、マニフェストを書く
│   └── validate_mock_pptx.py    自動検査 + プレビュー PDF + 検査記録
├── assets/generated_shapes/     コード内で生成した抽象画像（外部素材なし）
├── output/
│   ├── mock_bidirectional_conversion_12slides.pptx
│   ├── mock_bidirectional_conversion_manifest.json
│   ├── mock_bidirectional_conversion_preview.pdf
│   └── mock_bidirectional_conversion_validation.md
├── tests/
│   ├── structure_test.py        枚数・題名・ページ番号・範囲内・縦横比・長文・リンク/マクロ無し
│   └── privacy_test.py          禁止パターン・プロパティ・絶対パス・数値注記
├── README.md
└── THIRD_PARTY_NOTICES.md
```

## 再生成手順
```bash
cd <リポジトリ直下>
start_windows.bat --setup-only       # 依存導入（初回のみ。Linux は ./start.sh --setup-only）
source .venv/bin/activate
python mock-pptx/src/generate_mock_pptx.py     # PPTX + manifest
python mock-pptx/src/validate_mock_pptx.py     # 検査 + preview.pdf + validation.md
python -m pytest mock-pptx/tests               # 自動検査のみ
```
依存バージョンは `requirements.txt`（python-pptx 1.0 系、Pillow 10 系、Playwright 1.4x 系）。

## 12 枚のマニフェスト要約
| # | id | type | 題名 | 試験目的 |
|---|---|---|---|---|
| 01 | slide-01 | cover | PowerPoint・Web図解 双方向変換デモ | 表紙、図形、文字色、背景色 |
| 02 | slide-02 | two_column_cards | 目的と対象 | 2 列、カード、折返し |
| 03 | slide-03 | three_column_cards | 現状課題 | 3 列グリッド、図形 + テキスト |
| 04 | slide-04 | process_flow | 変換フロー | 6 工程、コネクター、順序 |
| 05 | slide-05 | before_after | Before / After | 左右比較、背景色、箇条書き、矢印図形 |
| 06 | slide-06 | kpi_cards | 数値カード | 大数字、注記、サイズ階層 |
| 07 | slide-07 | table | 要素別の変換方式 | 5 行 4 列（+ヘッダー）、セル背景 |
| 08 | slide-08 | images | 画像配置 | 横長・縦長画像、縦横比 |
| 09 | slide-09 | composite | 複合レイアウト | 上段 2 カード + タイムライン |
| 10 | slide-10 | long_text | 長文・オーバーフロー試験 | 2 段組 250–350 字、警告ボックス |
| 11 | slide-11 | scope | 対象外要素の説明 | 対応 / 条件付き / 対象外 |
| 12 | slide-12 | summary | まとめ | 3 メッセージ + ボタン風図形 |

## 検査方法
- 自動: `python -m pytest mock-pptx/tests`（指示書 8 章の項目を網羅）と、変換アプリの品質検査（`python scripts/convert.py check mock-pptx/output/mock_bidirectional_conversion_12slides.pptx`）。
- 目視: `output/mock_bidirectional_conversion_preview.pdf`（変換アプリのレンダラー出力）を全ページ確認し、結果を `validation.md` に記録。
- 実機: PowerPoint / Keynote で `output/*.pptx` を開き、仕様 8 章「2 環境以上で表示確認」を実機で実施する（CI 環境には無い）。

## 想定リスク と 既知制約
- プレビュー PDF は PowerPoint の描画ではない。フォント（Arial の日本語代替）で行送りが変わる可能性がある。
- 画像は SVG ではなく PNG（python-pptx は SVG 埋め込みを標準で扱わない）。生成コードは `generate_mock_pptx.py` に同梱し、外部素材は使わない。
- 矢印付きコネクターは OOXML（`a:tailEnd`）を直接書いている。
- 禁止語は一般パターン（メールアドレス、絶対パス、URL、社名表記）のみ。実在名の追加は `tests/forbidden_words.txt` に 1 行 1 語で置く（リポジトリには含めない）。
