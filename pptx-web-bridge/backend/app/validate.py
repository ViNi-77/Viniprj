"""Presentation JSON の検証と自動修復。

- 検証: JSON Schema（Draft 2020-12）で構造を確認する。
- 修復: よくある欠落（id 欠如、index ずれ、bbox の負値など）を補い、再検証する。
  AI 出力の揺れや手編集の破損を「エラー停止」ではなく「警告 + 修復」で扱う。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .config import get_config
from .diagrams import item_limits, normalize_items, normalize_type, word_of
from .model import SCHEMA_VERSION, new_presentation, warning

_schema_cache: dict | None = None
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def load_schema() -> dict:
    global _schema_cache
    if _schema_cache is None:
        path: Path = get_config().path("schema_file")
        with path.open("r", encoding="utf-8") as f:
            _schema_cache = json.load(f)
    return _schema_cache


def validate(presentation: Any) -> list[str]:
    """スキーマ違反メッセージの一覧を返す（空なら合格）。"""
    validator = Draft202012Validator(load_schema())
    errors = sorted(validator.iter_errors(presentation), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors]


def _normalize_color(value: Any) -> str | None:
    """'#abc' や 'rgb(1,2,3)' などを '#RRGGBB' に正規化する。解釈不能なら None。"""
    if not isinstance(value, str):
        return None
    v = value.strip()
    if _HEX_COLOR.match(v):
        return v.upper()
    m = re.match(r"^#([0-9A-Fa-f])([0-9A-Fa-f])([0-9A-Fa-f])$", v)
    if m:
        return ("#" + "".join(c * 2 for c in m.groups())).upper()
    m = re.match(r"^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", v)
    if m:
        r, g, b = (min(255, int(x)) for x in m.groups())
        return f"#{r:02X}{g:02X}{b:02X}"
    return None


def repair(presentation: Any) -> tuple[dict, list[dict]]:
    """壊れた JSON を可能な範囲で修復し、(修復後, 修復内容の警告一覧) を返す。"""
    fixes: list[dict] = []
    if not isinstance(presentation, dict):
        fixes.append(warning("repair", "ROOT_NOT_OBJECT", "ルートがオブジェクトではないため空の資料へ置き換えました。"))
        return new_presentation(), fixes

    base = new_presentation()
    p: dict = presentation

    if not isinstance(p.get("schema_version"), str):
        p["schema_version"] = SCHEMA_VERSION
        fixes.append(warning("repair", "SCHEMA_VERSION_ADDED", "schema_version を補いました。"))
    elif p["schema_version"] != SCHEMA_VERSION and p["schema_version"].startswith("1."):
        # 1.0 → 1.1: 追加フィールドはすべて任意のため、版数を上げるだけで読める
        fixes.append(warning("repair", "SCHEMA_MIGRATED", f"schema_version {p['schema_version']} → {SCHEMA_VERSION} へ更新しました。"))
        p["schema_version"] = SCHEMA_VERSION
    for key in ("meta", "canvas", "theme"):
        if not isinstance(p.get(key), dict):
            p[key] = base[key]
            fixes.append(warning("repair", f"{key.upper()}_ADDED", f"{key} を既定値で補いました。"))
    for dim in ("width_pt", "height_pt"):
        try:
            v = float(p["canvas"].get(dim))
            if v <= 0:
                raise ValueError
            p["canvas"][dim] = v
        except (TypeError, ValueError):
            p["canvas"][dim] = base["canvas"][dim]
            fixes.append(warning("repair", "CANVAS_FIXED", f"canvas.{dim} を既定値へ戻しました。"))
    if not isinstance(p.get("assets"), dict):
        p["assets"] = {}
    if not isinstance(p.get("warnings"), list):
        p["warnings"] = []
    if not isinstance(p.get("slides"), list):
        p["slides"] = []
        fixes.append(warning("repair", "SLIDES_ADDED", "slides が配列ではないため空にしました。"))

    # テーマ色の正規化
    colors = p["theme"].get("colors")
    if isinstance(colors, dict):
        for k, v in list(colors.items()):
            nv = _normalize_color(v)
            if nv is None:
                colors[k] = base["theme"]["colors"].get(k, "#000000")
                fixes.append(warning("repair", "COLOR_FIXED", f"theme.colors.{k} を解釈できないため既定値にしました。"))
            else:
                colors[k] = nv
    else:
        p["theme"]["colors"] = base["theme"]["colors"]

    # 未知のトップレベルキーは削除（additionalProperties: false）
    allowed = {"schema_version", "meta", "canvas", "theme", "assets", "slides", "warnings"}
    for key in list(p.keys()):
        if key not in allowed:
            p.pop(key)
            fixes.append(warning("repair", "UNKNOWN_KEY_REMOVED", f"未知のキー '{key}' を削除しました。"))

    # スライド・要素の修復
    valid_slides = []
    for i, s in enumerate(p["slides"]):
        if not isinstance(s, dict):
            fixes.append(warning("repair", "SLIDE_DROPPED", f"{i + 1}番目のスライドがオブジェクトではないため除外しました。"))
            continue
        s.setdefault("id", f"s{i + 1:03d}")
        s["index"] = len(valid_slides)
        if s.get("layout") not in ("title", "section", "title_body", "two_column", "three_column", "image", "table", "blank", "closing"):
            s["layout"] = "title_body"
        if not isinstance(s.get("elements"), list):
            s["elements"] = []
        if not isinstance(s.get("warnings"), list):
            s["warnings"] = []
        valid_elements = []
        for j, el in enumerate(s["elements"]):
            if not isinstance(el, dict) or el.get("type") not in ("text", "image", "shape", "line", "table", "diagram", "unsupported"):
                fixes.append(warning("repair", "ELEMENT_DROPPED", "型が不明な要素を除外しました。", slide_id=s["id"]))
                continue
            el.setdefault("id", f"{s['id']}_e{j + 1:03d}")
            b = el.get("bbox")
            if isinstance(b, dict):
                bad = False
                for k in ("x", "y", "w", "h"):
                    try:
                        v = float(b.get(k, 0))
                        if v != v or v in (float("inf"), float("-inf")):  # NaN / inf
                            raise ValueError
                        b[k] = v
                    except (TypeError, ValueError):
                        b[k] = 0.0
                        bad = True
                if b["w"] < 0:
                    b["w"] = 0.0
                if b["h"] < 0:
                    b["h"] = 0.0
                # キャンバスの 2 倍を超える座標・寸法は丸める（出力側の整数変換であふれないように）
                cw, ch = float(p["canvas"]["width_pt"]), float(p["canvas"]["height_pt"])
                limits = {"x": (-cw, 2 * cw), "y": (-ch, 2 * ch), "w": (0.0, 2 * cw), "h": (0.0, 2 * ch)}
                for k, (lo, hi) in limits.items():
                    if b[k] < lo or b[k] > hi:
                        b[k] = min(hi, max(lo, b[k]))
                        bad = True
                if bad:
                    fixes.append(warning("repair", "BBOX_CLAMPED", "bbox の値が不正または範囲外のため丸めました。", slide_id=s["id"], element_id=el["id"]))
            elif b is not None:
                el["bbox"] = None
                fixes.append(warning("repair", "BBOX_FIXED", "bbox が不正なため自動レイアウトへ回しました。", slide_id=s["id"], element_id=el["id"]))
            if el["type"] in ("text", "shape"):
                el["paragraphs"] = _repair_paragraphs(el.get("paragraphs"), fixes, s["id"], el["id"])
            if el["type"] == "diagram":
                spec = el.get("diagram") if isinstance(el.get("diagram"), dict) else {}
                items = normalize_items(spec.get("items"))
                dtype = normalize_type(spec.get("type"))
                _min, maxn = item_limits(dtype)
                if len(items) > maxn:
                    items = items[:maxn]
                    fixes.append(warning("repair", "DIAGRAM_ITEMS_TRIMMED", f"図解「{word_of(dtype)}」の項目が多いため {maxn} 件に切り詰めました。", slide_id=s["id"], element_id=el["id"]))
                if not items:
                    fixes.append(warning("repair", "ELEMENT_DROPPED", "項目の無い図解要素を除外しました。", slide_id=s["id"]))
                    continue
                el["diagram"] = {"type": dtype, "items": items}
            if el["type"] == "table":
                el["rows"] = _repair_rows(el.get("rows"), fixes, s["id"], el["id"])
                if not isinstance(el.get("header_rows"), int) or el["header_rows"] < 0:
                    el["header_rows"] = 1 if el["rows"] else 0
            for ck in ("fill", "stroke"):
                if el.get(ck) is not None:
                    el[ck] = _normalize_color(el[ck])
            if el.get("font_scale") is not None:
                try:
                    el["font_scale"] = min(1.0, max(0.5, float(el["font_scale"])))
                except (TypeError, ValueError):
                    el.pop("font_scale", None)
                    fixes.append(warning("repair", "FONT_SCALE_FIXED", "font_scale が不正なため除去しました。", slide_id=s["id"], element_id=el["id"]))
            valid_elements.append(el)
        s["elements"] = valid_elements
        valid_slides.append(s)
    ids = {s["id"] for s in valid_slides}
    for s in valid_slides:
        if s.get("continuation_of") and s["continuation_of"] not in ids:
            s.pop("continuation_of", None)
            s.pop("continuation_index", None)
            fixes.append(warning("repair", "CONTINUATION_FIXED", "元スライドが無い続きページの印を外しました。", slide_id=s["id"]))
    p["slides"] = valid_slides
    return p, fixes


_MAX_FONT_PT = 400.0


def _repair_paragraphs(paras: Any, fixes: list[dict], slide_id: str, el_id: str) -> list[dict]:
    """段落・ランの型を強制する。文字列は 1 ランに、数値は文字列化、不明な物は除外。"""
    if not isinstance(paras, list):
        if paras is not None:
            fixes.append(warning("repair", "PARAGRAPHS_FIXED", "paragraphs が配列ではないため空にしました。", slide_id=slide_id, element_id=el_id))
        return []
    out: list[dict] = []
    dropped = False
    for para in paras:
        if isinstance(para, str):
            para = {"runs": [{"text": para}]}
        if not isinstance(para, dict):
            dropped = True
            continue
        runs = para.get("runs")
        if isinstance(runs, str):
            runs = [{"text": runs}]
        if not isinstance(runs, list):
            dropped = dropped or runs is not None
            runs = []
        clean_runs: list[dict] = []
        for r in runs:
            if isinstance(r, (str, int, float)):
                r = {"text": str(r)}
            if not isinstance(r, dict):
                dropped = True
                continue
            r["text"] = "" if r.get("text") is None else str(r["text"])
            if r.get("color") is not None:
                r["color"] = _normalize_color(r["color"])
            if r.get("size_pt") is not None:
                try:
                    size = float(r["size_pt"])
                    if size != size or size <= 0 or size > _MAX_FONT_PT:
                        raise ValueError
                    r["size_pt"] = size
                except (TypeError, ValueError):
                    r["size_pt"] = None
                    dropped = True
            clean_runs.append(r)
        para["runs"] = clean_runs
        try:
            para["level"] = max(0, min(8, int(para.get("level") or 0)))
        except (TypeError, ValueError):
            para["level"] = 0
        if para.get("bullet") not in ("bullet", "number", None):
            para["bullet"] = "bullet"
        if para.get("align") not in ("left", "center", "right", "justify", None):
            para["align"] = None
        out.append(para)
    if dropped:
        fixes.append(warning("repair", "PARAGRAPH_FIXED", "段落またはランの型が不正な部分を補正・除外しました。", slide_id=slide_id, element_id=el_id))
    return out


def _repair_rows(rows: Any, fixes: list[dict], slide_id: str, el_id: str) -> list[list[dict]]:
    """表の行・セルの型を強制する。文字列・数値のセルは {text} に包む。"""
    if not isinstance(rows, list):
        if rows is not None:
            fixes.append(warning("repair", "TABLE_FIXED", "rows が配列ではないため空にしました。", slide_id=slide_id, element_id=el_id))
        return []
    out: list[list[dict]] = []
    dropped = False
    for row in rows:
        if not isinstance(row, list):
            dropped = True
            continue
        cells: list[dict] = []
        for c in row:
            if isinstance(c, (str, int, float)) or c is None:
                c = {"text": "" if c is None else str(c)}
            if not isinstance(c, dict):
                dropped = True
                continue
            c["text"] = "" if c.get("text") is None else str(c["text"])
            for k in ("colspan", "rowspan"):
                try:
                    c[k] = max(1, int(c.get(k) or 1))
                except (TypeError, ValueError):
                    c[k] = 1
            if c.get("fill") is not None:
                c["fill"] = _normalize_color(c["fill"])
            if c.get("paragraphs") is not None:
                c["paragraphs"] = _repair_paragraphs(c["paragraphs"], fixes, slide_id, el_id)
            cells.append(c)
        if cells:
            out.append(cells)
    if dropped:
        fixes.append(warning("repair", "TABLE_FIXED", "表の行またはセルの型が不正な部分を補正・除外しました。", slide_id=slide_id, element_id=el_id))
    return out


def validate_and_repair(presentation: Any) -> tuple[dict, list[str], list[dict]]:
    """検証 → 失敗なら修復 → 再検証。(結果, 残った違反, 修復警告) を返す。"""
    errors = validate(presentation)
    if not errors and isinstance(presentation, dict):
        return presentation, [], []
    repaired, fixes = repair(presentation)
    remaining = validate(repaired)
    return repaired, remaining, fixes
