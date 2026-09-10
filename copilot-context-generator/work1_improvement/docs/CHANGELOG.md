# CHANGELOG

## v3.0.0 (2026-08-20)

「AIナレッジ生成ツール」から「文書を精製し、機械にも人にも届ける装置」への
大型アップデート。部署内での実運用レビューと、そこから判明した
運用事故に直結する不具合の修正を含む。

### 修正した不具合（すべて再現実験で確認）

| ID | 不具合 | 実測 |
|---|---|---|
| B1 | 中断すると既存ナレッジが部分内容で上書きされる | 9→2チャンクに破壊 |
| B2 | 参照元が空だと既存ナレッジが消える | 収録0件で上書き |
| B3 | 全抽出器で「一部の破損＝全体消失」 | Excel/PDF/Word/ZIP 全滅 |
| B4 | 重複検出プリパスによる二重抽出 | 9件→18回抽出 |
| B5 | 1ファイルのハングを止める仕組みが無い | タイムアウト機構なし |
| B6 | JSONL が本文を二重保存 | 容量が約2倍 |

B1/B2 は夜間バッチと組み合わさると、Box未同期・ネットワーク断・停止操作の
いずれでも気づかないうちに Copilot のナレッジが壊れる状態だった。

### 追加

- **柱0 原子的公開** (`publish.py`)
  生成物をステージングへ書き、完全成功時のみ差し替える。
  中断・対象0件・前回比50%未満のときは公開を保留して既存を温存し、
  `_AI_CONTEXT_HOLD.md` に理由を残す。`--force-publish` で明示的に上書き可。
  CLI終了コード **4 = 公開見送り**（スケジューラで区別可能）。
- **柱1 部分的失敗の局所化** (`extractors/UnitCollector`)
  ページ/シート/スライド/エントリ単位で保護し、無事な部分は必ず残す。
  新ステータス `partial` と抽出カバレッジを追加し、
  どの単位がなぜ失敗したかをレポートに明示。キャッシュにも保存。
- **柱2 人間向け読解キット** (`digest.py`, `outputs/human_digest.py`)
  LLM を使わずに、目次（手打ち章番号にも対応）・鮮度（和暦対応）・
  文書内の重複・参照切れ・想定質問を抽出し `_HUMAN_DIGEST/*.md` を出力。
  末尾の「Copilotに聞くときのコピペ用」で LLM 活用へ接続する。
  `--digest`（フォルダ） / `--digest-file`（1ファイルだけ分解）。
- **柱3 文書健康診断** (`outputs/health.py`)
  `_AI_CONTEXT_HEALTH.md` に総合スコア(100点)と改善アクションを1枚で出力。
- **柱4 GUI のコンパクト化** (`widgets.py`)
  折りたたみセクションを導入。必要高さ 920px → 648px（30%削減）。
  閉じたヘッダに要約を表示し、開閉状態とウィンドウサイズを保存。
  「1ファイルを読み解く」ボタンを追加。
- Word の見出しスタイルを構造マーカーとして保持（目次・分割精度が向上）

### 互換性

- `--legacy` は従来どおり原本 exe と同一出力（パリティテスト4件で担保）
- 既存のキャッシュDBは `ALTER TABLE` で移行され、作り直し不要

### テスト

- 145件（v2.2.0 の 92件から +53件）。パリティ4件は不変でグリーン。

## v2.2.0 (2026-07-16)

部署内で実際に使ってもらったレビュー（週報PPTXの抽出失敗報告）を
起点とした修正と機能追加。

### 修正（重大）

- **図形1つでファイル全体の抽出が失敗する不具合**
  `collect_ppt_shape_text()` の `hasattr(shape, 'table')` が原因。
  python-pptx の `GraphicFrame.table` は「表でない場合 ValueError」を
  投げるが、Python3 の `hasattr` が吸収するのは AttributeError のみ。
  そのため **グラフや埋め込みExcel（どちらも GraphicFrame）が1つでも
  あると例外が伝播し、タイトルも本文も含めて 0 文字**になっていた。
  `getattr(shape, 'has_table', False)` に修正。
  併せて図形単位で try/except を張り、1つの図形の失敗が
  ファイル全体を巻き添えにしない構造（部分的失敗の局所化）にした。

  **原本 exe から継承していた不具合**であり、v2 系で作り込んだ回帰では
  ない。`restored/` にも同じ行が存在する。なお `tests/test_parity.py`
  が通り続けているのは、パリティ用サンプルに GraphicFrame を含む
  PPTX が無いため。**原本のバグまで再現し続ける必要はない**という
  判断で、この点は意図的に原本と挙動が異なる。

