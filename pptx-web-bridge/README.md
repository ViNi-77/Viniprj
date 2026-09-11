# PPTX ⇄ Web図解 双方向変換アプリ（MVP）

PowerPoint（PPTX）と Web図解（HTML 一式）を共通の **Presentation JSON** で接続し、双方へ変換するローカル Web アプリです。
Windows で `start_windows.bat` を実行する（または exe 版をダブルクリックする）とブラウザ UI が開き、ファイル投入 → プレビュー → 編集 → 出力をブラウザだけで行えます。

```
PPTX ──parse──▶ Presentation JSON ──render──▶ Web図解（index.html + assets）
HTML ──parse──▶ Presentation JSON ──layout──▶ PPTX（編集性優先 / 見た目優先 / ハイブリッド）
```

## 0. いちばん簡単な起動（Windows、Python 不要）
GitHub Actions の **build-windows** が作る `pptx-web-bridge-windows.zip` を展開し、`pptx-web-bridge.exe` をダブルクリックするだけで起動します。黒い窓が開き、数秒後にブラウザで `http://127.0.0.1:8765/` が開きます。終了は窓を閉じるだけです。
- 入手: リポジトリの Actions → build-windows → 最新の実行 → Artifacts。タグ `v*` を push した場合は Releases にも添付されます。
- 同梱物: exe 本体（`_internal/` に依存一式）、`config/`（設定・テンプレート・ロゴ素材。編集可）、`samples/`（試用ファイル）、`README.md`、`はじめにお読みください.txt`。`projects/` `output/` `logs/` は exe の隣に作られます。
- 見た目優先モードは Windows 標準の Microsoft Edge を使って画像化します（Chromium の追加ダウンロード不要）。exe 版には Playwright のドライバ（Node.js 本体を含み約120MB）は同梱していません。見た目優先モードで Edge/Chrome が見つからない場合は自動的に編集性優先モードにフォールバックします（機能自体は使えます。必要なら 1. の手順でソースから起動してください）。
- **版の確認**: 画面右上のバッジに版とコミットが出ます（exe は同梱の `build_info.json` を読みます）。古い exe を起動していないかはここで分かります。
- 初回に SmartScreen の警告が出た場合は「詳細情報」→「実行」。社内配布で警告を消すにはコード署名が必要です。
- 自分でビルドする場合: `pip install pyinstaller && python packaging/build_exe.py`（Windows 上で実行すると Windows 用ができます）。
- **展開先は `C:\pptx-web-bridge` のようになるべく短いパスにしてください。** ダウンロードフォルダや OneDrive 同期フォルダの奥深くに展開すると、依存パッケージの中に含まれる長いファイルパスが Windows の上限（260文字）を超え、起動時にエラーになることがあります。
- 起動直後にエラー画面が出て閉じてしまう場合は、`logs/startup_error.log` の内容を確認してください（Enter を押すまで窓は閉じません）。よくある原因: 展開先パスが長すぎる／ウイルス対策ソフトや EDR が一部ファイルをブロックしている／ZIP の展開が途中で終わっている。展開し直しても改善しない場合は情シス・セキュリティ担当に exe の除外設定を相談してください。

## 1. 起動（Windows / Linux、Python あり）
```bat
git clone https://github.com/ViNi-77/Viniprj.git
cd Viniprj\pptx-web-bridge
start_windows.bat              # 初回: 仮想環境作成・依存導入・Chromium 導入（数分）→ サーバ起動 → ブラウザが開く
start_windows.bat --no-browser # ブラウザを開かない
start_windows.bat --setup-only # 依存導入のみ
```
- 必要: Python 3.10 以上。初回のみネットワーク（pip）。画面はノート PC（1366×768 の 125% 表示、1920×1080 の 150% 表示）で切れずに使えることを自動試験で確かめています。
- URL: `http://127.0.0.1:8765/`（`config/app_config.json` の `server.*` で変更）。
- 見た目優先モード用の Chromium 導入に失敗しても、編集性優先モードで動作します。

`start_windows.bat` はダブルクリックでも動きます。PowerShell の実行ポリシーに依存せず、`py` ランチャー／`python` を自動で探し、仮想環境の作成・依存導入・Chromium 導入・サンプル生成・起動まで行います。プロキシ環境では `pip` の設定（`HTTPS_PROXY` 環境変数）を先に行ってください。

