"""ローカルサーバ起動スクリプト。`python backend/run_server.py` で起動する。"""
from __future__ import annotations

import sys
import threading
import webbrowser
from pathlib import Path

# Windows のコンソール（cp932）で日本語ログが化けたり例外になったりしないよう UTF-8 に揃える
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

from app.config import get_config  # noqa: E402
from app.logging_setup import get_logger  # noqa: E402


def main() -> None:
    if getattr(sys, "frozen", False):  # exe 化時は launcher の経路（ポート自動選択・準備待ち）を使う
        from launcher import main as launcher_main

        raise SystemExit(launcher_main())
    cfg = get_config()
    host = str(cfg.get("server.host", "127.0.0.1"))
    port = int(cfg.get("server.port", 8765))
    url = f"http://{host}:{port}/"
    log = get_logger("server")
    log.info("起動: %s (config=%s)", url, cfg.config_path)
    if cfg.get("server.open_browser", True) and "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host=host, port=port, log_level="info", reload="--reload" in sys.argv)


if __name__ == "__main__":
    main()
