"""トークンの水 — ローカルで開く。

dist/（なければ親フォルダの index.html は module のため動かないので、dist が必要）を標準ライブラリの http.server で配り、
空いているポートを選んでブラウザを開く。依存なし。Ctrl+C で止まる。
"""
from __future__ import annotations

import http.server
import json
import os
import socket
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
sys.path.insert(0, str(Path(__file__).resolve().parent))


class Handler(http.server.SimpleHTTPRequestHandler):
    """dist/ を配り、/api/me で自分の実ログの集計を返す（本文は読まない。127.0.0.1 だけで待つ）"""

    def log_message(self, *a, **k):  # noqa: ANN002, ANN003
        pass

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?")[0] == "/api/me":
            try:
                import water_meter
                body = json.dumps(water_meter.refresh(), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
            except Exception as e:  # noqa: BLE001
                body = json.dumps({"error": type(e).__name__}).encode("utf-8")
                self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def pick_port(start: int = 8766) -> int:
    for p in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise RuntimeError("空いているポートが見つからない")


def main() -> int:
    if not (DIST / "index.html").exists():
        print("dist/ がありません。先に `npm install && npm run build` を実行してください。")
        return 1
    port = pick_port()
    os.chdir(DIST)
    handler = Handler

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True

    with Server(("127.0.0.1", port), handler) as httpd:
        url = f"http://127.0.0.1:{port}/"
        print(f"トークンの水: {url}  （止めるときは Ctrl+C）")
        if "--no-browser" not in sys.argv:
            threading.Timer(0.4, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
