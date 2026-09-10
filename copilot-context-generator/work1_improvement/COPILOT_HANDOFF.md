# 社内 M365 Copilot への伴走依頼プロンプト

このファイルは、会社環境の M365 Copilot にセットアップ〜exeビルドを
伴走してもらうためのコピペ用プロンプト集です。

**使い方**
1. 下の「■ 初回プロンプト」をそのまま Copilot チャットに貼る
2. 以降は Copilot の指示に従い、コマンド結果やエラー全文を貼って進める
3. 日をまたいだら「■ 再開プロンプト」で状況を思い出させる

**貼ってよいもの / いけないもの**
- ✅ ツールのログ・エラーメッセージ・コマンド出力・このリポジトリのコードやdocs
- ❌ 部署の実文書の中身、生成されたコンテキストファイルの本文（社内文書そのものなので）

**Copilot に「ファイルを見せて」と言われたら**（1ファイルずつ貼る）
- ビルド手順 → `docs/BUILD_WINDOWS.md`
- 運用・スケジューラ → `docs/OPERATIONS.md`
- 機能一覧・CLIオプション → `docs/README.md`
- spec の中身 → `contextgen_onefile.spec`
- エラーが特定モジュールなら → `contextgen/` 配下の該当ファイル

---

## ■ 初回プロンプト（ここから下をコピペ）

あなたには、社内ツールの Windows セットアップと exe ビルドの伴走支援をお願いします。ローカルファイルはあなたから直接見えないので、必要なファイルの中身やエラーは私がその都度貼ります。**1ステップずつ、実行するコマンドと確認ポイントを指示してください。**

### 事情
- ツール名: **contextgen v2.1.0**（Copilot M365用コンテキスト生成ツール）。部署の Box フォルダを走査し、Word/Excel/PowerPoint/PDF/ZIP から本文を抽出して、M365 Copilot エージェントのナレッジに投入する固定名TXT（INDEX 1 + 本文最大19 = 20ファイル）と Markdown/JSONL/各種レポートを生成する Python 3.12 製ツールです。
- 開発・テスト（pytest 86件）は完了済み。
- 私のゴールは、この PC でのセットアップ → Windows固有機能の動作確認 → **単一exeビルド** → 部署配布と夜間自動実行の設定です。

### 持ち込んだフォルダ構成（work1_improvement）
- `contextgen/` … 本体パッケージ（config / pipeline / scanner / extractors / outputs / cli / gui など）
- `tests/` … pytest 86件（原本exe互換のパリティテスト含む）
- `launcher_gui.py` … exeエントリポイント。**引数なし=GUI起動 / 引数あり=CLI動作**
- `contextgen_onefile.spec` … **単一exe用 PyInstaller spec（今回使うのはこれ）**
- `contextgen.spec` … フォルダ配布（onedir）用の別spec
- `pyproject.toml` … 依存定義。extras `[ocr-windows]` = pypdfium2 + winsdk
- `docs/` … README / OPERATIONS / BUILD_WINDOWS / CHANGELOG
- `scripts/run_contextgen_nightly.bat` … タスクスケジューラ登録用の雛形

### 進めてほしい手順（この順で）
1. **環境確認**: Python 3.12 の有無（なければ python.org 版を「Add python.exe to PATH」付きでインストール）
2. **セットアップ**:
   ```
   cd <配置先フォルダ>
   python -m venv .venv
   .venv\Scripts\pip install -e ".[dev,ocr-windows]"
   .venv\Scripts\pip install pyinstaller pywin32
   ```
3. **テスト**: `.venv\Scripts\python -m pytest tests` → 86件パスの確認
4. **Windows固有の動作確認**（この3点は実機未検証です）
   - OCR: `--ocr auto` でテキスト層のないPDFが本文化されるか（Windows.Media.Ocr / winsdk 経由。日本語言語パックは Windows 標準）
   - Box Drive: `--cloud-only warn` でオンラインオンリーファイルの検知が働くか（st_file_attributes のクラウド属性で判定）
   - GUI: `.venv\Scripts\python -m contextgen.gui` が開き、「ドライラン（見積のみ）」ボタンが動くか
5. **単一exeビルド**: `.venv\Scripts\pyinstaller contextgen_onefile.spec` → `dist\CopilotM365ContextGenerator.exe`
6. **exe動作確認**: ダブルクリックでGUI / `CopilotM365ContextGenerator.exe --source ... --output ... --dry-run` でCLI見積
7. **本番初回実行**: まず `--dry-run --cloud-only warn` で見積 →問題なければ本実行 → 生成された `_AI_CONTEXT_UPLOAD.md`（再アップロード指示書）に従って Copilot エージェントのナレッジへ登録
8. **自動化**: `scripts/run_contextgen_nightly.bat` を編集してタスクスケジューラ登録、Teams Incoming Webhook（`--teams-webhook`）設定

### 制約・お願い
- 社内文書の実データはこのチャットに貼りません。貼るのはツールのログ・エラー・コード・設定だけです
- pip が社内プロキシ/SSL検査で失敗したら、プロキシ設定や社内ミラー、ホイール持ち込みなどの代替手順を提案してください
- exe は未署名なので SmartScreen 警告が出る想定です。回避策ではなく、社内配布として適切な方法（署名、配布時の周知など）を提案してください
- ファイルの削除・上書き・レジストリ変更など元に戻しにくい操作は、先に理由と影響を説明してください

### トラブル時に私が貼る情報
実行したコマンド / エラー全文 / `python --version` / `.venv\Scripts\pip list` の結果

それでは、ステップ1の環境確認から始めます。最初に実行すべきコマンドを教えてください。

---

## ■ 再開プロンプト（2回目以降のセッション用）

contextgen v2.1.0（部署BoxフォルダからM365 Copilotエージェント用ナレッジを生成するPython製社内ツール）のWindowsセットアップの続きです。手順は「環境確認→venv+依存→pytest 86件→Windows固有確認（OCR/Box属性/GUI）→pyinstaller contextgen_onefile.spec で単一exe→動作確認→タスクスケジューラ+Teams通知」。前回は【◯◯】まで完了し、いま【◯◯】で止まっています。状況: 【エラーや出力を貼る】。続きを1ステップずつお願いします。

---

## ■ うまくいかない時の頻出パターン（Copilot に相談する際のヒント）

| 症状 | 貼るとよい情報 / 補足 |
|---|---|
| pip install が SSL/接続エラー | エラー全文。社内プロキシの可能性。`--proxy` や信頼済みホスト設定、別PCでのホイールDL持ち込みが代替策 |
| winsdk が入らない / OCRが動かない | `pip show winsdk` の結果。OCRなし構成（`pip install -e .`）でも本体は動く（OCR候補レポートになるだけ） |
| pyinstaller 後に exe が起動しない | `dist` をコンソールから実行した際の出力。`--debug` ビルドや onedir spec（contextgen.spec）での切り分け |
| SmartScreen 警告 | 未署名のため想定内。「詳細情報→実行」。恒久対応はコード署名 |
| exe が AV に隔離される | 情シスへの除外申請が正道。UPXは無効化済み。onedir 版は誤検知が減る |
