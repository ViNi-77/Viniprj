"""PyInstaller 用エントリポイント.

引数なし（ダブルクリック起動）→ GUI
引数あり（タスクスケジューラ等） → CLI として動作
  例: CopilotM365ContextGenerator.exe --source D:\\docs --output D:\\ctx

exe は windowed ビルド（console=False）のため、フリーズ環境では
sys.stdout / sys.stderr / sys.stdin が None になる。この状態で
print() や argparse の --help 等が呼ばれると即 OSError で落ちるため、
起動直後・他の何もインポートする前に os.devnull へフォールバックする。
進捗・結果は「管理」フォルダのログファイル（events.Emitter.log が
print() と独立にファイル書き込みするため影響を受けない）と
Teams 通知（--teams-webhook）で確認する。
"""
import os
import sys


def _ensure_stdio() -> None:
    if sys.stdin is None:
        sys.stdin = open(os.devnull, 'r')
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')


_ensure_stdio()

if len(sys.argv) > 1:
    from contextgen.cli import main
    sys.exit(main())
else:
    from contextgen.gui import run_gui
    run_gui()
