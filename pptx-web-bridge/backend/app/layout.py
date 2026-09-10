"""自動レイアウト。bbox を持たない要素（HTML 由来など）に座標を割り当てる。

方針:
- 決定的な計算のみ。AI に座標を決めさせない。
- 文字サイズは typography.py で一本化した基準（el.font_pt）を使う。
- タイトル → 本文の順に上から積む。layout_hint.columns があれば列に、layout_hint.row があれば「文字＋画像」の横並びにする。
- 画像は実寸（px×0.75）と縦横比を保ち、上限は高さ比、下限は最小高さ。下限を割るなら縮めずに次ページへ送る。
- 収まらないときは、まず文字を自動縮小（font_scale）し、それでも駄目なら分割する。残りが少なければ分割せず要素ごと次ページへ。
- 続きページには「（続き）」を付け、continuation_of で元スライドを示す。
"""
from __future__ import annotations

import copy
import re

from .config import get_config
from .model import bbox, new_slide, paragraph, run, text_element, warning
from .text_metrics import estimate_paragraphs_height
from .typography import element_font_pt, font_scale, normalize_presentation


def _layout_params() -> dict:
    cfg = get_config()
    steps = cfg.get("layout.autofit_steps") or [1.0, 0.95, 0.9, 0.85]
    return {
        "margin": float(cfg.get("layout.margin_pt", 36)),
        "gutter": float(cfg.get("layout.gutter_pt", 18)),
        "title_h": float(cfg.get("layout.title_height_pt", 64)),
        "title_font": float(cfg.get("layout.title_font_pt", 28)),
        "body_font": float(cfg.get("layout.body_font_pt", 16)),
        "caption_font": float(cfg.get("layout.caption_font_pt", 12)),
        "max_columns": int(cfg.get("layout.max_columns", 3)),
        "image_max_h_ratio": float(cfg.get("layout.image_max_height_ratio", 0.45)),
        "image_min_h": float(cfg.get("layout.image_min_height_pt", 120)),
        "image_side_weight": float(cfg.get("layout.image_side_weight", 0.4)),
        "autofit_steps": [float(x) for x in steps],
        "autofit_min": float(cfg.get("layout.autofit_min_scale", 0.85)),
        "split_min_ratio": float(cfg.get("layout.split_min_remaining_ratio", 0.25)),
    }


def _hint(el: dict) -> dict:
    return el.get("layout_hint") or {}


def _without_row(el: dict) -> dict:
    """次ページへ送る要素から横並びの印を外し、通常の流し込みへ戻す。"""
    h = {k: v for k, v in _hint(el).items() if k not in ("row", "side", "weight")}
    return dict(el, layout_hint=h or None)


def _image_box(el: dict, max_w: float, params: dict, assets: dict, canvas_h: float) -> tuple[float, float]:
    """画像の (幅, 高さ) pt。実寸（px×0.75）と縦横比を保ち、列幅と高さ上限で抑える。"""
    asset = assets.get(el.get("asset_id") or "", {}) if el.get("asset_id") else {}
    w_px, h_px = asset.get("width_px"), asset.get("height_px")
    if w_px and h_px:
        natural_w = float(w_px) * 0.75
        aspect = float(h_px) / float(w_px)
    else:
        natural_w = max_w * (0.4 if el.get("placeholder") else 1.0)
        aspect = 9 / 16
    w = min(natural_w, max_w)
    h = w * aspect
    cap = params["image_max_h_ratio"] * canvas_h
    if h > cap:
        h = cap
        w = min(max_w, h / aspect) if aspect else max_w
    return max(1.0, w), max(1.0, h)


def _element_height(el: dict, width: float, params: dict, assets: dict, scale: float = 1.0, canvas_h: float = 540.0) -> float:
    """要素の推定高さ（pt）。画像は縦横比から、表は行数から、テキストは折り返しから求める。"""
    t = el.get("type")
    if t == "text":
        font = element_font_pt(el)
        # レンダラーの内側余白（左右 6px ずつ）を差し引いて折り返しを見積もる
        return max(font * scale * 1.5, estimate_paragraphs_height(el.get("paragraphs", []), width - 12, font, scale=scale))
    if t == "image":
        return _image_box(el, width, params, assets, canvas_h)[1]
    if t == "table":
        rows = el.get("rows", [])
        row_h = params["body_font"] * 1.9
        return max(row_h, row_h * len(rows))
    if t == "shape":
        font = element_font_pt(el)
        pad = params["gutter"]
        inner = estimate_paragraphs_height(el.get("paragraphs", []), width - pad * 2, font, scale=scale)
        if _hint(el).get("band"):
            return max(font * scale * 1.6, inner + pad)
        return max(font * scale * 3, inner + pad * 2)
    if t == "line":
        return 2.0
    return params["body_font"] * 2


