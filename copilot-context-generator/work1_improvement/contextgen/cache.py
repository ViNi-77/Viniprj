"""改善①: SQLite 抽出キャッシュとフォルダ差分.

管理フォルダの extract_cache.db に「パス / サイズ / mtime / 抽出結果」を保存し、
サイズ+mtime が一致するファイルは再抽出をスキップする。
各実行のファイル一覧（インベントリ）も保存し、前回実行との差分
（追加 / 変更 / 削除）を算出する。
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .extractors import ExtractResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS extract_cache (
    path TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '',
    extracted_at TEXT NOT NULL,
    units TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    file_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS inventory (
    run_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    PRIMARY KEY (run_id, path)
);
CREATE TABLE IF NOT EXISTS package_state (
    file_name TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def load_package_state(db_path: Path) -> dict[str, str]:
    """v2.1 F1: 前回の固定名ファイルの内容ハッシュを読む."""
    db_path = Path(db_path)
    if not db_path.exists():
        return {}
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(SCHEMA)
        return dict(conn.execute("SELECT file_name, sha256 FROM package_state"))


def save_package_state(db_path: Path, mapping: dict[str, str], now: str) -> None:
    """v2.1 F1: 今回の固定名ファイルの内容ハッシュを保存する（全置換）."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(SCHEMA)
        conn.execute("DELETE FROM package_state")
        conn.executemany(
            "INSERT INTO package_state (file_name, sha256, updated_at) VALUES (?, ?, ?)",
            [(name, sha, now) for name, sha in mapping.items()],
        )


@dataclass
class DiffReport:
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    previous_run_at: str | None = None

    @property
    def has_previous(self) -> bool:
        return self.previous_run_at is not None

    @property
    def total(self) -> int:
        return len(self.added) + len(self.changed) + len(self.removed)

    def summary_lines(self, limit: int = 50) -> list[str]:
        lines = []
        if not self.has_previous:
            lines.append('- 初回実行（比較対象なし）')
            return lines
        lines.append(f"- 前回実行: {self.previous_run_at}")
        lines.append(f"- 追加 {len(self.added)} / 変更 {len(self.changed)} / 削除 {len(self.removed)}")
        for label, items in (('追加', self.added), ('変更', self.changed), ('削除', self.removed)):
            for p in items[:limit]:
                lines.append(f"  - [{label}] {p}")
            if len(items) > limit:
                lines.append(f"  - [{label}] …ほか {len(items) - limit} 件")
        return lines


class ExtractCache:
    """抽出結果キャッシュ。with 文で開閉する。"""

    def __init__(self, db_path: Path, now_text_fn):
        self.db_path = Path(db_path)
        self._now = now_text_fn
        self.hits = 0
        self.misses = 0
        self._conn: sqlite3.Connection | None = None
        self._run_id: int | None = None

    def __enter__(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.executescript(SCHEMA)
        # v3: 既存キャッシュを捨てずに units 列を足す（無ければ追加、あれば無視）
        try:
            self._conn.execute("ALTER TABLE extract_cache ADD COLUMN units TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._conn is not None:
            if exc_type is None:
                self._conn.commit()
            self._conn.close()
            self._conn = None
        return False

    # ---- 抽出キャッシュ ----

    def get(self, path: Path, size: int, mtime: float) -> ExtractResult | None:
        row = self._conn.execute(
            "SELECT status, reason, text, units FROM extract_cache"
            " WHERE path = ? AND size = ? AND mtime = ?",
            (str(path), size, mtime),
        ).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        status, reason, text, units_json = row
        result = ExtractResult(text=text, status=status, reason=reason, meta={'cache': 'hit'})
        # v3: 構成単位の抽出状況もキャッシュから復元する
        # （復元しないと、キャッシュヒットしたファイルのカバレッジが毎回失われる）
        if units_json:
            try:
                units = json.loads(units_json)
                result.units_total = units.get('total', 0)
                result.units_ok = units.get('ok', 0)
                result.unit_failures = [tuple(f) for f in units.get('failures', [])]
            except Exception:
                pass
        return result

    def put(self, path: Path, size: int, mtime: float, result: ExtractResult) -> None:
        units_json = ''
        if result.units_total:
            units_json = json.dumps({
                'total': result.units_total,
                'ok': result.units_ok,
                'failures': result.unit_failures,
            }, ensure_ascii=False)
        self._conn.execute(
            "INSERT OR REPLACE INTO extract_cache"
            " (path, size, mtime, status, reason, text, extracted_at, units)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(path), size, mtime, result.status, result.reason, result.text,
             self._now(), units_json),
        )

    # ---- インベントリと差分 ----

    def begin_run(self) -> int:
        cur = self._conn.execute(
            "INSERT INTO runs (started_at) VALUES (?)", (self._now(),)
        )
        self._run_id = cur.lastrowid
        return self._run_id

    def record_inventory(self, entries: list[tuple[str, int, float]]) -> None:
        self._conn.executemany(
            "INSERT OR REPLACE INTO inventory (run_id, path, size, mtime) VALUES (?, ?, ?, ?)",
            [(self._run_id, p, s, m) for p, s, m in entries],
        )
        self._conn.execute(
            "UPDATE runs SET file_count = ? WHERE run_id = ?",
            (len(entries), self._run_id),
        )

    def diff_from_previous(self) -> DiffReport:
        prev = self._conn.execute(
            "SELECT run_id, started_at FROM runs WHERE run_id < ? ORDER BY run_id DESC LIMIT 1",
            (self._run_id,),
        ).fetchone()
        if prev is None:
            return DiffReport()
        prev_id, prev_at = prev

        prev_map = dict()
        for path, size, mtime in self._conn.execute(
            "SELECT path, size, mtime FROM inventory WHERE run_id = ?", (prev_id,)
        ):
            prev_map[path] = (size, mtime)

        cur_map = dict()
        for path, size, mtime in self._conn.execute(
            "SELECT path, size, mtime FROM inventory WHERE run_id = ?", (self._run_id,)
        ):
            cur_map[path] = (size, mtime)

        report = DiffReport(previous_run_at=prev_at)
        for path in sorted(cur_map):
            if path not in prev_map:
                report.added.append(path)
            elif prev_map[path] != cur_map[path]:
                report.changed.append(path)
        for path in sorted(prev_map):
            if path not in cur_map:
                report.removed.append(path)
        return report

    def cleanup(self, keep_runs: int = 5) -> None:
        """古いインベントリと、直近実行に存在しないキャッシュ行を掃除する。"""
        ids = [r[0] for r in self._conn.execute(
            "SELECT run_id FROM runs ORDER BY run_id DESC"
        ).fetchall()]
        if len(ids) > keep_runs:
            drop = ids[keep_runs:]
            marks = ','.join('?' * len(drop))
            self._conn.execute(f"DELETE FROM inventory WHERE run_id IN ({marks})", drop)
            self._conn.execute(f"DELETE FROM runs WHERE run_id IN ({marks})", drop)
        if self._run_id is not None:
            self._conn.execute(
                "DELETE FROM extract_cache WHERE path NOT IN"
                " (SELECT path FROM inventory WHERE run_id = ?)",
                (self._run_id,),
            )
