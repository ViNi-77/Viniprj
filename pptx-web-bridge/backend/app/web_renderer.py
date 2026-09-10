"""Presentation JSON → Web図解（静的 HTML 一式）。

- 1pt = 1px の座標系でスライドを描き、ビューア JS が画面に合わせて拡縮する。
- 出力は index.html / viewer.css / viewer.js / presentation.json / assets/*。
- プレビュー用に画像を data URI で埋め込んだ単一 HTML も生成できる。
"""
from __future__ import annotations

import base64
import html
import json
import mimetypes
from pathlib import Path

from . import template_kit
from .config import get_config
from .model import slide_title
from .typography import effective_size, element_font_pt, font_scale, role_default_pt

_VIEWER_DIR = Path(__file__).resolve().parent / "viewer"
_SAFE_HREF_PREFIXES = ("http://", "https://", "mailto:")


def _esc(s: str) -> str:
    return html.escape(str(s or ""), quote=True)


def _run_html(r: dict, el: dict | None = None) -> str:
    styles = []
    if r.get("bold"):
        styles.append("font-weight:bold")
    if r.get("italic"):
        styles.append("font-style:italic")
    if r.get("underline"):
        styles.append("text-decoration:underline")
    if r.get("size_pt"):
        styles.append(f"font-size:{effective_size(r, el or {}):g}px")
    if r.get("color"):
        styles.append(f"color:{_esc(r['color'])}")
    if r.get("font") and "font" not in (r.get("inherited") or []):
        styles.append(f"font-family:'{_esc(r['font'])}',var(--font)")  # 継承フォント（テーマ latin 名）はテーマ既定に任せる
    text = _esc(r.get("text", ""))
    inner = f'<span style="{";".join(styles)}">{text}</span>' if styles else text
    href = r.get("href")
    if href and str(href).lower().startswith(_SAFE_HREF_PREFIXES):
        return f'<a href="{_esc(href)}" target="_blank" rel="noopener">{inner}</a>'
    return inner


def paragraphs_html(paragraphs: list[dict], el: dict | None = None) -> str:
    """段落列を HTML へ。連続する箇条書きは ul/ol にまとめる。"""
    out: list[str] = []
    open_list: str | None = None
    for p in paragraphs:
        runs_html = "".join(_run_html(r, el) for r in p.get("runs", [])) or "&nbsp;"
        align = p.get("align")
        cls = f' class="align-{_esc(align)}"' if align in ("center", "right", "justify") else ""
        bullet = p.get("bullet")
        level = int(p.get("level", 0) or 0)
        if bullet in ("bullet", "number"):
            tag = "ul" if bullet == "bullet" else "ol"
            if open_list != tag:
                if open_list:
                    out.append(f"</{open_list}>")
                out.append(f"<{tag}>")
                open_list = tag
            out.append(f'<li class="level-{level}"{cls}>{runs_html}</li>')
        else:
            if open_list:
                out.append(f"</{open_list}>")
                open_list = None
            out.append(f"<p{cls}>{runs_html}</p>")
    if open_list:
        out.append(f"</{open_list}>")
    return "".join(out)


def _bbox_style(b: dict | None, z: int = 0, rotation: float | None = None) -> str:
    if not b:
        return ""
    rot = f";transform:rotate({float(rotation):g}deg)" if rotation else ""
    return f"left:{b['x']:g}px;top:{b['y']:g}px;width:{b['w']:g}px;height:{b['h']:g}px;z-index:{z}{rot}"


def _asset_src(presentation: dict, asset_id: str | None, inline_assets: bool) -> str | None:
    asset = presentation.get("assets", {}).get(asset_id or "")
    if not asset:
        return None
    if inline_assets:
        return f"data:{asset.get('mime', 'image/png')};base64,{asset.get('data_base64', '')}"
    return f"assets/{asset_filename(asset_id, asset)}"


def asset_filename(asset_id: str, asset: dict) -> str:
    name = asset.get("filename")
    if name:
        return name
    ext = mimetypes.guess_extension(asset.get("mime", "image/png")) or ".bin"
    return f"{asset_id}{ext}"


