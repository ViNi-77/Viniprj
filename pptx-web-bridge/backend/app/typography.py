"""文字サイズの決定を 1 か所にまとめる。

これまで「run.size_pt（明示 / 継承）」「描画時の役割既定」「レイアウト推定の別値」の 3 系統が
別々に存在し、同じ資料でも描画・推定・出力で大きさが食い違っていた。ここで
- 役割ごとの既定サイズと許容帯域（config: layout.*）
- 継承値の帯域クランプと要素単位の基準サイズ（el.font_pt）の確定
- 自動縮小（el.font_scale）を含めた実効サイズ
を定義し、レイアウト・Web 描画・PPTX 生成・レポート・品質検査はすべてこれを使う。
"""
from __future__ import annotations

from .config import get_config

_DEFAULT_BANDS: dict[str, list[float]] = {"title": [24, 36], "subtitle": [16, 24], "body": [12, 20], "caption": [9, 14], "card": [11, 18]}


def role_default_pt(role: str | None) -> float:
    cfg = get_config()
    if role == "title":
        return float(cfg.get("layout.title_font_pt", 28))
    if role == "subtitle":
        return float(cfg.get("layout.body_font_pt", 16)) * 1.25
    if role == "caption":
        return float(cfg.get("layout.caption_font_pt", 12))
    if role == "card":
        return float(cfg.get("layout.body_font_pt", 16)) * 0.875
    return float(cfg.get("layout.body_font_pt", 16))


def size_band(role: str | None) -> tuple[float, float]:
    """役割の許容サイズ帯 (min, max)。継承値だけをこの帯へ丸める（明示値は触らない）。"""
    bands = get_config().get("layout.size_bands") or {}
    band = bands.get(role or "body") or _DEFAULT_BANDS.get(role or "body") or _DEFAULT_BANDS["body"]
    lo, hi = float(band[0]), float(band[1])
    return (min(lo, hi), max(lo, hi))


def _role_key(el: dict) -> str | None:
    role = el.get("role")
    if el.get("type") == "shape" and role not in ("title", "subtitle", "caption"):
        return "card"
    return role


def normalize_element(el: dict) -> None:
    """run の継承サイズを帯域へ丸め、要素の基準サイズ el.font_pt を確定する。"""
    if el.get("type") not in ("text", "shape"):
        return
    role = _role_key(el)
    lo, hi = size_band(role)
    sizes: list[float] = []
    for p in el.get("paragraphs", []) or []:
        for r in p.get("runs", []) or []:
            size = r.get("size_pt")
            if size is None:
                continue
            size = float(size)
            if "size_pt" in (r.get("inherited") or []):
                size = min(hi, max(lo, size))
                r["size_pt"] = round(size, 1)
            sizes.append(size)
    el["font_pt"] = round(max(sizes), 1) if sizes else round(role_default_pt(role), 1)
    if el.get("font_scale") is None:
        el.pop("font_scale", None)


def normalize_presentation(presentation: dict) -> dict:
    for s in presentation.get("slides", []):
        for el in s.get("elements", []):
            normalize_element(el)
    return presentation


def element_font_pt(el: dict) -> float:
    """要素の基準サイズ（未正規化なら役割既定）。"""
    fp = el.get("font_pt")
    return float(fp) if fp else role_default_pt(_role_key(el))


def font_scale(el: dict) -> float:
    try:
        return max(0.5, min(1.0, float(el.get("font_scale") or 1.0)))
    except (TypeError, ValueError):
        return 1.0


def effective_size(run: dict, el: dict) -> float:
    """run の実効サイズ（pt）。明示/継承サイズ → 要素基準 の順に決め、自動縮小率を掛ける。"""
    base = run.get("size_pt")
    size = float(base) if base else element_font_pt(el)
    return size * font_scale(el)
