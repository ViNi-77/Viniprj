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

from . import copilot_handoff, pipeline, storage, template_from_pptx, template_kit, template_store
from .layout import element_height, layout_slide
from .report import build_report
from .config import get_config, resource_path
from .logging_setup import get_logger
from .model import new_presentation
from .rasterize import is_available as raster_available
from .typography import normalize_presentation
from .validate import validate_and_repair
from .web_renderer import _VIEWER_DIR, render_html, slide_html, theme_css

log = get_logger("api")


def _cfg():
    """設定は呼び出し時に引く（試験で差し替えた設定や、再読込した設定を API がそのまま使えるように）。"""
    return get_config()


cfg = _cfg()
app = FastAPI(title="PPTX ⇄ Web図解 変換アプリ", version="0.1.0")
FRONTEND_DIR = resource_path("frontend")
_MAX_UPLOAD = int(_cfg().get("limits.max_upload_mb", 50)) * 1024 * 1024


class PresentationBody(BaseModel):
    presentation: dict[str, Any]
    mode: str | None = None
    template_id: str | None = None
    name: str | None = None
    write_to_output: bool = False
    use_base_pptx: bool = False  # PPTX から作ったテンプレートの元ファイルを土台にして出力する


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
        t = _cfg().template(template_id)
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
        "templates": [{"id": t["id"], "name": t.get("name", t["id"]), "description": t.get("description", ""), "source": t.get("source", "builtin"), "has_base_pptx": bool(t.get("base_pptx"))} for t in _cfg().templates()],
        "pptx_modes": _cfg().get("pptx_export.modes"),
        "default_mode": _cfg().get("pptx_export.default_mode"),
        "raster_available": raster_available(),
        "max_upload_mb": _cfg().get("limits.max_upload_mb"),
        "output_dir": str(_cfg().path("output_dir")),
        "projects_dir": str(_cfg().path("projects_dir")),
        "version": app.version,
        "log_level": logging.getLevelName(logging.getLogger("pptx_web_bridge").level),
        "layout": {"margin_pt": _cfg().get("layout.margin_pt"), "gutter_pt": _cfg().get("layout.gutter_pt"), "size_bands": _cfg().get("layout.size_bands"), "body_font_pt": _cfg().get("layout.body_font_pt"), "title_font_pt": _cfg().get("layout.title_font_pt")},
        "canvas": {"width_pt": _cfg().get("canvas.default_width_pt"), "height_pt": _cfg().get("canvas.default_height_pt")},
    }


class RenderBody(PresentationBody):
    indices: list[int] | None = None


@app.post("/api/render/slides")
def api_render_slides(body: RenderBody) -> dict:
    """編集キャンバス・サムネイル用に、指定スライドの HTML 断片を返す（描画器はサーバ側の 1 つだけ）。

    prepare（修復 → 正規化 → レイアウト → テンプレート）後の資料も返すので、クライアントはこれを状態として採用する。
    """
    pres, errors, fixes = pipeline.prepare(_apply_template(body.presentation, body.template_id))
    template = _cfg().template(pres.get("theme", {}).get("template_id"))
    slides = pres.get("slides", [])
    indices = body.indices if body.indices is not None else list(range(len(slides)))
    html = {str(i): slide_html(slides[i], pres, inline_assets=True, template=template, with_notes=False) for i in indices if 0 <= i < len(slides)}
    return {"presentation": pres, "canvas": pres["canvas"], "theme_css": theme_css(pres), "slides": html, "warnings": fixes, "schema_errors": errors}


class LayoutSlideBody(PresentationBody):
    index: int
    scope: str = "unplaced"  # unplaced: 座標の無い要素だけ / all: 全要素を配置し直す


@app.post("/api/layout/slide")
def api_layout_slide(body: LayoutSlideBody) -> dict:
    """1 枚だけ自動配置する（分割されて複数枚になることがある）。"""
    pres, errors, fixes = validate_and_repair(_apply_template(body.presentation, body.template_id))
    slides = pres.get("slides", [])
    if not 0 <= body.index < len(slides):
        raise HTTPException(400, "スライド番号が範囲外です。")
    normalize_presentation(pres)
    target = slides[body.index]
    if body.scope == "all":
        for el in target.get("elements", []):
            el["bbox"] = None
            el.pop("font_scale", None)
            el.pop("user_bbox", None)
    template = template_kit.template_for(pres)
    new_slides = layout_slide(target, pres["canvas"], pres.get("assets", {}), None, template if template_kit.has_parts(template) else None)
    slides[body.index : body.index + 1] = new_slides
    for i, s in enumerate(slides):
        s["index"] = i
    pres = template_kit.apply_template(pres)
    return {"presentation": pres, "count": len(new_slides), "schema_errors": errors, "warnings": fixes}


