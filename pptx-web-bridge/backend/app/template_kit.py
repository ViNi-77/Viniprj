"""テンプレート部品（表紙・中身・最終ページ）の共通処理。

Web レンダラーと PPTX 生成器の両方が同じ判定・同じ座標を使うようにここへ集約する。
- スライド種別: cover（表紙）/ closing（最終ページ）/ content（中身）
- 画像資産: config/templates.json のパスを読み、base64 で返す（キャッシュ）
- 文字列置換: {title} {date} {organization} {page} {total}
- 座標: テンプレートは 960×540 基準。比率が違うキャンバスには相対的に拡縮する。
"""
from __future__ import annotations

import base64
import contextvars
import mimetypes
import re
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from .config import get_config, resource_path

_BASE_W, _BASE_H = 960.0, 540.0
_image_cache: dict[str, tuple[str, str]] = {}
# 未保存のテンプレート（PPTX から作成中の提案）で描画するときの一時的な上書き
_override: contextvars.ContextVar[dict | None] = contextvars.ContextVar("template_override", default=None)


@contextmanager
def use_template(template: dict | None) -> Iterator[None]:
    """この with の中では、資料の template_id に関係なく与えたテンプレート定義を使う（プレビュー用）。"""
    token = _override.set(template)
    try:
        yield
    finally:
        _override.reset(token)


def slide_kind(slide: dict, presentation: dict) -> str:
    """表紙 / 最終ページ / 中身 を判定する。表紙は layout=title の先頭スライドのみ。"""
    layout = slide.get("layout")
    if layout == "closing":
        return "closing"
    if layout == "title" and int(slide.get("index", 0)) == 0:
        return "cover"
    return "content"


def template_for(presentation: dict) -> dict:
    forced = _override.get()
    if forced is not None:
        return forced
    return get_config().template(presentation.get("theme", {}).get("template_id"))


def has_parts(template: dict) -> bool:
    """cover / content / closing の定義を持つ「部品付きテンプレート」か。"""
    return any(isinstance(template.get(k), dict) for k in ("cover", "content", "closing"))


def scale(box: dict, canvas: dict) -> dict:
    """テンプレート座標（960×540 基準）をキャンバスへ写像する。"""
    sx = float(canvas.get("width_pt", _BASE_W)) / _BASE_W
    sy = float(canvas.get("height_pt", _BASE_H)) / _BASE_H
    out = dict(box)
    for k, f in (("x", sx), ("y", sy), ("w", sx), ("h", sy)):
        if k in out and out[k] is not None:
            out[k] = round(float(out[k]) * f, 2)
    return out


def image_data(rel_path: str | None) -> tuple[str, str] | None:
    """(mime, base64) を返す。存在しなければ None（呼び出し側はロゴ無しで続行）。"""
    if not rel_path:
        return None
    p = resource_path(rel_path)
    if not p.exists():
        return None
    key = f"{rel_path}@{p.stat().st_mtime_ns}"  # 作り直したユーザーテンプレートの画像を古いキャッシュで描かない
    if key in _image_cache:
        return _image_cache[key]
    mime = mimetypes.guess_type(str(p))[0] or "image/png"
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    _image_cache[key] = (mime, data)
    return _image_cache[key]


def image_size(rel_path: str | None) -> tuple[int, int] | None:
    """画像の画素寸法（縦横比の維持に使う）。"""
    if not rel_path:
        return None
    p = resource_path(rel_path)
    try:
        from PIL import Image

        with Image.open(p) as im:
            return im.size
    except Exception:  # noqa: BLE001
        return None


def logo_box(part: dict, canvas: dict) -> dict | None:
    """ロゴ定義 {image, x, y, w} から高さを縦横比で補った bbox を返す。"""
    logo = part.get("logo") if isinstance(part, dict) else None
    if not logo or not logo.get("image"):
        return None
    size = image_size(logo["image"])
    if not size:
        return None
    w = float(logo.get("w", 120))
    h = w * size[1] / size[0]
    return scale({"x": float(logo.get("x", 0)), "y": float(logo.get("y", 0)), "w": w, "h": h, "image": logo["image"]}, canvas)


