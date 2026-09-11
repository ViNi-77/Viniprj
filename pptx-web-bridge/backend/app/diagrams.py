"""図解部品（フロー・カード・比較・KPI・年表）。

新しい要素種別を増やさず、`type: "diagram"` の 1 要素に「型 + 項目」を持たせ、
描画・PPTX 出力の直前に既存のプリミティブ（shape / text / line）へ展開する。

- 正は `diagram: {type, items[]}`。座標を持つのは親の bbox だけで、子は展開時に決まる。
- 展開後は既存の描画・生成・品質検査がそのまま使えるので、二重実装にならない。
- Copilot へは `型: フロー` のような 1 語で渡し、戻りの箇条書きから項目を組み立てる。
"""
from __future__ import annotations

import math
import re
from typing import Any

from .config import get_config
from .model import bbox, line_element, paragraph, run, shape_element, text_element
from .typography import role_default_pt

# 型ごとの定義: 表示名・Copilot に渡す語・項目数の目安・高さ比（本文幅に対する）
TYPES: dict[str, dict[str, Any]] = {
    "flow": {"name": "フロー", "words": ("フロー", "手順", "流れ", "ステップ"), "min": 2, "max": 6, "height_ratio": 0.26},
    "cards": {"name": "カード", "words": ("カード", "3分割", "要点", "ポイント"), "min": 2, "max": 6, "height_ratio": 0.30},
    "compare": {"name": "比較", "words": ("比較", "Before", "対比"), "min": 2, "max": 2, "height_ratio": 0.46},
    "kpi": {"name": "数値", "words": ("KPI", "数値", "指標"), "min": 1, "max": 4, "height_ratio": 0.26},
    "timeline": {"name": "年表", "words": ("年表", "タイムライン", "沿革"), "min": 2, "max": 6, "height_ratio": 0.22},
}
DEFAULT_TYPE = "flow"
_VALUE_SEP = re.compile(r"\s*[｜|]\s*")
_TITLE_SEP = re.compile(r"\s*[:：]\s*")

MARKDOWN_SPEC = """# 図解の型（`型:` の行で指定する）

| 型 | 書き方 | 例 |
|---|---|---|
| `型: フロー` | 箇条書き 1 行が 1 ステップ。`見出し: 説明` で説明を足せる | `- 受付: 窓口で受け取る` |
| `型: カード` | 箇条書き 1 行が 1 枚。`見出し: 説明` | `- 手作業が多い: 月 40 時間` |
| `型: 比較` | 箇条書きを 2 行だけ書く。左が現状、右が改善後 | `- Before: 二重作業` / `- After: 一度で済む` |
| `型: 数値` | `値｜ラベル`（縦棒は全角でも半角でもよい） | `- 40%｜作業時間の削減` |
| `型: 年表` | `時点: できごと` | `- 2024: 試験導入` |

- 1 枚に 1 つの図解。項目は 2〜6 個（比較は 2 個、数値は 4 個まで）
- 見出しは 12 字以内、説明は 30 字以内を目安にする
- 図解にしない普通の箇条書きは `型:` を書かないか、`型: 表紙 / 最終ページ / 画像 / 表` を使う
"""


# ---------------------------------------------------------------- 生成・正規化
def normalize_type(value: str | None) -> str:
    """型の指定（英語の id でも日本語の語でも）を id に直す。"""
    v = str(value or "").strip()
    if v in TYPES:
        return v
    low = v.lower()
    for key, spec in TYPES.items():
        if low == key or any(low == w.lower() for w in spec["words"]):
            return key
    for key, spec in TYPES.items():
        if any(w.lower() in low for w in spec["words"] if w):
            return key
    return DEFAULT_TYPE