def element_html(el: dict, presentation: dict, inline_assets: bool) -> str:
    t = el.get("type")
    z = int(el.get("z", 0) or 0)
    style = _bbox_style(el.get("bbox"), z, el.get("rotation_deg"))
    role = el.get("role")
    eid = _esc(el.get("id", ""))
    if t == "text":
        size = element_font_pt(el) * font_scale(el)
        va = el.get("vertical_align")
        cls = f"el el-text role-{role or 'body'}" + (f" va-{va}" if va in ("middle", "bottom") else "")
        fill = f"background:{_esc(el['fill'])};" if el.get("fill") else ""
        return f'<div class="{cls}" id="{eid}" style="{style};font-size:{size:g}px;{fill}">{paragraphs_html(el.get("paragraphs", []), el)}</div>'
    if t == "shape":
        size = element_font_pt(el) * font_scale(el)
        shape = el.get("shape") or "rect"
        radius = {
            "rounded_rect": "border-radius:10px;",
            "ellipse": "border-radius:50%;",
            "triangle": "clip-path:polygon(50% 0,100% 100%,0 100%);",
            "diamond": "clip-path:polygon(50% 0,100% 50%,50% 100%,0 50%);",
            "arrow_right": "clip-path:polygon(0 25%,65% 25%,65% 0,100% 50%,65% 100%,65% 75%,0 75%);",
            "parallelogram": "clip-path:polygon(12% 0,100% 0,88% 100%,0 100%);",
        }.get(shape, "")
        fill = f"background:{_esc(el['fill'])};" if el.get("fill") else ""
        stroke = f"border:{float(el.get('stroke_width_pt') or 1):g}px solid {_esc(el['stroke'])};" if el.get("stroke") else ""
        va = el.get("vertical_align") or "middle"
        jc = {"top": "flex-start", "bottom": "flex-end"}.get(va, "center")
        return f'<div class="el el-shape shape-{_esc(shape)}" id="{eid}" style="{style};font-size:{size:g}px;{fill}{stroke}{radius}justify-content:{jc};">{paragraphs_html(el.get("paragraphs", []), el)}</div>'
    if t == "image":
        src = _asset_src(presentation, el.get("asset_id"), inline_assets)
        fit = {"cover": "cover", "stretch": "fill"}.get(el.get("fit") or "contain", "contain")
        if not src:
            label = _esc(el.get("alt") or "画像")
            return f'<div class="el el-image placeholder" id="{eid}" style="{style}"><span>{label}</span></div>'
        return f'<div class="el el-image" id="{eid}" style="{style}"><img src="{src}" alt="{_esc(el.get("alt") or "")}" style="object-fit:{fit}"></div>'
    if t == "line":
        pts = el.get("points") or []
        b = el.get("bbox") or {"x": 0, "y": 0, "w": 0, "h": 0}
        if len(pts) == 2:
            (x1, y1), (x2, y2) = pts
        else:
            x1, y1, x2, y2 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
        stroke = _esc(el.get("stroke") or "#666666")
        sw = float(el.get("stroke_width_pt") or 1)
        w, h = max(1.0, float(b["w"])), max(1.0, float(b["h"]))
        return (
            f'<div class="el el-line" id="{eid}" style="left:{b["x"]:g}px;top:{b["y"]:g}px;width:{w:g}px;height:{h:g}px;z-index:{z}">'
            f'<svg width="{w:g}" height="{h:g}" viewBox="0 0 {w:g} {h:g}"><line x1="{x1 - b["x"]:g}" y1="{y1 - b["y"]:g}" x2="{x2 - b["x"]:g}" y2="{y2 - b["y"]:g}" stroke="{stroke}" stroke-width="{sw:g}"/></svg></div>'
        )
    if t == "table":
        rows = el.get("rows", [])
        header_rows = int(el.get("header_rows", 1) or 0)
        widths = el.get("col_widths_pt") or []
        colgroup = ""
        if widths:
            total = sum(widths) or 1
            colgroup = "<colgroup>" + "".join(f'<col style="width:{w / total * 100:.2f}%">' for w in widths) + "</colgroup>"
        trs = []
        for ri, row in enumerate(rows):
            tag = "th" if ri < header_rows else "td"
            tds = []
            for c in row:
                attrs = ""
                if int(c.get("colspan", 1) or 1) > 1:
                    attrs += f' colspan="{int(c["colspan"])}"'
                if int(c.get("rowspan", 1) or 1) > 1:
                    attrs += f' rowspan="{int(c["rowspan"])}"'
                st = []
                if c.get("fill"):
                    st.append(f"background:{_esc(c['fill'])}")
                if c.get("bold"):
                    st.append("font-weight:bold")
                if c.get("align") in ("center", "right"):
                    st.append(f"text-align:{c['align']}")
                if st:
                    attrs += f' style="{";".join(st)}"'
                content = paragraphs_html(c["paragraphs"]) if c.get("paragraphs") else _esc(c.get("text", "")).replace("\n", "<br>")
                tds.append(f"<{tag}{attrs}>{content}</{tag}>")
            trs.append("<tr>" + "".join(tds) + "</tr>")
        size = (element_font_pt(el) if el.get("font_pt") else role_default_pt("caption") + 2) * font_scale(el)
        return f'<div class="el el-table" id="{eid}" style="{style};font-size:{size:g}px"><table>{colgroup}{"".join(trs)}</table></div>'
    label = _esc(el.get("alt") or el.get("original_type") or "未対応要素")
    return f'<div class="el el-unsupported" id="{eid}" style="{style}">{label}</div>'


