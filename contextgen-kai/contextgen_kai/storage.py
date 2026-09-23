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


COLLECTION_DEFAULTS = dict(library_ids=[], selection_mode="dynamic", excluded_document_ids=[],
    target="builder", cleanup="none", include_hidden=True, include_notes=True, include_embedded=True,
    unit_overrides={}, unit_override_bases={}, audience="", answer_scope="", out_of_scope="", description="", evaluation_questions=[])


def validate_override_bases(data):
    bases = data.get("unit_override_bases", {})
    if not isinstance(bases, dict):
        raise ValueError("個別の整理設定の確認基準が不正です")
    for key, basis in bases.items():
        if not isinstance(key, str) or not isinstance(basis, dict) or set(basis) != {"source_hash", "text_hash"}:
            raise ValueError("個別の整理設定の確認基準が不正です")
        if (not isinstance(basis["source_hash"], str) or not re.fullmatch(r"(?:[0-9a-f]{64})?", basis["source_hash"])
                or not isinstance(basis["text_hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", basis["text_hash"])):
            raise ValueError("個別の整理設定の確認基準が不正です")

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
            # 0.2.x の本文・修正・セットをそのまま保持する追加型の移行。
            if "revision" not in {r[1] for r in con.execute("PRAGMA table_info(documents)")}:
                con.execute("ALTER TABLE documents ADD COLUMN revision INTEGER NOT NULL DEFAULT 0")
            con.executescript("""
              CREATE TABLE IF NOT EXISTS collection_options(
                collection_id TEXT PRIMARY KEY REFERENCES collections(id) ON DELETE CASCADE,
                settings TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS edit_history(
                id TEXT PRIMARY KEY,document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                revision INTEGER NOT NULL,edited_text TEXT,source_hash TEXT NOT NULL,created_at TEXT NOT NULL);
              CREATE INDEX IF NOT EXISTS history_document ON edit_history(document_id,revision);
              CREATE TABLE IF NOT EXISTS handoffs(
                id TEXT PRIMARY KEY,collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
                target TEXT NOT NULL,generation_id TEXT NOT NULL,recorded_at TEXT NOT NULL,files TEXT NOT NULL);
              CREATE INDEX IF NOT EXISTS handoff_target ON handoffs(collection_id,target,recorded_at);
            """)
            con.execute("UPDATE meta SET value='2' WHERE key='schema_version'")
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

    def list_documents(self, library_id="", query="", status="", offset=0, limit=50, extension=""):
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
        if extension:
            if not re.fullmatch(r"\.?[A-Za-z0-9]{1,12}", extension):
                raise ValueError("形式を確認してください")
            where += " AND lower(d.relative_path) LIKE ?"
            args.append("%." + extension.lower().lstrip("."))
        with self.connect() as con:
            total = con.execute("SELECT count(*) FROM documents d WHERE " + where, args).fetchone()[0]
            rows = con.execute("SELECT d.id,d.library_id,d.relative_path,d.status,d.excluded,d.conflict,d.updated_at,json_array_length(d.warnings) warning_count, substr(d.effective_text,max(1,instr(lower(d.effective_text),lower(?))-60),220) snippet FROM documents d WHERE " + where + " ORDER BY d.relative_path,d.id LIMIT ? OFFSET ?", (query, *args, limit, offset))
            return dict(total=total, items=[dict(r) for r in rows])

    def upsert_extraction(self, library_id: str, relative_path: str, path: Path, size: int, mtime_ns: int, source_hash: str, extracted: dict):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            old = con.execute("SELECT * FROM documents WHERE library_id=? AND relative_path=?", (library_id, relative_path)).fetchone()
            text = extracted.get("text", "")
            conflict = bool(old and old["edited_text"] is not None and (old["edit_base_hash"] != source_hash or (old["original_text"] and old["original_text"] != text)))
            effective = old["edited_text"] if old and old["edited_text"] is not None and not conflict else text
            values = (str(path), size, mtime_ns, source_hash, extracted["status"], text, effective, int(conflict),
                      json.dumps(extracted.get("warnings", []), ensure_ascii=False), json.dumps(extracted.get("units", []), ensure_ascii=False),
                      json.dumps(extracted.get("metadata", {}), ensure_ascii=False), now())
            if old:
                con.execute("UPDATE documents SET source_path=?,size=?,mtime_ns=?,source_hash=?,status=?,original_text=?,effective_text=?,conflict=?,warnings=?,units=?,metadata=?,updated_at=?,active=1,revision=revision+1 WHERE id=?", (*values, old["id"]))
            else:
                con.execute("INSERT INTO documents(source_path,size,mtime_ns,source_hash,status,original_text,effective_text,conflict,warnings,units,metadata,updated_at,id,library_id,relative_path) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (*values, identifier(), library_id, relative_path))

    def edit_document(self, doc_id: str, data: dict):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            doc = con.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
            if not doc:
                raise LookupError("資料が見つかりません")
            if "expected_revision" in data and data["expected_revision"] != doc["revision"]:
                raise RuntimeError("別の画面または再読み取りで内容が更新されました。入力を控えて最新の内容と比較してください")
            if "text" in data:
                text = data["text"]
                if (text is not None or "expected_revision" in data) and data.get("expected_hash") != doc["source_hash"]:
                    raise RuntimeError("原本が更新されています。読み直してから修正してください")
                con.execute("INSERT INTO edit_history VALUES(?,?,?,?,?,?)", (identifier(), doc_id, doc["revision"], doc["edited_text"], doc["source_hash"], now()))
                con.execute("UPDATE documents SET edited_text=?,edit_base_hash=?,effective_text=?,conflict=0,updated_at=? WHERE id=?",
                            (text, doc["source_hash"] if text is not None else None, text if text is not None else doc["original_text"], now(), doc_id))
            if "excluded" in data:
                con.execute("UPDATE documents SET excluded=?,updated_at=? WHERE id=?", (int(data["excluded"]), now(), doc_id))
            con.execute("UPDATE documents SET revision=revision+1 WHERE id=?", (doc_id,))
        return self.document(doc_id)

    def save_collection(self, data: dict, collection_id=None):
        if collection_id is not None:
            validate_identifier(collection_id)
        data = self.validate_collection(data)
        row = {"id": collection_id or identifier(), "name": data["name"], "library_id": data["library_id"], "query": data.get("query", ""),
               "folder": data.get("folder", ""), "document_ids": json.dumps(data.get("document_ids", [])), "purpose": data.get("purpose", "overview"),
               "instructions": data.get("instructions", ""), "updated_at": now()}
        with self.connect() as con:
            con.execute("INSERT INTO collections VALUES(:id,:name,:library_id,:query,:folder,:document_ids,:purpose,:instructions,:updated_at) ON CONFLICT(id) DO UPDATE SET name=excluded.name,library_id=excluded.library_id,query=excluded.query,folder=excluded.folder,document_ids=excluded.document_ids,purpose=excluded.purpose,instructions=excluded.instructions,updated_at=excluded.updated_at", row)
            con.execute("INSERT INTO collection_options VALUES(?,?) ON CONFLICT(collection_id) DO UPDATE SET settings=excluded.settings", (row["id"], json.dumps({key: data[key] for key in COLLECTION_DEFAULTS}, ensure_ascii=False)))
        return self.collection(row["id"])

    def validate_collection(self, data):
        if "selection_mode" not in data and data.get("document_ids"):
            data = {**data, "selection_mode": "fixed"}
        data = {**COLLECTION_DEFAULTS, **data}
        libs = list(dict.fromkeys(data.get("library_ids") or [data.get("library_id")]))
        if not libs or any(not self.one("SELECT id FROM libraries WHERE id=?", (lib,)) for lib in libs):
            raise ValueError("登録フォルダを選択してください")
        data["library_ids"], data["library_id"] = libs, libs[0]
        if data["selection_mode"] == "fixed" and not data.get("document_ids"):
            raise ValueError("固定選択の資料を1件以上選択してください")
        if data["target"] not in ("builder", "studio") or data["cleanup"] not in ("none", "standard"):
            raise ValueError("登録先と整理方法を選択してください")
        if data["selection_mode"] not in ("fixed", "dynamic") or data.get("purpose", "overview") not in ("overview", "compare", "questions", "procedure", "reference"):
            raise ValueError("資料の選択方法と用途を確認してください")
        for key in ("document_ids", "excluded_document_ids"):
            ids = data.get(key, [])
            found = self.one("SELECT count(*) n FROM documents WHERE library_id IN (SELECT value FROM json_each(?)) AND id IN (SELECT value FROM json_each(?))", (json.dumps(libs), json.dumps(ids)))["n"]
            if found != len(set(ids)):
                raise ValueError("選択した登録フォルダ内の資料を指定してください")
        if any(value not in ("include", "exclude") for value in data["unit_overrides"].values()):
            raise ValueError("個別の整理設定が不正です")
        validate_override_bases(data)
        return data

    def collection(self, collection_id):
        row = self.one("SELECT * FROM collections WHERE id=?", (collection_id,))
        if not row:
            return None
        row["document_ids"] = json.loads(row["document_ids"])
        options = self.one("SELECT settings FROM collection_options WHERE collection_id=?", (collection_id,))
        return {**COLLECTION_DEFAULTS, **row, "library_ids": [row["library_id"]], "selection_mode": "fixed" if row["document_ids"] else "dynamic", **(json.loads(options["settings"]) if options else {})}

    def collection_filters(self, collection, *, include_excluded=False):
        fixed = collection.get("selection_mode") == "fixed"
        where, args = self.filters("", "" if fixed else collection.get("query", ""), "" if fixed else collection.get("folder", ""), (collection.get("document_ids") or []) if fixed else [])
        if fixed:
            # 利用者が固定選択した資料は、原本削除後も未収録理由を示すため候補に残す。
            where = where.replace("d.active=1", "1=1", 1)
        where += " AND d.library_id IN (SELECT value FROM json_each(?))"
        args.append(json.dumps(collection.get("library_ids") or [collection["library_id"]]))
        if collection.get("selection_mode") == "fixed" and not collection.get("document_ids"):
            where += " AND 0"
        if not include_excluded:
            where += " AND d.id NOT IN (SELECT value FROM json_each(?))"
            args.append(json.dumps(collection.get("excluded_document_ids", [])))
        return where, args

    def handoff(self, collection_id, target):
        row = self.one("SELECT * FROM handoffs WHERE collection_id=? AND target=? ORDER BY recorded_at DESC,rowid DESC LIMIT 1", (collection_id, target))
        if row:
            row["files"] = json.loads(row["files"])
        return row

    def collections(self):
        return [self.collection(r["id"]) for r in self.all("SELECT id FROM collections ORDER BY updated_at DESC")]

    def counts(self):
        return self.one("SELECT count(*) total,coalesce(sum(status='ok'),0) ok,coalesce(sum(status NOT IN ('ok','empty') OR conflict=1),0) attention,coalesce(sum(excluded),0) excluded FROM documents WHERE active=1")
