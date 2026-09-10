# Viniprj

小規模な業務改善ツールを 1 つのリポジトリで管理する。
各ツールは独立したフォルダに置き、それぞれが README・依存定義・テスト・起動手順を持つ。

| ツール | フォルダ | 概要 | 入口 |
|---|---|---|---|
| PPTX ⇄ Web図解 双方向変換アプリ | [`pptx-web-bridge/`](pptx-web-bridge/) | PowerPoint と Web図解を Presentation JSON で双方向変換するローカル Web アプリ | `cd pptx-web-bridge && start_windows.bat`（Linux / WSL は `./start.sh`）→ [README](pptx-web-bridge/README.md) |
| contextgen（M365 Copilot コンテキスト生成ツール） | [`copilot-context-generator/`](copilot-context-generator/) | フォルダ内の Word / Excel / PowerPoint / PDF から本文を抽出し、M365 Copilot エージェント用ナレッジ・人間向け読解キット・文書健康診断を生成 | [README](copilot-context-generator/README.md) → 本体は `work1_improvement/`、横展開は `work2_cross_ai/` |

## はじめかた（clone して起動）

```bash
git clone https://github.com/ViNi-77/Viniprj.git
cd Viniprj/pptx-web-bridge
start_windows.bat        # Windows（Python 3.10 以上が必要。仮想環境の作成〜起動まで自動）
./start.sh               # Linux / WSL
```

Python を入れられない PC では、GitHub Actions の **build-windows** が作る exe 版 ZIP（Actions → 最新の実行 → Artifacts、または `dist/windows` ブランチ）を展開して `pptx-web-bridge.exe` を実行する。詳細は [pptx-web-bridge/README.md](pptx-web-bridge/README.md) の 0 章。

## リポジトリの運用

- 既定ブランチは `main`。作業は Issue ごとにブランチを切り、PR（本文に `Closes #番号`）で `main` へ取り込む
- CI（`.github/workflows/`）
  - `loop-check`: 全 push / PR で PPTX 変換アプリの検査（`pptx-web-bridge/scripts/loop.py`）を実行
  - `build-windows`: `pptx-web-bridge/` の関連ファイル変更時に Windows 用 exe をビルドし、ZIP を `dist/windows` ブランチに置く（タグ `v*` で Release にも添付）
- 依存や仮想環境（`.venv`）は各ツールのフォルダ内で完結させる。ルートの `.gitignore` は汎用パターンのみで、ツール固有の除外は各フォルダの `.gitignore` に置く
- 公開リポジトリのため、ロゴ・社名・機密情報・個人情報を含むファイルは置かない。`pptx-web-bridge/config/template_assets/` の画像はサンプル用のダミー素材で、実運用では各自のローカルで差し替える（差し替えた素材はコミットしない）

## ツールを追加するとき

1 フォルダ = 1 ツール。フォルダ直下に README と依存定義（`pyproject.toml` / `requirements.txt`）を置き、上の表に 1 行足す。
CI が必要なら `.github/workflows/` に追加し、`paths:` と `working-directory` でそのフォルダに限定する。
