"""利用者専用SQLite。原本・抽出・修正・ジョブを分離して永続化する。"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def identifier() -> str:
    return uuid.uuid4().hex


def validate_identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", value):
        raise ValueError("保存データの識別子が不正です")
    return value


def default_state_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "ContextgenKai"
    return Path.home() / "Library/Application Support/ContextgenKai" if sys.platform == "darwin" else Path.home() / ".local/share/contextgen-kai"


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
INSERT OR IGNORE INTO meta VALUES('schema_version','1');
CREATE TABLE IF NOT EXISTS libraries(
 id TEXT PRIMARY KEY,name TEXT NOT NULL,path TEXT NOT NULL UNIQUE,kind TEXT NOT NULL DEFAULT 'folder',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents(
 id TEXT PRIMARY KEY, library_id TEXT NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
 relative_path TEXT NOT NULL, source_path TEXT NOT NULL, size INTEGER NOT NULL,mtime_ns INTEGER NOT NULL,
 source_hash TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'pending',
 original_text TEXT NOT NULL DEFAULT '',edited_text TEXT,edit_base_hash TEXT,
 effective_text TEXT NOT NULL DEFAULT '',excluded INTEGER NOT NULL DEFAULT 0,conflict INTEGER NOT NULL DEFAULT 0,
 warnings TEXT NOT NULL DEFAULT '[]',units TEXT NOT NULL DEFAULT '[]',metadata TEXT NOT NULL DEFAULT '{}',
 active INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL,UNIQUE(library_id,relative_path));
CREATE INDEX IF NOT EXISTS documents_library ON documents(library_id,active,relative_path);
CREATE INDEX IF NOT EXISTS documents_hash ON documents(source_hash);
CREATE TABLE IF NOT EXISTS collections(
 id TEXT PRIMARY KEY,name TEXT NOT NULL,library_id TEXT NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
 query TEXT NOT NULL DEFAULT '',folder TEXT NOT NULL DEFAULT '',document_ids TEXT NOT NULL DEFAULT '[]',
 purpose TEXT NOT NULL DEFAULT 'overview',instructions TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY,library_id TEXT REFERENCES libraries(id) ON DELETE CASCADE,kind TEXT NOT NULL DEFAULT 'scan',
 state TEXT NOT NULL DEFAULT 'queued',stage TEXT NOT NULL DEFAULT '',processed INTEGER NOT NULL DEFAULT 0,
 total INTEGER NOT NULL DEFAULT 0,errors INTEGER NOT NULL DEFAULT 0,message TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL,payload TEXT NOT NULL DEFAULT '{}',
 scan_complete INTEGER NOT NULL DEFAULT 0,export_id TEXT,owner_pid INTEGER);
CREATE TABLE IF NOT EXISTS job_files(
 job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,relative_path TEXT NOT NULL,source_path TEXT NOT NULL,
 size INTEGER NOT NULL,mtime_ns INTEGER NOT NULL,cloud_only INTEGER NOT NULL DEFAULT 0,processed INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(job_id,relative_path));
CREATE INDEX IF NOT EXISTS job_files_remaining ON job_files(job_id,processed,relative_path);
CREATE TABLE IF NOT EXISTS exports(
 id TEXT PRIMARY KEY,collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
 state TEXT NOT NULL,created_at TEXT NOT NULL,document_count INTEGER NOT NULL DEFAULT 0,
 chunk_count INTEGER NOT NULL DEFAULT 0,reason TEXT NOT NULL DEFAULT '',path TEXT NOT NULL,
 is_active INTEGER NOT NULL DEFAULT 0,manifest TEXT NOT NULL DEFAULT '{}');
CREATE UNIQUE INDEX IF NOT EXISTS one_active_export ON exports(collection_id) WHERE is_active=1;
"""