**Linux / WSL**: `./start.sh`（`--no-browser` / `--setup-only` も同じ）。

手動セットアップ:
```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium   # 任意（見た目優先モード）
python samples/make_sample_pptx.py      # サンプル PPTX 生成
python backend/run_server.py
```

## 1.1 これまでの実装・対応内容のサマリー
| 版 | 内容 | 検証 |
|---|---|---|
| 第1版 | PPTX→JSON→Web、HTML→JSON→PPTX の往復。FastAPI + ブラウザ UI（D&D、編集、プレビュー、保存・復元、出力）。Presentation JSON v1.0 スキーマと自動修復。決定的レイアウト（分割・「（続き）」）。3 モード PPTX 出力。品質検査（文字切れ・重なり・画像比率・順序）。匿名化サンプル。文書一式 | pytest 35、E2E 23 |
| 第2版 | コーポレート標準テンプレート（表紙・中身・最終ページを Web/PPTX 同座標で描画）。文字は全モードでテキストシェイプ（座標・pt 付き）、要素判別レポート。模擬 12 枚 PPTX（生成器・検査・検査記録・PDF）。図形種別と表セル書式の拡張。設計基準書対応（qcDebug、ログレベル、進捗バー、イベント委譲） | pytest 56、模擬 15、E2E 28 |
| ループ運用 | Issue 駆動の反復（`scripts/loop.py`、CI `loop-check`、Issue/PR テンプレート、運用文書、実行記録） | 全周で合格を確認 |
| Issue #4 #5 #14 | テーマ色・clrMapOvr の解決、マスター継承のフォントサイズ・箇条書き・フォント、継承値と明示値の区別（`inherited`） | 別エージェントによる 2 周のレビューを反映 |
| Issue #6 #8 #11 | 同梱 CSS の Computed Style 反映（JS 無効・通信遮断）、表紙/最終ページの往復復元、例外系試験の自動化 | pytest 62〜71 |
| デバッグ | 境界入力 50 種の探索で 10 件修正（グリッド折返し、巨大座標の丸め、型強制、表・長文の分割、空要素除外、案内メッセージ）。`docs/10_デバッグ所見.md` | クラッシュ 0 件、決定性・往復・安全性を確認 |
| exe 配布 | PyInstaller での exe 化（onedir）。Windows 用起動バッチ、CI（build-windows）でのビルド・起動試験・配布ブランチへの反映 | Windows CI での起動・取込試験に合格 |
| exe 配布・不具合対応 | 別 PC で起動直後にクラッシュ（`jsonschema`/`referencing` の仕様データ関連）した件を調査。原因の切り分けとして Playwright ドライバ（Node.js 本体、約120MB）の同梱をやめ配布物を約 1/3 に縮小（展開先パス長・ウイルス対策ソフトの誤検知リスクを低減）、`jsonschema` 系パッケージのメタデータ同梱を追加、起動失敗時にエラー内容を画面とログに残す仕組みを追加 | Linux 上のビルドで取込 API 経由の検証まで確認。次回 Windows ビルドでの実機確認待ち |
| レイアウト改善（Phase A） | 文字サイズの一本化（`typography.py`）、画像の実寸配置と本文との横並び、分割前の自動縮小と分割抑制、HTML の背景色・帯・区切り線・代替画像、PPTX のトリミング焼き込み・回転・固定要素との衝突回避。スキーマ 1.1 | pytest 88、E2E 33 |
| 編集 UI（Phase B） | iframe プレビューをやめ、サーバ描画の断片を同一オリジンのキャンバスに差し込んで直接編集（選択・ドラッグ・リサイズ・スナップ・キーボード・undo/redo・数値入力・画像差し替え・要素追加）。サムネイル付きスライド一覧と D&D 並べ替え、ペイン幅の調整。API: `/api/render/slides` `/api/layout/slide` `/api/layout/fit` | pytest 96、E2E 33、UI スモーク 13 |
| PPTX からテンプレート作成（Phase C） | 自分の PowerPoint（表紙・中身・最終ページ）を読み込み、背景・ロゴ・帯・題名/副題/本文領域・フッター・ページ番号・一言を推定して「この解釈で入ります」を番号付きの枠で表示。枠をドラッグして直し、ユーザーテンプレートとして保存（`config/user_templates.json`）。中身の本文はテンプレートの本文領域に流し込む。任意で元の PowerPoint を土台にした PPTX 出力。API: `/api/templates/from-pptx` `/api/templates/preview` `PUT/DELETE /api/templates/{id}` | pytest 106、E2E 37、UI スモーク 20 |
| Copilot 連携（Phase D） | API を使わず M365 Copilot と受け渡す。「Copilot に頼む」で用途（ブランドスライド化 / 図解風 / 要約 / 発表者ノート / 翻訳 / JSON）を選び、指示と資料の内容（Markdown）をコピーして Copilot に貼る。Word 文書（Copilot in PowerPoint の「ファイルから作成」用）と一式 ZIP も保存できる。回答（Markdown / 簡易 JSON）を貼り付けると新しい資料になり、`型: カード / 比較` は図解風の列配置、`ノート:` は発表者ノートになる。プロンプトは `config/copilot_prompts.json` | pytest 157、E2E 46、UI スモーク 26 |
| Copilot エージェント一式（Phase E） | 上の書式を Copilot 側にも覚えさせる。「Copilot に頼む」→「3. エージェント」で、宣言型エージェントの定義（`declarativeAgent.json`）・指示文（`instructions.md`）・ナレッジ用テキスト（1 ファイル 30,000 字・20 ファイル以内）・登録手順を ZIP で書き出す。Copilot Studio に手で登録すると、前置き無しでこのアプリの Markdown 形式のまま返ってくる。ここでも API は使わない | pytest 157、E2E 46、UI スモーク 26 |
| 図解部品（Phase F） | フロー・カード・比較・数値・年表の 5 型を「型 + 項目」で持つ図解要素。ツールバーの「図解」から追加し、インスペクタで項目を編集する。PowerPoint へは編集できる図形として出力し、取り込み直すと図解に戻る。Copilot とは `型: フロー` のような 1 語でやり取りし、回答の箇条書きがそのまま図解になる | pytest 157、E2E 46、UI スモーク 26 |
| 差分マージ再取込（Phase G） | 同じ資料を直したファイルを投入すると「差分を取り込む / まるごと置き換える」を選べる。差分では手で動かした枠・直した文字・発表者ノートを残したまま、変わったところだけを反映する。両方で変わった箇所は競合として一覧に出し、1 件ずつ元の文言に戻せる。Copilot の回答も「差分として反映」できる | pytest 157、E2E 46、UI スモーク 26 |
| 画面基盤（Phase H） | ノート PC（125〜150% 表示）で切れずに押せる画面。フォーム・ボタン・ダイアログは Pico.css、3 ペインの分割は Split.js、モーダルは HTML 標準の `<dialog>`（保存・キャンセルは常に見えるフッター）。キャンバスは ResizeObserver で自動で収め直す | UI スモーク 45（うちノート PC 2 構成 18） |
| テンプレート推定の精度（Phase I） | 帯は「細長く・端に寄る」形で判定し、色見本（同じ大きさの色チップ）や飾りの四角は部品にしない（色はテーマ候補へ）。帯は 3 個まで。中身スライドは題名・本文プレースホルダを持つものを自動で選ぶ。部品ごとに信頼度（確か / 要確認）と「この解釈で入ります」の要約を出し、画面の表で役割（帯 ⇄ 装飾、文字候補 → 題名/フッター …）を変えられる | pytest 173、E2E 48 |
| テンプレートの着せ替え（Phase J） | テンプレートを選んで「テンプレートで着せ替える」を押すと、資料全体の色・フォント・題名の位置・背景がテンプレートにそろう（文章は変えない）。全面を覆う塗り図形は背景に畳み込み、2 回以上使われた色だけをテンプレートの色に置き換える（1 回だけの色＝写真の差し色などは触らない）。結果は色の対応表つきで表示し、「元の見た目に戻す」（Ctrl+Z でも可）で完全に戻せる。PowerPoint 出力は元の PowerPoint を土台にし、題名はマスターの題名プレースホルダに入るので「デザイン」タブのテーマがそのまま効く | pytest 186、E2E 52、UI スモーク 47 |
| 配布 | `start_windows.bat`（Windows）、`start.sh`（Linux）、exe 版（PyInstaller、Actions の Windows ランナーでビルド、Edge で画像化） | Linux 版バイナリで凍結ロジックを検証、Windows は CI のスモークテスト |