### 追加

- **埋め込みOfficeファイル（OLEオブジェクト）の本文抽出**
  PowerPoint / Word に「オブジェクトの挿入」で貼られた Excel は、
  zip 内 `<prefix>/embeddings/` に元ファイルのまま格納されている。
  これを取り出して通常の抽出器へ流し、`# 埋め込みオブジェクト`
  セクションとして本文に収録する（`extractors/embedded.py`）。
  上限は 20 件 / 1件 20MB。
  旧形式（`oleObject*.bin` = OLE複合ドキュメント）は取り出せないため、
  「抽出できなかった埋め込みファイル」として名前を記録し、
  黙って落とさない。

### テスト

- 92件（v2.1.1 の 86件 + 6件）。追加分は `tests/test_embedded.py`。
  グラフ入りPPTXで回帰を防ぎ、埋め込みExcelのセル値が本文に
  出ることを PPTX / DOCX 双方で検証。

## v2.1.1 (2026-07-15)

会社Windows実機での初回セットアップ（Python 3.12 導入 → venv → pytest →
Windows固有機能確認 → 単一exeビルド → 実データ動作確認）で見つかった
不具合の修正。venv版とexe版で数値完全一致（25ファイル/53チャンク/
推定350,316トークン/あふれ7チャンク）を確認した実データ検証込み。

### 修正

- **F1 winsdk バージョン制約**: `pyproject.toml` の `winsdk>=1.0` を
  `winsdk>=1.0.0b10` に修正。PyPI に正式版 1.0.0 が存在せず
  `--pre` を付けても解決不可能なため、新規 Windows セットアップが
  必ず失敗していた。
- **F2 `console=False` での起動クラッシュ**: onefile（windowed）ビルドでは
  `sys.stdout`/`stderr`/`stdin` が `None` になり、`print()` 呼び出しで
  `OSError: [Errno 22] Invalid argument` が発生していた。
  `launcher_gui.py` の起動直後（他の import より前）に None を
  `os.devnull` へフォールバックする処理を追加し、根本原因を解消。
  ログファイル書き込み（`events.Emitter.log`）は `print()` と独立した
  経路のため、この問題の影響を受けていなかった。これにより
  `console=False` を維持でき、ダブルクリック起動時の黒いコンソール窓を
  回避できる。