def type_from_word(word: str | None) -> str | None:
    """`型:` の語が図解型を指していれば id を返す（そうでなければ None）。曖昧一致はしない。"""
    v = str(word or "").strip()
    if not v:
        return None
    if v in TYPES:
        return v
    low = v.lower()
    for key, spec in TYPES.items():
        if low == key or any(low == w.lower() for w in spec["words"]):
            return key
    for key, spec in TYPES.items():
        if any(w and w.lower() in low for w in spec["words"]):
            return key
    return None


def word_of(diagram_type: str) -> str:
    return str(TYPES.get(normalize_type(diagram_type), TYPES[DEFAULT_TYPE])["name"])


def normalize_items(items: list[dict] | None) -> list[dict]:
    out: list[dict] = []
    for it in items or []:
        if not isinstance(it, dict):
            it = {"title": str(it)}
        item = {"title": str(it.get("title", "") or "").strip()}
        for key in ("text", "value"):
            if str(it.get(key, "") or "").strip():
                item[key] = str(it[key]).strip()
        if item["title"] or item.get("text") or item.get("value"):
            out.append(item)
    return out


def item_limits(diagram_type: str) -> tuple[int, int]:
    spec = TYPES[normalize_type(diagram_type)]
    return int(spec["min"]), int(spec["max"])


def default_height(diagram_type: str, width: float, canvas_h: float = 540.0) -> float:
    """図解の標準の高さ。本文幅に対する比で決め、キャンバス高の一定割合で頭打ちにする。"""
    cfg = get_config()
    ratio = float(TYPES[normalize_type(diagram_type)]["height_ratio"])
    cap = float(cfg.get("layout.diagram_max_height_ratio", 0.55)) * float(canvas_h)
    return round(min(ratio * float(width), cap), 2)


def diagram_element(el_id: str, diagram_type: str, items: list[dict], box: dict | None = None, **extra: Any) -> dict:
    """図解要素。`diagram` に型と項目を持ち、子要素は描画・出力の直前に作る。"""
    el: dict[str, Any] = {
        "id": el_id,
        "type": "diagram",
        "role": None,
        "bbox": box,
        "diagram": {"type": normalize_type(diagram_type), "items": normalize_items(items)},
        "editable": True,
    }
    el.update({k: v for k, v in extra.items() if v is not None})
    return el


def is_diagram(el: dict) -> bool:
    return el.get("type") == "diagram"


def _colors(template: dict | None) -> dict:
    colors = dict((template or {}).get("colors") or {})
    return {
        "primary": colors.get("primary", "#1F3A5F"),
        "accent": colors.get("accent", "#E07A1F"),
        "surface": colors.get("surface", "#F4F6F9"),
        "line": colors.get("line", "#C9D1DB"),
        "text": colors.get("text", "#222222"),
        "muted": colors.get("muted", "#666666"),
        "background": colors.get("background", "#FFFFFF"),
    }


def _fit_scale(count: int, base_max: int) -> float:
    """項目が多いときの文字の縮み方（Phase A の font_scale と同じ 0.5〜1.0）。"""
    if count <= 3:
        return 1.0
    return round(max(0.7, 1.0 - 0.08 * (count - 3)), 2)


# ---------------------------------------------------------------- 展開
def expand_diagram(el: dict, template: dict | None = None, box: dict | None = None) -> list[dict]:
    """図解要素 → 既存のプリミティブ要素の並び。座標は親の bbox の内側に収める。"""
    spec = el.get("diagram") or {}
    dtype = normalize_type(spec.get("type"))
    items = normalize_items(spec.get("items"))
    b = box or el.get("bbox")
    if not b or not items:
        return []
    c = _colors(template)
    eid = str(el.get("id", "d"))
    z = int(el.get("z", 0) or 0)
    builder = {"flow": _flow, "cards": _cards, "compare": _compare, "kpi": _kpi, "timeline": _timeline}[dtype]
    children = builder(eid, items, dict(b), c)
    for i, child in enumerate(children):
        child["z"] = z
        child["editable"] = False
        child["diagram_of"] = eid
        child["diagram_index"] = i
    return children