def _reading_order(elements: list[dict]) -> list[dict]:
    """DOM 順を読み順（上→下、左→右）にする。縦読みモードと支援技術のため。"""
    def key(el: dict):
        b = el.get("bbox") or {"x": 0, "y": 0}
        role_rank = 0 if el.get("role") == "title" else 1
        return (role_rank, round(float(b["y"]) / 20), float(b["x"]))
    return sorted(elements, key=key)


def _template_image_src(rel_path: str, inline_assets: bool) -> str | None:
    data = template_kit.image_data(rel_path)
    if not data:
        return None
    if inline_assets:
        return f"data:{data[0]};base64,{data[1]}"
    return f"assets/{template_asset_filename(rel_path)}"


def template_asset_filename(rel_path: str) -> str:
    return "template_" + Path(rel_path).name


def slide_html(slide: dict, presentation: dict, inline_assets: bool, template: dict) -> str:
    """1 スライドの HTML。テンプレート部品（背景・ロゴ・帯・フッター・ページ番号）は template_kit の座標で描く。"""
    canvas = presentation["canvas"]
    w, h = float(canvas["width_pt"]), float(canvas["height_pt"])
    chrome = template_kit.chrome_spec(slide, presentation)
    bg = (slide.get("background") or {}).get("color") or chrome.get("background_color") or presentation["theme"].get("colors", {}).get("background", "#FFFFFF")
    style = f"width:{w:g}px;height:{h:g}px;background:{_esc(bg)}"
    text_color = (slide.get("background") or {}).get("text_color")
    if text_color:
        style += f";color:{_esc(text_color)}"
    if chrome.get("background_image"):
        src = _template_image_src(chrome["background_image"], inline_assets)
        if src:
            style += f";background-image:url('{src}');background-size:cover;background-position:center"
    parts = [f'<section class="slide kind-{chrome["kind"]}" id="{_esc(slide["id"])}" style="{style}" aria-label="{_esc(slide_title(slide))}">']
    # テンプレート部品は本文より背面（z:-1）に置き、pointer-events を切る
    for bar in chrome["bars"]:
        clip = ""
        if bar.get("slant_pt"):
            clip = f"clip-path:polygon({bar['slant_pt']:g}px 0,100% 0,100% 100%,0 100%);"
        parts.append(f'<div class="tpl tpl-bar" style="left:{bar["x"]:g}px;top:{bar["y"]:g}px;width:{bar["w"]:g}px;height:{bar["h"]:g}px;background:{_esc(bar["color"])};{clip}"></div>')
    for img in chrome["images"]:
        src = _template_image_src(img["image"], inline_assets)
        if src:
            parts.append(f'<img class="tpl tpl-logo" src="{src}" alt="" style="left:{img["x"]:g}px;top:{img["y"]:g}px;width:{img["w"]:g}px;height:{img["h"]:g}px">')
    for t in chrome["texts"]:
        parts.append(f'<div class="tpl tpl-text" style="left:{t["x"]:g}px;top:{t["y"]:g}px;width:{t["w"]:g}px;height:{t["h"]:g}px;font-size:{t["size_pt"]:g}px;color:{_esc(t["color"])};text-align:{_esc(t.get("align", "left"))}">{_esc(t["text"])}</div>')
    for el in _reading_order(slide.get("elements", [])):
        parts.append(element_html(el, presentation, inline_assets))
    parts.append("</section>")
    notes = slide.get("notes")
    notes_html = f'<aside class="notes">{_esc(notes)}</aside>' if notes else ""
    return f'<div class="slide-wrap" data-index="{int(slide.get("index", 0))}">' + "".join(parts) + "</div>" + notes_html


