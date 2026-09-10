#!/usr/bin/env bash
# Linux / WSL 用の起動スクリプト（Windows は start_windows.bat）。初回は仮想環境を作成して依存を導入し、ローカルサーバを起動してブラウザを開く。
# 使い方: ./start.sh            … 起動（ブラウザ自動オープン）
#         ./start.sh --no-browser … ブラウザを開かない
#         ./start.sh --setup-only … 依存導入のみ
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 が見つかりません。apt などで Python 3.10 以上を導入してください。" >&2
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "仮想環境を作成します: $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if [ ! -f "$VENV_DIR/.deps_installed" ] || [ requirements.txt -nt "$VENV_DIR/.deps_installed" ]; then
  echo "依存パッケージを導入します（初回のみ数分かかります）"
  pip install --upgrade pip >/dev/null
  pip install -r requirements.txt
  touch "$VENV_DIR/.deps_installed"
  # 見た目優先モード用のブラウザ。失敗しても編集性優先モードで動作する。
  if [ "${SKIP_PLAYWRIGHT_INSTALL:-0}" != "1" ]; then
    python -m playwright install chromium || echo "Playwright のブラウザ導入に失敗しました。見た目優先モードは編集性優先へ代替されます。"
  fi
fi

if [ "${1:-}" = "--setup-only" ]; then
  echo "セットアップ完了"
  exit 0
fi

if [ ! -f samples/sample_deck.pptx ]; then
  python samples/make_sample_pptx.py >/dev/null && echo "サンプル PPTX を生成しました: samples/sample_deck.pptx"
fi

exec python backend/run_server.py "$@"
