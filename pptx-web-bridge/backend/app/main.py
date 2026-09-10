"""ローカル API（FastAPI）。ブラウザ UI から呼ばれる。

- 外部へファイルを送信しない。すべてローカルで処理する。
- 失敗は HTTP 4xx/5xx + 日本語メッセージで返し、ログに工程名を残す。
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import logging

from . import pipeline, storage, template_kit
from .report import build_report
from .config import get_config, resource_path
from .logging_setup import get_logger
from .model import new_presentation
from .rasterize import is_available as raster_available
from .validate import validate_and_repair
from .web_renderer import render_html

log = get_logger("api")
cfg = get_config()
app = FastAPI(title="PPTX ⇄ Web図解 変換アプリ", version="0.1.0")
FRONTEND_DIR = resource_path("frontend")
_MAX_UPLOAD = int(cfg.get("limits.max_upload_mb", 50)) * 1024 * 1024


class PresentationBody(BaseModel):
    presentation: dict[str, Any]
    mode: str | None = None
    template_id: str | None = None
    name: str | None = None
    write_to_output: bool = False


class SaveBody(BaseModel):
    name: str = Field(min_length=1)
    presentation: dict[str, Any]


def _content_disposition(filename: str) -> str:
    """日本語ファイル名は RFC 5987 で符号化する（HTTP ヘッダは Latin-1 のみ）。"""
    ascii_name = filename.encode("ascii", "ignore").decode("ascii").strip() or "download"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def _check_size(data: bytes, filename: str) -> None:
    if len(data) > _MAX_UPLOAD:
        raise HTTPException(413, f"ファイルが大きすぎます（上限 {_MAX_UPLOAD // (1024 * 1024)}MB）: {filename}")
    if not data:
        raise HTTPException(400, f"空のファイルです: {filename}")


def _apply_template(pres: dict, template_id: str | None) -> dict:
    if template_id:
        t = cfg.template(template_id)
        pres.setdefault("theme", {})
        pres["theme"]["template_id"] = t.get("id")
        pres["theme"]["fonts"] = dict(t.get("fonts", {}))
        pres["theme"]["colors"] = dict(t.get("colors", {}))
    return pres


@app.get("/", response_class=HTMLResponse)
def index() -> Any:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/config")
def api_config() -> dict:
    return {
        "templates": [{"id": t["id"], "name": t.get("name", t["id"]), "description": t.get("description", "")} for t in cfg.templates()],
        "pptx_modes": cfg.get("pptx_export.modes"),
        "default_mode": cfg.get("pptx_export.default_mode"),
        "raster_available": raster_available(),
        "max_upload_mb": cfg.get("limits.max_upload_mb"),
        "output_dir": str(cfg.path("output_dir")),
        "projects_dir": str(cfg.path("projects_dir")),
        "version": app.version,
        "log_level": logging.getLevelName(logging.getLogger("pptx_web_bridge").level),
    }


@app.post("/api/import/pptx")
async def api_import_pptx(file: UploadFile = File(...), template_id: str | None = Form(None)) -> dict:
    data = await file.read()
    _check_size(data, file.filename or "")
    try:
        return await run_in_threadpool(pipeline.import_pptx, data, file.filename or "input.pptx", template_id)
    except (ValueError, zipfile.BadZipFile, KeyError) as e:
        log.warning("PPTX 取込を拒否（入力起因）: %s: %s", file.filename, e)
        raise HTTPException(422, f"PPTX を読み込めませんでした（工程: pptx_parser）: {e}") from e
    except Exception as e:  # noqa: BLE001
        log.exception("PPTX 取込に失敗: %s", file.filename)
        raise HTTPException(422, f"PPTX を読み込めませんでした（工程: pptx_parser）: {e}") from e


@app.post("/api/import/html")
async def api_import_html(file: UploadFile = File(...), template_id: str | None = Form(None), assets: list[UploadFile] | None = File(None), computed_style: bool | None = Form(None)) -> dict:
    data = await file.read()
    _check_size(data, file.filename or "")
    extra: dict[str, bytes] = {}
    for a in assets or []:
        blob = await a.read()
        if blob:
            extra[a.filename or "asset"] = blob
    try:
        # 同期 Playwright はイベントループ上で動かないため、スレッドプールで実行する
        return await run_in_threadpool(pipeline.import_html, data, file.filename or "input.html", template_id, extra, computed_style)
    except (ValueError, zipfile.BadZipFile) as e:
        log.warning("HTML 取込を拒否（入力起因）: %s: %s", file.filename, e)
        raise HTTPException(422, f"HTML を読み込めませんでした（工程: html_parser）: {e}") from e
    except Exception as e:  # noqa: BLE001
        log.exception("HTML 取込に失敗: %s", file.filename)
        raise HTTPException(422, f"HTML を読み込めませんでした（工程: html_parser）: {e}") from e


@app.post("/api/import/json")
async def api_import_json(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    _check_size(data, file.filename or "")
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise HTTPException(422, f"JSON として読み込めません: {e}") from e
    pres, errors, fixes = validate_and_repair(raw)
    return {"presentation": pres, "warnings": fixes, "schema_errors": errors, "quality": pipeline.quality(pres)}


@app.post("/api/validate")
def api_validate(body: PresentationBody) -> dict:
    pres, errors, fixes = validate_and_repair(body.presentation)
    return {"presentation": pres, "schema_errors": errors, "repairs": fixes, "valid": not errors}


@app.post("/api/quality")
def api_quality(body: PresentationBody) -> dict:
    return pipeline.quality(body.presentation)


@app.post("/api/layout")
def api_layout(body: PresentationBody) -> dict:
    pres, errors, fixes = pipeline.prepare(_apply_template(body.presentation, body.template_id))
    return {"presentation": pres, "schema_errors": errors, "warnings": fixes, "quality": pipeline.quality(pres)}


@app.post("/api/preview/html", response_class=HTMLResponse)
def api_preview_html(body: PresentationBody) -> Any:
    pres, _e, _f = pipeline.prepare(_apply_template(body.presentation, body.template_id))
    return HTMLResponse(render_html(pres, inline_assets=True, inline_viewer=True))


@app.post("/api/export/html")
def api_export_html(body: PresentationBody) -> Response:
    pres, _e, _f = pipeline.prepare(_apply_template(body.presentation, body.template_id))
    name = storage.safe_name(body.name or pres.get("meta", {}).get("title") or "web")
    data = storage.bundle_zip(pres)
    headers = {"Content-Disposition": _content_disposition(f"{name}_web.zip")}
    if body.write_to_output:
        path = storage.write_web_dir(pres, name)
        headers["X-Output-Path"] = quote(str(path))
        log.info("Web 一式を書き出し: %s", path)
    return Response(content=data, media_type="application/zip", headers=headers)


@app.post("/api/export/pptx")
def api_export_pptx(body: PresentationBody) -> Response:
    try:
        data, pres, warns = pipeline.export_pptx(_apply_template(body.presentation, body.template_id), body.mode)
    except Exception as e:  # noqa: BLE001
        log.exception("PPTX 生成に失敗")
        raise HTTPException(500, f"PPTX を生成できませんでした（工程: pptx_generator）: {e}") from e
    name = storage.safe_name(body.name or pres.get("meta", {}).get("title") or "presentation")
    headers = {"Content-Disposition": _content_disposition(f"{name}.pptx"), "X-Warning-Count": str(len(warns)), "X-Warnings": json.dumps([w["code"] for w in warns], ensure_ascii=True)}
    if body.write_to_output:
        path = storage.write_output("pptx", name, data, "pptx")
        headers["X-Output-Path"] = quote(str(path))
        log.info("PPTX を書き出し: %s", path)
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation", headers=headers)


@app.post("/api/export/json")
def api_export_json(body: PresentationBody) -> Response:
    pres, _e, _f = validate_and_repair(body.presentation)
    name = storage.safe_name(body.name or pres.get("meta", {}).get("title") or "presentation")
    data = json.dumps(pres, ensure_ascii=False, indent=2).encode("utf-8")
    headers = {"Content-Disposition": _content_disposition(f"{name}.json")}
    if body.write_to_output:
        headers["X-Output-Path"] = quote(str(storage.write_output("json", name, data, "json")))
    return Response(content=data, media_type="application/json", headers=headers)


@app.get("/api/projects")
def api_projects() -> dict:
    return {"projects": storage.list_projects()}


@app.post("/api/projects")
def api_save_project(body: SaveBody) -> dict:
    pres, errors, _fixes = validate_and_repair(body.presentation)
    path = storage.save_project(body.name, pres)
    return {"saved": str(path), "name": path.stem, "schema_errors": errors}


@app.get("/api/projects/{name}")
def api_load_project(name: str) -> dict:
    try:
        pres = storage.load_project(name)
    except FileNotFoundError as e:
        raise HTTPException(404, "プロジェクトが見つかりません。") from e
    pres, errors, fixes = validate_and_repair(pres)
    return {"presentation": pres, "schema_errors": errors, "warnings": fixes, "quality": pipeline.quality(pres)}


@app.delete("/api/projects/{name}")
def api_delete_project(name: str) -> dict:
    return {"deleted": storage.delete_project(name)}


@app.get("/api/new")
def api_new(template_id: str | None = None) -> dict:
    return {"presentation": new_presentation("新規資料", "manual", "", template_id)}


@app.post("/api/report")
def api_report(body: PresentationBody) -> dict:
    """要素判別レポート（文字/画像の区別、座標、フォントサイズ）。"""
    pres, _e, _f = pipeline.prepare(_apply_template(body.presentation, body.template_id))
    return build_report(pres)


@app.post("/api/closing-slide")
def api_closing_slide(body: PresentationBody) -> dict:
    """テンプレートの最終ページ（ロゴ中央）を末尾へ追加した資料を返す。"""
    pres, _e, _f = validate_and_repair(body.presentation)
    if pres["slides"] and pres["slides"][-1].get("layout") == "closing":
        return {"presentation": pres, "added": False}
    n = len(pres["slides"])
    pres["slides"].append(template_kit.make_closing_slide(f"s_end{n + 1:03d}", n, body.name or ""))
    pres, _e2, _f2 = pipeline.prepare(pres)
    return {"presentation": pres, "added": True}


class LogLevelBody(BaseModel):
    level: str


@app.get("/api/loglevel")
def api_get_loglevel() -> dict:
    return {"level": logging.getLevelName(logging.getLogger("pptx_web_bridge").level)}


@app.post("/api/loglevel")
def api_set_loglevel(body: LogLevelBody) -> dict:
    """設計基準 7.3: ログレベルを実行時に切り替える（DEBUG / INFO / WARNING / ERROR）。"""
    level = body.level.upper()
    if level not in ("DEBUG", "INFO", "WARNING", "WARN", "ERROR"):
        raise HTTPException(400, "ログレベルは DEBUG / INFO / WARNING / ERROR のいずれかです。")
    logging.getLogger("pptx_web_bridge").setLevel(getattr(logging, "WARNING" if level == "WARN" else level))
    log.warning("ログレベルを %s に変更しました", level)
    return {"level": level}


@app.get("/api/health")
def api_health() -> dict:
    return {"ok": True}


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