def render_html(presentation: dict, inline_assets: bool = False, inline_viewer: bool = False) -> str:
    """ビューア HTML を生成する。inline_* を True にすると単一ファイルで完結する。"""
    cfg = get_config()
    template = cfg.template(presentation.get("theme", {}).get("template_id"))
    fonts = cfg.font_fallback()
    colors = presentation.get("theme", {}).get("colors", {})
    title = presentation.get("meta", {}).get("title") or "Web図解"
    canvas = presentation["canvas"]
    toc = "".join(f'<li><span class="num">{i + 1}</span>{_esc(slide_title(s))}</li>' for i, s in enumerate(presentation.get("slides", [])))
    slides = "".join(slide_html(s, presentation, inline_assets, template) for s in presentation.get("slides", []))
    theme_css = ":root{--font:%s;--text:%s;--muted:%s;--line:%s;--surface:%s;--accent:%s}" % (
        fonts.get("web_font_stack", "sans-serif"),
        colors.get("text", "#222222"),
        colors.get("muted", "#666666"),
        colors.get("line", "#C9D1DB"),
        colors.get("surface", "#F4F6F9"),
        colors.get("accent", "#E07A1F"),
    )
    if inline_viewer:
        css = f"<style>{(_VIEWER_DIR / 'viewer.css').read_text(encoding='utf-8')}</style>"
        js = f"<script>{(_VIEWER_DIR / 'viewer.js').read_text(encoding='utf-8')}</script>"
    else:
        css = '<link rel="stylesheet" href="viewer.css">'
        js = '<script src="viewer.js"></script>'
    warnings_count = len(presentation.get("warnings", []))
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}{_esc(cfg.get("web_export.viewer_title_suffix", ""))}</title>
<meta name="generator" content="{_esc(presentation.get("meta", {}).get("generator", ""))}">
{css}
<style>{theme_css}</style>
</head>
<body class="slide-mode" data-canvas-w="{float(canvas["width_pt"]):g}" data-canvas-h="{float(canvas["height_pt"]):g}" data-flow-breakpoint="{int(cfg.get("web_export.flow_breakpoint_px", 720))}">
<header class="viewer-header">
  <button id="btn-toc" title="目次">目次</button>
  <h1>{_esc(title)}</h1>
  <button id="btn-prev" title="前へ (←)">前へ</button>
  <span class="counter">1 / {len(presentation.get("slides", []))}</span>
  <button id="btn-next" title="次へ (→)">次へ</button>
  <button id="btn-mode" title="表示切替">縦読み表示</button>
  <button id="btn-notes" title="ノート (N)">ノート</button>
  <button id="btn-full" title="全画面 (F)">全画面</button>
  <button id="btn-print" title="印刷">印刷</button>
  <span class="counter" title="変換時の警告数">警告 {warnings_count}</span>
</header>
<div class="viewer-body">
  <nav class="toc"><ol>{toc}</ol></nav>
  <main class="stage">{slides}</main>
</div>
{js}
</body>
</html>
"""


def build_bundle(presentation: dict) -> dict[str, bytes]:
    """静的一式を {相対パス: バイト列} で返す。ZIP 化やディレクトリ書き出しは呼び出し側が行う。"""
    files: dict[str, bytes] = {}
    files["index.html"] = render_html(presentation, inline_assets=False, inline_viewer=False).encode("utf-8")
    files["viewer.css"] = (_VIEWER_DIR / "viewer.css").read_bytes()
    files["viewer.js"] = (_VIEWER_DIR / "viewer.js").read_bytes()
    for asset_id, asset in presentation.get("assets", {}).items():
        try:
            files[f"assets/{asset_filename(asset_id, asset)}"] = base64.b64decode(asset.get("data_base64", ""))
        except (ValueError, TypeError):
            continue
    template = get_config().template(presentation.get("theme", {}).get("template_id"))
    for part_key in ("cover", "content", "closing"):
        part = template.get(part_key)
        if not isinstance(part, dict):
            continue
        for rel in (part.get("background_image"), (part.get("logo") or {}).get("image")):
            data = template_kit.image_data(rel) if rel else None
            if data:
                files[f"assets/{template_asset_filename(rel)}"] = base64.b64decode(data[1])
    slim = dict(presentation)
    slim["assets"] = {k: {kk: vv for kk, vv in v.items() if kk != "data_base64"} | {"path": f"assets/{asset_filename(k, v)}"} for k, v in presentation.get("assets", {}).items()}
    files["presentation.json"] = json.dumps(slim, ensure_ascii=False, indent=2).encode("utf-8")
    from .report import to_markdown

    files["conversion_report.md"] = to_markdown(presentation).encode("utf-8")
    return files


def write_bundle(presentation: dict, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    for rel, data in build_bundle(presentation).items():
        target = out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return out_dir
