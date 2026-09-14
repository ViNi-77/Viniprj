# 図解プロンプト作成（PowerPoint ⇄ Web 図解）

PowerPoint や HTML 図解を読み取って、**Copilot にそのまま貼れる指示文（プロンプト）を作る**ローカルアプリです。

**図解を作るのはこのアプリではなく Copilot です。** このアプリの仕事は、資料の中身を
「何が書いてあるか（文章）」と「どんな構造か（型）」と「どんな見た目か（配色・フォント）」に分け、
Copilot が迷わず作れる形の言葉にすることだけです。

```
HTML 図解 ──読み取り──▶ 図解仕様 + 見た目 ──▶ プロンプト ──▶ Copilot in PowerPoint ──▶ PowerPoint
PowerPoint ─読み取り──▶ 図解仕様 + 見た目 ──▶ プロンプト ──▶ Copilot チャット ─────▶ HTML 図解
```

資料の中身は**手元だけで処理し、外部に送信しません**。貼り付け先だけはご自身で選びます。

---

## 1. 使い方（4 手順）

1. **資料を投入する** — PowerPoint（`.pptx`）か HTML 図解（`.html` / 画像入りの `.zip`）をドロップ
2. **読み取った中身を確かめる** — 頁ごとの型（フロー / カード / 比較 / 数値 / 年表 / 表 / 箇条書き…）と、
   **そう判定した理由**が表に出ます。外れていたらその場で直せます
3. **見た目を決める** — 元ファイルの配色をそのまま使う／別の HTML 図解テーマを読み込んで差し替える／指示しない
4. **Copilot に渡す** — プロンプトをコピーするか、一式（ZIP）をダウンロードして貼り付ける

画像がある資料では、プロンプトはファイル名で参照します。一式 ZIP の `画像/` を Copilot に添付してください。

### 一式 ZIP の中身

| ファイル | 使いみち |
|---|---|
| `プロンプト.txt` | そのまま貼り付けるもの |
| `図解仕様.yaml` | アプリが読み取った中身（プロンプトにも含まれます） |
| `構成.docx` | Copilot in PowerPoint の「ファイルから作成」に使えます |
| `画像/` | 資料に入っていた画像 |
| `はじめにお読みください.txt` | 手順と、読み取れなかったものの一覧 |

---

## 2. 起動

### Windows（Python 不要・いちばん簡単）

GitHub Actions の **build-windows** が作る `pptx-web-bridge-windows.zip` を展開し、`pptx-web-bridge.exe` をダブルクリックします。
数秒後にブラウザで `http://127.0.0.1:8765/` が開きます。終了は窓を閉じるだけです。

- 入手: リポジトリの Actions → build-windows → 最新の実行 → Artifacts
- **展開先は `C:\pptx-web-bridge` のような短いパスにしてください。** 奥深くに展開すると Windows のパス長上限（260 文字）に当たることがあります
- 起動直後にエラーで閉じる場合は `logs/startup_error.log` を確認してください
- **版の確認**: 画面右上のバッジに版とコミットが出ます。古い exe を起動していないかはここで分かります

### Windows / Linux（Python あり）

```bat
git clone https://github.com/ViNi-77/Viniprj.git
cd Viniprj\pptx-web-bridge
start_windows.bat              初回: 仮想環境作成・依存導入 → サーバ起動 → ブラウザが開く
start_windows.bat --no-browser ブラウザを開かない
start_windows.bat --setup-only 依存導入のみ
```

Linux / WSL は `./start.sh`（引数は同じ）。必要なのは Python 3.10 以上と、初回のみネットワーク（pip）です。

手動で入れる場合:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python backend/run_server.py
```

更新するときは `git pull origin main` のあと、もう一度起動してください。画面右上のバッジが変わっていれば新しい版です。

---

## 3. 何が読み取れて、何が読み取れないか

読み取れなかったものは**黙って消さず、画面の「読み取れなかったもの・注意」に理由が出ます**。

| 入力 | 読み取れるもの | 読み取れないもの |
|---|---|---|
| PowerPoint | 題名・本文・箇条書き・表・画像・図形の文字・ノート・テーマ色・テーマフォント | SmartArt の内部構造、動画、マクロ |
| HTML 図解 | 見出し・段落・箇条書き・表・画像・`div` のカード / グリッド、`<style>` と `style=` の配色（CSS 変数も解決） | **SVG・canvas で描いた図**、外部 CSS ファイル、JavaScript で生成される内容 |

SVG や canvas の図が入った HTML を読ませると、その図は取り込めません（警告が出ます）。
現状で確実に通るのは `div` ベースのカード・グリッドです。

---

## 4. 開発するとき

```bash
cd pptx-web-bridge
python scripts/loop.py           # 全部（単体・API → 通し検査 → 画面検査）。全部緑になるまでコミットしない
python scripts/loop.py --quick   # 単体・API のみ（実装中の高速反復）
```

| 検査 | 中身 |
|---|---|
| `tests/` | 単体・API（pytest） |
| `scripts/run_e2e.py` | 通し検査: 投入 → 図解仕様 → プロンプト → 一式。`docs/試験結果.md` に書き出す |
| `scripts/ui_smoke.py` | 画面検査（Playwright）。ノート PC 2 構成（1093×614 / 1280×720）で切れずに押せること |

試験資料は `samples/make_sample_pptx.py`（PowerPoint）と `samples/make_html_themes.py`（HTML 図解テーマ 6 種）が作ります。
実ファイル 1 つに合わせ込むと他で壊れるので、**壊れる軸を網羅した生成器**を使っています。

構成は `docs/` の番号付き文書にあります。現在地は [`docs/11_引き継ぎ.md`](docs/11_引き継ぎ.md) から読んでください。

---

## 5. 機密の扱い

このアプリは**資料の本文をそのまま Copilot に貼る**前提です。

- 社外秘の資料は**社内テナントの M365 Copilot でのみ**使ってください。外部の AI サービスに貼らないでください
- アプリ自体は外部へ通信しません（解析も生成もすべて手元で行います）
- **このリポジトリは public です。** ファイルを追加するときは、認証情報・トークン・社内ホスト名・個人情報が混ざっていないか確認してください