def _autofit(el: dict, width: float, avail: float, params: dict, assets: dict, canvas_h: float) -> tuple[float, float] | None:
    """縮小率を順に試し、収まる (高さ, 縮小率) を返す。収まらなければ None。"""
    if el.get("type") not in ("text", "shape") or not el.get("paragraphs"):
        return None
    for s in params["autofit_steps"]:
        if s < params["autofit_min"] - 1e-9:
            break
        h = _element_height(el, width, params, assets, scale=s, canvas_h=canvas_h)
        if h <= avail:
            return h, s
    return None


_SENTENCE_BREAK = re.compile(r"(?<=[。．.!?！？])")


def _explode_long_paragraph(para: dict, width: float, max_h: float, size: float, scale: float = 1.0) -> list[dict]:
    """1 段落だけで枠に収まらない場合、文の切れ目で複数段落に分ける（書式は先頭ランのものを引き継ぐ）。"""
    if estimate_paragraphs_height([para], width, size, scale=scale) <= max_h or len(para.get("runs", [])) == 0:
        return [para]
    text = "".join(r.get("text", "") for r in para["runs"])
    pieces = [x for x in _SENTENCE_BREAK.split(text) if x]
    if len(pieces) <= 1:
        # 文の切れ目が無い場合は概ね収まる文字数で機械的に切る
        per_line = max(1, int(width / (size * scale)))
        lines = max(1, int(max_h / (size * scale * 1.35)))
        chunk = max(20, per_line * lines - per_line)
        pieces = [text[i : i + chunk] for i in range(0, len(text), chunk)]
    base_run = {k: v for k, v in para["runs"][0].items() if k != "text"}
    out: list[dict] = []
    current = ""
    for piece in pieces:
        trial = current + piece
        if current and estimate_paragraphs_height([{"runs": [{**base_run, "text": trial}], "level": para.get("level", 0)}], width, size, scale=scale) > max_h:
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
    size = element_font_pt(el)
    scale = font_scale(el)
    inner_w = width - 12
    kept: list[dict] = []
    rest: list[dict] = []
    paragraphs: list[dict] = []
    for para in el.get("paragraphs", []):
        paragraphs.extend(_explode_long_paragraph(para, inner_w, max_h, size, scale))
    for para in paragraphs:
        if rest:
            rest.append(para)
            continue
        trial = kept + [para]
        if estimate_paragraphs_height(trial, inner_w, size, scale=scale) <= max_h or not kept:
            kept.append(para)
        else:
            rest.append(para)
    first = dict(el, paragraphs=kept)
    if not rest:
        return first, None
    second = dict(el, id=el["id"] + "_cont", paragraphs=rest)
    return first, second


def _free_band(fixed: list[dict], y0: float, y1: float, gutter: float) -> tuple[float, float]:
    """固定要素（bbox 済み）が占める縦区間を避けた、最も広い空き帯 (上端, 下端) を返す。"""
    occupied = sorted((float(b["y"]), float(b["y"]) + float(b["h"])) for el in fixed if (b := el.get("bbox")) and float(b.get("h") or 0) > 0)
    best, best_h, cur = (y0, y1), -1.0, y0
    for a, b in occupied:
        if a - cur > best_h:
            best, best_h = (cur, a), a - cur
        cur = max(cur, b)
    if y1 - cur > best_h:
        best = (cur, y1)
    top, bottom = best
    if top > y0:
        top += gutter
    if bottom < y1:
        bottom -= gutter
    return (top, bottom) if bottom - top > gutter else (y0, y1)


