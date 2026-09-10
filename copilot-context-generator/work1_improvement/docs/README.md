# contextgen — Copilot M365用コンテキスト生成ツール（v3.0）

フォルダを走査し、Office文書・PDF・ZIPからテキストを抽出して、
M365 Copilot エージェントのナレッジに投入できる固定名TXTパッケージ
（INDEX 1 + 本文最大19 = 20ファイル）と、Markdown / JSONL のコンテキスト
一式を生成するツールです。

従来の exe 版（`box_copy_gui_direct_context_mode_fixed.pyw`）の完全互換
後継です。`--legacy` を付けると従来版と同一の出力を生成します
（tests/test_parity.py で恒常的に担保）。

## セットアップ

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e .          # Windows: .venv\Scripts\pip install -e .
```

## 使い方

### GUI（従来と同じ操作感 + オプション欄）

```bash
python -m contextgen.gui
```

### CLI / ヘッドレス（改善④）

```bash
python -m contextgen --source <参照元フォルダ> --output <出力先フォルダ>
```

主なオプション:

| オプション | 説明 |
|---|---|
| `--full-rescan` | キャッシュを無視して全ファイル再抽出 |
| `--no-cache` | 差分キャッシュを使わない |
| `--capacity tokens` | M365ファイル容量を推定トークン基準で管理（改善③） |
| `--packing bestfit` | 空きの大きいパートへ詰めて余白を削減（改善⑤） |
| `--sort mtime_desc` | 更新日の新しい順に収録（上限あふれ対策、改善⑤） |
| `--priority-folder <相対パス>` | 優先収録するサブフォルダ（複数指定可） |
| `--split-by-subfolder` | サブフォルダごとに別の20ファイルパッケージを生成 |
| `--legacy` | 従来版exeと同一出力（全改善オフ） |
| `--chunk-mode legacy` / `--summary-mode legacy` | 分割・要約のみ従来方式に |

v2.1 の新機能オプション:

| オプション | 説明 |
|---|---|
| `--dry-run` | 見積のみ（対象数・推定トークン・20ファイルに収まるか予測）。何も書き込まない |
| `--teams-webhook <URL>` | 実行結果を Teams チャネルに投稿（env: CONTEXTGEN_TEAMS_WEBHOOK） |
| `--cloud-only skip\|warn` | Box Drive のオンラインオンリーファイルを抽出しない/検知して報告 |
| `--sensitive warn\|mask\|block` | 機密情報スキャン（既定 warn=検知のみ。辞書: 管理\sensitive_patterns.txt） |
| `--dedupe warn\|exclude` | 重複・類似文書の検出（既定 warn。exclude で最新版のみ収録） |
| `--ocr auto` | テキスト層のないPDFをOCRで本文化（要 extras、Windows標準OCR/macOS Vision） |

v3 の新機能オプション:

| オプション | 説明 |
|---|---|
| `--digest` | **人間向け読解キット**（目次・鮮度・重複・参照切れ）を `_HUMAN_DIGEST/` に出力 |
| `--digest-file <ファイル>` | **1ファイルだけ分解する**。長いマニュアルを読み解く入口（`--source` 不要） |
| `--force-publish` | 収録量が大幅に減っていても公開する（既定は既存ナレッジを温存） |

終了コード: `0`=正常 / `2`=指定誤り / `3`=停止・実行時エラー / `4`=公開見送り（既存ナレッジを温存）

## 生成物

| ファイル | 内容 |
|---|---|
| `M365AgentContext_INDEX.txt` + `M365AgentContext_001..0NN.txt` | M365 Copilot エージェント投入用（固定名） |
| `Archive/M365AgentContext_<stamp>_*.txt` | タイムスタンプ付き世代保存 |
| `_AI_CONTEXT_SUMMARY_<stamp>_NNN.md` / `_AI_CONTEXT_SUMMARY.md` | 人間閲覧・ChatGPT等向け Markdown 分割と一覧 |
| `_AI_CONTEXT_DATA.jsonl` | 全チャンクの構造化データ（RAG・他AI連携の入力） |
| `_AI_CONTEXT_REPORT.md` | 抽出カバレッジレポート（改善②）: 全文/本文なし/OCR候補/要変換/保護/エラーの内訳と明細、前回差分、類似文書グループ、機密検知 |
| `_AI_CONTEXT_UPLOAD.md` | **再アップロード指示書**: 20ファイルのうち今回内容が変わったものだけを列挙 |
| `_AI_CONTEXT_HEALTH.md` | **文書健康診断（v3）**: 総合スコアと「まず手を付けるとよいこと」を1枚に |
| `_HUMAN_DIGEST/*.md` + `_HUMAN_DIGEST_INDEX.md` | **人間向け読解キット（v3、`--digest` 時）**: 目次・鮮度警告・重複・参照切れ・Copilotへのコピペ用 |
| `_AI_CONTEXT_HOLD.md` | **公開見送りの通知（v3）**: 既存ナレッジを守るため差し替えを保留したときだけ作られる |

管理フォルダ（既定: 出力先の隣の `管理`）には、ログ・設定・
差分キャッシュ `extract_cache.db`（改善①）が保存されます。

## 従来版からの改善点

1. **インクリメンタル更新（改善①）** — サイズ+更新日時が同じファイルは
   キャッシュから即時取得。2回目以降の実行が大幅に高速化し、
   追加/変更/削除の差分が INDEX（`## LastDiff`）とレポートに記録される。
2. **抽出カバレッジと透明性（改善②）** — CP932等の文字コード自動判定、
   「本文なし」と「抽出失敗」の区別、OCR候補PDF・要変換.doc・保護ファイル
   の一覧化。macOS(textutil)/Windows(Word) では .doc の自動変換も試みる。
3. **セマンティックチャンク（改善③）** — ページ/シート/スライド境界を
   優先した分割とチャンク間オーバーラップ。トークン数推定を JSONL に記録し、
   容量管理をトークン基準に切替可能。
4. **CLI/ヘッドレス（改善④)** — 無人実行・タスクスケジューラ対応
   （docs/OPERATIONS.md 参照）。
5. **20ファイル上限の賢い運用（改善⑤）** — 収録優先度・詰め込み最適化・
   サブフォルダ別マルチエージェントパッケージ・INDEX へのファイル別要約。

## v2.1 の新機能

1. **再アップロード指示書** — 実質内容ハッシュで前回と比較し、
   Copilot に上げ直すべきファイルだけを `_AI_CONTEXT_UPLOAD.md` に列挙。
2. **ドライラン容量予測** — 実行前に対象数・推定トークン・あふれ予測を表示。
3. **Teams通知** — 夜間実行の結果（件数・差分・エラー・要アップロード）を
   Incoming Webhook でチャネルに投稿。
4. **Boxオンラインオンリー制御** — クラウドのみのファイルを検知して
   スキップ/警告（初回の大量ダウンロード暴発を防止）。
5. **機密情報スキャン** — 個人番号・電話・メール・カード番号 + 部署辞書で
   検知。warn/mask/block の3段階。
6. **重複・類似文書検出** — 「v1とv2が92%同一」を検知し、警告または
   最新版のみ収録。INDEX に除外理由を記載。
7. **OCR実行** — テキスト層のないPDFを Windows 標準OCR（追加インストール
   不要）/ macOS Vision で本文化。エンジンがない環境では従来どおり
   OCR候補として報告。

## テスト

```bash
.venv/bin/python -m pytest tests/
```

`tests/test_parity.py` は「legacy モードの出力 = 復元版（=原本exe）」を
検証する回帰ネットです。原本挙動に関わる変更を入れたら必ず実行してください。

## v3.0 の新機能

1. **壊さない（原子的公開）** — 生成物はいったんステージングに作り、
   完全に成功したときだけ差し替えます。中断・参照元が空・収録量が半減した
   場合は公開を見送り、**公開中のナレッジをそのまま維持**します。
   理由は `_AI_CONTEXT_HOLD.md` と Teams 通知、終了コード4で分かります。
2. **壊れない（部分的失敗の局所化）** — 1ページ・1シート・1エントリの
   解析に失敗しても、その文書の他の部分は必ず残ります。
   「12ページ中10ページ抽出（p.4: 解析失敗）」のように理由まで記録します。
3. **人間向け読解キット** — `--digest` / `--digest-file`。
   長いマニュアルの目次・鮮度・重複・参照切れを機械的に取り出します。
   LLM を使わないので API キー不要・データ持ち出しゼロのままです。
4. **文書健康診断** — `_AI_CONTEXT_HEALTH.md`。
   「AIが読める割合」「鮮度」「重複」「上限」「機密」を100点満点で1枚に。
5. **コンパクトなGUI** — 折りたたみで既定の高さが 920px → 648px に。
   「1ファイルを読み解く」ボタンから、資料を1つ選ぶだけで分解できます。

### 長いマニュアルを1つ分解してみる（最短の使い方）

```bash
python -m contextgen --digest-file "設備点検マニュアル.docx" --output ./out
```

`out/_HUMAN_DIGEST/設備点検マニュアル.md` に、目次・古さの警告・
重複箇所・参照切れ・想定質問と、Copilotに貼るためのテキストが出力されます。
