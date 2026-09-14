"""投入されたファイル → 図解仕様 + 見た目。API と CLI の両方から同じ関数を呼ぶ。

このアプリの仕事は 2 段だけ:

1. `analyze()` — PowerPoint か HTML 図解を読み、**何が書いてあるか**（図解仕様）と
   **どんな見た目か**（テーマ）に分ける。
2. `prompt_builder.build()` — それを Copilot への指示文にする。

描画はしない。描くのは Copilot。
"""
from __future__ import annotations

import io
import posixpath
import zipfile
from typing import Any

from . import spec_builder, theme_from_html, theme_from_pptx
from .html_parser import parse_html
from .logging_setup import get_logger
from .pptx_parser import parse_pptx

log = get_logger("pipeline")

PPTX_EXT = (".pptx", ".potx", ".ppsx")
HTML_EXT = (".html", ".htm")


def _files_from_zip(data: bytes, filename: str) -> tuple[bytes, str, dict[str, bytes]]:
    """ZIP（HTML + CSS + 画像）→ (HTML 本体, その名前, 同梱ファイル)。"""
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            if info.is_dir() or info.filename.startswith("__MACOSX/"):
                continue
            files[info.filename.replace("\\", "/")] = z.read(info)
    html_names = sorted(
        [n for n in files if n.lower().endswith(HTML_EXT)],
        key=lambda n: (n.count("/"), 0 if posixpath.basename(n).lower().startswith("index") else 1, n),
    )
    if not html_names:
        if "[Content_Types].xml" in files:
            raise ValueError("これは PowerPoint（PPTX）ファイルのようです。そのまま PPTX として投入してください。")
        raise ValueError("ZIP の中に HTML ファイルがありませんでした。")
    name = html_names[0]
    return files[name], name, files


def detect_kind(data: bytes, filename: str) -> str:
    """'pptx' か 'html'。拡張子より中身を優先する（拡張子は当てにならない）。"""
    low = (filename or "").lower()
    if data[:2] == b"PK":
        try:
            names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
        except zipfile.BadZipFile as e:
            raise ValueError(f"ZIP として読めませんでした: {e}") from e
        if "[Content_Types].xml" in names and any(n.startswith("ppt/") for n in names):
            return "pptx"
        return "html"  # HTML + 画像の ZIP
    head = data[:400].lower()
    if b"<html" in head or b"<!doctype" in head or low.endswith(HTML_EXT):
        return "html"
    if low.endswith(PPTX_EXT):
        raise ValueError("PPTX（ZIP 形式）として読めません。ファイルが壊れているか、別の形式です。")
    raise ValueError("PowerPoint（.pptx）か HTML 図解（.html / .zip）を投入してください。")


def analyze(data: bytes, filename: str, kind_overrides: dict[str, str] | None = None) -> dict[str, Any]:
    """投入ファイル → {kind, presentation, spec, spec_yaml, theme, warnings}。"""
    kind = detect_kind(data, filename)
    if kind == "pptx":
        pres = parse_pptx(data, filename)
        theme = theme_from_pptx.extract_theme(data, filename)
    else:
        html_bytes, html_name, files = (data, filename, {})
        if data[:2] == b"PK":
            html_bytes, html_name, files = _files_from_zip(data, filename)
        pres = parse_html(html_bytes, html_name, files=files or None)
        theme = theme_from_html.extract_theme(html_bytes, html_name)

    spec = spec_builder.build_spec(pres, kind_overrides)
    warnings = list(spec.get("warnings", [])) + list(theme.get("warnings", []))
    log.info("解析: %s（%s）%s 枚 警告=%s", filename, kind, spec.get("slide_count"), len(warnings))
    return {
        "kind": kind,
        "presentation": pres,
        "spec": spec,
        "spec_yaml": spec_builder.to_yaml(spec),
        "theme": theme,
        "warnings": warnings,
    }


def analyze_theme(data: bytes, filename: str) -> dict[str, Any]:
    """HTML 図解テーマだけを読む（見た目の指示に使う）。"""
    html_bytes, html_name = data, filename
    if data[:2] == b"PK":
        html_bytes, html_name, _ = _files_from_zip(data, filename)
    return theme_from_html.extract_theme(html_bytes, html_name)
