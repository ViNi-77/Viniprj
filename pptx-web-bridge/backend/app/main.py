"""ローカル API（FastAPI）。ブラウザ UI から呼ばれる。

このアプリは図解を描かない。**読み取って、Copilot への指示文にする**だけ。
だから API も 3 本しかない: 投入（`/api/analyze`）、テーマ（`/api/theme`）、
プロンプト（`/api/prompt` と `/api/pack.zip`）。

- 外部へファイルを送信しない。すべてローカルで処理する。
- 失敗は HTTP 4xx + 日本語メッセージで返し、ログに工程名を残す。
"""
from __future__ import annotations

import logging
import re
import uuid
import zipfile
from collections import OrderedDict
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import handoff_pack, pipeline, prompt_builder, spec_builder
from . import version as version_mod
from .config import get_config, resource_path
from .logging_setup import get_logger

log = get_logger("api")


def _cfg():
    """設定は呼び出し時に引く（試験で差し替えた設定をそのまま使えるように）。"""
    return get_config()


app = FastAPI(title="図解プロンプト作成（PowerPoint ⇄ Web 図解）", version=version_mod.APP_VERSION)
FRONTEND_DIR = resource_path("frontend")
_MAX_UPLOAD = int(_cfg().get("limits.max_upload_mb", 50)) * 1024 * 1024

# 解析結果の預かり所。ZIP を作るときに画像の実体が要るのでサーバー側に置く。
# 手元で 1 人が使う前提なので、古いものから順に捨てる小さな箱で足りる。
_SESSIONS: "OrderedDict[str, dict]" = OrderedDict()
_THEMES: "OrderedDict[str, dict]" = OrderedDict()
_KEEP = 8


def _remember(store: OrderedDict, value: dict) -> str:
    key = uuid.uuid4().hex[:12]
    store[key] = value
    while len(store) > _KEEP:
        store.popitem(last=False)
    return key


def _session(session_id: str) -> dict:
    got = _SESSIONS.get(session_id)
    if not got:
        raise HTTPException(404, "投入したファイルの情報が見つかりません。もう一度ファイルを投入してください。")
    _SESSIONS.move_to_end(session_id)
    return got


def _content_disposition(filename: str) -> str:
    """日本語ファイル名は RFC 5987 で符号化する（HTTP ヘッダは Latin-1 のみ）。"""
    ascii_name = filename.encode("ascii", "ignore").decode("ascii").strip() or "download"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def _check_size(data: bytes, filename: str) -> None:
    if len(data) > _MAX_UPLOAD:
        raise HTTPException(413, f"ファイルが大きすぎます（上限 {_MAX_UPLOAD // (1024 * 1024)}MB）: {filename}")
    if not data:
        raise HTTPException(400, f"空のファイルです: {filename}")


_ASSET_REF = re.compile(r'(?P<ref>(?:href|src)="/static/[^"?]+)"')


@app.get("/", response_class=HTMLResponse)
def index() -> Any:
    """画面の HTML。JS・CSS の URL に版の印を付けて、古いものが使われないようにする。"""
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    html = _ASSET_REF.sub(lambda m: f'{m.group("ref")}?v={version_mod.asset_tag()}"', html)
    return HTMLResponse(html, headers={"Cache-Control": "no-store, must-revalidate"})


@app.get("/api/version")
def api_version() -> dict:
    """版・コミット・入っている機能の一覧。「更新できているか」の確認に使う。"""
    return version_mod.version_info()


@app.get("/api/config")
def api_config() -> dict:
    return {
        "directions": prompt_builder.directions(),
        "kinds": spec_builder.kind_options(),
        "max_upload_mb": _cfg().get("limits.max_upload_mb"),
        "max_prompt_chars": _cfg().get("copilot.max_prompt_chars", prompt_builder.DEFAULT_MAX_CHARS),
        "version": app.version,
        "build": version_mod.build_info(),
        "log_level": logging.getLevelName(logging.getLogger("pptx_web_bridge").level),
    }


def _analyze_payload(session_id: str, got: dict) -> dict:
    return {
        "session_id": session_id,
        "kind": got["kind"],
        "filename": got["filename"],
        "spec": got["spec"],
        "spec_yaml": got["spec_yaml"],
        "theme": {k: v for k, v in got["theme"].items() if k != "warnings"},
        "images": handoff_pack.image_manifest(got["spec"]),
        "warnings": got["warnings"],
        "suggested_direction": "to_html" if got["kind"] == "pptx" else "to_pptx",
    }