## 1.2 第2版で追加したもの
- **コーポレート標準スタイル**（`config/templates.json` の `corporate_standard`）: 表紙（紺背景 + 白ロゴ + 32pt 白題名 + 21pt 副題 + 右下日付/著作権）、中身（左下ロゴ + 紺帯 + ページ番号）、最終ページ（中央ロゴ）を Web と PPTX の両方へ同じ座標で描く。ロゴ・背景は参考画像から作った暫定素材のため `config/template_assets/` を正式素材に差し替える。
- **文字はテキストシェイプ**: すべての文字を座標 (x, y, w, h: pt) とフォント pt 付きの編集可能なテキストとして出力する。「要素一覧」タブと Web 一式の `conversion_report.md` で 文字/画像/図形/表 の判別と数値を確認できる。
- **模擬 12 枚 PPTX**（`mock-pptx/`）: 匿名化スライド仕様書どおりの受入試験用資料。生成器・マニフェスト・自動検査・検査記録・プレビュー PDF を同梱。
- **設計基準書の反映**: `window.qcDebug` デバッグコマンド、ログレベル切替、大ステップ + 累積％の進捗バー、ドキュメントレベルのイベント委譲。

## 1.3 版の確認（「更新できているか」を確かめる）

画面右上に **「版 0.5.0 (コミット)」** のバッジが出ます。押すと、その版に入っている機能が段階ごとに一覧で出ます。