class FitBody(PresentationBody):
    index: int
    element_id: str


@app.post("/api/layout/fit")
def api_layout_fit(body: FitBody) -> dict:
    """「内容に合わせる」: 要素の現在幅での推定高さを返す。"""
    pres, _e, _f = validate_and_repair(body.presentation)
    normalize_presentation(pres)
    try:
        slide = pres["slides"][body.index]
        el = next(e for e in slide.get("elements", []) if e.get("id") == body.element_id)
    except (IndexError, StopIteration) as e:
        raise HTTPException(404, "要素が見つかりません。") from e
    width = float((el.get("bbox") or {}).get("w") or (float(pres["canvas"]["width_pt"]) - 2 * float(_cfg().get("layout.margin_pt", 36))))
    return {"h": round(element_height(el, width, pres), 2), "font_pt": el.get("font_pt")}


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
        data, pres, warns = pipeline.export_pptx(_apply_template(body.presentation, body.template_id), body.mode, body.use_base_pptx)
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


# ---------------------------------------------------------------- テンプレート（PPTX から作成）
class TemplateBody(BaseModel):
    template: dict[str, Any]
    previous_id: str | None = None  # 画面で ID を変えたとき、画像フォルダを移す元の ID


def _template_previews(template: dict) -> dict:
    """提案テンプレートで 3 枚のサンプル（表紙 / 中身 / 最終）を描く。未保存でも描けるよう use_template で差し込む。"""
    with template_kit.use_template(template):
        pres, _e, _f = pipeline.prepare(template_from_pptx.sample_presentation(template))
        html = {}
        for s in pres["slides"]:
            kind = template_kit.slide_kind(s, pres)
            html[kind] = slide_html(s, pres, inline_assets=True, template=template, with_notes=False)
        return {"previews": html, "canvas": pres["canvas"], "theme_css": theme_css(pres), "sample": pres}


def _slide_thumbs(data: bytes, filename: str, limit: int = 12) -> list[str]:
    """投入した PPTX の各スライドを（テンプレート部品を描かずに）縮小表示用の断片にする。"""
    try:
        from .pptx_parser import parse_pptx

        pres = parse_pptx(data, filename)
        pres, _e, _f = pipeline.prepare(pres)
        with template_kit.use_template({}):
            return [slide_html(s, pres, inline_assets=True, template={}, with_notes=False) for s in pres["slides"][:limit]]
    except Exception as e:  # noqa: BLE001
        log.warning("テンプレート元 PPTX のサムネイル描画に失敗: %s", e)
        return []


@app.get("/api/templates")
def api_templates() -> dict:
    return {"templates": _cfg().templates()}


@app.post("/api/templates/from-pptx")
async def api_template_from_pptx(file: UploadFile = File(...), roles: str | None = Form(None), template_id: str | None = Form(None), name: str | None = Form(None), thumbs: bool = Form(True)) -> dict:
    """PPTX（表紙・中身・最終ページ）を解析し、テンプレート定義の提案とプレビューを返す。roles は {"0": "cover", ...} の JSON。"""
    data = await file.read()
    _check_size(data, file.filename or "")
    if data[:2] != b"PK":
        raise HTTPException(422, "PPTX（ZIP 形式）として読めません。")
    overrides: dict[int, str] = {}
    if roles:
        try:
            overrides = {int(k): str(v) for k, v in json.loads(roles).items()}
        except (ValueError, AttributeError) as e:
            raise HTTPException(400, f"roles の形式が不正です: {e}") from e
    try:
        result = await run_in_threadpool(template_from_pptx.analyze, data, file.filename or "template.pptx", template_id, overrides, name)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:  # noqa: BLE001
        log.exception("テンプレート推定に失敗: %s", file.filename)
        raise HTTPException(422, f"テンプレートを推定できませんでした（工程: template_from_pptx）: {e}") from e
    result.update(await run_in_threadpool(_template_previews, result["proposal"]))
    result.pop("sample", None)
    if thumbs:
        result["thumbs"] = await run_in_threadpool(_slide_thumbs, data, file.filename or "template.pptx")
    return result


@app.post("/api/templates/preview")
def api_template_preview(body: TemplateBody) -> dict:
    """画面で座標を直した提案を描き直す。parts も返す（番号付き枠の一覧）。"""
    out = _template_previews(body.template)
    out.pop("sample", None)
    out["parts"] = template_from_pptx.parts_of(body.template)
    return out


@app.put("/api/templates/{template_id}")
def api_template_save(template_id: str, body: TemplateBody) -> dict:
    t = dict(body.template)
    t["id"] = template_store.safe_id(template_id)
    if body.previous_id and body.previous_id != t["id"]:
        t = template_store.rename_assets(body.previous_id, t["id"], t)
        template_store.delete_template(body.previous_id)
    try:
        saved = template_store.save_template(t)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    log.info("ユーザーテンプレートを保存: %s", saved["id"])
    return {"template": saved, "templates": api_config()["templates"]}


