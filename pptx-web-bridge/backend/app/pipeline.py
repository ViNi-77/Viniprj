"""変換パイプラインの入口。API と CLI の両方から同じ関数を呼ぶ。"""
from __future__ import annotations

import io
import posixpath
import zipfile

from . import template_kit
from .html_parser import parse_html
from .layout import layout_presentation
from .pptx_generator import generate_pptx
from .pptx_parser import parse_pptx
from .quality_check import check_presentation, summarize
from .validate import validate_and_repair


def import_pptx(data: bytes, filename: str, template_id: str | None = None) -> dict:
    if data[:2] != b"PK":
        head = data[:200].lower()
        if b"<html" in head or b"<!doctype" in head:
            raise ValueError("これは HTML ファイルのようです。HTML として投入してください。")
        raise ValueError("PPTX（ZIP 形式）として読めません。ファイルが壊れているか、別形式です。")
    pres = parse_pptx(data, filename, template_id)
    pres, errors, fixes = validate_and_repair(pres)
    return {"presentation": pres, "warnings": pres.get("warnings", []) + fixes, "schema_errors": errors, "quality": _quality(pres)}


def _files_from_upload(data: bytes, filename: str) -> tuple[bytes, str, dict[str, bytes]]:
    """HTML 単体または ZIP（HTML + CSS + 画像）を受け取り、(HTML, HTML名, 同梱ファイル) を返す。"""
    if filename.lower().endswith(".zip") or data[:2] == b"PK":
        files: dict[str, bytes] = {}
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                if info.is_dir() or info.filename.startswith("__MACOSX/"):
                    continue
                files[info.filename.replace("\\", "/")] = z.read(info)
        html_names = sorted([n for n in files if n.lower().endswith((".html", ".htm"))], key=lambda n: (n.count("/"), 0 if posixpath.basename(n).lower().startswith("index") else 1, n))
        if not html_names:
            if "[Content_Types].xml" in files:
                raise ValueError("これは PowerPoint（PPTX）ファイルのようです。PPTX として投入してください。")
            raise ValueError("ZIP 内に HTML ファイルがありません。")
        name = html_names[0]
        return files[name], name, files
    return data, filename, {}


def import_html(data: bytes, filename: str, template_id: str | None = None, extra_files: dict[str, bytes] | None = None, computed_style: bool | None = None) -> dict:
    html_bytes, html_name, files = _files_from_upload(data, filename)
    if extra_files:
        files.update(extra_files)
    pres = parse_html(html_bytes, html_name, files, template_id, computed_style=computed_style)
    pres = layout_presentation(pres)
    pres, errors, fixes = validate_and_repair(pres)
    return {"presentation": pres, "warnings": pres.get("warnings", []) + fixes, "schema_errors": errors, "quality": _quality(pres)}


def prepare(presentation: dict) -> tuple[dict, list[str], list[dict]]:
    """出力前の共通処理: 修復 → 未レイアウト要素の配置。"""
    pres, errors, fixes = validate_and_repair(presentation)
    pres = layout_presentation(pres)
    pres = template_kit.apply_template(pres)
    return pres, errors, fixes


def export_pptx(presentation: dict, mode: str | None = None, use_base_pptx: bool = False) -> tuple[bytes, dict, list[dict]]:
    pres, _errors, fixes = prepare(presentation)
    data, warns = generate_pptx(pres, mode, use_base_pptx=use_base_pptx)
    return data, pres, fixes + warns


def _quality(pres: dict) -> dict:
    issues = check_presentation(pres)
    return {"issues": issues, "summary": summarize(issues)}


def quality(presentation: dict) -> dict:
    pres, _e, _f = prepare(presentation)
    return _quality(pres)