def substitute(text: str, presentation: dict, template: dict, slide: dict | None = None, part: dict | None = None) -> str:
    """フッター等の文字列に含まれるプレースホルダを置換する。"""
    if not text:
        return ""
    part = part or {}
    fmt = str(part.get("date_format") or template.get("date_format") or "%Y-%m-%d")
    today_d = date.today()
    # '%-d' '%-m'（先頭ゼロ無し）は Windows の strftime では使えないため、先に数値へ置き換える
    fmt = fmt.replace("%-d", str(today_d.day)).replace("%-m", str(today_d.month)).replace("%-H", str(today_d.strftime("%H")).lstrip("0") or "0")
    try:
        today = today_d.strftime(fmt)
    except ValueError:
        today = today_d.isoformat()
    total = len(presentation.get("slides", []))
    page = int(slide.get("index", 0)) + 1 if slide else 0
    values = {
        "{title}": presentation.get("meta", {}).get("title", ""),
        "{date}": today,
        "{organization}": str(part.get("organization") or template.get("organization") or ""),
        "{page}": str(page),
        "{total}": str(total),
    }
    for k, v in values.items():
        text = text.replace(k, v)
    return text


def content_area(template: dict, canvas: dict) -> dict | None:
    """中身スライドの本文領域（テンプレートの content.body）をキャンバス座標で返す。無ければ None（余白既定を使う）。"""
    content = template.get("content") if isinstance(template, dict) else None
    body = content.get("body") if isinstance(content, dict) else None
    if not isinstance(body, dict) or not all(k in body for k in ("x", "y", "w", "h")):
        return None
    b = scale({k: float(body[k]) for k in ("x", "y", "w", "h")}, canvas)
    if b["w"] < 100 or b["h"] < 60:
        return None
    return b


def content_title_box(template: dict, canvas: dict) -> dict | None:
    """中身スライドの題名枠（content.title の x/y/w/h）。座標が無い定義なら None。"""
    content = template.get("content") if isinstance(template, dict) else None
    t = content.get("title") if isinstance(content, dict) else None
    if not isinstance(t, dict) or not all(k in t for k in ("x", "y", "w", "h")):
        return None
    return scale({k: float(t[k]) for k in ("x", "y", "w", "h")}, canvas)


def closing_message_box(template: dict, canvas: dict) -> dict | None:
    closing = template.get("closing") if isinstance(template, dict) else None
    m = closing.get("message") if isinstance(closing, dict) else None
    if not isinstance(m, dict) or not all(k in m for k in ("x", "y", "w", "h")):
        return None
    return scale({k: float(m[k]) for k in ("x", "y", "w", "h")}, canvas)


