"""localhost専用API。原本アクセスは登録済み資料に限定する。"""
from __future__ import annotations

import json
import io
import os
import secrets
import shutil
import subprocess
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .exporting import activate_export, zip_export
from .jobs import ACTIVE, JobManager, ProcessLock
from .storage import Store, default_state_dir, identifier, now, validate_identifier
from .scheduling import Scheduler


class LibraryInput(BaseModel):
    name: str = Field(default="", max_length=160)
    path: str = Field(min_length=1, max_length=4096)


class JobInput(BaseModel):
    library_id: str
    collection_id: str | None = None
    export_after: bool = False


class EditInput(BaseModel):
    text: str | None = Field(default=None, max_length=20_000_000)
    expected_hash: str | None = None
    excluded: bool | None = None


class CollectionInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    library_id: str
    query: str = Field(default="", max_length=500)
    folder: str = Field(default="", max_length=4096)
    document_ids: list[str] = Field(default_factory=list, max_length=100_000)
    purpose: str = "overview"
    instructions: str = Field(default="", max_length=20000)


class ExportInput(BaseModel):
    collection_id: str
    force: bool = False


def runtime_command(*args):
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, "-m", "contextgen_kai", *args]


def create_app(state_dir: Path | None = None, *, use_process=True, enable_scheduler=True, shutdown_callback=None):
    store = Store(state_dir or default_state_dir())
    jobs = JobManager(store, use_process=use_process)
    token = secrets.token_urlsafe(32)

    def scheduled_run(schedule):
        return jobs.start(schedule["library_id"], collection_id=schedule.get("collection_id"), export_after=bool(schedule.get("collection_id")), schedule_id=schedule["id"])["id"]

    scheduler = Scheduler(store.root, scheduled_run)
    jobs.complete_callback = scheduler.complete

    @asynccontextmanager
    async def lifespan(app):
        if enable_scheduler:
            scheduler.start()
        yield
        scheduler.stop()
        jobs.close()

    app = FastAPI(title="contextgen 改", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.store = store
    app.state.jobs = jobs
    app.state.scheduler = scheduler
    app.state.token = token

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in ("127.0.0.1", "localhost", "testserver"):
            return JSONResponse({"detail": "このアプリはlocalhost専用です"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "別のページからの操作は受け付けません"}, status_code=403)
        if request.url.path.startswith("/api/") and request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "別のページからの操作は受け付けません"}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS") and not secrets.compare_digest(request.headers.get("x-contextgen-token", ""), token):
            return JSONResponse({"detail": "画面を再読み込みしてから操作してください"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; frame-src 'self' blob:; object-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'"
        return response

    @app.exception_handler(ValueError)
    async def invalid(_request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__, "application": "contextgen-kai"}

    @app.get("/api/version")
    def version():
        return {"version": __version__, "status": "開発版・利用予定PCでの受入前"}

    @app.get("/api/status")
    def status():
        return dict(version=__version__, token=token, libraries=store.all("SELECT * FROM libraries ORDER BY created_at"), collections=store.collections(), counts=store.counts(), jobs=jobs.list(), schedules=scheduler.list())

    @app.get("/api/libraries")
    def libraries():
        return store.all("SELECT * FROM libraries ORDER BY created_at")

    @app.post("/api/libraries")
    def add_library(data: LibraryInput):
        return store.add_library(data.name, data.path)

    @app.put("/api/libraries/{library_id}")
    def change_library(library_id: str, data: LibraryInput):
        if store.one("SELECT id FROM jobs WHERE library_id=? AND state IN ('queued','scanning','extracting','exporting')", (library_id,)):
            raise ValueError("処理を停止してから登録を変更してください")
        target = Path(data.path).expanduser().resolve()
        if not target.is_dir() or target == store.root or store.root in target.parents:
            raise ValueError("有効な資料フォルダを選択してください")
        collision = store.one("SELECT id FROM libraries WHERE path=? AND id<>?", (str(target), library_id))
        if collision:
            raise ValueError("このフォルダはすでに登録されています")
        with store.connect() as con:
            con.execute("UPDATE libraries SET name=?,path=?,kind='folder' WHERE id=?", (data.name or target.name, str(target), library_id))
            # 再抽出時に参照パスを更新する。修正は原本ハッシュ照合で維持する。
            con.execute("UPDATE documents SET status='pending' WHERE library_id=?", (library_id,))
        return store.one("SELECT * FROM libraries WHERE id=?", (library_id,))

    @app.delete("/api/libraries/{library_id}")
    def remove_library(library_id: str):
        if store.one("SELECT id FROM jobs WHERE library_id=? AND state IN ('queued','scanning','extracting','exporting')", (library_id,)):
            raise ValueError("処理を停止してから登録を解除してください")
        if any(s["library_id"] == library_id for s in scheduler.list()):
            raise ValueError("このフォルダの実行予約を削除してから登録を解除してください")
        store.execute("DELETE FROM libraries WHERE id=?", (library_id,))
        return {"ok": True}

    @app.post("/api/pick-folder")
    def pick_folder():
        output = store.root / ("picker-" + identifier() + ".json")
        try:
            result = subprocess.run(runtime_command("--picker-file", str(output)), timeout=300, capture_output=True)
            if result.returncode or not output.exists():
                raise ValueError("フォルダ選択画面を開けませんでした。パスを直接入力してください")
            return json.loads(output.read_text(encoding="utf-8"))
        except subprocess.TimeoutExpired:
            raise ValueError("フォルダ選択を終了しました。もう一度選択してください")
        finally:
            output.unlink(missing_ok=True)

    @app.post("/api/uploads")
    async def uploads(files: list[UploadFile] = File(...), name: str = Form("取り込んだ資料")):
        from .extractors import SUPPORTED_EXTENSIONS
        if not files or len(files) > 100:
            raise ValueError("単発投入は1回100ファイルまでです。大量資料はフォルダ登録を利用してください")
        directory = store.root / "imports" / identifier()
        directory.mkdir(parents=True)
        try:
            for file in files:
                filename = (file.filename or "資料").replace("\\", "/").split("/")[-1]
                if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
                    raise ValueError(f"この形式には対応していません: {filename}")
                if any(c in filename for c in '<>:"|?*') or filename in (".", ".."):
                    raise ValueError("ファイル名に利用できない文字が含まれます")
                target = directory / filename
                if target.exists():
                    target = target.with_name(f"{target.stem}-{identifier()[:6]}{target.suffix}")
                size = 0
                with target.open("wb") as out:
                    while block := await file.read(1024 * 1024):
                        size += len(block)
                        if size > 250 * 1024 * 1024:
                            raise ValueError("単発投入の1ファイル上限は250MBです")
                        out.write(block)
            return store.add_library(name, str(directory), kind="upload")
        except BaseException:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    @app.get("/api/jobs")
    def list_jobs():
        return jobs.list()

    @app.post("/api/jobs")
    def start_job(data: JobInput):
        if data.export_after:
            coll = store.one("SELECT * FROM collections WHERE id=? AND library_id=?", (data.collection_id, data.library_id))
            if not coll:
                raise ValueError("同じ登録フォルダの資料セットを選択してください")
        return jobs.start(**data.model_dump())

    @app.post("/api/jobs/{job_id}/stop")
    def stop_job(job_id: str):
        jobs.stop(job_id)
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/resume")
    def resume_job(job_id: str):
        return jobs.resume(job_id)

    @app.get("/api/documents")
    def documents(library_id="", q="", status="", offset: int = 0, limit: int = 50):
        if not (0 <= offset and 1 <= limit <= 200) or len(q) > 500:
            raise ValueError("検索条件を確認してください")
        return store.list_documents(library_id, q, status, offset, limit)

    @app.get("/api/documents/{doc_id}")
    def document(doc_id: str):
        result = store.document(doc_id)
        if not result:
            raise HTTPException(404, "資料が見つかりません")
        return result

    @app.put("/api/documents/{doc_id}")
    def edit_document(doc_id: str, data: EditInput):
        try:
            return store.edit_document(doc_id, data.model_dump(exclude_unset=True))
        except RuntimeError as exc:
            raise HTTPException(409, str(exc))
        except LookupError as exc:
            raise HTTPException(404, str(exc))

    def source_path(doc_id):
        doc = document(doc_id)
        library = store.one("SELECT * FROM libraries WHERE id=?", (doc["library_id"],))
        root = Path(library["path"]).resolve()
        path = Path(doc["source_path"]).resolve()
        if root not in path.parents or not path.is_file():
            raise ValueError("原本が移動・削除されています。再読み取りしてください")
        return path

    def open_path(path):
        if os.name == "nt":
            os.startfile(str(path))
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @app.post("/api/documents/{doc_id}/open")
    def open_document(doc_id: str):
        open_path(source_path(doc_id))
        return {"ok": True}

    @app.get("/api/documents/{doc_id}/preview")
    def preview(doc_id: str):
        path = source_path(doc_id)
        if path.suffix.lower() in (".tif", ".tiff", ".bmp", ".gif"):
            from PIL import Image
            with Image.open(path) as source:
                source.seek(0)
                source.thumbnail((2400, 2400))
                buffer = io.BytesIO()
                source.convert("RGB").save(buffer, "PNG")
            return Response(buffer.getvalue(), media_type="image/png")
        types = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
        if path.suffix.lower() not in types:
            raise ValueError("この資料は原本を開いて確認してください")
        return FileResponse(path, media_type=types[path.suffix.lower()])

    @app.get("/api/collections")
    def collections():
        return store.collections()

    def validate_collection(data):
        if data.purpose not in ("overview", "compare", "questions"):
            raise ValueError("利用目的を選択してください")
        if data.document_ids:
            count = store.one("SELECT count(*) n FROM documents WHERE library_id=? AND id IN (SELECT value FROM json_each(?))", (data.library_id, json.dumps(data.document_ids)))["n"]
            if count != len(set(data.document_ids)):
                raise ValueError("同じ登録フォルダの資料を選択してください")

    @app.post("/api/collections")
    def add_collection(data: CollectionInput):
        validate_collection(data)
        return store.save_collection(data.model_dump())

    @app.put("/api/collections/{collection_id}")
    def update_collection(collection_id: str, data: CollectionInput):
        validate_collection(data)
        return store.save_collection(data.model_dump(), collection_id)

    @app.get("/api/exports")
    def exports():
        return store.all("SELECT id,collection_id,state,created_at,document_count,chunk_count,reason,is_active FROM exports ORDER BY created_at DESC,rowid DESC LIMIT 100")

    @app.post("/api/exports")
    def export(data: ExportInput):
        coll = store.one("SELECT * FROM collections WHERE id=?", (data.collection_id,))
        if not coll:
            raise ValueError("資料セットを選択してください")
        return jobs.start(coll["library_id"], kind="export", collection_id=data.collection_id, force=data.force)

    @app.post("/api/exports/{export_id}/activate")
    def activate(export_id: str):
        lock = ProcessLock(store.root)
        if not lock.acquire():
            raise ValueError("処理が終わってから確定してください")
        try:
            return activate_export(store, export_id)
        finally:
            lock.release()

    def get_export(export_id):
        item = store.one("SELECT * FROM exports WHERE id=?", (export_id,))
        if not item:
            raise HTTPException(404, "出力が見つかりません")
        return item

    @app.get("/api/exports/{export_id}/download")
    def download(export_id: str):
        return FileResponse(zip_export(store, export_id), filename=f"contextgen-kai-{export_id[:8]}.zip", media_type="application/zip")

    @app.get("/api/exports/{export_id}/prompt")
    def prompt(export_id: str):
        return {"text": (Path(get_export(export_id)["path"]) / "prompt.txt").read_text(encoding="utf-8")}

    @app.post("/api/exports/{export_id}/open")
    def open_export(export_id: str):
        open_path(Path(get_export(export_id)["path"]))
        return {"ok": True}

    @app.get("/api/schedules")
    def schedules():
        return scheduler.list()

    def save_schedule(data):
        if not store.one("SELECT id FROM libraries WHERE id=?", (data.get("library_id"),)):
            raise ValueError("登録フォルダを選択してください")
        if data.get("collection_id") and not store.one("SELECT id FROM collections WHERE id=? AND library_id=?", (data["collection_id"], data["library_id"])):
            raise ValueError("同じ登録フォルダの資料セットを選択してください")
        try:
            return scheduler.save(data)
        except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
            raise ValueError(str(exc)) from exc

    @app.post("/api/schedules")
    def create_schedule(data: dict):
        return save_schedule(data)

    @app.put("/api/schedules/{schedule_id}")
    def update_schedule(schedule_id: str, data: dict):
        return save_schedule({**data, "id": schedule_id})

    @app.delete("/api/schedules/{schedule_id}")
    def delete_schedule(schedule_id: str):
        scheduler.delete(schedule_id)
        return {"ok": True}

    @app.post("/api/schedules/{schedule_id}/run")
    def run_schedule(schedule_id: str):
        return {"job_id": scheduler.run_now(schedule_id)}

    @app.get("/api/backup")
    def backup():
        backup_data = dict(schema_version=1, application="contextgen-kai", created_at=now(), libraries=libraries(), collections=collections(), schedules=schedules(), documents=store.all("SELECT id,library_id,relative_path,source_hash,edited_text,edit_base_hash,excluded FROM documents"), note="原本資料・抽出キャッシュ・出力世代は含みません。原本は別に保管してください。復元後は読み取りを実行してください。")
        return Response(json.dumps(backup_data, ensure_ascii=False), media_type="application/json", headers={"Content-Disposition": 'attachment; filename="contextgen-kai-backup.json"'})

    @app.post("/api/restore")
    async def restore(file: UploadFile = File(...)):
        data = await file.read(128 * 1024 * 1024 + 1)
        if len(data) > 128 * 1024 * 1024:
            raise ValueError("バックアップが128MBを超えています")
        try:
            data = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            raise ValueError("JSONバックアップを読み込めません")
        if data.get("application") != "contextgen-kai" or data.get("schema_version") != 1:
            raise ValueError("対応していないバックアップ形式です")
        if libraries() or schedules():
            raise ValueError("復元は登録フォルダのない空の保存領域で実行してください")
        lock = ProcessLock(store.root)
        if not lock.acquire():
            raise ValueError("実行中の処理が終わってから復元してください")
        try:
            with store.connect() as con:
                roots = {}
                for lib in data.get("libraries", []):
                    validate_identifier(lib["id"])
                    path = Path(lib["path"]).expanduser().resolve()
                    roots[lib["id"]] = path
                    con.execute("INSERT INTO libraries VALUES (?,?,?,?,?)", (lib["id"], lib["name"], str(path), lib.get("kind", "folder"), now()))
                for doc in data.get("documents", []):
                    validate_identifier(doc["id"])
                    root = roots[doc["library_id"]]
                    path = (root / doc["relative_path"]).resolve()
                    if root not in path.parents:
                        raise ValueError("バックアップの資料パスが不正です")
                    con.execute("INSERT INTO documents(id,library_id,relative_path,source_path,size,mtime_ns,source_hash,edited_text,edit_base_hash,effective_text,excluded,status,updated_at) VALUES(?,?,?,?,0,0,?,?,?,?,?,'pending',?)", (doc["id"], doc["library_id"], doc["relative_path"], str(path), doc["source_hash"], doc.get("edited_text"), doc.get("edit_base_hash"), doc.get("edited_text") or "", int(doc.get("excluded", False)), now()))
                for collection in data.get("collections", []):
                    validate_identifier(collection["id"])
                    parsed = CollectionInput.model_validate(collection).model_dump()
                    con.execute("INSERT INTO collections VALUES(?,?,?,?,?,?,?,?,?)", (collection["id"], parsed["name"], parsed["library_id"], parsed["query"], parsed["folder"], json.dumps(parsed["document_ids"]), parsed["purpose"], parsed["instructions"], now()))
                scheduler.restore(data.get("schedules", []))
            return {"ok": True, "message": "復元しました。原本の場所を確認して読み取りを実行してください。予約は停止しています"}
        except (KeyError, TypeError) as exc:
            raise ValueError("バックアップの構造が不正です") from exc
        finally:
            lock.release()

    @app.post("/api/shutdown")
    def shutdown():
        if shutdown_callback:
            threading.Timer(0.3, shutdown_callback).start()
        return {"ok": True}

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Git版と配布EXEのどちらでも、利用者に見えるアプリ直下を文書の正本にする。
    document_root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    manual_files = {"contextgen改_操作マニュアル.html", "README.md", "仕様書兼要件定義書.md", "アプリ概要とバージョン履歴.md", "アプリ基本設計基準書.md"}

    @app.get("/manual/")
    def manual():
        path = document_root / "contextgen改_操作マニュアル.html"
        if not path.is_file():
            raise HTTPException(404, "マニュアルが見つかりません。アプリ一式を更新してください")
        return FileResponse(path)

    @app.get("/manual/{filename}")
    def design_document(filename: str):
        if filename not in manual_files or not (document_root / filename).is_file():
            raise HTTPException(404, "文書が見つかりません")
        return FileResponse(document_root / filename)

    app.mount("/manual/images", StaticFiles(directory=document_root / "images", check_dir=False), name="manual-images")

    @app.get("/")
    def index():
        return FileResponse(static_dir / "index.html")

    return app