def _card_box(b: dict, i: int, n: int, gap: float, top: float = 0.0, height: float | None = None) -> dict:
    w = (b["w"] - gap * (n - 1)) / n
    return bbox(b["x"] + i * (w + gap), b["y"] + top, w, (height if height is not None else b["h"] - top))


def _title_para(text: str, size: float, color: str, align: str = "center"):
    return paragraph([run(text, bold=True, size_pt=size, color=color)], align=align)


def _text_para(text: str, size: float, color: str, align: str = "center"):
    return paragraph([run(text, size_pt=size, color=color)], align=align)


def _flow(eid: str, items: list[dict], b: dict, c: dict) -> list[dict]:
    n = len(items)
    scale = _fit_scale(n, 6)
    arrow = min(28.0, b["w"] * 0.05)
    gap = arrow + 8
    size = role_default_pt("card") * scale
    out: list[dict] = []
    for i, it in enumerate(items):
        box = _card_box(b, i, n, gap)
        paras = [_title_para(it["title"], size * 1.1, c["background"])]
        if it.get("text"):
            paras.append(_text_para(it["text"], size * 0.9, c["background"]))
        out.append(shape_element(f"{eid}_s{i}", "rounded_rect", box, fill=c["primary"], paragraphs=paras, role="card", vertical_align="middle"))
        if i < n - 1:
            ax = box["x"] + box["w"] + 4
            ah = min(20.0, b["h"] * 0.3)
            out.append(shape_element(f"{eid}_a{i}", "arrow_right", bbox(ax, b["y"] + (b["h"] - ah) / 2, arrow, ah), fill=c["accent"]))
    return out


def _cards(eid: str, items: list[dict], b: dict, c: dict) -> list[dict]:
    n = len(items)
    per_row = n if n <= 3 else math.ceil(n / 2)
    rows = math.ceil(n / per_row)
    gap = 12.0
    row_h = (b["h"] - gap * (rows - 1)) / rows
    scale = _fit_scale(n, 6)
    size = role_default_pt("card") * scale
    out: list[dict] = []
    for i, it in enumerate(items):
        r, col = divmod(i, per_row)
        cols = min(per_row, n - r * per_row)
        row_box = {"x": b["x"], "y": b["y"] + r * (row_h + gap), "w": b["w"], "h": row_h}
        box = _card_box(row_box, col, cols, gap)
        paras = [_title_para(it["title"], size * 1.15, c["primary"], align="left")]
        if it.get("text"):
            paras.append(_text_para(it["text"], size, c["text"], align="left"))
        out.append(shape_element(f"{eid}_c{i}", "rect", box, fill=c["surface"], stroke=c["line"], stroke_width_pt=1, paragraphs=paras, role="card", vertical_align="top"))
    return out


def _compare(eid: str, items: list[dict], b: dict, c: dict) -> list[dict]:
    items = items[:2]
    gap = 16.0
    head_h = min(30.0, b["h"] * 0.22)
    size = role_default_pt("card")
    out: list[dict] = []
    for i, it in enumerate(items):
        box = _card_box(b, i, len(items), gap)
        fill = c["muted"] if i == 0 else c["primary"]
        out.append(shape_element(f"{eid}_h{i}", "rect", bbox(box["x"], box["y"], box["w"], head_h), fill=fill, paragraphs=[_title_para(it["title"], size * 1.1, c["background"])], role="card", vertical_align="middle"))
        body = bbox(box["x"], box["y"] + head_h, box["w"], box["h"] - head_h)
        out.append(shape_element(f"{eid}_b{i}", "rect", body, fill=c["surface"], stroke=c["line"], stroke_width_pt=1, paragraphs=[_text_para(it.get("text", ""), size, c["text"], align="left")], role="card", vertical_align="top"))
    return out


