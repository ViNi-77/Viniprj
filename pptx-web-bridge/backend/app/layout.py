"""自動レイアウト。bbox を持たない要素（HTML 由来など）に座標を割り当てる。

方針:
- 決定的な計算のみ。AI に座標を決めさせない。
- タイトル → 本文の順に上から積む。layout_hint.columns があれば列に分ける。
- 1枚に収まらない場合はスライドを分割し、「（続き）」を付けて次のスライドへ送る。
"""
from __future__ import annotations

import copy
import re

from .config import get_config
from .model import bbox, new_slide, paragraph, run, text_element, warning
from .text_metrics import estimate_paragraphs_height


def _layout_params() -> dict:
    cfg = get_config()
    return {
        "margin": float(cfg.get("layout.margin_pt", 36)),
        "gutter": float(cfg.get("layout.gutter_pt", 18)),
        "title_h": float(cfg.get("layout.title_height_pt", 64)),
        "title_font": float(cfg.get("layout.title_font_pt", 28)),
        "body_font": float(cfg.get("layout.body_font_pt", 16)),
        "caption_font": float(cfg.get("layout.caption_font_pt", 12)),
        "max_columns": int(cfg.get("layout.max_columns", 3)),
    }


def _element_height(el: dict, width: float, params: dict, assets: dict) -> float:
    """要素の推定高さ（pt）。画像は縦横比から、表は行数から、テキストは折り返しから求める。"""
    t = el.get("type")
    if t == "text":
        size = params["body_font"] if el.get("role") in (None, "body", "card") else params["caption_font"]
        if el.get("role") == "subtitle":
            size = params["body_font"] * 1.25
        # レンダラーの内側余白（左右 6px ずつ）を差し引いて折り返しを見積もる
        return max(size * 1.5, estimate_paragraphs_height(el.get("paragraphs", []), width - 12, size))
    if t == "image":
        asset = assets.get(el.get("asset_id") or "", {})
        w_px, h_px = asset.get("width_px"), asset.get("height_px")
        if w_px and h_px:
            return width * (float(h_px) / float(w_px))
        return width * 0.5625
    if t == "table":
        rows = el.get("rows", [])
        row_h = params["body_font"] * 1.9
        return max(row_h, row_h * len(rows))
    if t == "shape":
        pad = params["gutter"]
        inner = estimate_paragraphs_height(el.get("paragraphs", []), width - pad * 2, params["body_font"])
        return max(params["body_font"] * 3, inner + pad * 2)
    if t == "line":
        return 2.0
    return params["body_font"] * 2


_SENTENCE_BREAK = re.compile(r"(?<=[。．.!?！？])")


def _explode_long_paragraph(para: dict, width: float, max_h: float, size: float) -> list[dict]:
    """1 段落だけで枠に収まらない場合、文の切れ目で複数段落に分ける（書式は先頭ランのものを引き継ぐ）。"""
    if estimate_paragraphs_height([para], width, size) <= max_h or len(para.get("runs", [])) == 0:
        return [para]
    text = "".join(r.get("text", "") for r in para["runs"])
    pieces = [x for x in _SENTENCE_BREAK.split(text) if x]
    if len(pieces) <= 1:
        # 文の切れ目が無い場合は概ね収まる文字数で機械的に切る
        per_line = max(1, int(width / size))
        lines = max(1, int(max_h / (size * 1.35)))
        chunk = max(20, per_line * lines - per_line)
        pieces = [text[i : i + chunk] for i in range(0, len(text), chunk)]
    base_run = {k: v for k, v in para["runs"][0].items() if k != "text"}
    out: list[dict] = []
    current = ""
    for piece in pieces:
        trial = current + piece
        if current and estimate_paragraphs_height([{"runs": [{"text": trial}], "level": para.get("level", 0)}], width, size) > max_h:
            out.append({**para, "runs": [{**base_run, "text": current}]})
            current = piece
        else:
            current = trial
    if current:
        out.append({**para, "runs": [{**base_run, "text": current}]})
    return out


