"""Presentation JSON の生成ヘルパー。

スキーマ（schema/presentation.schema.json）と同じ構造の辞書を組み立てる。
クラスではなく辞書を採用しているのは、JSON との往復とスキーマ検証を単純にするため。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import get_config

SCHEMA_VERSION = "1.1"
GENERATOR_NAME = "pptx-web-bridge/0.3.0"


def new_presentation(title: str = "", source_type: str = "manual", filename: str = "", template_id: str | None = None) -> dict:
    cfg = get_config()
    template = cfg.template(template_id)
    return {
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "title": title,
            "author": "",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "generator": GENERATOR_NAME,
            "source": {"type": source_type, "filename": filename},
        },
        "canvas": {
            "width_pt": float(cfg.get("canvas.default_width_pt", 960)),
            "height_pt": float(cfg.get("canvas.default_height_pt", 540)),
            "aspect": str(cfg.get("canvas.aspect", "16:9")),
        },
        "theme": {
            "template_id": template.get("id", "plain"),
            "fonts": dict(template.get("fonts", {})),
            "colors": dict(template.get("colors", {})),
        },
        "assets": {},
        "slides": [],
        "warnings": [],
    }


def new_slide(slide_id: str, index: int, layout: str = "title_body", title: str | None = None) -> dict:
    return {"id": slide_id, "index": index, "layout": layout, "title": title, "notes": None, "background": None, "elements": [], "warnings": []}


def bbox(x: float, y: float, w: float, h: float) -> dict:
    return {"x": round(float(x), 2), "y": round(float(y), 2), "w": round(max(0.0, float(w)), 2), "h": round(max(0.0, float(h)), 2)}


def run(text: str, **style: Any) -> dict:
    r: dict[str, Any] = {"text": text}
    for k in ("bold", "italic", "underline", "size_pt", "color", "font", "href"):
        if k in style and style[k] is not None:
            r[k] = style[k]
    return r


def paragraph(runs: list[dict], level: int = 0, bullet: str | None = None, align: str | None = None) -> dict:
    p: dict[str, Any] = {"runs": runs, "level": level, "bullet": bullet}
    if align:
        p["align"] = align
    return p


def text_element(el_id: str, paragraphs: list[dict], role: str | None = "body", box: dict | None = None, **extra: Any) -> dict:
    el: dict[str, Any] = {"id": el_id, "type": "text", "role": role, "bbox": box, "paragraphs": paragraphs, "editable": True}
    el.update({k: v for k, v in extra.items() if v is not None})
    return el


def simple_text_element(el_id: str, text: str, role: str | None = "body", box: dict | None = None, **style: Any) -> dict:
    return text_element(el_id, [paragraph([run(text, **style)])], role=role, box=box)


def image_element(el_id: str, asset_id: str, box: dict | None = None, alt: str | None = None, fit: str = "contain", **extra: Any) -> dict:
    el: dict[str, Any] = {"id": el_id, "type": "image", "role": None, "bbox": box, "asset_id": asset_id, "alt": alt or "", "fit": fit, "editable": True}
    el.update({k: v for k, v in extra.items() if v is not None})
    return el


def shape_element(el_id: str, shape: str, box: dict | None, fill: str | None = None, stroke: str | None = None, stroke_width_pt: float | None = None, paragraphs: list[dict] | None = None, role: str | None = None, **extra: Any) -> dict:
    el: dict[str, Any] = {
        "id": el_id,
        "type": "shape",
        "role": role,
        "bbox": box,
        "shape": shape,
        "fill": fill,
        "stroke": stroke,
        "stroke_width_pt": stroke_width_pt,
        "paragraphs": paragraphs or [],
        "editable": True,
    }
    el.update({k: v for k, v in extra.items() if v is not None})
    return el


def line_element(el_id: str, x1: float, y1: float, x2: float, y2: float, stroke: str | None = None, stroke_width_pt: float | None = 1.0) -> dict:
    x, y = min(x1, x2), min(y1, y2)
    return {
        "id": el_id,
        "type": "line",
        "role": None,
        "bbox": bbox(x, y, abs(x2 - x1), abs(y2 - y1)),
        "points": [[round(x1, 2), round(y1, 2)], [round(x2, 2), round(y2, 2)]],
        "stroke": stroke,
        "stroke_width_pt": stroke_width_pt,
        "editable": True,
    }


def cell(text: str, bold: bool = False, fill: str | None = None, colspan: int = 1, rowspan: int = 1, align: str | None = None) -> dict:
    c: dict[str, Any] = {"text": text, "bold": bold, "colspan": colspan, "rowspan": rowspan}
    if fill:
        c["fill"] = fill
    if align:
        c["align"] = align
    return c


def table_element(el_id: str, rows: list[list[dict]], box: dict | None = None, header_rows: int = 1, col_widths_pt: list[float] | None = None, **extra: Any) -> dict:
    el: dict[str, Any] = {"id": el_id, "type": "table", "role": None, "bbox": box, "rows": rows, "header_rows": header_rows, "col_widths_pt": col_widths_pt, "editable": True}
    el.update({k: v for k, v in extra.items() if v is not None})
    return el


def unsupported_element(el_id: str, original_type: str, box: dict | None, message: str) -> dict:
    """未対応要素。エラー停止させず、位置だけを残して警告表示に使う。"""
    return {"id": el_id, "type": "unsupported", "role": None, "bbox": box, "original_type": original_type, "alt": message, "editable": False}


def warning(stage: str, code: str, message: str, slide_id: str | None = None, element_id: str | None = None, fallback: str | None = None) -> dict:
    return {"stage": stage, "slide_id": slide_id, "element_id": element_id, "code": code, "message": message, "fallback": fallback}


def add_warning(presentation: dict, w: dict, slide: dict | None = None) -> None:
    presentation.setdefault("warnings", []).append(w)
    if slide is not None:
        slide.setdefault("warnings", []).append(w)


def element_plain_text(el: dict) -> str:
    """要素のテキストを改行区切りで取り出す（品質検査・目次生成用）。"""
    if el.get("type") in ("text", "shape"):
        return "\n".join("".join(r.get("text", "") for r in p.get("runs", [])) for p in el.get("paragraphs", []))
    if el.get("type") == "table":
        return "\n".join("\t".join(c.get("text", "") for c in row) for row in el.get("rows", []))
    return ""


def slide_title(slide: dict) -> str:
    """スライドの表示タイトル。title フィールド → title 役割の要素 → 先頭テキスト の順で決める。"""
    if slide.get("title"):
        return str(slide["title"])
    for el in slide.get("elements", []):
        if el.get("role") == "title":
            t = element_plain_text(el).strip()
            if t:
                return t.splitlines()[0]
    for el in slide.get("elements", []):
        t = element_plain_text(el).strip()
        if t:
            return t.splitlines()[0][:40]
    return f"スライド {int(slide.get('index', 0)) + 1}"