@app.delete("/api/templates/{template_id}")
def api_template_delete(template_id: str) -> dict:
    if template_store.is_builtin(template_id):
        raise HTTPException(400, "組込テンプレートは削除できません。")
    deleted = template_store.delete_template(template_id)
    return {"deleted": deleted, "templates": api_config()["templates"]}


# ---------------------------------------------------------------- Copilot 連携（API を使わない受け渡し）
class HandoffBody(PresentationBody):
    purpose: str | None = None
    options: dict[str, Any] | None = None


class CopilotReplyBody(BaseModel):
    text: str = Field(min_length=1)
    apply: str = "new"  # new: 新しい資料として取り込む / notes: 既存資料のノートへ反映
    presentation: dict[str, Any] | None = None
    template_id: str | None = None


@app.get("/api/copilot/prompts")
def api_copilot_prompts() -> dict:
    data = _cfg().copilot_prompts()
    return {"chat_url": data.get("chat_url"), "purposes": [{k: v for k, v in p.items() if k != "prompt"} for p in data.get("purposes", [])]}


@app.post("/api/copilot/handoff")
def api_copilot_handoff(body: HandoffBody) -> dict:
    """資料を Copilot に貼る形（プロンプト + Markdown / JSON）にする。"""
    pres, _e, _f = validate_and_repair(_apply_template(body.presentation, body.template_id))
    return copilot_handoff.build_prompt(pres, body.purpose, body.options)


@app.post("/api/copilot/handoff.zip")
def api_copilot_handoff_zip(body: HandoffBody) -> Response:
    """Copilot へ渡す一式（prompt.txt / outline.md / outline.json / outline.docx / images）。"""
    pres, _e, _f = validate_and_repair(_apply_template(body.presentation, body.template_id))
    name = storage.safe_name(body.name or pres.get("meta", {}).get("title") or "copilot")
    data = copilot_handoff.bundle_zip(pres, body.purpose, body.options)
    headers = {"Content-Disposition": _content_disposition(f"{name}_copilot.zip")}
    if body.write_to_output:
        path = storage.write_output("copilot", name, data, "zip")
        headers["X-Output-Path"] = quote(str(path))
    return Response(content=data, media_type="application/zip", headers=headers)


@app.post("/api/copilot/docx")
def api_copilot_docx(body: PresentationBody) -> Response:
    """Word 文書だけ（Copilot in PowerPoint の「ファイルから作成」用）。"""
    pres, _e, _f = validate_and_repair(_apply_template(body.presentation, body.template_id))
    name = storage.safe_name(body.name or pres.get("meta", {}).get("title") or "outline")
    return Response(content=copilot_handoff.to_docx(pres), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": _content_disposition(f"{name}.docx")})


@app.post("/api/copilot/import")
def api_copilot_import(body: CopilotReplyBody) -> dict:
    """Copilot の回答（Markdown / 簡易 JSON）を資料にする。apply=new で新規、notes で既存資料のノートへ。"""
    if len(body.text) > _MAX_UPLOAD:
        raise HTTPException(413, "貼り付けた文章が大きすぎます。")
    if body.apply == "notes":
        if not body.presentation:
            raise HTTPException(400, "ノートを反映する資料がありません。")
        pres, _e, _f = validate_and_repair(body.presentation)
        pres, count = copilot_handoff.apply_notes(pres, body.text)
        return {"presentation": pres, "applied": count, "mode": "notes", "warnings": [], "schema_errors": [], "quality": pipeline.quality(pres)}
    kind, data = copilot_handoff.parse_copilot_reply(body.text)
    try:
        pres = copilot_handoff.import_outline_json(data, body.template_id) if kind == "json" else copilot_handoff.import_markdown(body.text, body.template_id)
    except Exception as e:  # noqa: BLE001
        log.exception("Copilot 回答の取込に失敗")
        raise HTTPException(422, f"回答を読み取れませんでした（工程: copilot_handoff）: {e}") from e
    if not pres.get("slides"):
        raise HTTPException(422, "回答からスライドを作れませんでした。見出し（## 1. 題名）と箇条書き（- ）の形式で貼り付けてください。")
    from .layout import layout_presentation

    pres = layout_presentation(pres)
    pres, errors, fixes = validate_and_repair(pres)
    return {"presentation": pres, "mode": "new", "format": kind, "warnings": pres.get("warnings", []) + fixes, "schema_errors": errors, "quality": pipeline.quality(pres)}


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
app.mount("/viewer", StaticFiles(directory=str(_VIEWER_DIR)), name="viewer")
