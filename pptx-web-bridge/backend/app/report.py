"""要素判別レポート。

「文字は画像ではなくテキストシェイプとして、フォントサイズと座標を数値で持つ」ことを
利用者が確認できるよう、スライドごとに 要素種別 / 役割 / x,y,w,h(pt) / フォント pt / 文字（抜粋）/ 編集可否 を列挙する。
JSON と Markdown の両方を返し、Web 一式にも conversion_report.md として同梱する。
"""
from __future__ import annotations

from .model import element_plain_text, slide_title
from .typography import effective_size

_TYPE_LABEL = {"text": "文字", "shape": "図形(文字付き)", "image": "画像", "line": "線", "table": "表", "diagram": "図解", "unsupported": "未対応"}


def element_rows(presentation: dict) -> list[dict]:
    rows: list[dict] = []
    assets = presentation.get("assets", {})
    for s in presentation.get("slides", []):
        for el in s.get("elements", []):
            b = el.get("bbox") or {}
            sizes = [round(effective_size(r, el), 1) for p in el.get("paragraphs", []) for r in p.get("runs", [])] if el.get("type") in ("text", "shape") else []
            text = element_plain_text(el).replace("\n", " / ")
            asset = assets.get(el.get("asset_id") or "", {})
            rows.append(
                {
                    "slide": int(s.get("index", 0)) + 1,
                    "slide_id": s.get("id"),
                    "slide_title": slide_title(s),
                    "element_id": el.get("id"),
                    "kind": _TYPE_LABEL.get(el.get("type"), el.get("type")),
                    "type": el.get("type"),
                    "role": el.get("role"),
                    "x": b.get("x"),
                    "y": b.get("y"),
                    "w": b.get("w"),
                    "h": b.get("h"),
                    "font_pt_min": min(sizes) if sizes else None,
                    "font_pt_max": max(sizes) if sizes else None,
                    "paragraphs": len(el.get("paragraphs", [])) if el.get("type") in ("text", "shape") else None,
                    "text": text[:60] + ("…" if len(text) > 60 else ""),
                    "image_px": f"{asset.get('width_px')}×{asset.get('height_px')}" if asset else None,
                    "editable": bool(el.get("editable", False)),
                }
            )
    return rows


def summary(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    text_rows = [r for r in rows if r["type"] in ("text", "shape", "table")]
    return {
        "elements": len(rows),
        "by_kind": counts,
        "text_as_shapes": len(text_rows),
        "text_with_bbox": sum(1 for r in text_rows if r["x"] is not None),
        "images": sum(1 for r in rows if r["type"] == "image"),
        "editable_ratio": round(sum(1 for r in rows if r["editable"]) / len(rows), 3) if rows else 1.0,
    }


def build_report(presentation: dict) -> dict:
    rows = element_rows(presentation)
    return {"summary": summary(rows), "rows": rows, "markdown": to_markdown(presentation, rows)}


def to_markdown(presentation: dict, rows: list[dict] | None = None) -> str:
    rows = rows if rows is not None else element_rows(presentation)
    sm = summary(rows)
    canvas = presentation.get("canvas", {})
    lines = [
        f"# 要素判別レポート: {presentation.get('meta', {}).get('title', '')}",
        "",
        f"- キャンバス: {canvas.get('width_pt')} × {canvas.get('height_pt')} pt（原点左上、単位 pt）",
        f"- 要素数: {sm['elements']}（{'、'.join(f'{k} {v}' for k, v in sm['by_kind'].items())}）",
        f"- 文字系要素（文字・図形・表）: {sm['text_as_shapes']} 件はすべてテキストシェイプとして出力（画像化しない）",
        f"- 編集可能率: {sm['editable_ratio']:.0%}",
        "",
        "| # | スライド | 要素ID | 種別 | 役割 | x | y | w | h | フォントpt | 文字（抜粋） | 画像px | 編集可 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        f = lambda v: "" if v is None else (f"{v:.1f}" if isinstance(v, float) else str(v))  # noqa: E731
        font = "" if r["font_pt_min"] is None else (f"{r['font_pt_min']:g}" if r["font_pt_min"] == r["font_pt_max"] else f"{r['font_pt_min']:g}–{r['font_pt_max']:g}")
        lines.append(f"| {i} | {r['slide']} | {r['element_id']} | {r['kind']} | {r['role'] or ''} | {f(r['x'])} | {f(r['y'])} | {f(r['w'])} | {f(r['h'])} | {font} | {(r['text'] or '').replace('|', '／')} | {r['image_px'] or ''} | {'○' if r['editable'] else '×'} |")
    return "\n".join(lines) + "\n"