- 端末から確認: `curl http://127.0.0.1:8765/api/version`（ポートは起動時に画面へ出ます）
- **画面が古いままに見えるとき**:
  1. **前に起動したサーバーが残っていないか**。残っているとブラウザはそちらの古い画面を開きます。起動時に「⚠ ポート 8765 では既にこのアプリ（版 …）が動いています」と出たら、前のウィンドウで Ctrl+C を押して終了してから開き直してください（新しい方は自動で別ポートへ移り、その URL を表示します）
  2. **Ctrl+F5**（強制再読み込み）。JS・CSS の URL には版の印が付くので通常は不要ですが、開いたままのタブは古い画面のことがあります
- 取り込んだ版が正しいか: `git log --oneline -1` の値がバッジのコミットと一致していれば最新です

| 版 | 入っているもの |
|---|---|
| 0.5.0 | Phase J（テンプレートの着せ替え: 色・フォント・題名・背景をそろえ、PowerPoint はマスターの枠へ。元に戻せる） |
| 0.4.1 | Phase I（テンプレート推定の精度: 帯の形状判定・色見本と装飾の除外・役割の変更） |
| 0.4.0 | Phase H（画面基盤: Pico.css / `<dialog>` / Split.js、ノート PC 対応） |
| 0.3.0 | Phase A〜G（レイアウト品質・編集 UI・PPTX テンプレート・Copilot 連携・エージェント一式・図解部品・差分マージ） |

