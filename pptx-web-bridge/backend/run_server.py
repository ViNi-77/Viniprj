"""ローカルサーバ起動スクリプト。`python backend/run_server.py` で起動する。"""
from __future__ import annotations

import json
import socket
import sys
import threading
import urllib.error
import urllib.request
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

from app import version  # noqa: E402
from app.config import get_config  # noqa: E402
from app.logging_setup import get_logger  # noqa: E402


def port_in_use(host: str, port: int) -> bool:
    """そのポートで既に誰かが受け付けているか。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def occupant_is_this_app(host: str, port: int) -> dict | None:
    """ポートを使っているのがこのアプリ自身か（= 前に起動したものが残っている）を調べる。"""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/version", timeout=1.0) as res:  # noqa: S310
            data = json.loads(res.read().decode("utf-8"))
            return data if isinstance(data, dict) and data.get("schema_version") else None
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        pass
    try:  # 版の表示が無い古い版なら /api/config で判別する
        with urllib.request.urlopen(f"http://{host}:{port}/api/config", timeout=1.0) as res:  # noqa: S310
            data = json.loads(res.read().decode("utf-8"))
            if isinstance(data, dict) and "templates" in data:
                return {"version": str(data.get("version") or "不明"), "old": True}
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        pass
    return None


def pick_port(host: str, port: int, log) -> int:
    """使えるポートを決める。埋まっていれば空きを探し、理由を画面に出す。

    前に起動したこのアプリが残っていると、新しく起動したつもりでもブラウザは古い方を開いてしまう。
    それを黙って起こさないよう、必ず気づける形で知らせる。
    """
    if not port_in_use(host, port):
        return port
    occupant = occupant_is_this_app(host, port)
    if occupant is not None:
        old = occupant.get("version", "不明")
        log.warning("ポート %d は既にこのアプリが使っています（版 %s）。前に起動したものが残っているようです。", port, old)
        print(f"\n⚠ ポート {port} では既にこのアプリ（版 {old}）が動いています。", flush=True)
        print("  そちらを閉じない限り、ブラウザには古い画面が出ます。", flush=True)
        print(f"  前のウィンドウで Ctrl+C を押して終了するか、下に出る新しい URL を開いてください。\n", flush=True)
    else:
        log.warning("ポート %d は別のアプリが使っています。", port)
        print(f"\n⚠ ポート {port} は別のアプリが使っています。空いているポートで起動します。\n", flush=True)
    for candidate in range(port + 1, port + 21):
        if not port_in_use(host, candidate):
            return candidate
    raise SystemExit(f"{port} から 20 個ぶん探しましたが、空いているポートがありません。")


def main() -> None:
    if getattr(sys, "frozen", False):  # exe 化時は launcher の経路（ポート自動選択・準備待ち）を使う
        from launcher import main as launcher_main

        raise SystemExit(launcher_main())
    cfg = get_config()
    host = str(cfg.get("server.host", "127.0.0.1"))
    log = get_logger("server")
    port = pick_port(host, int(cfg.get("server.port", 8765)), log)
    url = f"http://{host}:{port}/"
    log.info("起動: %s %s (config=%s)", url, version.label(), cfg.config_path)
    print(f"\n  PPTX ⇄ Web図解 変換アプリ {version.label()}\n  {url}\n", flush=True)
    if cfg.get("server.open_browser", True) and "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host=host, port=port, log_level="info", reload="--reload" in sys.argv)


if __name__ == "__main__":
    main()
