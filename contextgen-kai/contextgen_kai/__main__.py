"""EXE/CLI共通入口。Windows予約のヘッドレス実行も同じジョブを利用する。"""
from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import multiprocessing
import socket
import sys
import threading
import webbrowser
from pathlib import Path


def main():
    multiprocessing.freeze_support()
    from .installation import InstallationBusy, installation_lock
    try:
        with installation_lock():
            return _main()
    except InstallationBusy as error:
        print(str(error), file=sys.stderr)
        return 2


def _main():
    parser = argparse.ArgumentParser(description="contextgen 改 — 手元の資料をCopilotへ")
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--run-schedule")
    parser.add_argument("--picker-file", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.picker_file:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            path = filedialog.askdirectory(title="資料フォルダを選択", mustexist=True, parent=root)
            args.picker_file.write_text(json.dumps({"path": path}, ensure_ascii=False), encoding="utf-8")
        finally:
            root.destroy()
        return 0
    from .storage import Store, default_state_dir
    state_dir = (args.state_dir or default_state_dir()).resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(state_dir / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")
    if args.run_schedule:
        from .jobs import JobManager
        from .scheduling import Scheduler
        jobs = JobManager(Store(state_dir))
        scheduler = Scheduler(state_dir, lambda s: jobs.start(s["library_id"], collection_id=s.get("collection_id"), export_after=bool(s.get("collection_id")), schedule_id=s["id"])["id"])
        jobs.complete_callback = scheduler.complete
        try:
            job_id = scheduler.run_reserved(args.run_schedule)
            if not job_id or job_id == "pending":
                return 0
            if job_id not in jobs.threads:
                return 0
            jobs.threads[job_id].join()
            job = jobs.store.one("SELECT * FROM jobs WHERE id=?", (job_id,))
            return 0 if job["state"] == "completed" else 4 if job["state"] == "held" else 3
        finally:
            jobs.close()
    import uvicorn
    from .api import create_app
    sock = None
    for port in range(args.port, min(args.port + 30, 65536)):
        candidate = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            candidate.bind(("127.0.0.1", port))
            candidate.listen(128)
            sock = candidate
            break
        except OSError:
            candidate.close()
    if sock is None:
        raise RuntimeError("起動用ポートを確保できませんでした")
    server = None
    app = create_app(state_dir, shutdown_callback=lambda: setattr(server, "should_exit", True))
    # windowed EXEにはstdout/stderrがない。既定の色付きコンソールログを作らない。
    config = uvicorn.Config(app, host="127.0.0.1", port=sock.getsockname()[1], access_log=False, log_level="warning", log_config=None, use_colors=False)
    server = uvicorn.Server(config)
    url = f"http://127.0.0.1:{sock.getsockname()[1]}/"
    logging.info("起動 version=%s port=%s", app.version, sock.getsockname()[1])
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.run(sockets=[sock])
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