## 2. 使い方
1. **ファイル投入**: PPTX / HTML / ZIP（HTML + CSS + 画像）/ JSON をドロップ。テンプレートを選ぶ。自分の様式を使うなら「PPTX からテンプレート作成」で表紙・中身・最終ページの PowerPoint（1〜3 枚）を読み込む。左でスライドの役割を確認し、右の番号付きの枠（背景・ロゴ・帯・題名・本文領域・フッター・ページ番号・一言）をドラッグして直し、不要な部品は ✕ で外して保存すると一覧に ★ 付きで載る。保存したテンプレートは「削除」で消せる。
2. **テンプレートで着せ替える**: テンプレートを選んだら「テンプレートで着せ替える」を押す。資料全体の色・フォント・題名の位置・背景がテンプレートにそろう（文章はそのまま）。どの色がどの色になったかは結果の画面に表が出る。思っていた見た目と違えば「元の見た目に戻す」（Ctrl+Z でも可）で完全に戻る。
3. **編集**: 右のキャンバスで要素をクリックして選択、ドラッグで移動、角のハンドルで大きさ変更（Shift: 縦横比固定、Alt: スナップ無効）。矢印キーで微調整、Delete で削除、Ctrl+D で複製、Ctrl+Z / Ctrl+Y で取り消し・やり直し。下の「編集」タブで x/y/幅/高さ・フォント pt・色・揃え・画像の差し替えを数値入力。ツールバーから文字/図形/画像/線を追加、「このスライドを自動配置」で座標未確定の要素だけ配置、「全要素を配置し直す」でそのスライドを作り直す。スライド一覧はサムネイル付きで、ドラッグまたは ↑↓ で並べ替え、⧉ で複製、✕ で削除。ペインの境界はドラッグで幅を変えられる。
4. **プレビュー**: 「全体プレビュー」で Web図解ビューア（目次、ページ送り、全画面、縦読み、ノート、印刷）を別タブに開く。
5. **出力**: Web 一式（ZIP）、PPTX（モード選択）、JSON。「output フォルダにも書き出す」で `output/` へ保存。「最終ページを追加」でテンプレートの最終ページを末尾に付ける。PPTX から作ったテンプレートでは「元の PowerPoint を土台にする」が既定で入り、マスター・テーマ・フォントを元ファイルのまま使い、題名はマスターの題名プレースホルダに入る（PowerPoint の「デザイン」タブがそのまま効く）。外すと従来どおり自由図形だけで出力する。
6. **保存・復元**: プロジェクト名で `projects/<名前>.json` に保存し、「開く」で復元。
7. **Copilot 連携（API 不使用）**: 「Copilot に頼む」で用途を選び「全部コピー」→ M365 Copilot チャットに貼る → 回答をコピー → 「回答を貼り付けて反映」。PowerPoint で作らせるときは「Word 文書を保存」して Copilot in PowerPoint の「ファイルから作成」に使い、ブランドキットを適用する。できた PowerPoint はそのまま「ファイル投入」で取り込んで Web 化できる。資料の文章をそのまま Copilot に貼るため、社外秘の資料は社内テナントの M365 Copilot でのみ使うこと（外部の AI サービスには貼らない）。
8. **Copilot エージェント一式（任意）**: 「Copilot に頼む」→「3. エージェント」→「一式を ZIP で保存」。Copilot Studio で新しいエージェントを作り、`instructions.md` の本文を指示に貼り、`knowledge/` のテキストをナレッジとして添付する（M365 Copilot は 20 ファイルまで）。以後はそのエージェントに貼るだけで、前置き無しの Markdown が返る。ここでも社外秘の資料は社内テナントの Copilot でのみ扱うこと。
9. **資料を直して取り込み直す**: 元の PowerPoint / HTML を直してもう一度投入すると、取り込み方を聞かれます。「差分を取り込む」を選ぶと、手で整えた位置・直した文字・ノートが残ったまま、変わったところだけが入ります。両方で変わった箇所は一覧に出るので、必要なら「今の資料の文言に戻す」を押します（Ctrl+Z でまとめて取り消すこともできます）。

コマンドラインでも変換できます:
```bash
python scripts/convert.py pptx2web  samples/sample_deck.pptx        output/deck_web
python scripts/convert.py html2pptx samples/sample_html/long.html   output/long.pptx --mode editable
python scripts/convert.py pptx2json samples/sample_deck.pptx        output/deck.json
python scripts/convert.py json2pptx output/deck.json                output/deck2.pptx --mode hybrid
python scripts/convert.py check     samples/sample_html/cards.html
```

