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


MANUAL_ASSETS = {
    "01_home.png", "02_register.png", "03_read_complete.png", "04_documents.png", "05_edit.png",
    "06_collection.png", "07_exports.png", "08_prompt.png", "09_schedule.png", "10_settings.png",
    "11_conflict.png", "12_held.png", "13_upload.png", "manual.js",
    "14_multifolder.png", "15_cleanup.png", "16_preflight.png", "17_studio.png", "18_handoff.png",
}


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
    expected_revision: int = Field(default=0, ge=0)


class CollectionInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    library_id: str = ""
    library_ids: list[str] = Field(default_factory=list, max_length=1000)
    selection_mode: str = "dynamic"
    excluded_document_ids: list[str] = Field(default_factory=list, max_length=100_000)
    target: str = "builder"
    cleanup: str = "standard"
    include_hidden: bool = True
    include_notes: bool = True
    include_embedded: bool = True
    unit_overrides: dict[str, str] = Field(default_factory=dict, max_length=100_000)
    unit_override_bases: dict[str, dict[str, str]] = Field(default_factory=dict, max_length=100_000)
    audience: str = Field(default="", max_length=2000)
    answer_scope: str = Field(default="", max_length=10000)
    out_of_scope: str = Field(default="", max_length=10000)
    description: str = Field(default="", max_length=10000)
    evaluation_questions: list[dict[str, str]] = Field(default_factory=list, max_length=100)
    query: str = Field(default="", max_length=500)
    folder: str = Field(default="", max_length=4096)
    document_ids: list[str] = Field(default_factory=list, max_length=100_000)
    purpose: str = "overview"
    instructions: str = Field(default="", max_length=20000)


