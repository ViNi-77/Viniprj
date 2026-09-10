# 運用ガイド（夜間自動実行・差分運用）

## 推奨運用: 毎晩の自動更新

改善①（差分キャッシュ）+ 改善④（CLI）の組み合わせで、
「毎晩自動で最新化 → 朝は差分レポートだけ確認」の運用ができます。

### 1. バッチファイル

`scripts/run_contextgen_nightly.bat` を環境に合わせて編集します。
**メモ帳や VSCode で直接開いて書き換える**のが最も安全です（下記の
注意点を踏まなくて済みます）。

```bat
@echo off
set PYTHON=C:\Tools\contextgen\.venv\Scripts\python.exe
set SOURCE=C:\BoxDrive\Box\第2ユニット生技部_全員\002_室運営\2026年\NZB00_アルミ開発室
set OUTPUT=C:\BoxDrive\Box\...\ChatGPT用コンテキストファイル生成\生成コンテキスト

"%PYTHON%" -m contextgen --source "%SOURCE%" --output "%OUTPUT%" --sort mtime_desc
exit /b %ERRORLEVEL%
```

> **⚠️ PowerShell でこの .bat を生成・上書きする場合の注意**
> `.bat`（cmd.exe が読む）は **CRLF改行 + cp932（Shift_JIS系）** を
> 前提にしています。PowerShell の `Out-File` や `Set-Content` は既定で
> UTF-8 や BOM付きで書き出すことがあり、それだと日本語コメントの文字化けや、
> 全角文字（全角の「＆」等）を含むパスの破損、さらに BOM が行頭1文字を
> 飲み込む症状（`chcp` が `hcp` になる等）が起こります。
> PowerShell で書き出す必要がある場合は、必ず次の形（CRLF明示 + cp932指定）
> にしてください:
> ```powershell
> $batContent = $batContent -replace "`r?`n", "`r`n"   # 改行をCRLFに統一
> [System.IO.File]::WriteAllText(
>     "C:\path\to\run_contextgen_nightly.bat",
>     $batContent,
>     [System.Text.Encoding]::GetEncoding(932)          # cp932、BOMなし
> )
> ```
> また `C:\Users\<名前>\Documents\R＆D\...` のような**全角文字を含む
> パス**は、bat内の `set` 変数や `cd` で予期しない文字化けの原因に
> なりやすいため、可能であれば `C:\contextgen` のような半角パスに
> ツール一式を配置することを推奨します。

Teams 通知を付ける場合（推奨）:

```bat
"%PYTHON%" -m contextgen --source "%SOURCE%" --output "%OUTPUT%" --sort mtime_desc ^
    --teams-webhook "https://xxxx.webhook.office.com/webhookb2/..."
```

Webhook URL は Teams チャネル → コネクタ →「Incoming Webhook」で発行します。

### 2. タスクスケジューラ登録（Windows）

1. タスクスケジューラ → 「基本タスクの作成」
2. トリガー: 毎日 6:00（Box Drive の同期が落ち着いた時間帯を推奨）
3. 操作: 「プログラムの開始」→ 上記 .bat を指定
4. 条件: 「AC電源接続時のみ」は運用に合わせて調整
5. 設定: 「タスクが失敗した場合の再起動」を1回程度

コマンドラインからの登録例:

```bat
schtasks /Create /TN "ContextGen Nightly" /TR "C:\Tools\contextgen\scripts\run_contextgen_nightly.bat" /SC DAILY /ST 06:00
```

### 2.5 終了コードの意味（v3）

| コード | 意味 | 対応 |
|---|---|---|
| 0 | 正常終了・公開済み | `_AI_CONTEXT_UPLOAD.md` を見て差し替え |
| 2 | 引数・フォルダ指定の誤り | バッチのパスを確認 |
| 3 | 停止・実行時エラー | ログを確認 |
| **4** | **公開見送り（既存ナレッジは無事）** | `_AI_CONTEXT_HOLD.md` を確認 |

**コード4は「失敗」ではありません。** 参照元が空・大幅減・中断のときに、
壊れた新版で上書きせず既存を守った状態です。原因（Boxの同期状態など）を
確認し、意図した削減であれば `--force-publish` を付けて実行してください。

### 3. 朝の確認ポイント

- **Teams 通知（または `_AI_CONTEXT_UPLOAD.md`）の「要再アップロード」**
  → 変わったファイルだけを Copilot エージェントのナレッジで置き換える。
  「再アップロード不要」なら作業なし
- **`_AI_CONTEXT_HOLD.md` があれば最優先で確認**（公開が見送られています）
- `_AI_CONTEXT_HEALTH.md` の総合スコアと「まず手を付けるとよいこと」
- `_AI_CONTEXT_REPORT.md` の「前回実行との差分」→ 追加/変更/削除の妥当性
- レポートの「部分抽出」→ 本文の一部が欠けている文書の有無
- 「OCR候補」「要変換」「機密情報検知」「類似文書グループ」→ 対応要否の判断
- `M365AgentContext_INDEX.txt` の `OverflowChunkCount` → 0 でなければ
  `--split-by-subfolder` や `--priority-folder` の検討（事前に `--dry-run` で予測可能）

## Box Drive 利用時の注意

- オンラインオンリーのファイルは初回抽出時にダウンロードが発生します。
  初回のみ全量、2回目以降は変更ファイルだけになるため、差分キャッシュを
  有効（既定）のまま運用してください。
- **v2.1**: `--cloud-only warn` でダウンロード発生件数を事前把握、
  `--cloud-only skip` でクラウドのみのファイルを抽出対象から外せます
  （スキップしたファイルはレポートに一覧されます）。
  初回導入時は `--dry-run --cloud-only warn` での見積もりを推奨します。
- Box の同期中に実行するとファイルロックでエラーになることがあります。
  エラーはレポートに記録され、次回実行で自動リトライされます。

## キャッシュのメンテナンス

- キャッシュ DB: `管理\extract_cache.db`
- 全リセット: DB を削除するか `--full-rescan` を実行
- 直近5回分のインベントリを保持し、それより古い履歴と
  存在しなくなったファイルのキャッシュは自動削除されます

## M365 Copilot エージェントへの投入

1. `M365AgentContext_INDEX.txt` と `RequiredFiles` に列挙された本文ファイル
   （最大計20ファイル）をエージェントのナレッジに追加
2. 再生成後もファイル名は固定なので、ナレッジの再アップロードは
   「同名ファイルの置き換え」で済みます
3. `Archive/` は履歴用。エージェントには追加しないでください