## 3. 構成
```
backend/app/
  main.py            ローカル API（FastAPI）
  pipeline.py        取込・出力の共通入口（API と CLI が共用）
  pptx_parser.py     PPTX → JSON（python-pptx + OOXML 補完）
  html_parser.py     HTML → JSON（BeautifulSoup）
  layout.py          座標未確定要素の決定的レイアウト・分割
  web_renderer.py    JSON → Web図解（viewer/ の CSS・JS を同梱）
  pptx_generator.py  JSON → PPTX（3 モード）
  rasterize.py       スライド画像化（Playwright、任意）
  validate.py        JSON Schema 検証と自動修復
  quality_check.py   文字切れ・重なり・画像比率・順序の検査
  storage.py         プロジェクト保存、出力書き出し
  template_kit.py    テンプレート部品（表紙・中身・最終ページ）の共通処理
  template_from_pptx.py  PowerPoint からテンプレート部品を推定（Phase C）
  template_store.py  ユーザーテンプレートの保存・削除
  copilot_handoff.py Copilot 連携（Markdown / JSON / Word への変換、回答の取込。API 不使用）
  copilot_agent_kit.py Copilot エージェント一式（定義・指示文・ナレッジの書き出し。API 不使用）
  diagrams.py       図解部品（フロー・カード・比較・数値・年表の展開と Markdown 記法）
  merge.py          差分マージ再取込（前回の取込記録と照合し、編集を残して差分だけ反映）
  report.py          要素判別レポート（文字/画像、座標、フォント pt）
  config.py          設定読込（値はすべて config/*.json）
frontend/            ブラウザ UI（素の HTML / JS。index.html、layout.css、ui.js、canvas.js ほか）
frontend/vendor/     同梱ライブラリ（Pico.css 2.0.6、Split.js 1.6.5。ビルド不要・オフライン。vendor/README.md）
schema/presentation.schema.json  Presentation JSON v1.0
config/              app_config.json / templates.json / font_fallback.json
samples/             匿名化サンプル（PPTX 生成スクリプト、HTML 3 種）
mock-pptx/           匿名化 12 枚模擬 PPTX（生成器・検査・検査記録・プレビュー PDF）
tests/               pytest（単体・API）
scripts/             convert.py（CLI）、run_e2e.py（往復 E2E）
docs/                企画書に対するレビュー、要件、仕様、試験、意思決定ログ
```

## 4. 設定（ハードコード禁止）
| ファイル | 内容 |
|---|---|
| `config/app_config.json` | ポート、保存先、上限、レイアウト余白・フォントサイズ、品質しきい値、ログ、HTML 取込時の Computed Style 利用（`html_import.use_computed_style`） |
| `config/templates.json` | テンプレート（色、フォント、表紙/中身/最終ページの部品座標、フッター、機密表示）。正式ブランド規則はここへ追加 |
| `config/template_assets/` | テンプレートのロゴ・背景画像（暫定。正式素材へ同名で差し替え） |
| `config/user_templates.json`, `config/template_assets/user/<id>/` | 「PPTX からテンプレート作成」で保存したテンプレートと画像・元ファイル（実行時生成。exe 版は exe の隣） |
| `config/font_fallback.json` | フォント代替表（環境間のフォント差を吸収） |
| `config/copilot_prompts.json` | 「Copilot に頼む」の用途プリセット（プロンプト文面、既定の枚数・言語、Copilot チャットの URL）と、書き出すエージェントの名前・説明（`agent`） |

環境変数 `PPTX_WEB_BRIDGE_CONFIG` で設定ファイルを差し替え、`PLAYWRIGHT_CHROMIUM_PATH` で Chromium の場所を指定できます。

## 5. 試験とループ運用
開発は Issue 駆動のループ（`docs/09_ループエンジニアリング運用.md`）で回す。1 周 = 1 Issue。

```bash
python scripts/loop.py --quick           # 実装中: 単体・API のみ（数秒）
python scripts/loop.py --issue 12        # コミット前: 単体・API → 模擬12枚 → E2E を一括、記録を追記
```
合格すると `docs/ループ実行記録.md` に 1 行追記され、push 後は GitHub Actions（`.github/workflows/loop.yml`）が同じ検査を再実行する。

```bash
python -m pytest             # 単体・API・模擬資料 56 件
python mock-pptx/src/validate_mock_pptx.py   # 模擬 12 枚の検査・検査記録・プレビュー PDF
python scripts/run_e2e.py    # サンプルでの往復 E2E → docs/試験結果.md を更新、output/e2e/ に成果物
```
最新の結果は [docs/試験結果.md](docs/試験結果.md)。

