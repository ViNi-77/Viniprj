"""HTML図解 → Presentation JSON 変換器。

BeautifulSoup で DOM を読み、意味構造（見出し・段落・リスト・画像・表・カード）を
bbox 無しの要素として取り出す。座標は後段の layout.py が決定的に割り当てる。

スライド境界の決め方（優先順）:
1. <section> / <article> / class に "slide" を含む要素
2. 無ければ h1/h2 見出しごとに分割
外部 URL の画像は取得しない（任意サイトのクロールは非目標）。
"""
from __future__ import annotations

import base64
import hashlib
import io
import posixpath
import re
from typing import Any
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from .config import get_config
from .ids import IdFactory
from .layout import make_title_slide
from .logging_setup import get_logger
from .model import add_warning, cell, image_element, new_presentation, new_slide, paragraph, run, shape_element, table_element, text_element, warning

log = get_logger("html_parser")

_SKIP_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "template", "svg", "iframe", "button", "form", "input"}
_CARD_CLASS = re.compile(r"(^|[\s_-])(card|panel|box|tile|item)([\s_-]|$)", re.I)
_GRID_CLASS = re.compile(r"(^|[\s_-])(grid|cards|columns|cols|row|flex)([\s_-]|$)", re.I)
_SLIDE_CLASS = re.compile(r"(^|[\s_-])(slide|page)([\s_-]|$)", re.I)
_SUBTITLE_CLASS = re.compile(r"(^|[\s_-])(lead|subtitle|sub|tagline|caption)([\s_-]|$)", re.I)
_WS = re.compile(r"\s+")
_PX_PER_PT = 96 / 72


def css_color_to_hex(value: str | None) -> str | None:
    """'rgb(11, 61, 145)' / 'rgba(...)' / '#abc' → '#RRGGBB'。透明・不明は None。"""
    if not value:
        return None
    v = value.strip()
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?", v)
    if m:
        if m.group(4) is not None and float(m.group(4)) == 0:
            return None
        return "#%02X%02X%02X" % tuple(min(255, int(m.group(i))) for i in (1, 2, 3))
    m = re.match(r"^#([0-9A-Fa-f]{6})$", v)
    if m:
        return "#" + m.group(1).upper()
    m = re.match(r"^#([0-9A-Fa-f]{3})$", v)
    if m:
        return ("#" + "".join(c * 2 for c in m.group(1))).upper()
    return None


def css_px_to_pt(value: str | None) -> float | None:
    if not value:
        return None
    m = re.match(r"([\d.]+)px", value.strip())
    return round(float(m.group(1)) / _PX_PER_PT, 1) if m else None


def _is_dark_hex(color: str) -> bool:
    try:
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    except (ValueError, TypeError):
        return False
    return (0.299 * r + 0.587 * g + 0.114 * b) < 128


_INLINE_PROPS = ("color", "background-color", "background", "font-size", "font-weight", "text-align", "float")


def _inline_style(node: Tag) -> dict[str, str]:
    """style 属性を Computed Style と同じ形の辞書へ（ブラウザが無い環境の代替。色は 16 進または rgb() のみ）。"""
    out: dict[str, str] = {}
    for part in str(node.get("style", "")).split(";"):
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        k, v = k.strip().lower(), v.strip()
        if k not in _INLINE_PROPS or not v:
            continue
        if k == "background":
            k = "background-color"
            m = re.search(r"(#[0-9A-Fa-f]{3,6}|rgba?\([^)]*\))", v)
            if not m:
                continue
            v = m.group(1)
        if k in ("color", "background-color") and not css_color_to_hex(v):
            continue
        out[k] = v
    return out


def tag_elements(soup: BeautifulSoup) -> None:
    """全タグに data-pwb-id を振る（Computed Style との突合キー）。"""
    for i, tag in enumerate(soup.find_all(True)):
        tag["data-pwb-id"] = str(i)