def _slide_autofit(body_els: list[dict], width: float, avail_h: float, params: dict, assets: dict, canvas_h: float) -> list[dict] | None:
    """本文全体が少し溢れる程度なら、分割せずに全要素を同じ率で縮める（PowerPoint の自動調整に相当）。

    列や横並びのヒントを持つスライドは高さの見積もりが複雑になるため対象外（要素単位の縮小に任せる）。
    """
    if not body_els or any(_hint(el).get("columns") or _hint(el).get("row") is not None for el in body_els):
        return None
    gutter = params["gutter"]

    def total(scale: float) -> float:
        return sum(_element_height(el, width, params, assets, scale=scale, canvas_h=canvas_h) for el in body_els) + gutter * (len(body_els) - 1)

    if total(1.0) <= avail_h:
        return None
    for s in params["autofit_steps"]:
        if s >= 1.0 or s < params["autofit_min"] - 1e-9:
            continue
        if total(s) <= avail_h:
            return [dict(el, font_scale=s) if el.get("type") in ("text", "shape") and el.get("paragraphs") else el for el in body_els]
    return None


def _continued_title(el: dict, page_no: int) -> dict:
    t = copy.deepcopy(el)
    for p in t.get("paragraphs", []):
        if p.get("runs"):
            p["runs"][-1]["text"] = p["runs"][-1].get("text", "") + "（続き）"
    t["id"] = f"{el['id']}_p{page_no + 1}"
    return t