- **F3 相対パスの OS依存区切り文字**: `pipeline.py` の `relative_of()` を
  `str()` 化する9箇所と `outputs/m365.py` の `SourcePath` が、Windows では
  `\` 区切りで出力されていた（他 OS は `/`）。JSONL・M365パッケージ・
  レポートが実行環境の OS によって内容が変わってしまう問題で、
  `.as_posix()` に統一して解消。原本互換パリティ・重複検出テストも
  この経路を通るため、副次的にプラットフォーム非依存性が上がった。
- **F4 夜間バッチのエンコーディング/改行罠**: PowerShell で `.bat` を
  生成・編集する際に UTF-8/BOM/LF 由来の文字化けと行頭文字欠落が
  発生した実例を `docs/OPERATIONS.md` に警告として追記
  （CRLF明示 + cp932指定の安全な書き方、全角パス回避の推奨）。
- **F5 セットアップ手順の pytest 欠落**: `pyproject.toml` の
  `dev = ["pytest>=8.0"]` extra 自体は存在していたが、
  `docs/BUILD_WINDOWS.md` と `COPILOT_HANDOFF.md` のインストール
  コマンドが `.[ocr-windows]` のみで `dev` を含んでいなかったため
  手順どおりに実行すると pytest が入らなかった。両ドキュメントを
  `.[dev,ocr-windows]` に修正。

### テスト

- 86件（変更なし）。F3 のパス正規化後も全件グリーン。

## v2.1.0 (2026-07-14)

会社環境（Box Drive / M365 Copilot / Windows）向け新機能アップデート。
オリジナル版の設計（固定名ファイル・出力フォーマット・GUI操作感）を
維持し、`--legacy` の原本互換パリティは不変。

### 追加（7機能）

- **F1 再アップロード指示書**: `_AI_CONTEXT_UPLOAD.md`。固定名ファイルの
  実質内容ハッシュ（生成時刻・LastDiff除外）を前回と比較し、Copilot に
  上げ直すべきファイルだけを列挙。
- **F2 ドライラン容量予測**: `--dry-run` / GUIボタン。抽出+チャンク+
  パッキング模擬で「19ファイルに収まるか」を事前予測。キャッシュは
  温めるが差分基準は進めない。
- **F3 Teams通知**: `--teams-webhook` / env / GUI欄。件数・差分・エラー・
  要再アップロードをチャネルへ投稿。失敗しても本処理は継続。
- **F4 Boxオンラインオンリー制御**: `--cloud-only download|skip|warn`。
  Windows のクラウドプレースホルダ属性で判定。
- **F5 機密情報スキャン**: `--sensitive off|warn|mask|block`（既定 warn）。
  組み込みパターン + `管理\sensitive_patterns.txt` 辞書。
- **F6 重複・類似文書検出**: `--dedupe off|warn|exclude`（既定 warn、
  閾値 0.90）。bottom-k シングルスケッチによる Jaccard 推定。exclude は
  更新日時が最新のものを残置し、INDEX の ExcludedFiles に理由を記載。
- **F7 OCR実行**: `--ocr auto` + extras（ocr-windows / ocr-macos）。
  needs_ocr の PDF を pypdfium2 でラスタライズし、Windows.Media.Ocr
  （Windows標準・日本語内蔵）または macOS Vision で本文化。
  エンジン不在時は従来どおり OCR 候補として報告。

### テスト

- 86件（v2.0比 +40）。パリティ4件は不変でグリーン。
- OCR の Windows 実機での実認識確認は要確認。

## v2.0.0 (2026-07-14)

元 exe（CopilotM365ContextGenerator_2026-05-28.exe）からの変更点。

### 経緯

元ソース (.pyw) が失われていたため、exe から抽出したバイトコードの
逆アセンブルからソースを忠実復元（51 code objects / 5,685 命令の
オペコード列一致を機械検証）。その復元版を土台にモジュール分割と
改善5項目を実装した。復元版は `restored/` に不変で保存。

### 追加

- **改善① インクリメンタル更新**: SQLite キャッシュ（管理\extract_cache.db）。
  サイズ+mtime 一致で再抽出スキップ。追加/変更/削除の差分レポート。
  `--full-rescan` / GUI チェックボックスで全再抽出。
- **改善② 抽出カバレッジと透明性**: 文字コード自動判定（UTF-8→CP932厳密
  →charset-normalizer）。抽出ステータス分類（本文なし/OCR候補/要変換/
  保護/エラー）。`_AI_CONTEXT_REPORT.md`。~$ロックファイル等のスキップ。
  .doc 自動変換（Windows: Word COM / macOS: textutil）。
- **改善③ セマンティックチャンク**: # Page / # Sheet / # Slide 境界優先の
  分割 + チャンク間オーバーラップ（12%）。見出し+先頭段落方式の要約。
  トークン数推定（JSONL に記録）。`--capacity tokens`。
- **改善④ CLI/ヘッドレス**: `python -m contextgen`。終了コード定義。
  タスクスケジューラ運用ガイドとサンプル .bat。
- **改善⑤ 20ファイル上限の運用**: `--sort mtime_desc` / `--priority-folder` /
  `--packing bestfit` / `--split-by-subfolder`。INDEX に FileSummaries /
  ExcludedChunks / LastDiff を追記。
- pytest 46件（うち原本互換パリティテスト4件）

### 互換性

- `--legacy` で従来版と同一の出力（固定名・整形・チャンク・INDEX）
- 既定でも M365 パッケージの固定ファイル名・基本フォーマットは同一
- 設定ファイル (box_copy_gui_settings.json) の既存キーは互換

### 既知の制限

- OCR 実行は未実装（候補レポートのみ。改善②の合意スコープ）
- exe ビルドは Windows 機で実施（docs/BUILD_WINDOWS.md）