def _kpi(eid: str, items: list[dict], b: dict, c: dict) -> list[dict]:
    n = len(items)
    gap = 16.0
    value_h = b["h"] * 0.6
    value_size = max(24.0, min(48.0, value_h * 0.7))
    label_size = role_default_pt("card")
    out: list[dict] = []
    for i, it in enumerate(items):
        box = _card_box(b, i, n, gap)
        value = it.get("value") or it["title"]
        label = it.get("text") or (it["title"] if it.get("value") else "")
        out.append(text_element(f"{eid}_v{i}", [_title_para(str(value), value_size, c["accent"])], role="title", box=bbox(box["x"], box["y"], box["w"], value_h), vertical_align="middle"))
        if label:
            out.append(text_element(f"{eid}_l{i}", [_text_para(str(label), label_size, c["muted"])], role="caption", box=bbox(box["x"], box["y"] + value_h, box["w"], box["h"] - value_h), vertical_align="top"))
    return out


def _timeline(eid: str, items: list[dict], b: dict, c: dict) -> list[dict]:
    n = len(items)
    size = role_default_pt("card") * _fit_scale(n, 6)
    dot = min(14.0, b["h"] * 0.22)
    axis_y = b["y"] + b["h"] * 0.42
    out: list[dict] = [line_element(f"{eid}_axis", b["x"], axis_y, b["x"] + b["w"], axis_y, stroke=c["line"], stroke_width_pt=2)]
    step = b["w"] / n
    for i, it in enumerate(items):
        cx = b["x"] + step * (i + 0.5)
        out.append(shape_element(f"{eid}_d{i}", "ellipse", bbox(cx - dot / 2, axis_y - dot / 2, dot, dot), fill=c["accent"]))
        label_box = bbox(cx - step / 2 + 4, b["y"], step - 8, b["h"] * 0.42 - dot / 2)
        out.append(text_element(f"{eid}_t{i}", [_title_para(it["title"], size, c["primary"])], role="caption", box=label_box, vertical_align="bottom"))
        if it.get("text"):
            body_top = axis_y + dot / 2 + 4
            out.append(text_element(f"{eid}_x{i}", [_text_para(it["text"], size * 0.95, c["text"])], role="caption", box=bbox(cx - step / 2 + 4, body_top, step - 8, max(8.0, b["y"] + b["h"] - body_top)), vertical_align="top"))
    return out


# ---------------------------------------------------------------- Markdown 往復
def from_bullets(el_id: str, kind_word: str, bullets: list[str], box: dict | None = None) -> dict:
    """`型:` の語と箇条書き（文字列）から図解要素を作る。"""
    dtype = normalize_type(kind_word)
    items: list[dict] = []
    for raw in bullets:
        text = str(raw).strip()
        if not text:
            continue
        items.append(_item_from_text(dtype, text))
    if dtype == "compare":
        items = items[:2]
    return diagram_element(el_id, dtype, items, box)


def _item_from_text(dtype: str, text: str) -> dict:
    if dtype == "kpi":
        parts = _VALUE_SEP.split(text, maxsplit=1)
        if len(parts) == 2:
            return {"title": parts[1], "value": parts[0], "text": ""}
        parts = _TITLE_SEP.split(text, maxsplit=1)
        if len(parts) == 2:
            return {"title": parts[0], "value": parts[0], "text": parts[1]}
        return {"title": text, "value": text}
    parts = _TITLE_SEP.split(text, maxsplit=1)
    if len(parts) == 2 and parts[0] and parts[1]:
        return {"title": parts[0], "text": parts[1]}
    return {"title": text}


def to_bullets(el: dict) -> list[str]:
    """図解要素 → Markdown の箇条書き（`from_bullets` と往復する）。"""
    spec = el.get("diagram") or {}
    dtype = normalize_type(spec.get("type"))
    out: list[str] = []
    for it in normalize_items(spec.get("items")):
        if dtype == "kpi" and it.get("value"):
            out.append(f"{it['value']}｜{it.get('text') or it['title']}")
        elif it.get("text"):
            out.append(f"{it['title']}: {it['text']}")
        else:
            out.append(it["title"])
    return out