def apply_cover_positions(slide: dict, presentation: dict, template: dict) -> None:
    """表紙スライドの title / subtitle を、テンプレートの表紙定義の位置・色・サイズへ揃える。"""
    cover = template.get("cover")
    if not isinstance(cover, dict):
        return
    canvas = presentation["canvas"]
    # 表紙背景（紺など）に対して読めるよう、表紙上の文字はすべて題名定義の色へ寄せる
    title_color = (cover.get("title") or {}).get("color")
    if title_color:
        for el in slide.get("elements", []):
            if el.get("type") == "text":
                for para in el.get("paragraphs", []):
                    for r in para.get("runs", []):
                        r["color"] = title_color
    placed: list[dict] = []
    bottom = None
    for role in ("title", "subtitle"):
        spec = cover.get(role)
        if not isinstance(spec, dict):
            continue
        # 座標が欠けた設定でも止めない（既定の表紙位置で補う）
        defaults = {"title": (60, 235, 660, 80), "subtitle": (60, 335, 660, 44)}[role]
        box = scale({k: float(spec.get(k, d)) for k, d in zip(("x", "y", "w", "h"), defaults)}, canvas)
        for el in slide.get("elements", []):
            if el.get("type") == "text" and el.get("role") == role:
                if not el.get("user_bbox"):  # 利用者が動かした枠はテンプレート位置で上書きしない
                    el["bbox"] = {"x": box["x"], "y": box["y"], "w": box["w"], "h": box["h"]}
                    el["vertical_align"] = el.get("vertical_align") or "middle"
                for para in el.get("paragraphs", []):
                    para["align"] = spec.get("align") or para.get("align")
                    for r in para.get("runs", []):
                        r["color"] = spec.get("color") or r.get("color")
                        r["size_pt"] = float(spec.get("size_pt")) if spec.get("size_pt") else r.get("size_pt")
                        if spec.get("bold") is not None:
                            r["bold"] = bool(spec.get("bold"))
                placed.append(el)
                bottom = box["y"] + box["h"]
                break
    # 題名・副題以外の文字（説明文など）は、副題の下へ順に積み直して重なりを避ける
    others = sorted([el for el in slide.get("elements", []) if el.get("type") == "text" and el not in placed and el.get("bbox") and not el.get("user_bbox")], key=lambda e: e["bbox"]["y"])
    if others and bottom is not None:
        ref = scale({"x": float((cover.get("title") or {}).get("x", 60)), "w": float((cover.get("title") or {}).get("w", 660))}, canvas)
        y = bottom + 10
        limit = float(canvas.get("height_pt", _BASE_H)) - 40
        for el in others:
            h = float(el["bbox"]["h"])
            if y + h > limit:
                h = max(20.0, limit - y)
            el["bbox"] = {"x": ref["x"], "y": round(y, 2), "w": ref["w"], "h": round(h, 2)}
            y += h + 6


def apply_content_title_positions(slide: dict, presentation: dict, template: dict) -> None:
    """中身スライドの題名を、テンプレートの題名定義（位置・色・サイズ）に揃える。座標は既存を尊重し、色とサイズのみ既定値を補う。"""
    content = template.get("content")
    if not isinstance(content, dict) or not isinstance(content.get("title"), dict):
        return
    spec = content["title"]
    for el in slide.get("elements", []):
        if el.get("type") == "text" and el.get("role") == "title":
            for para in el.get("paragraphs", []):
                for r in para.get("runs", []):
                    inh = set(r.get("inherited") or [])
                    # 明示指定は保持し、無い／継承で補った値だけテンプレートで上書きする
                    if (not r.get("color") or "color" in inh) and spec.get("color"):
                        r["color"] = spec["color"]
                    if (not r.get("size_pt") or "size_pt" in inh) and spec.get("size_pt"):
                        r["size_pt"] = float(spec["size_pt"])
                    if (not r.get("font") or "font" in inh) and spec.get("font"):
                        r["font"] = spec["font"]
            break


def apply_template(presentation: dict) -> dict:
    """テンプレートの部品定義を資料へ反映する（表紙位置、題名の色・サイズ）。部品を持たないテンプレートでは何もしない。"""
    template = template_for(presentation)
    if not has_parts(template):
        return presentation
    for s in presentation.get("slides", []):
        kind = slide_kind(s, presentation)
        if kind == "cover":
            apply_cover_positions(s, presentation, template)
        elif kind == "content":
            apply_content_title_positions(s, presentation, template)
    return presentation


def make_closing_slide(slide_id: str, index: int, message: str = "") -> dict:
    """最終ページ（ロゴ中央）の雛形。message は任意の一言。"""
    from .model import new_slide, paragraph, run, text_element

    s = new_slide(slide_id, index, layout="closing", title="最終ページ")
    if message:
        s["elements"].append(text_element(f"{slide_id}_msg", [paragraph([run(message)], align="center")], role="body"))
    return s