class ExportInput(BaseModel):
    collection_id: str
    force: bool = False
    refresh_sources: bool = True


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
        if store.one("SELECT id FROM jobs WHERE state IN ('queued','scanning','extracting','exporting')"):
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
        if store.one("SELECT id FROM jobs WHERE state IN ('queued','scanning','extracting','exporting')"):
            raise ValueError("処理を停止してから登録を解除してください")
        if any(s["library_id"] == library_id for s in scheduler.list()):
            raise ValueError("このフォルダの実行予約を削除してから登録を解除してください")
        if any(library_id in c["library_ids"] and len(c["library_ids"]) > 1 for c in store.collections()):
            raise ValueError("案件用セットの登録元からこのフォルダを外してから解除してください")
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
            coll = store.collection(data.collection_id)
            if not coll or coll["library_ids"] != [data.library_id]:
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
    def documents(library_id="", q="", status="", offset: int = 0, limit: int = 50, extension=""):
        if not (0 <= offset and 1 <= limit <= 200) or len(q) > 500:
            raise ValueError("検索条件を確認してください")
        return store.list_documents(library_id, q, status, offset, limit, extension)

    @app.get("/api/documents/{doc_id}")
    def document(doc_id: str):
        result = store.document(doc_id)
        if not result:
            raise HTTPException(404, "資料が見つかりません")
        return result

    @app.put("/api/documents/{doc_id}")
    def edit_document(doc_id: str, data: EditInput):
        try:
            return store.edit_document(doc_id, {**data.model_dump(exclude_unset=True), "expected_revision": data.expected_revision})
        except RuntimeError as exc:
            raise HTTPException(409, str(exc))
        except LookupError as exc:
            raise HTTPException(404, str(exc))

    @app.get("/api/documents/{doc_id}/history")
    def edit_history(doc_id: str):
        document(doc_id)
        return store.all("SELECT id,revision,edited_text,source_hash,created_at FROM edit_history WHERE document_id=? ORDER BY rowid DESC LIMIT 100", (doc_id,))

    @app.post("/api/documents/{doc_id}/reextract")
    def reextract(doc_id: str):
        doc = document(doc_id)
        return jobs.start(doc["library_id"], document_id=doc_id, force_extract=True)

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
        parsed = data.model_dump()
        if "selection_mode" not in data.model_fields_set and data.document_ids:
            parsed["selection_mode"] = "fixed"
        for question in data.evaluation_questions:
            if not question.get("question", "").strip() or len(question["question"]) > 1000 or any(len(v) > 20000 for v in question.values()):
                raise ValueError("評価質問は1〜1000文字で入力してください")
        return store.validate_collection(parsed)

    @app.post("/api/collections")
    def add_collection(data: CollectionInput):
        return store.save_collection(validate_collection(data))

    @app.put("/api/collections/{collection_id}")
    def update_collection(collection_id: str, data: CollectionInput):
        existing = store.collection(collection_id)
        if not existing:
            raise HTTPException(404, "資料セットが見つかりません")
        incoming = data.model_dump(exclude_unset=True)
        if "library_id" in incoming and "library_ids" not in incoming and incoming["library_id"] != existing["library_id"]:
            incoming["library_ids"] = [incoming["library_id"]]
        if "document_ids" in incoming and "selection_mode" not in incoming:
            incoming["selection_mode"] = "fixed" if incoming["document_ids"] else "dynamic"
        parsed = validate_collection(CollectionInput.model_validate({**existing, **incoming}))
        if store.one("SELECT id FROM jobs WHERE json_extract(payload,'$.collection_id')=? AND state IN ('queued','scanning','extracting','exporting')", (collection_id,)):
            raise ValueError("セットの処理が終わってから設定を変更してください")
        if any(s.get("collection_id") == collection_id for s in scheduler.list()) and len(parsed["library_ids"]) != 1:
            raise ValueError("複数フォルダに変更する前に、このセットの実行予約を削除してください")
        return store.save_collection(parsed, collection_id)

    @app.post("/api/collections/preview")
    def collection_preview(data: CollectionInput, offset: int = 0, limit: int = 100):
        from .review import preview_collection
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError("表示範囲を確認してください")
        return preview_collection(store, validate_collection(data), offset, limit)

    @app.post("/api/collections/{collection_id}/preview-document")
    def collection_preview_document(collection_id: str, data: dict):
        from .curation import prepare_document
        coll = store.collection(collection_id)
        if not coll:
            raise HTTPException(404, "資料セットが見つかりません")
        if "options" in data:
            coll = validate_collection(CollectionInput.model_validate(data["options"]))
        doc = document(data.get("document_id", ""))
        if doc["library_id"] not in coll["library_ids"]:
            raise ValueError("セットの登録元に含まれない資料です")
        result = prepare_document(doc, coll)
        return result

    @app.get("/api/collections/{collection_id}/preflight")
    def preflight(collection_id: str):
        from .review import preflight_collection
        coll = store.collection(collection_id)
        if not coll:
            raise HTTPException(404, "資料セットが見つかりません")
        return preflight_collection(store, coll)

    @app.get("/api/exports")
    def exports():
        rows = store.all("SELECT * FROM exports ORDER BY created_at DESC,rowid DESC LIMIT 100")
        for row in rows:
            manifest = json.loads(row.pop("manifest"))
            row["file_count"] = len(manifest.get("knowledge_files", {name: digest for name, digest in manifest.get("files", {}).items() if name.startswith("M365/")}))
            row["target"] = manifest.get("target", "builder")
        return rows

    @app.post("/api/exports")
    def export(data: ExportInput):
        coll = store.collection(data.collection_id)
        if not coll:
            raise ValueError("資料セットを選択してください")
        return jobs.start(coll["library_id"], kind="export", collection_id=data.collection_id, force=data.force, refresh_sources=data.refresh_sources)

    @app.post("/api/exports/{export_id}/activate")
    def activate(export_id: str):
        lock = ProcessLock(store.root)
        if not lock.acquire():
            raise ValueError("処理が終わってから確定してください")
        try:
            return activate_export(store, export_id, verify_sources=True)
        finally:
            lock.release()

    def get_export(export_id):
        item = store.one("SELECT * FROM exports WHERE id=?", (export_id,))
        if not item:
            raise HTTPException(404, "出力が見つかりません")
        return item

    @app.get("/api/exports/{export_id}/handoff")
    def handoff_info(export_id: str):
        from .review import handoff_status
        return handoff_status(store, get_export(export_id))

    @app.post("/api/exports/{export_id}/handoff")
    def record_handoff(export_id: str, data: dict):
        from .review import record_handoff as record
        lock = ProcessLock(store.root)
        if not lock.acquire():
            raise ValueError("処理が終わってから登録済み版を記録してください")
        try:
            return record(store, get_export(export_id), data)
        finally:
            lock.release()

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
        if data.get("collection_id"):
            coll = store.collection(data["collection_id"])
            if not coll or coll["library_ids"] != [data["library_id"]]:
                raise ValueError("定期更新は同じ登録フォルダだけの資料セットを選択してください")
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
        from .backups import make_backup
        return Response(make_backup(store, scheduler), media_type="application/json", headers={"Content-Disposition": 'attachment; filename="contextgen-kai-backup.json"'})

    @app.post("/api/restore")
    async def restore(file: UploadFile = File(...)):
        from .backups import MAX_BACKUP_BYTES, restore_backup
        raw = await file.read(MAX_BACKUP_BYTES + 1)
        if len(raw) > MAX_BACKUP_BYTES:
            raise ValueError("バックアップが512MBを超えています")
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise ValueError("JSONバックアップを読み込めません")
        lock = ProcessLock(store.root)
        if not lock.acquire():
            raise ValueError("実行中の処理が終わってから復元してください")
        try:
            restore_backup(store, scheduler, data, CollectionInput)
            return {"ok": True, "message": "復元しました。原本の場所を確認して読み取りを実行してください。予約は停止しています"}
        finally:
            lock.release()

    @app.post("/api/shutdown")
    def shutdown():
        if shutdown_callback:
            threading.Timer(0.3, shutdown_callback).start()
        return {"ok": True}

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # 配布物は利用者向け4点だけを表に置き、画像は_internalへまとめる。
    # ディレクトリごとの公開はせず、文書・画像の許可リストに含まれる実体だけを返す。
    frozen = getattr(sys, "frozen", False)
    document_root = Path(sys.executable).parent if frozen else Path(__file__).resolve().parents[1]
    image_root = (Path(getattr(sys, "_MEIPASS", document_root / "_internal")) / "manual/images"
                  if frozen else document_root / "images")
    manual_files = {"contextgen改_操作マニュアル.html", "最初にお読みください.txt"} if frozen else {
        "contextgen改_操作マニュアル.html", "README.md", "仕様書兼要件定義書.md", "アプリ概要とバージョン履歴.md", "アプリ基本設計基準書.md"}

    def bundled_file(root, filename, allowed):
        path = (root / filename).resolve()
        if filename not in allowed or path.parent != root.resolve() or not path.is_file():
            raise HTTPException(404, "文書・画像が見つかりません")
        return FileResponse(path)

    @app.get("/manual/")
    def manual():
        return bundled_file(document_root, "contextgen改_操作マニュアル.html", manual_files)

    @app.get("/manual/{filename}")
    def design_document(filename: str):
        return bundled_file(document_root, filename, manual_files)

    @app.get("/manual/images/{filename}")
    def source_manual_image(filename: str):
        if frozen:
            raise HTTPException(404, "画像が見つかりません")
        return bundled_file(image_root, filename, MANUAL_ASSETS)

    @app.get("/manual/_internal/manual/images/{filename}")
    def packaged_manual_image(filename: str):
        if not frozen:
            raise HTTPException(404, "画像が見つかりません")
        return bundled_file(image_root, filename, MANUAL_ASSETS)

    @app.get("/")
    def index():
        return FileResponse(static_dir / "index.html")

    return app
