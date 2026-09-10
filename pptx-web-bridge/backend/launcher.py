"""exe 化（PyInstaller）用の起動エントリ。ダブルクリックで起動し、ブラウザでローカルページを開く。

基本設計基準書 8 章: multiprocessing.freeze_support() を最優先で実行し、sys._MEIPASS を考慮したパス解決を使う。
- ポートが使用中なら空きポートへ自動で切り替える
- サーバの準備ができてからブラウザを開く（空ページ防止）
- Ctrl+C または窓を閉じると終了。ログは exe の隣の logs/app.log
"""
from __future__ import annotations

import multiprocessing
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path


def _prepare_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _find_free_port(host: str, preferred: int, attempts: int = 20) -> int:
    for port in range(preferred, preferred + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            if s.connect_ex((host, port)) != 0:
                return port
    return preferred


def _wait_ready(url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "api/health", timeout=1) as r:  # noqa: S310 - ローカルのみ
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.3)
    return False


def main() -> int:
    multiprocessing.freeze_support()
    _prepare_streams()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from app.config import ROOT_DIR, get_config  # noqa: E402
    from app.logging_setup import get_logger  # noqa: E402

    cfg = get_config()
    log = get_logger("launcher")
    host = str(cfg.get("server.host", "127.0.0.1"))
    port = _find_free_port(host, int(cfg.get("server.port", 8765)))
    url = f"http://{host}:{port}/"
    no_browser = "--no-browser" in sys.argv or not cfg.get("server.open_browser", True)

    print("=" * 60)
    print(" PPTX <-> Web図解 変換アプリ")
    print(f" URL: {url}")
    print(f" 保存先: {ROOT_DIR / 'projects'}  出力: {ROOT_DIR / 'output'}  ログ: {ROOT_DIR / 'logs'}")
    print(" 終了するには この窓を閉じるか Ctrl+C を押してください")
    print("=" * 60, flush=True)
    log.info("起動: %s (frozen=%s, root=%s)", url, getattr(sys, "frozen", False), ROOT_DIR)

    import uvicorn  # noqa: E402

    from app.main import app  # noqa: E402

    config = uvicorn.Config(app, host=host, port=port, log_level="info", workers=1)
    server = uvicorn.Server(config)

    def _open() -> None:
        if _wait_ready(url):
            if not no_browser:
                webbrowser.open(url)
        else:
            print("サーバの起動を確認できませんでした。logs/app.log を確認してください。", flush=True)

    threading.Thread(target=_open, daemon=True).start()
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    print("終了しました。", flush=True)
    return 0


def _report_fatal_error(exc: BaseException) -> None:
    """起動時の想定外の例外を分かりやすく表示し、ログにも残す（窓が一瞬で閉じるのを防ぐ）。"""
    tb = traceback.format_exc()
    print("=" * 60)
    print(" 起動に失敗しました（想定外のエラー）")
    print("=" * 60)
    print(tb)
    print("よくある原因と対処:")
    print(" ・ZIP の展開先のパスが長すぎる（例: 深い階層の OneDrive/ダウンロード内）")
    print("   → C:\\pptx-web-bridge のような短いパスに展開し直してください")
    print(" ・ウイルス対策ソフト/EDR がファイルの一部をブロック/削除している")
    print("   → 展開したフォルダを一度削除し、ZIP を展開し直してください。")
    print("     改善しない場合は情シス/セキュリティ担当にこの exe の除外設定を相談してください")
    print(" ・ZIP が壊れている、または展開が途中で終わっている")
    print("   → ZIP を再ダウンロードし、フォルダごと展開し直してください")
    try:
        from app.config import ROOT_DIR  # noqa: E402

        log_dir = ROOT_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "startup_error.log").write_text(tb, encoding="utf-8", errors="replace")
        print(f"詳細は {log_dir / 'startup_error.log'} にも保存しました。")
    except Exception:  # noqa: BLE001
        pass
    print("この画面の内容を担当者に共有してください。Enter キーで閉じます。")
    try:
        input()
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - 起動失敗を必ず画面に残すための最終防波堤
        _report_fatal_error(exc)
        raise SystemExit(1)
