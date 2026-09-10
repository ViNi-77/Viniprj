"""文字量からテキスト高さを推定する。

フォント計測エンジンを持たないため、CJK 全角＝フォントサイズ幅、欧文＝サイズ×0.55 の
近似で折り返し行数を求める。文字切れ警告と自動レイアウトの両方で使う。
"""
from __future__ import annotations

import unicodedata

from .config import get_config


def _is_wide(ch: str) -> bool:
    return unicodedata.east_asian_width(ch) in ("W", "F")


def text_width_pt(text: str, size_pt: float) -> float:
    cfg = get_config()
    cjk = float(cfg.get("layout.cjk_char_width_ratio", 1.0))
    latin = float(cfg.get("layout.latin_char_width_ratio", 0.55))
    return sum(size_pt * (cjk if _is_wide(ch) else latin) for ch in text)


def wrapped_lines(text: str, size_pt: float, width_pt: float) -> int:
    """指定幅に折り返したときの行数（最低1行）。"""
    if width_pt <= 0:
        return max(1, len(text.splitlines()) or 1)
    total = 0
    for line in text.split("\n") or [""]:
        w = text_width_pt(line, size_pt)
        total += max(1, int(-(-w // width_pt)))  # 切り上げ
    return max(1, total)


def paragraph_size_pt(para: dict, default_size: float) -> float:
    sizes = [r.get("size_pt") for r in para.get("runs", []) if r.get("size_pt")]
    return float(max(sizes)) if sizes else default_size


def estimate_paragraphs_height(paragraphs: list[dict], width_pt: float, default_size: float, line_height_ratio: float | None = None, indent_pt: float = 18.0) -> float:
    cfg = get_config()
    ratio = float(line_height_ratio or cfg.get("layout.line_height_ratio", 1.35))
    height = 0.0
    for para in paragraphs:
        size = paragraph_size_pt(para, default_size)
        text = "".join(r.get("text", "") for r in para.get("runs", []))
        avail = width_pt - (indent_pt * (int(para.get("level", 0)) + (1 if para.get("bullet") else 0)))
        lines = wrapped_lines(text, size, max(1.0, avail))
        height += lines * size * ratio
        height += float(para.get("space_after_pt") or size * 0.3)
    return height
