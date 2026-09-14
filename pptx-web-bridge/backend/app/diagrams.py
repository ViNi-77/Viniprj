"""図解の型の語彙。

かつては図解を図形へ展開する描画器だったが、描画は Copilot の仕事になったので
**語彙と、まとまりを 1 要素にする入れ物だけ**が残っている。

ここに残す理由: `pptx_parser` が「横並びの同じ形の図形」を 1 つの `diagram` 要素に
まとめており、その型が `spec_builder` の推定にそのまま使える。型の名前と呼び方を
2 か所に持つと必ずずれるので、正はこのファイルだけにする。
"""
from __future__ import annotations

import re
from typing import Any

# 型ごとの定義: 表示名・言葉から当てるための語・項目数の目安
TYPES: dict[str, dict[str, Any]] = {
    "flow": {"name": "フロー", "words": ("フロー", "手順", "流れ", "ステップ"), "min": 2, "max": 6},
    "cards": {"name": "カード", "words": ("カード", "3分割", "要点", "ポイント"), "min": 2, "max": 6},
    "compare": {"name": "比較", "words": ("比較", "Before", "対比"), "min": 2, "max": 2},
    "kpi": {"name": "数値", "words": ("KPI", "数値", "指標"), "min": 1, "max": 4},
    "timeline": {"name": "年表", "words": ("年表", "タイムライン", "沿革"), "min": 2, "max": 6},
}
DEFAULT_TYPE = "flow"
_TITLE_SEP = re.compile(r"\s*[:：]\s*")


def normalize_type(value: str | None) -> str:
    """'フロー' でも 'flow' でも受ける。分からなければ既定の型。"""
    if not value:
        return DEFAULT_TYPE
    v = str(value).strip()
    if v in TYPES:
        return v
    for key, spec in TYPES.items():
        if v == spec["name"] or v.lower() == key:
            return key
    return type_from_word(v) or DEFAULT_TYPE


def type_from_word(word: str | None) -> str | None:
    """文章の中の言葉から型を当てる（見つからなければ None）。"""
    if not word:
        return None
    low = str(word).lower()
    for key, spec in TYPES.items():
        for w in spec["words"]:
            if w and w.lower() in low:
                return key
    return None


def word_of(diagram_type: str) -> str:
    return TYPES.get(normalize_type(diagram_type), TYPES[DEFAULT_TYPE])["name"]


def item_limits(diagram_type: str) -> tuple[int, int]:
    spec = TYPES.get(normalize_type(diagram_type), TYPES[DEFAULT_TYPE])
    return int(spec["min"]), int(spec["max"])


def normalize_items(items: list[dict] | None) -> list[dict]:
    """項目を {title, text} に整える。'見出し: 説明' の 1 行も受ける。"""
    out: list[dict] = []
    for it in items or []:
        if isinstance(it, str):
            parts = _TITLE_SEP.split(it, 1)
            out.append({"title": parts[0].strip(), "text": (parts[1].strip() if len(parts) > 1 else "")})
            continue
        if not isinstance(it, dict):
            continue
        out.append({"title": str(it.get("title") or it.get("heading") or "").strip(), "text": str(it.get("text") or it.get("body") or "").strip()})
    return [it for it in out if it["title"] or it["text"]]


def diagram_element(el_id: str, diagram_type: str, items: list[dict], box: dict | None = None, **extra: Any) -> dict:
    """まとまった図解を 1 要素にする。子の座標は持たない（描くのはこのアプリではない）。"""
    dtype = normalize_type(diagram_type)
    el: dict[str, Any] = {
        "id": el_id,
        "type": "diagram",
        "role": None,
        "bbox": box,
        "diagram": {"type": dtype, "items": normalize_items(items)},
        "diagram_type": dtype,
        "editable": True,
    }
    el.update({k: v for k, v in extra.items() if v is not None})
    return el


def is_diagram(el: dict) -> bool:
    return el.get("type") == "diagram" and isinstance(el.get("diagram"), dict)
