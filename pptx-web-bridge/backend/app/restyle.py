"""テンプレートの「適用」= 資料全体の着せ替え。

これまでの適用はロゴ・帯・フッターを背面に重ねるだけで、取り込んだ資料の文字色・
フォント・題名の位置は元のままだった（＝ PowerPoint の「デザイン適用」に見えない）。
ここでは資料そのものをテンプレートへ寄せる:

1. 全面を覆う塗り図形をスライドの背景に畳み込む（テンプレートの部品が隠れるのを防ぐ）
2. 題名・副題をテンプレートの枠へ移し、色・大きさ・フォントを合わせる
3. 資料でよく使われている色を、テンプレートの色（primary / accent / text / muted …）へ対応表で置換
4. フォントをテンプレートの見出し・本文フォントに統一
5. 本文領域からはみ出す固定要素を、領域に収まるよう一括で拡縮・平行移動

変更前の状態は `meta.original_style` に残し、`unstyle()` で元に戻せる。
同じテンプレートで 2 回適用しても変化しない（`meta.restyled_with`）。
"""
from __future__ import annotations

import copy
from typing import Any

from . import template_kit
from .logging_setup import get_logger

log = get_logger("restyle")

# 置換先の色の役割（テンプレートの colors のキー）
_ROLE_KEYS = ("primary", "accent", "text", "muted", "surface", "line", "background")
_BACKGROUND_AREA_RATIO = 0.9  # これ以上を覆う塗り図形は背景とみなす
_MIN_COLOR_USES = 2  # 対応表に載せるのは 2 回以上使われている色だけ（写真的な多色を触らない）


# ---------------------------------------------------------------- 色の道具
def _rgb(hex_color: str) -> tuple[int, int, int] | None:
    s = str(hex_color or "").strip()
    if not s.startswith("#") or len(s) != 7:
        return None
    try:
        return (int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16))
    except ValueError:
        return None


def _hsl(hex_color: str) -> tuple[float, float, float] | None:
    rgb = _rgb(hex_color)
    if rgb is None:
        return None
    r, g, b = (v / 255.0 for v in rgb)
    mx, mn = max(r, g, b), min(r, g, b)
    light = (mx + mn) / 2
    if mx == mn:
        return (0.0, 0.0, light)
    d = mx - mn
    denom = 1 - abs(2 * light - 1)
    sat = d / denom if denom else 0.0
    if mx == r:
        hue = ((g - b) / d) % 6
    elif mx == g:
        hue = (b - r) / d + 2
    else:
        hue = (r - g) / d + 4
    return (hue * 60.0, sat, light)