def _split_table_element(el: dict, max_h: float, params: dict) -> tuple[dict, dict | None]:
    """表を行単位で「収まる分」と「残り」に分ける。ヘッダー行は続きの表にも付ける。"""
    rows = el.get("rows") or []
    header_n = min(int(el.get("header_rows", 1) or 0), len(rows))
    row_h = params["body_font"] * 1.9
    capacity = max(header_n + 1, int(max_h // row_h))
    if len(rows) <= capacity:
        return el, None
    first = dict(el, rows=rows[:capacity])
    rest_rows = rows[:header_n] + rows[capacity:]
    second = dict(el, id=el["id"] + "_cont", rows=rest_rows)
    return first, second


def _split_text_element(el: dict, width: float, max_h: float, params: dict) -> tuple[dict, dict | None]:
    """テキスト要素を段落単位で「収まる分」と「残り」に分ける。1 段落で収まらない場合は文で分ける。"""
    size = params["body_font"]
    kept: list[dict] = []
    rest: list[dict] = []
    paragraphs: list[dict] = []
    for para in el.get("paragraphs", []):
        paragraphs.extend(_explode_long_paragraph(para, width, max_h, size))
    for para in paragraphs:
        if rest:
            rest.append(para)
            continue
        trial = kept + [para]
        if estimate_paragraphs_height(trial, width, size) <= max_h or not kept:
            kept.append(para)
        else:
            rest.append(para)
    first = dict(el, paragraphs=kept)
    if not rest:
        return first, None
    second = dict(el, id=el["id"] + "_cont", paragraphs=rest)
    return first, second


def layout_slide(slide: dict, canvas: dict, assets: dict, params: dict | None = None) -> list[dict]:
    """1枚のスライドをレイアウトし、分割が必要なら複数枚を返す。"""
    params = params or _layout_params()
    cw, ch = float(canvas["width_pt"]), float(canvas["height_pt"])
    margin, gutter = params["margin"], params["gutter"]
    content_w = cw - margin * 2

    result_slides: list[dict] = []
    pending = [el for el in slide.get("elements", [])]
    fixed = [el for el in pending if el.get("bbox")]
    flow = [el for el in pending if not el.get("bbox")]

    # 表紙・区切りスライドは中央寄せの専用レイアウト
    if slide.get("layout") == "closing":
        s = copy.deepcopy(slide)
        s["elements"] = list(fixed)
        for el in flow:
            s["elements"].append(dict(el, bbox=bbox(margin * 3, ch * 0.62, cw - margin * 6, params["title_h"])))
        return [s]
    if slide.get("layout") in ("title", "section") and flow:
        s = copy.deepcopy(slide)
        s["elements"] = list(fixed)
        y = ch * 0.32
        for el in flow:
            is_title = el.get("role") == "title"
            h = params["title_h"] * (1.4 if is_title else 0.8)
            el2 = dict(el, bbox=bbox(margin, y, content_w, h))
            if is_title:
                for p in el2.get("paragraphs", []):
                    p["align"] = p.get("align") or "center"
            else:
                for p in el2.get("paragraphs", []):
                    p["align"] = p.get("align") or "center"
            s["elements"].append(el2)
            y += h + gutter
        return [s]

    title_els = [el for el in flow if el.get("role") == "title"]
    body_els = [el for el in flow if el.get("role") != "title"]
    title_el = title_els[0] if title_els else None
    extra_titles = title_els[1:]
    body_els = extra_titles + body_els  # 2つ目以降のタイトルは本文扱い

    page_no = 0
    while True:
        s = copy.deepcopy(slide)
        s["elements"] = list(fixed) if page_no == 0 else []
        if page_no > 0:
            s["id"] = f"{slide['id']}_p{page_no + 1}"
            if s.get("title"):
                s["title"] = f"{s['title']}（続き）"
        y = margin
        if title_el is not None:
            t = copy.deepcopy(title_el)
            if page_no > 0:
                for p in t.get("paragraphs", []):
                    if p.get("runs"):
                        p["runs"][-1]["text"] = p["runs"][-1].get("text", "") + "（続き）"
                t["id"] = f"{t['id']}_p{page_no + 1}"
            t["bbox"] = bbox(margin, y, content_w, params["title_h"])
            s["elements"].append(t)
            y += params["title_h"] + gutter
        max_y = ch - margin

        # 列レイアウト: layout_hint.columns を持つ連続要素をまとめて配置
        remaining: list[dict] = []
        i = 0
        placed_any = False
        while i < len(body_els):
            el = body_els[i]
            hint = el.get("layout_hint") or {}
            cols = int(hint.get("columns") or 1)
            if cols > 1:
                cols = min(cols, params["max_columns"])
                group = []
                while i < len(body_els) and int((body_els[i].get("layout_hint") or {}).get("columns") or 1) == cols:
                    group.append(body_els[i])
                    i += 1
                col_w = (content_w - gutter * (cols - 1)) / cols
                col_y = [y] * cols
                for k, g in enumerate(group):
                    c = int((g.get("layout_hint") or {}).get("column", k % cols)) % cols
                    h = _element_height(g, col_w, params, assets)
                    if col_y[c] + h > max_y and placed_any:
                        remaining.extend(group[k:])
                        break
                    g2 = dict(g, bbox=bbox(margin + c * (col_w + gutter), col_y[c], col_w, min(h, max_y - col_y[c])))
                    s["elements"].append(g2)
                    col_y[c] += h + gutter
                    placed_any = True
                y = max(col_y)
                continue
            h = _element_height(el, content_w, params, assets)
            if y + h > max_y and el.get("type") == "image":
                # 画像は縦横比を保ったまま残り高さに縮小し、左右中央へ寄せる。残りが少なければ次ページへ。
                avail = max_y - y
                if avail >= (ch - margin * 2) * 0.35 or not placed_any:
                    ratio = h / content_w if content_w else 1.0
                    new_h = max(1.0, avail)
                    new_w = min(content_w, new_h / ratio) if ratio else content_w
                    s["elements"].append(dict(el, bbox=bbox(margin + (content_w - new_w) / 2, y, new_w, new_h)))
                    placed_any = True
                    y += new_h + gutter
                    i += 1
                    continue
                remaining.extend(body_els[i:])
                break
            if y + h > max_y:
                if el.get("type") == "text" and el.get("paragraphs") and (max_y - y) > params["body_font"] * 3:
                    first, second = _split_text_element(el, content_w, max_y - y, params)
                    if second is not None and first.get("paragraphs"):
                        first["bbox"] = bbox(margin, y, content_w, max_y - y)
                        s["elements"].append(first)
                        placed_any = True
                        remaining.append(second)
                        remaining.extend(body_els[i + 1:])
                        break
                if el.get("type") == "table" and len(el.get("rows") or []) > 2 and (max_y - y) > params["body_font"] * 1.9 * 3:
                    first, second = _split_table_element(el, max_y - y, params)
                    if second is not None:
                        first["bbox"] = bbox(margin, y, content_w, min(max_y - y, params["body_font"] * 1.9 * len(first["rows"])))
                        s["elements"].append(first)
                        placed_any = True
                        remaining.append(second)
                        remaining.extend(body_els[i + 1:])
                        break
                if placed_any or (y > margin + params["title_h"] + gutter and title_el is not None):
                    remaining.extend(body_els[i:])
                    break
                # 1要素で1枚に収まらない場合は高さを切り詰め、警告を残す
                h = max_y - y
                s.setdefault("warnings", []).append(warning("layout", "ELEMENT_TRUNCATED", "要素がスライドに収まらないため高さを切り詰めました。", slide_id=s["id"], element_id=el.get("id"), fallback="高さを切り詰め"))
            s["elements"].append(dict(el, bbox=bbox(margin, y, content_w, h)))
            placed_any = True
            y += h + gutter
            i += 1

        result_slides.append(s)
        if not remaining:
            break
        body_els = remaining
        page_no += 1
        if page_no > 50:  # 無限ループ防止
            break
    for idx, s in enumerate(result_slides):
        if idx > 0:
            s["warnings"] = s.get("warnings", []) + [warning("layout", "SLIDE_SPLIT", "内容が1枚に収まらないため分割しました。", slide_id=s["id"], fallback="スライド分割")]
    return result_slides


def layout_presentation(presentation: dict) -> dict:
    """全スライドをレイアウトし、index を振り直した新しい資料を返す。"""
    params = _layout_params()
    out = copy.deepcopy(presentation)
    new_slides: list[dict] = []
    for s in out.get("slides", []):
        if all(el.get("bbox") for el in s.get("elements", [])):
            new_slides.append(s)
            continue
        for ns in layout_slide(s, out["canvas"], out.get("assets", {}), params):
            new_slides.append(ns)
    for i, s in enumerate(new_slides):
        s["index"] = i
        for w in s.get("warnings", []):
            if w not in out.setdefault("warnings", []):
                out["warnings"].append(w)
    out["slides"] = new_slides
    return out


def make_title_slide(slide_id: str, index: int, title: str, subtitle: str | None = None) -> dict:
    """表紙スライドの雛形（HTML 変換で h1 を表紙にする際に使う）。"""
    s = new_slide(slide_id, index, layout="title", title=title)
    s["elements"].append(text_element(f"{slide_id}_title", [paragraph([run(title, bold=True)], align="center")], role="title"))
    if subtitle:
        s["elements"].append(text_element(f"{slide_id}_sub", [paragraph([run(subtitle)], align="center")], role="subtitle"))
    return s