@app.post("/api/analyze")
async def api_analyze(file: UploadFile = File(...)) -> dict:
    """PowerPoint か HTML 図解を投入し、図解仕様と見た目を取り出す。"""
    data = await file.read()
    name = file.filename or "input"
    _check_size(data, name)
    try:
        got = await run_in_threadpool(pipeline.analyze, data, name)
    except (ValueError, zipfile.BadZipFile, KeyError) as e:
        log.warning("解析を拒否（入力起因）: %s: %s", name, e)
        raise HTTPException(422, str(e)) from e
    except Exception as e:  # noqa: BLE001
        log.exception("解析に失敗: %s", name)
        raise HTTPException(422, f"ファイルを読み込めませんでした: {e}") from e
    got["filename"] = name
    return _analyze_payload(_remember(_SESSIONS, got), got)


class KindBody(BaseModel):
    session_id: str
    kind_overrides: dict[str, str] = {}


@app.post("/api/spec")
def api_spec(body: KindBody) -> dict:
    """画面で型を直したときに、仕様を作り直す。"""
    got = _session(body.session_id)
    spec = spec_builder.build_spec(got["presentation"], body.kind_overrides)
    got["spec"] = spec
    got["spec_yaml"] = spec_builder.to_yaml(spec)
    got["kind_overrides"] = body.kind_overrides
    got["warnings"] = list(spec.get("warnings", [])) + list(got["theme"].get("warnings", []))
    return _analyze_payload(body.session_id, got)


@app.post("/api/theme")
async def api_theme(file: UploadFile = File(...)) -> dict:
    """HTML 図解テーマを投入する（見た目の指示に使う）。"""
    data = await file.read()
    name = file.filename or "theme.html"
    _check_size(data, name)
    try:
        theme = await run_in_threadpool(pipeline.analyze_theme, data, name)
    except (ValueError, zipfile.BadZipFile) as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:  # noqa: BLE001
        log.exception("テーマの解析に失敗: %s", name)
        raise HTTPException(422, f"テーマを読み込めませんでした: {e}") from e
    theme_id = _remember(_THEMES, theme)
    return {"theme_id": theme_id, "theme": theme, "lines": prompt_builder.theme_from_html.to_prompt_lines(theme), "warnings": theme.get("warnings", [])}


class PromptBody(BaseModel):
    session_id: str
    direction: str = "to_pptx"
    theme_id: str | None = None
    use_source_theme: bool = True
    kind_overrides: dict[str, str] | None = None


def _build(body: PromptBody) -> tuple[dict, dict, dict]:
    got = _session(body.session_id)
    spec = got["spec"]
    if body.kind_overrides is not None:
        spec = spec_builder.build_spec(got["presentation"], body.kind_overrides)
        got["spec"] = spec
        got["spec_yaml"] = spec_builder.to_yaml(spec)
    theme: dict | None = None
    if body.theme_id:
        theme = _THEMES.get(body.theme_id)
        if theme is None:
            raise HTTPException(404, "テーマが見つかりません。もう一度テーマを投入してください。")
    elif body.use_source_theme:
        theme = got.get("theme") or None
    built = prompt_builder.build(spec, theme, body.direction)
    return got, spec, built


@app.post("/api/prompt")
def api_prompt(body: PromptBody) -> dict:
    """図解仕様 + 見た目 → Copilot に貼るプロンプト。"""
    _got, _spec, built = _build(body)
    return built


@app.post("/api/pack.zip")
def api_pack(body: PromptBody) -> Response:
    """プロンプト・仕様・Word・画像をまとめた ZIP。"""
    got, spec, built = _build(body)
    blob = handoff_pack.build_zip(built, spec, got["presentation"])
    return Response(
        blob,
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(handoff_pack.pack_name(spec, built))},
    )


@app.get("/api/loglevel")
def api_get_loglevel() -> dict:
    return {"level": logging.getLevelName(logging.getLogger("pptx_web_bridge").level)}


@app.post("/api/loglevel")
def api_set_loglevel(payload: dict) -> dict:
    level = str(payload.get("level", "INFO")).upper()
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        raise HTTPException(400, "level は DEBUG / INFO / WARNING / ERROR のいずれかです。")
    logging.getLogger("pptx_web_bridge").setLevel(level)
    return {"level": level}


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok", "version": app.version}


@app.exception_handler(404)
async def not_found(_request, exc) -> JSONResponse:  # noqa: ANN001
    return JSONResponse({"detail": getattr(exc, "detail", "見つかりません")}, status_code=404)


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