def _hue_gap(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _norm(hex_color: Any) -> str | None:
    s = str(hex_color or "").strip().upper()
    return s if _rgb(s) else None


def _text_runs(el: dict):
    for para in el.get("paragraphs", []) or []:
        for r in para.get("runs", []) or []:
            yield r


# ---------------------------------------------------------------- 色の対応表
def collect_colors(presentation: dict) -> dict[str, int]:
    """資料で使われている色と回数（文字色・図形の塗り・線）。"""
    counts: dict[str, int] = {}

    def bump(c: Any, n: int = 1) -> None:
        h = _norm(c)
        if h:
            counts[h] = counts.get(h, 0) + n

    for s in presentation.get("slides", []):
        bump((s.get("background") or {}).get("color"))
        for el in s.get("elements", []):
            bump(el.get("fill"))
            bump(el.get("stroke"))
            for r in _text_runs(el):
                bump(r.get("color"))
            for row in el.get("rows", []) or []:
                for cell in row:
                    bump(cell.get("fill"))
    return counts


def build_color_map(presentation: dict, template: dict) -> dict[str, str]:
    """資料の色 → テンプレートの色。確信の持てる色だけを載せる（写真や図解の多色は触らない）。

    判定は明度と彩度だけ: 鮮やかで最もよく使われている色 → primary、色相が離れた鮮やかな色 → accent、
    暗い無彩色 → text、中間の無彩色 → muted、明るい無彩色 → surface / line、白 → background。
    """
    tpl = {k: _norm((template.get("colors") or {}).get(k)) for k in _ROLE_KEYS}
    counts = collect_colors(presentation)
    used = [(c, n) for c, n in counts.items() if n >= _MIN_COLOR_USES and _hsl(c)]
    if not used:
        return {}
    used.sort(key=lambda t: -t[1])
    mapping: dict[str, str] = {}
    primary_hue: float | None = None
    for color, _n in used:
        hue, sat, light = _hsl(color)  # type: ignore[misc]
        target: str | None = None
        if sat >= 0.18 and 0.12 <= light <= 0.75:  # 鮮やかな色
            if primary_hue is None:
                target, primary_hue = tpl.get("primary"), hue
            elif _hue_gap(hue, primary_hue) >= 25:
                target = tpl.get("accent")
            else:
                target = tpl.get("primary")
        elif light <= 0.3:
            target = tpl.get("text")
        elif light >= 0.93:
            target = tpl.get("background")
        elif light >= 0.8:
            target = tpl.get("surface") or tpl.get("line")
        elif sat < 0.18:
            target = tpl.get("muted")
        if target and target != color:
            mapping[color] = target
    return mapping


# ---------------------------------------------------------------- 変更前の記録
def _snapshot_element(el: dict) -> dict:
    keep = {k: copy.deepcopy(el[k]) for k in ("bbox", "fill", "stroke", "vertical_align", "font_pt") if k in el}
    if el.get("paragraphs"):
        keep["paragraphs"] = copy.deepcopy(el["paragraphs"])
    if el.get("rows"):
        keep["rows"] = copy.deepcopy(el["rows"])
    return keep


def _record(store: dict, slide: dict, el: dict) -> None:
    slot = store.setdefault(slide["id"], {"background": copy.deepcopy(slide.get("background")), "elements": {}})
    slot["elements"].setdefault(el["id"], _snapshot_element(el))


def _record_slide(store: dict, slide: dict) -> None:
    store.setdefault(slide["id"], {"background": copy.deepcopy(slide.get("background")), "elements": {}})


# ---------------------------------------------------------------- 各工程
def fold_background_shapes(slide: dict, canvas: dict, store: dict, report: dict) -> None:
    """スライド全面を覆う塗り図形を背景に畳み込む（テンプレートのロゴ・帯が隠れるのを防ぐ）。"""
    cw, ch = float(canvas["width_pt"]), float(canvas["height_pt"])
    area = cw * ch
    keep: list[dict] = []
    for el in slide.get("elements", []):
        b = el.get("bbox") or {}
        covers = el.get("type") == "shape" and not el.get("paragraphs") and el.get("fill") and b and (float(b.get("w", 0)) * float(b.get("h", 0))) >= area * _BACKGROUND_AREA_RATIO
        if covers:
            _record_slide(store, slide)
            store[slide["id"]].setdefault("removed", []).append(copy.deepcopy(el))
            slide["background"] = {**(slide.get("background") or {}), "color": _norm(el["fill"]) or el["fill"]}
            report["folded_backgrounds"] += 1
            continue
        keep.append(el)
    slide["elements"] = keep


def apply_colors_and_fonts(slide: dict, cmap: dict[str, str], fonts: dict, store: dict, report: dict) -> None:
    """色の対応表とテンプレートのフォントを、文字・図形・表へ当てる。"""
    heading, body = _norm_font(fonts.get("heading")), _norm_font(fonts.get("body"))
    for el in slide.get("elements", []):
        changed = False
        font = heading if el.get("role") in ("title", "subtitle") else body
        for r in _text_runs(el):
            new_color = cmap.get(_norm(r.get("color")) or "")
            if new_color:
                if not changed:
                    _record(store, slide, el)
                    changed = True
                r["color"] = new_color
                report["colors"] += 1
            if font and r.get("font") != font:
                if not changed:
                    _record(store, slide, el)
                    changed = True
                r["font"] = font
                r["inherited"] = [k for k in (r.get("inherited") or []) if k != "font"]
                report["fonts"] += 1
        for key in ("fill", "stroke"):
            new_color = cmap.get(_norm(el.get(key)) or "")
            if new_color:
                if not changed:
                    _record(store, slide, el)
                    changed = True
                el[key] = new_color
                report["colors"] += 1
        for row in el.get("rows", []) or []:
            for cell in row:
                new_color = cmap.get(_norm(cell.get("fill")) or "")
                if new_color:
                    if not changed:
                        _record(store, slide, el)
                        changed = True
                    cell["fill"] = new_color
                    report["colors"] += 1


def _norm_font(name: Any) -> str | None:
    s = str(name or "").strip()
    return s or None


def move_titles(slide: dict, kind: str, presentation: dict, template: dict, store: dict, report: dict) -> None:
    """題名・副題をテンプレートの枠へ移し、色・大きさ・フォント・揃えを合わせる（手で動かした枠は尊重）。"""
    part = template.get("cover" if kind == "cover" else "content")
    if not isinstance(part, dict):
        return
    canvas = presentation["canvas"]
    roles = ("title", "subtitle") if kind == "cover" else ("title",)
    for role in roles:
        spec = part.get(role)
        if not isinstance(spec, dict) or not all(k in spec for k in ("x", "y", "w", "h")):
            continue
        box = template_kit.scale({k: float(spec[k]) for k in ("x", "y", "w", "h")}, canvas)
        for el in slide.get("elements", []):
            if el.get("type") != "text" or el.get("role") != role:
                continue
            _record(store, slide, el)
            if not el.get("user_bbox"):
                el["bbox"] = {"x": box["x"], "y": box["y"], "w": box["w"], "h": box["h"]}
                el["vertical_align"] = el.get("vertical_align") or "middle"
                report["titles_moved"] += 1
            for para in el.get("paragraphs", []):
                if spec.get("align"):
                    para["align"] = spec["align"]
                for r in para.get("runs", []):
                    if spec.get("color"):
                        r["color"] = spec["color"]
                    if spec.get("size_pt"):
                        r["size_pt"] = float(spec["size_pt"])
                    if spec.get("font"):
                        r["font"] = spec["font"]
                    if spec.get("bold") is not None:
                        r["bold"] = bool(spec["bold"])
                    r["inherited"] = []
            el["font_pt"] = float(spec["size_pt"]) if spec.get("size_pt") else el.get("font_pt")
            report["titles_styled"] += 1
            break


def fit_into_content_area(slide: dict, kind: str, presentation: dict, template: dict, store: dict, report: dict) -> None:
    """本文領域からはみ出す固定要素を、領域に収まるよう一括で拡縮・平行移動する（縦横比は保つ）。"""
    if kind != "content":
        return
    area = template_kit.content_area(template, presentation["canvas"])
    if not area:
        return
    movable = [el for el in slide.get("elements", []) if el.get("bbox") and not el.get("user_bbox") and el.get("role") != "title"]
    if not movable:
        return
    xs = [float(el["bbox"]["x"]) for el in movable]
    ys = [float(el["bbox"]["y"]) for el in movable]
    x2 = [float(el["bbox"]["x"]) + float(el["bbox"]["w"]) for el in movable]
    y2 = [float(el["bbox"]["y"]) + float(el["bbox"]["h"]) for el in movable]
    bx, by, bw, bh = min(xs), min(ys), max(x2) - min(xs), max(y2) - min(ys)
    if bw <= 0 or bh <= 0:
        return
    ax, ay, aw, ah = float(area["x"]), float(area["y"]), float(area["w"]), float(area["h"])
    if bx >= ax - 1 and by >= ay - 1 and bx + bw <= ax + aw + 1 and by + bh <= ay + ah + 1:
        return  # 既に収まっている
    k = min(1.0, aw / bw, ah / bh)
    for el in movable:
        _record(store, slide, el)
        b = el["bbox"]
        el["bbox"] = {
            "x": round(ax + (float(b["x"]) - bx) * k, 2),
            "y": round(ay + (float(b["y"]) - by) * k, 2),
            "w": round(float(b["w"]) * k, 2),
            "h": round(float(b["h"]) * k, 2),
        }
        if k < 0.999:
            el["font_scale"] = round(max(0.5, min(1.0, float(el.get("font_scale", 1.0)) * k)), 2)
    report["fitted"] += len(movable)


# ---------------------------------------------------------------- 入口
def new_report() -> dict:
    return {"folded_backgrounds": 0, "colors": 0, "fonts": 0, "titles_moved": 0, "titles_styled": 0, "fitted": 0, "color_map": {}, "template_id": None, "slides": 0}


def restyle(presentation: dict, template: dict | None = None) -> tuple[dict, dict]:
    """資料をテンプレートへ着せ替える。返り値: (資料, レポート)。同じテンプレートで 2 回目は何もしない。"""
    pres = copy.deepcopy(presentation)
    template = template or template_kit.template_for(pres)
    report = new_report()
    report["template_id"] = template.get("id")
    if not template_kit.has_parts(template):
        report["skipped"] = "部品を持たないテンプレートのため、着せ替えはしません。"
        return pres, report
    meta = pres.setdefault("meta", {})
    if meta.get("restyled_with") == template.get("id"):
        report["skipped"] = "このテンプレートで既に着せ替え済みです。"
        return pres, report
    if meta.get("restyled_with"):  # 別のテンプレートで着せ替え済み → まず元へ戻す
        pres = unstyle(pres)[0]
        meta = pres.setdefault("meta", {})

    store: dict[str, Any] = {}
    cmap = build_color_map(pres, template)
    fonts = template.get("fonts") or {}
    report["color_map"] = cmap
    for slide in pres.get("slides", []):
        kind = template_kit.slide_kind(slide, pres)
        fold_background_shapes(slide, pres["canvas"], store, report)
        move_titles(slide, kind, pres, template, store, report)
        apply_colors_and_fonts(slide, cmap, fonts, store, report)
        fit_into_content_area(slide, kind, pres, template, store, report)
        report["slides"] += 1
    theme = pres.setdefault("theme", {})
    theme["template_id"] = template.get("id")
    theme["colors"] = dict(template.get("colors", {}))
    theme["fonts"] = dict(fonts)
    meta["restyled_with"] = template.get("id")
    meta["original_style"] = store
    log.info("着せ替え: template=%s slides=%d colors=%d fonts=%d titles=%d fitted=%d", template.get("id"), report["slides"], report["colors"], report["fonts"], report["titles_styled"], report["fitted"])
    return pres, report


def unstyle(presentation: dict) -> tuple[dict, dict]:
    """着せ替えを取り消して元の見た目へ戻す。返り値: (資料, レポート)。"""
    pres = copy.deepcopy(presentation)
    meta = pres.setdefault("meta", {})
    store = meta.get("original_style") or {}
    report = {"restored": 0, "slides": 0, "template_id": meta.get("restyled_with")}
    if not store:
        report["skipped"] = "着せ替えの記録がありません。"
        return pres, report
    for slide in pres.get("slides", []):
        slot = store.get(slide["id"])
        if not slot:
            continue
        slide["background"] = copy.deepcopy(slot.get("background"))
        by_id = {el["id"]: el for el in slide.get("elements", [])}
        for el_id, saved in (slot.get("elements") or {}).items():
            el = by_id.get(el_id)
            if not el:
                continue
            for key, value in saved.items():
                el[key] = copy.deepcopy(value)
            report["restored"] += 1
        for removed in slot.get("removed") or []:
            if removed["id"] not in by_id:
                slide.setdefault("elements", []).insert(0, copy.deepcopy(removed))
                report["restored"] += 1
        report["slides"] += 1
    meta.pop("original_style", None)
    meta.pop("restyled_with", None)
    return pres, report


def summary_text(report: dict) -> str:
    """画面に出す 1 行の要約。"""
    if report.get("skipped"):
        return str(report["skipped"])
    return (
        f"色 {report['colors']} か所 / フォント {report['fonts']} か所 / 題名 {report['titles_styled']} 枚 / "
        f"背景の畳み込み {report['folded_backgrounds']} 枚 / 収め直し {report['fitted']} 要素"
    )