def _clean(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


def _inline_runs(node: Tag | NavigableString, inherited: dict | None = None) -> list[dict]:
    """インライン要素（strong/em/a/br…）をランへ展開する。"""
    inherited = dict(inherited or {})
    out: list[dict] = []
    if isinstance(node, NavigableString):
        text = _WS.sub(" ", str(node))
        if text:
            out.append(run(text, **inherited))
        return out
    if not isinstance(node, Tag):
        return out
    name = node.name.lower()
    if name in _SKIP_TAGS:
        return out
    if name == "br":
        out.append(run("\n", **inherited))
        return out
    if name in ("strong", "b"):
        inherited["bold"] = True
    elif name in ("em", "i"):
        inherited["italic"] = True
    elif name == "u":
        inherited["underline"] = True
    elif name == "a" and node.get("href"):
        inherited["href"] = str(node.get("href"))
    style = str(node.get("style", ""))
    m = re.search(r"color\s*:\s*(#[0-9A-Fa-f]{3,6}|rgb\([^)]*\))", style)
    if m:
        inherited["color"] = m.group(1)
    for child in node.children:
        out.extend(_inline_runs(child, inherited))
    return out


def _merge_runs(runs: list[dict]) -> list[dict]:
    """同じ書式の連続ランを結合し、前後の空白を整える。"""
    merged: list[dict] = []
    for r in runs:
        if merged and {k: v for k, v in merged[-1].items() if k != "text"} == {k: v for k, v in r.items() if k != "text"}:
            merged[-1]["text"] += r["text"]
        else:
            merged.append(dict(r))
    if merged:
        merged[0]["text"] = merged[0]["text"].lstrip()
        merged[-1]["text"] = merged[-1]["text"].rstrip()
    return [r for r in merged if r["text"]]


def _para_from(node: Tag, **kw: Any) -> dict | None:
    runs = _merge_runs(_inline_runs(node))
    if not runs:
        return None
    align = None
    style = str(node.get("style", ""))
    m = re.search(r"text-align\s*:\s*(center|right|justify)", style)
    if m:
        align = m.group(1)
    elif "center" in " ".join(node.get("class", [])):
        align = "center"
    return paragraph(runs, align=align, **kw)


def _apply_computed(para: dict | None, style: dict[str, str], default: dict[str, str] | None = None) -> dict | None:
    """Computed Style（色・サイズ・太字・寄せ）を、明示指定の無いランへ補う。

    body の Computed Style（default）と同じ色は「既定」とみなして書かない（ハードコードの除外リストは持たない）。
    サイズは常に継承値として書き、typography の帯域で役割ごとに整える。
    """
    if not para or not style:
        return para
    default = default or {}
    color = css_color_to_hex(style.get("color"))
    size = css_px_to_pt(style.get("font-size"))
    base_color = css_color_to_hex(default.get("color")) or "#000000"
    weight = style.get("font-weight", "")
    bold = weight.isdigit() and int(weight) >= 600 or weight == "bold"
    for r in para["runs"]:
        inh = list(r.get("inherited") or [])
        # CSS 由来の値は「継承値」として印を付け、テンプレート適用時に上書きできるようにする（明示 style 属性は _inline_runs で先に入る）
        if color and color != base_color and not r.get("color"):
            r["color"], inh = color, inh + ["color"]
        if size and not r.get("size_pt"):
            r["size_pt"], inh = size, inh + ["size_pt"]
        if bold and not r.get("bold"):
            r["bold"], inh = True, inh + ["bold"]
        if inh:
            r["inherited"] = inh
    align = style.get("text-align", "")
    if align in ("center", "right", "justify") and not para.get("align"):
        para["align"] = align
    return para


def _list_paragraphs(list_node: Tag, level: int = 0, ctx: "_Ctx | None" = None) -> list[dict]:
    kind = "number" if list_node.name.lower() == "ol" else "bullet"
    paras: list[dict] = []
    for li in list_node.find_all("li", recursive=False):
        # li 直下のテキスト（入れ子リストを除く）
        own = Tag(name="span")
        nested: list[Tag] = []
        for child in li.children:
            if isinstance(child, Tag) and child.name.lower() in ("ul", "ol"):
                nested.append(child)
            else:
                own.append(child.__copy__() if hasattr(child, "__copy__") else child)
        p = _para_from(own, level=level, bullet=kind)
        if ctx is not None:
            p = ctx.styled(p, li)
        if p:
            paras.append(p)
        for n in nested:
            paras.extend(_list_paragraphs(n, level + 1, ctx))
    return paras


class _Ctx:
    def __init__(self, presentation: dict, files: dict[str, bytes], base_path: str):
        self.presentation = presentation
        self.ids = IdFactory()
        self.files = files
        self.base_dir = posixpath.dirname(base_path)
        self.asset_by_hash: dict[str, str] = {}
        self.styles: dict[str, dict[str, str]] = {}  # data-pwb-id → Computed Style（Issue #6、無ければ空）

        self.default_style: dict[str, str] = {}  # body の Computed Style（既定値の判定に使う）

    def style_of(self, node: Tag | None) -> dict[str, str]:
        """node の Computed Style。ブラウザで取得できていない環境では style 属性の直書きだけを読む。"""
        if node is None:
            return {}
        if self.styles:
            return self.styles.get(str(node.get("data-pwb-id", "")), {})
        return _inline_style(node)

    def styled(self, para: dict | None, node: Tag | None) -> dict | None:
        """段落に node の Computed Style を適用する（取得していなければそのまま）。"""
        return _apply_computed(para, self.style_of(node), self.default_style)

    def add_asset(self, blob: bytes, mime: str, name_hint: str) -> str:
        digest = hashlib.sha1(blob).hexdigest()
        if digest in self.asset_by_hash:
            return self.asset_by_hash[digest]
        asset_id = self.ids.next("img")
        w = h = None
        try:
            from PIL import Image

            with Image.open(io.BytesIO(blob)) as im:
                w, h = im.size
                if not mime or mime == "application/octet-stream":
                    mime = Image.MIME.get(im.format or "", "image/png")
        except Exception:  # noqa: BLE001
            pass
        ext = (name_hint.rsplit(".", 1)[-1].lower() if "." in name_hint else None) or (mime.split("/")[-1] if mime else "bin")
        if ext == "jpg":
            ext = "jpeg"
        self.presentation["assets"][asset_id] = {"mime": mime or "image/png", "filename": f"{asset_id}.{ext}", "data_base64": base64.b64encode(blob).decode("ascii"), "width_px": w, "height_px": h}
        self.asset_by_hash[digest] = asset_id
        return asset_id

    def resolve_image(self, src: str, slide: dict) -> str | None:
        """画像を資産へ取り込む。data URI と同梱ファイルのみ対応。"""
        src = (src or "").strip()
        if not src:
            return None
        if src.startswith("data:"):
            m = re.match(r"data:([^;,]+)?(;base64)?,(.*)", src, re.S)
            if not m:
                return None
            mime, is_b64, payload = m.group(1) or "image/png", m.group(2), m.group(3)
            try:
                blob = base64.b64decode(payload) if is_b64 else unquote(payload).encode("utf-8")
            except (ValueError, TypeError):
                return None
            return self.add_asset(blob, mime, "data." + mime.split("/")[-1])
        parsed = urlparse(src)
        if parsed.scheme in ("http", "https"):
            add_warning(self.presentation, warning("html_parser", "REMOTE_IMAGE_SKIPPED", f"外部画像は取得しません: {src}", slide["id"], None, "代替枠を表示"), slide)
            return None
        rel = unquote(parsed.path)
        candidates = [posixpath.normpath(posixpath.join(self.base_dir, rel)) if self.base_dir else posixpath.normpath(rel), posixpath.normpath(rel), posixpath.basename(rel)]
        for cand in candidates:
            cand = cand.lstrip("./")
            for key, blob in self.files.items():
                nk = key.replace("\\", "/").lstrip("./")
                if nk == cand or nk.endswith("/" + cand) or posixpath.basename(nk) == posixpath.basename(cand) and cand == posixpath.basename(cand):
                    import mimetypes

                    mime = mimetypes.guess_type(nk)[0] or "image/png"
                    return self.add_asset(blob, mime, nk)
        add_warning(self.presentation, warning("html_parser", "IMAGE_NOT_FOUND", f"画像ファイルが同梱されていません: {src}", slide["id"], None, "代替枠を表示"), slide)
        return None


def _table_element(ctx: _Ctx, table: Tag) -> dict | None:
    rows: list[list[dict]] = []
    header_rows = 0
    trs = table.find_all("tr")
    for ri, tr in enumerate(trs):
        row: list[dict] = []
        in_thead = tr.find_parent("thead") is not None
        for td in tr.find_all(["td", "th"], recursive=False):
            text = "\n".join(_clean(x) for x in td.stripped_strings) if td.find("br") else _clean(td.get_text(" "))
            row.append(cell(text, bold=(td.name == "th"), colspan=int(td.get("colspan", 1) or 1), rowspan=int(td.get("rowspan", 1) or 1)))
        if row:
            rows.append(row)
            if in_thead or all(td.name == "th" for td in tr.find_all(["td", "th"], recursive=False)):
                if header_rows == len(rows) - 1:
                    header_rows += 1
    if not rows:
        return None
    return table_element(ctx.ids.next("el"), rows, None, header_rows=header_rows)


def _card_element(ctx: _Ctx, card: Tag, column: int, columns: int, slide: dict) -> list[dict]:
    """カード（見出し + 本文）を塗り付き図形へ。画像を含む場合は画像要素を別に出す。"""
    paras: list[dict] = []
    extra: list[dict] = []
    for child in card.descendants:
        if not isinstance(child, Tag):
            continue
        name = child.name.lower()
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            p = ctx.styled(_para_from(child), child)
            if p:
                for r in p["runs"]:
                    r["bold"] = True
                paras.append(p)
        elif name == "p" and not child.find_parent("li"):
            p = ctx.styled(_para_from(child), child)
            if p:
                paras.append(p)
        elif name in ("ul", "ol") and child.find_parent(["ul", "ol"]) is None:
            paras.extend(_list_paragraphs(child, 0, ctx))
        elif name == "img":
            asset_id = ctx.resolve_image(str(child.get("src", "")), slide)
            if asset_id:
                extra.append(image_element(ctx.ids.next("el"), asset_id, None, alt=str(child.get("alt", "")), layout_hint={"column": column, "columns": columns}))
    if not paras and not extra:
        text = _clean(card.get_text(" "))
        if text:
            paras.append(paragraph([run(text)]))
    colors = ctx.presentation["theme"].get("colors", {})
    out: list[dict] = []
    if paras:
        cs = ctx.style_of(card)
        fill = css_color_to_hex(cs.get("background-color")) or colors.get("surface", "#F4F6F9")
        stroke = css_color_to_hex(cs.get("border-top-color")) if css_px_to_pt(cs.get("border-top-width")) else None
        hint: dict[str, Any] = {"column": column, "columns": columns}
        chars = sum(len(r.get("text", "")) for p in paras for r in p.get("runs", []))
        if columns == 1 and chars < int(get_config().get("layout.band_max_chars", 80)):
            hint["band"] = True  # 短文の帯（見出し帯など）: 最小高さを抑える
        out.append(shape_element(ctx.ids.next("el"), "rounded_rect", None, fill=fill, stroke=stroke or colors.get("line", "#C9D1DB"), stroke_width_pt=1.0, paragraphs=paras, role="card", layout_hint=hint, vertical_align="top"))
    out.extend(extra)
    return out


_SIDE_RIGHT = re.compile(r"(^|[\s_-])(right|img-right|float-right|pull-right|end)([\s_-]|$)", re.I)
_SIDE_LEFT = re.compile(r"(^|[\s_-])(left|img-left|float-left|pull-left|start)([\s_-]|$)", re.I)


def _image_side(node: Tag, ctx: _Ctx) -> str | None:
    """画像の左右指定（class / float）を読む。無ければ None（DOM 順で決める）。"""
    for n in (node, node.parent if isinstance(node.parent, Tag) else None):
        if n is None:
            continue
        classes = " ".join(n.get("class", []))
        fl = ctx.style_of(n).get("float", "")
        if fl == "right" or _SIDE_RIGHT.search(classes):
            return "right"
        if fl == "left" or _SIDE_LEFT.search(classes):
            return "left"
    return None


def _image_or_placeholder(ctx: _Ctx, img: Tag, slide: dict) -> dict:
    asset_id = ctx.resolve_image(str(img.get("src", "")), slide)
    side = _image_side(img, ctx)
    hint = {"side": side} if side else None
    if asset_id:
        return image_element(ctx.ids.next("el"), asset_id, None, alt=str(img.get("alt", "")), layout_hint=hint)
    return image_element(ctx.ids.next("el"), None, None, alt=f"画像（未取得）{img.get('alt', '')}", placeholder=True, layout_hint=hint)


def _pairable_text(el: dict) -> bool:
    return el.get("type") == "text" and el.get("role") in (None, "body", "caption") and not _hint(el).get("columns") and _hint(el).get("row") is None


def _hint(el: dict) -> dict:
    return el.get("layout_hint") or {}


def _wide_image(el: dict, assets: dict, content_w: float) -> bool:
    asset = assets.get(el.get("asset_id") or "", {})
    w_px = asset.get("width_px")
    return bool(w_px) and float(w_px) * 0.75 > content_w * 0.6


def _pair_text_and_images(elements: list[dict], assets: dict, content_w: float) -> list[dict]:
    """隣接する本文と画像を「横並びの行」にまとめる（layout_hint.row / side）。直後のキャプションは画像側へ付ける。"""
    row = 0
    i = 0
    while i < len(elements):
        el = elements[i]
        if el.get("type") != "image" or _hint(el).get("columns") or _hint(el).get("row") is not None or _wide_image(el, assets, content_w):
            i += 1
            continue
        cap = elements[i + 1] if i + 1 < len(elements) and elements[i + 1].get("type") == "text" and elements[i + 1].get("role") == "caption" and _hint(elements[i + 1]).get("row") is None else None
        after_idx = i + (2 if cap is not None else 1)
        after = elements[after_idx] if after_idx < len(elements) and _pairable_text(elements[after_idx]) else None
        before = elements[i - 1] if i > 0 and _pairable_text(elements[i - 1]) else None
        txt = before if before is not None else after
        if txt is None:
            i = after_idx
            continue
        row += 1
        side = _hint(el).get("side") or ("right" if before is not None else "left")
        for m in [el] + ([cap] if cap is not None else []):
            m["layout_hint"] = {**_hint(m), "row": row, "side": side}
        txt["layout_hint"] = {**_hint(txt), "row": row, "side": "left" if side == "right" else "right"}
        i = after_idx + (1 if txt is after else 0)
    return elements


def _is_grid(node: Tag) -> bool:
    classes = " ".join(node.get("class", []))
    style = str(node.get("style", ""))
    if _GRID_CLASS.search(classes) or "display:grid" in style.replace(" ", "") or "display:flex" in style.replace(" ", ""):
        children = [c for c in node.children if isinstance(c, Tag)]
        return len(children) >= 2  # 列数は max_columns で折り返す
    return False


def _walk_block(node: Tag, ctx: _Ctx, slide: dict, max_columns: int) -> list[dict]:
    """ブロック要素を要素列へ変換する（再帰）。"""
    out: list[dict] = []
    for child in node.children:
        if isinstance(child, NavigableString):
            text = _clean(str(child))
            if text and node.name.lower() not in ("ul", "ol"):
                out.append(text_element(ctx.ids.next("el"), [paragraph([run(text)])], role="body"))
            continue
        if not isinstance(child, Tag):
            continue
        name = child.name.lower()
        if name in _SKIP_TAGS:
            continue
        if name in ("h1", "h2", "h3"):
            p = ctx.styled(_para_from(child), child)
            if p:
                for r in p["runs"]:
                    r["bold"] = True
                out.append(text_element(ctx.ids.next("el"), [p], role="title"))
        elif name in ("h4", "h5", "h6"):
            p = ctx.styled(_para_from(child), child)
            if p:
                for r in p["runs"]:
                    r["bold"] = True
                short = sum(len(r.get("text", "")) for r in p["runs"]) <= int(get_config().get("layout.keep_with_next_max_chars", 40))
                out.append(text_element(ctx.ids.next("el"), [p], role="body", layout_hint={"keep_with_next": True} if short else None))
        elif name == "p":
            p = ctx.styled(_para_from(child), child)
            if p:
                role = "caption" if _SUBTITLE_CLASS.search(" ".join(child.get("class", []))) and len(out) > 0 else "body"
                out.append(text_element(ctx.ids.next("el"), [p], role=role))
        elif name in ("ul", "ol"):
            paras = _list_paragraphs(child, 0, ctx)
            if paras:
                out.append(text_element(ctx.ids.next("el"), paras, role="body"))
        elif name == "table":
            el = _table_element(ctx, child)
            if el:
                out.append(el)
        elif name == "img":
            out.append(_image_or_placeholder(ctx, child, slide))
        elif name in ("figure", "picture"):
            img = child.find("img")
            if img is not None:
                out.append(_image_or_placeholder(ctx, img, slide))
            cap = child.find("figcaption")
            if cap is not None:
                p = ctx.styled(_para_from(cap), cap)
                if p:
                    out.append(text_element(ctx.ids.next("el"), [p], role="caption"))
        elif name == "blockquote":
            paras = [p for p in (_para_from(x) for x in child.find_all("p")) if p] or ([_para_from(child)] if _para_from(child) else [])
            if paras:
                colors = ctx.presentation["theme"].get("colors", {})
                out.append(shape_element(ctx.ids.next("el"), "rect", None, fill=colors.get("surface"), stroke=colors.get("accent"), stroke_width_pt=2.0, paragraphs=paras, role="body"))
        elif name in ("pre", "code"):
            text = child.get_text("\n").rstrip()
            if text:
                out.append(text_element(ctx.ids.next("el"), [paragraph([run(line, font="Menlo")]) for line in text.split("\n")], role="body"))
        elif _is_grid(child):
            cards = [c for c in child.children if isinstance(c, Tag)]
            columns = min(max_columns, len(cards))
            if len(cards) > max_columns:
                add_warning(ctx.presentation, warning("html_parser", "GRID_COLUMNS_LIMITED", f"{len(cards)} 個のカードを {max_columns} 列に折り返します。", slide["id"], None, "列数を制限"), slide)
            for i, card in enumerate(cards):
                out.extend(_card_element(ctx, card, i % columns, columns, slide))
        elif _CARD_CLASS.search(" ".join(child.get("class", []))):
            out.extend(_card_element(ctx, child, 0, 1, slide))
        elif name in ("div", "section", "article", "main", "body", "aside", "details", "summary", "span", "li", "dl", "dd", "dt", "small"):
            out.extend(_walk_block(child, ctx, slide, max_columns))
        elif name in ("hr",):
            colors = ctx.presentation["theme"].get("colors", {})
            out.append({"id": ctx.ids.next("el"), "type": "line", "role": None, "bbox": None, "points": None, "stroke": colors.get("line", "#C9D1DB"), "stroke_width_pt": 1.0, "editable": True})
        else:
            # 未知タグは中身をたどる（テキストを失わない）
            out.extend(_walk_block(child, ctx, slide, max_columns))
    return out


def _find_slide_containers(soup: BeautifulSoup) -> list[Tag]:
    body = soup.body or soup
    explicit = [t for t in body.find_all(["section", "article"]) if not t.find_parent(["section", "article"])]
    if explicit:
        return explicit
    classed = [t for t in body.find_all(True) if _SLIDE_CLASS.search(" ".join(t.get("class", []))) and not any(_SLIDE_CLASS.search(" ".join(p.get("class", []))) for p in t.parents if isinstance(p, Tag))]
    if classed:
        return classed
    return []


def _split_by_headings(body: Tag) -> list[list[Tag | NavigableString]]:
    """section が無い長尺 HTML を h1/h2 単位で分割する。"""
    groups: list[list[Tag | NavigableString]] = [[]]
    container = body.find("main") or body
    for child in container.children:
        if isinstance(child, Tag) and child.name.lower() in ("h1", "h2") and groups[-1]:
            groups.append([])
        groups[-1].append(child)
    return [g for g in groups if any(isinstance(c, Tag) or _clean(str(c)) for c in g)]


def parse_html(data: bytes | str, filename: str = "input.html", files: dict[str, bytes] | None = None, template_id: str | None = None, max_columns: int | None = None, computed_style: bool | None = None) -> dict:
    """HTML を Presentation JSON へ変換する。bbox は付けず、layout_presentation で確定させる。

    computed_style: True なら Playwright で Computed Style（色・サイズ・太字）を取得して補う（Issue #6）。
    None なら設定 html_import.use_computed_style に従う。取得できない環境では静的解析のみで続行する。
    """
    cfg = get_config()
    max_columns = int(max_columns or cfg.get("layout.max_columns", 3))
    html_text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    soup = BeautifulSoup(html_text, "lxml")
    tag_elements(soup)
    doc_title = _clean(soup.title.get_text()) if soup.title else ""
    presentation = new_presentation(title=doc_title, source_type="html", filename=filename, template_id=template_id)
    ctx = _Ctx(presentation, files or {}, filename.replace("\\", "/"))
    use_cs = bool(cfg.get("html_import.use_computed_style", True)) if computed_style is None else bool(computed_style)
    if use_cs:
        from .rasterize import collect_computed_styles

        ctx.styles, reason = collect_computed_styles(str(soup), files or {}, filename.replace("\\", "/"))
        if not ctx.styles:
            add_warning(presentation, warning("html_parser", "COMPUTED_STYLE_UNAVAILABLE", f"ブラウザによるスタイル取得ができないため、HTML 内の色・サイズは反映されません（{reason or '要素なし'}）。", None, None, "静的解析のみ"))
        elif soup.body is not None:
            ctx.default_style = ctx.style_of(soup.body)
    body = soup.body or soup

    containers = _find_slide_containers(soup)
    groups: list[list[Tag | NavigableString]]
    container_tags: list[Tag | None] = []
    if containers:
        groups = [list(c.children) for c in containers]
        container_tags = list(containers)
        # section の外にある h1（ページ見出し）は表紙にする
        stray_h1 = next((h for h in body.find_all("h1") if h.find_parent(["section", "article"]) is None), None)
        if stray_h1 is not None:
            sub = stray_h1.find_next_sibling("p")
            subtitle = _clean(sub.get_text(" ")) if sub is not None and sub.find_parent(["section", "article"]) is None and _SUBTITLE_CLASS.search(" ".join(sub.get("class", [])) or "lead") else None
            presentation["slides"].append(make_title_slide(ctx.ids.next("s"), 0, _clean(stray_h1.get_text(" ")), subtitle))
            if not presentation["meta"]["title"]:
                presentation["meta"]["title"] = _clean(stray_h1.get_text(" "))
    else:
        groups = _split_by_headings(body)
        if not groups:
            add_warning(presentation, warning("html_parser", "NO_CONTENT", "本文を見つけられませんでした。", None, None, "空の資料"))

    content_w = float(presentation["canvas"]["width_pt"]) - 2 * float(cfg.get("layout.margin_pt", 36))
    body_bg = css_color_to_hex(ctx.default_style.get("background-color")) if ctx.default_style else None
    for gi, group in enumerate(groups):
        slide = new_slide(ctx.ids.next("s"), len(presentation["slides"]))
        holder = Tag(name="div")
        for node in group:
            holder.append(node.__copy__() if hasattr(node, "__copy__") else node)
        elements = _pair_text_and_images(_walk_block(holder, ctx, slide, max_columns), presentation["assets"], content_w)
        if not elements:
            continue
        container = container_tags[gi] if gi < len(container_tags) else None
        bg = css_color_to_hex(ctx.style_of(container).get("background-color")) if container is not None else None
        if bg and bg != (body_bg or "#FFFFFF"):
            slide["background"] = {"color": bg}
            if _is_dark_hex(bg):
                slide["background"]["text_color"] = "#FFFFFF"
        # 先頭が h1 で本文が短い場合は表紙扱い
        first = elements[0]
        if first.get("role") == "title":
            slide["title"] = "".join(r["text"] for r in first["paragraphs"][0]["runs"])
            first_tag = next((n for n in group if isinstance(n, Tag)), None)
            if first_tag is not None and first_tag.name.lower() == "h1" and len(elements) <= 2 and not presentation["slides"]:
                slide["layout"] = "title"
                if len(elements) == 2 and elements[1].get("type") == "text":
                    elements[1]["role"] = "subtitle"
        else:
            slide["title"] = None
        if slide["layout"] != "title":
            types = [e["type"] for e in elements]
            hints = [e.get("layout_hint") for e in elements if e.get("layout_hint")]
            if hints:
                cols = max(int(h.get("columns", 1)) for h in hints)
                slide["layout"] = "two_column" if cols == 2 else ("three_column" if cols >= 3 else "title_body")
            elif "table" in types:
                slide["layout"] = "table"
            elif "image" in types and types.count("text") <= 2:
                slide["layout"] = "image"
        slide["elements"] = elements
        presentation["slides"].append(slide)

    if not presentation["slides"] and not any(w["code"] == "NO_CONTENT" for w in presentation["warnings"]):
        add_warning(presentation, warning("html_parser", "NO_CONTENT", "変換できる本文（見出し・段落・リスト・画像・表）が見つかりませんでした。", None, None, "空の資料"))
    if not presentation["meta"]["title"]:
        presentation["meta"]["title"] = presentation["slides"][0].get("title") if presentation["slides"] and presentation["slides"][0].get("title") else filename.rsplit(".", 1)[0]
    log.info("HTML 解析完了: %s slides=%d assets=%d warnings=%d", filename, len(presentation["slides"]), len(presentation["assets"]), len(presentation["warnings"]))
    return presentation