def _place_row(group: list[dict], x0: float, y: float, max_y: float, content_w: float, params: dict, assets: dict, canvas_h: float, placed_any: bool) -> tuple[list[dict], list[dict], float]:
    """文字＋画像の横並び。戻り値 (配置した要素, 次ページへ送る要素, 次の y)。"""
    gutter = params["gutter"]
    img_side = next((_hint(g).get("side") for g in group if g.get("type") == "image" and _hint(g).get("side")), "right")
    weight = next((float(_hint(g)["weight"]) for g in group if _hint(g).get("weight")), params["image_side_weight"])
    weight = min(0.6, max(0.25, weight))
    img_w = content_w * weight
    txt_w = content_w - img_w - gutter
    left_w, right_w = (img_w, txt_w) if img_side == "left" else (txt_w, img_w)
    col_x = {"left": x0, "right": x0 + left_w + gutter}
    col_w = {"left": left_w, "right": right_w}
    cols: dict[str, list[dict]] = {"left": [], "right": []}
    for g in group:
        side = _hint(g).get("side") or (img_side if g.get("type") == "image" else ("left" if img_side == "right" else "right"))
        cols["left" if side == "left" else "right"].append(g)

    placed: list[dict] = []
    leftover: list[dict] = []
    bottom = y
    for side in ("left", "right"):
        cy = y
        w = col_w[side]
        members = cols[side]
        for k, g in enumerate(members):
            if g.get("type") == "image":
                iw, ih = _image_box(g, w, params, assets, canvas_h)
                if cy + ih > max_y:
                    room = max_y - cy
                    if room >= params["image_min_h"] or not (placed_any or placed):
                        aspect = ih / iw if iw else 1.0
                        ih = max(1.0, room)
                        iw = min(w, ih / aspect) if aspect else w
                    else:
                        leftover.extend(_without_row(m) for m in members[k:])
                        break
                placed.append(dict(g, bbox=bbox(col_x[side] + (w - iw) / 2, cy, iw, ih)))
                cy += ih + gutter
                continue
            h = _element_height(g, w, params, assets, canvas_h=canvas_h)
            if cy + h > max_y:
                fit = _autofit(g, w, max_y - cy, params, assets, canvas_h)
                if fit:
                    h, sc = fit
                    g = dict(g, font_scale=sc)
                elif g.get("type") == "text" and g.get("paragraphs") and (max_y - cy) > element_font_pt(g) * 3:
                    first, second = _split_text_element(g, w, max_y - cy, params)
                    if second is not None and first.get("paragraphs"):
                        placed.append(dict(first, bbox=bbox(col_x[side], cy, w, max_y - cy)))
                        cy = max_y
                        leftover.append(_without_row(second))
                        leftover.extend(_without_row(m) for m in members[k + 1 :])
                        break
                    if placed_any or placed:
                        leftover.extend(_without_row(m) for m in members[k:])
                        break
                    h = max_y - cy
                elif placed_any or placed:
                    leftover.extend(_without_row(m) for m in members[k:])
                    break
                else:
                    h = max_y - cy
            placed.append(dict(g, bbox=bbox(col_x[side], cy, w, h)))
            cy += h + gutter
        bottom = max(bottom, cy)
    return placed, leftover, bottom


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
            for p in el2.get("paragraphs", []):
                p["align"] = p.get("align") or "center"
            s["elements"].append(el2)
            y += h + gutter
        return [s]

    title_els = [el for el in flow if el.get("role") == "title"]
    body_els = [el for el in flow if el.get("role") != "title"]
    title_el = title_els[0] if title_els else None
    body_els = title_els[1:] + body_els  # 2つ目以降のタイトルは本文扱い
    fixed_title = next((el for el in fixed if el.get("role") == "title"), None)
    band_top, band_bottom = _free_band(fixed, margin, ch - margin, gutter) if fixed else (margin, ch - margin)
    min_split = params["split_min_ratio"] * (ch - margin * 2)

    page_no = 0
    while True:
        s = copy.deepcopy(slide)
        if page_no == 0:
            s["elements"] = list(fixed)
            y, max_y = band_top, band_bottom
        else:
            s["elements"] = []
            s["id"] = f"{slide['id']}_p{page_no + 1}"
            s["continuation_of"] = slide["id"]
            s["continuation_index"] = page_no
            if s.get("title"):
                s["title"] = f"{s['title']}（続き）"
            y, max_y = margin, ch - margin
            if fixed_title is not None:
                ft = _continued_title(fixed_title, page_no)
                s["elements"].append(ft)
                y = max(y, float(fixed_title["bbox"]["y"]) + float(fixed_title["bbox"]["h"]) + gutter)
        if title_el is not None:
            t = copy.deepcopy(title_el) if page_no == 0 else _continued_title(title_el, page_no)
            t["bbox"] = bbox(margin, y, content_w, params["title_h"])
            s["elements"].append(t)
            y += params["title_h"] + gutter
        has_title = title_el is not None or fixed_title is not None
        if page_no == 0:
            fitted = _slide_autofit(body_els, content_w, max_y - y, params, assets, ch)
            if fitted is not None:
                body_els = fitted

        remaining: list[dict] = []
        i = 0
        placed_any = False
        overflow = False
        while i < len(body_els) and not overflow:
            el = body_els[i]
            hint = _hint(el)
            cols = int(hint.get("columns") or 1)

            # 文字＋画像の横並び
            if hint.get("row") is not None:
                row_id = hint["row"]
                group: list[dict] = []
                while i < len(body_els) and _hint(body_els[i]).get("row") == row_id:
                    group.append(body_els[i])
                    i += 1
                placed, leftover, new_y = _place_row(group, margin, y, max_y, content_w, params, assets, ch, placed_any)
                if not placed:
                    remaining.extend(_without_row(g) for g in group)
                    remaining.extend(body_els[i:])
                    overflow = True
                    break
                s["elements"].extend(placed)
                placed_any = True
                y = new_y
                if leftover:
                    remaining.extend(leftover)
                    remaining.extend(body_els[i:])
                    overflow = True
                continue

            # 列レイアウト: layout_hint.columns を持つ連続要素をまとめて配置
            if cols > 1:
                cols = min(cols, params["max_columns"])
                group = []
                while i < len(body_els) and int(_hint(body_els[i]).get("columns") or 1) == cols and _hint(body_els[i]).get("row") is None:
                    group.append(body_els[i])
                    i += 1
                col_w = (content_w - gutter * (cols - 1)) / cols
                col_y = [y] * cols
                for k, g in enumerate(group):
                    c = int(_hint(g).get("column", k % cols)) % cols
                    if g.get("type") == "image":
                        iw, ih = _image_box(g, col_w, params, assets, ch)
                        if col_y[c] + ih > max_y and placed_any:
                            remaining.extend(group[k:])
                            remaining.extend(body_els[i:])
                            overflow = True
                            break
                        ih = min(ih, max_y - col_y[c]) if col_y[c] + ih > max_y else ih
                        s["elements"].append(dict(g, bbox=bbox(margin + c * (col_w + gutter) + (col_w - iw) / 2, col_y[c], iw, max(1.0, ih))))
                        col_y[c] += ih + gutter
                        placed_any = True
                        continue
                    h = _element_height(g, col_w, params, assets, canvas_h=ch)
                    if col_y[c] + h > max_y:
                        fit = _autofit(g, col_w, max_y - col_y[c], params, assets, ch)
                        if fit:
                            h, sc = fit
                            g = dict(g, font_scale=sc)
                        elif placed_any:
                            remaining.extend(group[k:])
                            remaining.extend(body_els[i:])
                            overflow = True
                            break
                        else:
                            h = max_y - col_y[c]
                    s["elements"].append(dict(g, bbox=bbox(margin + c * (col_w + gutter), col_y[c], col_w, h)))
                    col_y[c] += h + gutter
                    placed_any = True
                y = max(col_y)
                continue

            # 単独（全幅）
            if el.get("type") == "line":
                s["elements"].append(dict(el, bbox=bbox(margin, y, content_w, 1.0), points=[[round(margin, 2), round(y, 2)], [round(margin + content_w, 2), round(y, 2)]]))
                y += 2.0 + gutter
                i += 1
                placed_any = True
                continue
            if el.get("type") == "image":
                iw, ih = _image_box(el, content_w, params, assets, ch)
                if y + ih > max_y:
                    room = max_y - y
                    if room >= params["image_min_h"] or not placed_any:
                        aspect = ih / iw if iw else 1.0
                        ih = max(1.0, room)
                        iw = min(content_w, ih / aspect) if aspect else content_w
                    else:
                        remaining.extend(body_els[i:])
                        overflow = True
                        break
                s["elements"].append(dict(el, bbox=bbox(margin + (content_w - iw) / 2, y, iw, ih)))
                placed_any = True
                y += ih + gutter
                i += 1
                continue

            h = _element_height(el, content_w, params, assets, canvas_h=ch)
            # 見出し的な短い段落を末尾に残さない
            if hint.get("keep_with_next") and i + 1 < len(body_els) and placed_any:
                nxt = body_els[i + 1]
                next_h = min(_element_height(nxt, content_w, params, assets, canvas_h=ch), params["body_font"] * 3)
                if y + h + gutter + next_h > max_y:
                    remaining.extend(body_els[i:])
                    overflow = True
                    break
            if y + h > max_y:
                fit = _autofit(el, content_w, max_y - y, params, assets, ch)
                if fit:
                    h, sc = fit
                    el = dict(el, font_scale=sc)
                else:
                    avail = max_y - y
                    can_split = avail >= min_split or not placed_any
                    if can_split and el.get("type") == "text" and el.get("paragraphs") and avail > element_font_pt(el) * 3:
                        first, second = _split_text_element(el, content_w, avail, params)
                        if second is not None and first.get("paragraphs"):
                            first["bbox"] = bbox(margin, y, content_w, avail)
                            s["elements"].append(first)
                            placed_any = True
                            remaining.append(second)
                            remaining.extend(body_els[i + 1 :])
                            overflow = True
                            break
                    if can_split and el.get("type") == "table" and len(el.get("rows") or []) > 2 and avail > params["body_font"] * 1.9 * 3:
                        first, second = _split_table_element(el, avail, params)
                        if second is not None:
                            first["bbox"] = bbox(margin, y, content_w, min(avail, params["body_font"] * 1.9 * len(first["rows"])))
                            s["elements"].append(first)
                            placed_any = True
                            remaining.append(second)
                            remaining.extend(body_els[i + 1 :])
                            overflow = True
                            break
                    if placed_any or (has_title and y > margin + params["title_h"]):
                        remaining.extend(body_els[i:])
                        overflow = True
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
    """全スライドをレイアウトし、index を振り直した新しい資料を返す。文字サイズの正規化もここで行う。"""
    params = _layout_params()
    out = normalize_presentation(copy.deepcopy(presentation))
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


def element_height(el: dict, width: float, presentation: dict) -> float:
    """UI の「内容に合わせる」用: 要素の推定高さ（自動縮小率込み）。"""
    return _element_height(el, width, _layout_params(), presentation.get("assets", {}), scale=font_scale(el), canvas_h=float(presentation["canvas"]["height_pt"]))


def make_title_slide(slide_id: str, index: int, title: str, subtitle: str | None = None) -> dict:
    """表紙スライドの雛形（HTML 変換で h1 を表紙にする際に使う）。"""
    s = new_slide(slide_id, index, layout="title", title=title)
    s["elements"].append(text_element(f"{slide_id}_title", [paragraph([run(title, bold=True)], align="center")], role="title"))
    if subtitle:
        s["elements"].append(text_element(f"{slide_id}_sub", [paragraph([run(subtitle)], align="center")], role="subtitle"))
    return s
