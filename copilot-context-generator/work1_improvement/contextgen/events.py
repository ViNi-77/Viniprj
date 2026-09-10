"""進捗・ログのイベント配信.

GUI はキュー、CLI は標準出力で同じイベントを受け取る。
イベント種別は原本互換: 'log' / 'current' / 'current_dir' / 'progress' / 'finish'
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


def now_text() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def filename_timestamp() -> str:
    return datetime.now().strftime('%Y%m%d_%H%M%S')


class Emitter:
    """イベント配信の基底。log() はタイムスタンプ付与とログファイル追記を行う。"""

    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path

    def emit(self, event_type: str, data) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def log(self, message: str) -> None:
        text = f"[{now_text()}] {message}"
        self.emit('log', text)
        if self.log_path is None:
            return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(text + '\n')
        except Exception:
            pass


class QueueEmitter(Emitter):
    """tkinter GUI 用: queue.Queue に (event_type, data) を積む。"""

    def __init__(self, q, log_path: Path | None = None):
        super().__init__(log_path)
        self.queue = q

    def emit(self, event_type: str, data) -> None:
        self.queue.put((event_type, data))


class ConsoleEmitter(Emitter):
    """CLI 用: log は標準出力、current/current_dir は quiet でなければ表示。"""

    def __init__(self, log_path: Path | None = None, verbose: bool = False):
        super().__init__(log_path)
        self.verbose = verbose

    def emit(self, event_type: str, data) -> None:
        if event_type == 'log':
            print(data, flush=True)
        elif event_type in ('current', 'current_dir') and self.verbose:
            print(f"  {data}", flush=True)


class NullEmitter(Emitter):
    """テスト用: 何もしない。"""

    def __init__(self):
        super().__init__(None)

    def emit(self, event_type: str, data) -> None:
        pass