def chrome_spec(slide: dict, presentation: dict) -> dict[str, Any]:
    """レンダラー/生成器が描くべきテンプレート部品を、キャンバス座標で列挙する。

    返り値: {"kind", "background_color", "background_image", "images": [{"image","x","y","w","h","name"}],
             "bars": [{"x","y","w","h","color","slant_pt"}], "texts": [{"text","x","y","w","h","size_pt","color","align","name"}]}
    """
    template = template_for(presentation)
    canvas = presentation["canvas"]
    kind = slide_kind(slide, presentation)
    spec: dict[str, Any] = {"kind": kind, "background_color": None, "background_image": None, "images": [], "bars": [], "texts": []}
    if not has_parts(template):
        # 旧式（footer / confidential_mark のみ）のテンプレート
        footer = template.get("footer") or {}
        cw, ch = float(canvas["width_pt"]), float(canvas["height_pt"])
        if footer.get("enabled") and kind != "cover":
            spec["texts"].append({"text": substitute(str(footer.get("text", "")), presentation, template, slide), "x": 24, "y": ch - 24, "w": cw * 0.6, "h": 18, "size_pt": 9, "color": template.get("colors", {}).get("muted", "#666666"), "align": "left", "name": "footer"})
            if footer.get("show_page_number"):
                spec["texts"].append({"text": str(int(slide.get("index", 0)) + 1), "x": cw - 84, "y": ch - 24, "w": 60, "h": 18, "size_pt": 9, "color": template.get("colors", {}).get("muted", "#666666"), "align": "right", "name": "page_number"})
        conf = template.get("confidential_mark") or {}
        if conf.get("enabled") and conf.get("text"):
            spec["texts"].append({"text": str(conf["text"]), "x": cw - 160, "y": 8, "w": 140, "h": 18, "size_pt": 9, "color": "#C0392B", "align": "right", "name": "confidential"})
        return spec

    part = template.get(kind) or {}
    spec["background_color"] = part.get("background_color")
    if part.get("background_image") and image_data(part["background_image"]):
        spec["background_image"] = part["background_image"]
        spec["background_source"] = part.get("background_source") or "slide"
    lb = logo_box(part, canvas)
    if lb and image_data(lb["image"]):
        spec["images"].append({**lb, "name": "logo", "source": (part.get("logo") or {}).get("source", "slide")})
    # 追加の装飾画像（PPTX から作ったテンプレートで複数の画像がある場合）
    for i, img in enumerate(part.get("images") or []):
        if not isinstance(img, dict) or not img.get("image") or not image_data(img["image"]):
            continue
        b = scale(img, canvas)
        spec["images"].append({"image": img["image"], "x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"], "name": f"decor{i + 1}", "source": img.get("source", "slide")})
    sx = float(canvas.get("width_pt", _BASE_W)) / _BASE_W
    bars = [part["bar"]] if isinstance(part.get("bar"), dict) else []
    bars += [b for b in (part.get("bars") or []) if isinstance(b, dict)]
    for i, bar in enumerate(bars):
        b = scale(bar, canvas)
        spec["bars"].append({"x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"], "color": bar.get("color", "#000000"), "slant_pt": round(float(bar.get("slant_pt", 0)) * sx, 2), "name": "bar" if i == 0 else f"bar{i + 1}", "source": bar.get("source", "slide")})
    for key in ("footer", "page_number"):
        t = part.get(key)
        if not isinstance(t, dict):
            continue
        text = substitute(str(t.get("text", "{page}" if key == "page_number" else "")), presentation, template, slide, part)
        if key == "page_number" and not t.get("text"):
            text = str(int(slide.get("index", 0)) + 1)
        if not text:
            continue
        b = scale(t, canvas)
        spec["texts"].append({"text": text, "x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"], "size_pt": float(t.get("size_pt", 9)), "color": t.get("color", "#666666"), "align": t.get("align", "left"), "name": key, "source": t.get("source", "slide")})
    return spec


TEMPLATE_CHROME_NAMES = {"footer", "page_number", "confidential", "logo", "bar", "cover_background"}
_CHROME_NAME_RE = re.compile(r"^(footer|page_number|confidential|logo|bar|cover_background|decor)\d*$")


def is_chrome_name(name: str | None) -> bool:
    """本アプリが出力したテンプレート部品の図形名か（再読込時に除外する）。bar2 / decor1 のような連番も含む。"""
    return bool(name) and bool(_CHROME_NAME_RE.match(str(name)))