class Store:
    """接続を操作ごとに開く。大きな本文の一覧転送は避ける。"""
    def __init__(self, state_dir: Path):
        self.root = Path(state_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "catalog.sqlite3"
        with self.connect() as con:
            con.executescript(SCHEMA)
            con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS document_search USING fts5(document_id UNINDEXED, body, tokenize='trigram')")
            con.executescript("""
              CREATE TRIGGER IF NOT EXISTS search_insert AFTER INSERT ON documents BEGIN
                INSERT INTO document_search(document_id,body) VALUES(new.id,new.relative_path || char(10) || new.effective_text); END;
              CREATE TRIGGER IF NOT EXISTS search_delete AFTER DELETE ON documents BEGIN
                DELETE FROM document_search WHERE document_id=old.id; END;
              CREATE TRIGGER IF NOT EXISTS search_update AFTER UPDATE OF effective_text,relative_path ON documents BEGIN
                DELETE FROM document_search WHERE document_id=old.id;
                INSERT INTO document_search(document_id,body) VALUES(new.id,new.relative_path || char(10) || new.effective_text); END;
            """)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.db_path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def all(self, sql: str, args=()) -> list[dict]:
        with self.connect() as con:
            return [dict(r) for r in con.execute(sql, args)]

    def one(self, sql: str, args=()) -> dict | None:
        with self.connect() as con:
            r = con.execute(sql, args).fetchone()
            return dict(r) if r else None

    def execute(self, sql: str, args=()):
        with self.connect() as con:
            con.execute(sql, args)

    def add_library(self, name: str, path: str, kind="folder") -> dict:
        folder = Path(path).expanduser().resolve()
        if not folder.is_dir():
            raise ValueError("参照元フォルダが見つかりません")
        if folder == self.root or self.root in folder.parents:
            if kind != "upload":
                raise ValueError("アプリの保存領域は参照元にできません")
        found = self.one("SELECT * FROM libraries WHERE path=?", (str(folder),))
        if found:
            return found
        item = dict(id=identifier(), name=name.strip() or folder.name, path=str(folder), kind=kind, created_at=now())
        self.execute("INSERT INTO libraries VALUES(:id,:name,:path,:kind,:created_at)", item)
        return item

    def update_job(self, job_id: str, **fields):
        allowed = {"state", "stage", "processed", "total", "errors", "message", "scan_complete", "export_id", "owner_pid"}
        if not set(fields) <= allowed:
            raise ValueError("不正なジョブ更新")
        fields["updated_at"] = now()
        self.execute("UPDATE jobs SET " + ",".join(f"{k}=?" for k in fields) + " WHERE id=?", (*fields.values(), job_id))

    def document(self, document_id: str) -> dict | None:
        item = self.one("SELECT * FROM documents WHERE id=?", (document_id,))
        if item:
            for key in ("warnings", "units", "metadata"):
                item[key] = json.loads(item[key])
            item["warning_count"] = len(item["warnings"])
        return item

    def filters(self, library_id="", query="", folder="", document_ids=None):
        clauses = ["d.active=1"]
        args: list = []
        if library_id:
            clauses.append("d.library_id=?")
            args.append(library_id)
        if query:
            # 3文字以上は日本語も全文索引へ。1〜2文字だけは部分一致を使用する。
            if len(query) >= 3:
                clauses.append("d.id IN (SELECT document_id FROM document_search WHERE body MATCH ?)")
                args.append('"' + query.replace('"', '""') + '"')
            else:
                escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                clauses.append("d.id IN (SELECT document_id FROM document_search WHERE body LIKE ? ESCAPE '\\')")
                args.append("%" + escaped + "%")
        if folder:
            folder = folder.replace("\\", "/").strip("/")
            escaped = folder.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("(d.relative_path=? OR d.relative_path LIKE ? ESCAPE '\\')")
            args.extend([folder, escaped + "/%"])
        if document_ids:
            # json_each avoids SQLite bound-variable limits for 10k explicit selections.
            clauses.append("d.id IN (SELECT value FROM json_each(?))")
            args.append(json.dumps(document_ids))
        return " AND ".join(clauses), args

    def list_documents(self, library_id="", query="", status="", offset=0, limit=50):
        where, args = self.filters(library_id, query)
        if status == "deleted":
            where = where.replace("d.active=1", "d.active=0", 1)
        elif status == "conflict":
            where += " AND d.conflict=1"
        elif status == "attention":
            where += " AND (d.status NOT IN ('ok','empty') OR d.conflict=1)"
        elif status == "excluded":
            where += " AND d.excluded=1"
        elif status:
            where += " AND d.status=?"
            args.append(status)
        with self.connect() as con:
            total = con.execute("SELECT count(*) FROM documents d WHERE " + where, args).fetchone()[0]
            rows = con.execute("SELECT d.id,d.library_id,d.relative_path,d.status,d.excluded,d.conflict,d.updated_at,json_array_length(d.warnings) warning_count FROM documents d WHERE " + where + " ORDER BY d.relative_path LIMIT ? OFFSET ?", (*args, limit, offset))
            return dict(total=total, items=[dict(r) for r in rows])

    def upsert_extraction(self, library_id: str, relative_path: str, path: Path, size: int, mtime_ns: int, source_hash: str, extracted: dict):
        with self.connect() as con:
            old = con.execute("SELECT * FROM documents WHERE library_id=? AND relative_path=?", (library_id, relative_path)).fetchone()
            conflict = bool(old and old["edited_text"] is not None and old["edit_base_hash"] != source_hash)
            text = extracted.get("text", "")
            effective = old["edited_text"] if old and old["edited_text"] is not None and not conflict else text
            values = (str(path), size, mtime_ns, source_hash, extracted["status"], text, effective, int(conflict),
                      json.dumps(extracted.get("warnings", []), ensure_ascii=False), json.dumps(extracted.get("units", []), ensure_ascii=False),
                      json.dumps(extracted.get("metadata", {}), ensure_ascii=False), now())
            if old:
                con.execute("UPDATE documents SET source_path=?,size=?,mtime_ns=?,source_hash=?,status=?,original_text=?,effective_text=?,conflict=?,warnings=?,units=?,metadata=?,updated_at=?,active=1 WHERE id=?", (*values, old["id"]))
            else:
                con.execute("INSERT INTO documents(source_path,size,mtime_ns,source_hash,status,original_text,effective_text,conflict,warnings,units,metadata,updated_at,id,library_id,relative_path) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (*values, identifier(), library_id, relative_path))

    def edit_document(self, doc_id: str, data: dict):
        with self.connect() as con:
            doc = con.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
            if not doc:
                raise LookupError("資料が見つかりません")
            if "text" in data:
                text = data["text"]
                if text is not None and data.get("expected_hash") != doc["source_hash"]:
                    raise RuntimeError("原本が更新されています。読み直してから修正してください")
                con.execute("UPDATE documents SET edited_text=?,edit_base_hash=?,effective_text=?,conflict=0,updated_at=? WHERE id=?",
                            (text, doc["source_hash"] if text is not None else None, text if text is not None else doc["original_text"], now(), doc_id))
            if "excluded" in data:
                con.execute("UPDATE documents SET excluded=?,updated_at=? WHERE id=?", (int(data["excluded"]), now(), doc_id))
        return self.document(doc_id)

    def save_collection(self, data: dict, collection_id=None):
        if collection_id is not None:
            validate_identifier(collection_id)
        if not self.one("SELECT id FROM libraries WHERE id=?", (data["library_id"],)):
            raise ValueError("登録フォルダを選択してください")
        row = {"id": collection_id or identifier(), "name": data["name"], "library_id": data["library_id"], "query": data.get("query", ""),
               "folder": data.get("folder", ""), "document_ids": json.dumps(data.get("document_ids", [])), "purpose": data.get("purpose", "overview"),
               "instructions": data.get("instructions", ""), "updated_at": now()}
        self.execute("INSERT INTO collections VALUES(:id,:name,:library_id,:query,:folder,:document_ids,:purpose,:instructions,:updated_at) ON CONFLICT(id) DO UPDATE SET name=excluded.name,library_id=excluded.library_id,query=excluded.query,folder=excluded.folder,document_ids=excluded.document_ids,purpose=excluded.purpose,instructions=excluded.instructions,updated_at=excluded.updated_at", row)
        row["document_ids"] = json.loads(row["document_ids"])
        return row

    def collections(self):
        rows = self.all("SELECT * FROM collections ORDER BY updated_at DESC")
        for r in rows:
            r["document_ids"] = json.loads(r["document_ids"])
        return rows

    def counts(self):
        return self.one("SELECT count(*) total,coalesce(sum(status='ok'),0) ok,coalesce(sum(status NOT IN ('ok','empty') OR conflict=1),0) attention,coalesce(sum(excluded),0) excluded FROM documents WHERE active=1")