## 6. 文書
| 文書 | 内容 |
|---|---|
| [docs/00_初回レビュー_不足矛盾リスク一覧.md](docs/00_初回レビュー_不足矛盾リスク一覧.md) | 企画書に対する不足・矛盾・高リスクと対処 |
| [docs/01_要件定義書.md](docs/01_要件定義書.md) | 画面、ワークフロー、入出力、エラー、受入条件 |
| [docs/02_Presentation_JSON仕様書.md](docs/02_Presentation_JSON仕様書.md) | フィールド、単位、座標系、互換性 |
| [docs/03_変換マッピング仕様書.md](docs/03_変換マッピング仕様書.md) | PPTX/HTML/JSON の対応、フォールバック条件 |
| [docs/04_受入試験仕様書.md](docs/04_受入試験仕様書.md) | 受入条件ごとの手順・合格基準・自動化状況 |
| [docs/05_AI開発指示書.md](docs/05_AI開発指示書.md) | AI の役割、禁止事項、変更手順、レビュー観点 |
| [docs/06_起動方式比較.md](docs/06_起動方式比較.md) | 起動・配布方式の比較と採用案 |
| [docs/07_既知課題と確認事項.md](docs/07_既知課題と確認事項.md) | 制約、確認待ち事項、依存ライセンス |
| [docs/08_特許出願アイディア提案書.md](docs/08_特許出願アイディア提案書.md) | 新規性・進歩性の論点になり得る構造の列挙（出願可否の判断は知財部門） |
| [docs/09_ループエンジニアリング運用.md](docs/09_ループエンジニアリング運用.md) | Issue 駆動の反復開発の回し方 |
| [docs/10_デバッグ所見.md](docs/10_デバッグ所見.md) | 境界入力の探索結果と「この状態で良いか」の判断 |
| [docs/11_引き継ぎ.md](docs/11_引き継ぎ.md) | 現在地（版・完了範囲・未実施の手動確認）と開発の引き継ぎ |
| [docs/ループ実行記録.md](docs/ループ実行記録.md) | `scripts/loop.py` の実行記録（自動追記） |
| [docs/99_意思決定ログ.md](docs/99_意思決定ログ.md) | 判断の記録 |
| [mock-pptx/README.md](mock-pptx/README.md) | 模擬 PPTX の採用技術、構成、マニフェスト、検査方法 |

## 6.1 配布方法の比較
| 方法 | 手順 | 向いている場面 | 注意 |
|---|---|---|---|
| **exe 版 ZIP**（推奨） | Actions の成果物を展開して exe を実行 | Python が無い PC、非エンジニアの試用 | 約 60〜70MB（Playwright 非同梱）。更新は ZIP の差し替え |
| ソース ZIP | `git archive` の ZIP を展開し `start_windows.bat` / `start.sh` | Python がある PC、設定やコードを触る人 | 初回に pip でネットワークが要る |
| git clone | `git clone` → `start_windows.bat` / `start.sh`。更新は `git pull` | 開発者、ループ運用に参加する人 | 社内プロキシで `git` の設定が必要な場合あり |

公開リポジトリのため、試用者には exe 版 ZIP、開発者には git clone を推奨します。ソース ZIP は保険として残します。

## 7. MVP の範囲と対象外
- 対応: タイトル、本文（箇条書き・階層）、画像、矩形/角丸/楕円/三角/ひし形/右矢印/平行四辺形、線、表、グループ、ノート、16:9（4:3 は警告付き）。HTML は section / h1-h3 / p / リスト / 画像 / 表 / カード（2〜3 列）/ 引用。
- 対象外（企画書どおり）: SmartArt の図形再現（文字列は退避）、グラフ、動画、音声、マクロ、アニメーション、任意 SPA、認証、DB、共同編集。
- すべてローカル処理。外部へファイルを送信せず、外部 URL の画像も取得しません。

## 8. 既知の制約
`docs/07_既知課題と確認事項.md` を参照。特に「生成 PPTX を PowerPoint で開いて編集できること」は PowerPoint 実機での確認が必要です（CI 環境には PowerPoint / LibreOffice Impress が無いため、python-pptx による再読込と XML 妥当性で代替しています）。
