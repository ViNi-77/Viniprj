"""変換品質の自動検査。文字切れ、重なり、画像歪み、はみ出し、ページ順を確認する。

結果は warning と同じ構造に severity を足した「issue」の一覧。エラー停止はしない。
しきい値は config/app_config.json の quality.* から読む。
"""
from __future__ import annotations

from .config import get_config
from .text_metrics import estimate_paragraphs_height
from .typography import element_font_pt, font_scale


def _issue(code: str, message: str, severity: str = "warning", slide_id: str | None = None, element_id: str | None = None) -> dict:
    return {"stage": "quality_check", "code": code, "message": message, "severity": severity, "slide_id": slide_id, "element_id": element_id, "fallback": None}


def _overlap_area(a: dict, b: dict) -> float:
    x1, y1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    x2, y2 = min(a["x"] + a["w"], b["x"] + b["w"]), min(a["y"] + a["h"], b["y"] + b["h"])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def check_presentation(presentation: dict) -> list[dict]:
    cfg = get_config()
    overflow_ratio = float(cfg.get("quality.text_overflow_ratio_warn", 1.0))
    overlap_ratio = float(cfg.get("quality.overlap_area_ratio_warn", 0.15))
    aspect_tol = float(cfg.get("quality.image_aspect_tolerance", 0.03))
    cw, ch = float(presentation["canvas"]["width_pt"]), float(presentation["canvas"]["height_pt"])
    issues: list[dict] = []
    assets = presentation.get("assets", {})

    seen_ids: set[str] = set()
    for expected, s in enumerate(presentation.get("slides", [])):
        sid = s.get("id")
        if sid in seen_ids:
            issues.append(_issue("DUPLICATE_SLIDE_ID", f"スライド ID が重複しています: {sid}", "error", sid))
        seen_ids.add(sid)
        if int(s.get("index", expected)) != expected:
            issues.append(_issue("SLIDE_INDEX_MISMATCH", f"index が並び順と一致しません（{s.get('index')} ≠ {expected}）。", "warning", sid))
        elements = s.get("elements", [])
        if not elements:
            issues.append(_issue("EMPTY_SLIDE", "要素が無い空のスライドです。", "info", sid))
        el_ids: set[str] = set()
        for el in elements:
            eid = el.get("id")
            if eid in el_ids:
                issues.append(_issue("DUPLICATE_ELEMENT_ID", f"要素 ID が重複しています: {eid}", "error", sid, eid))
            el_ids.add(eid)
            b = el.get("bbox")
            if not b:
                issues.append(_issue("NO_BBOX", "座標が未確定の要素です（レイアウト未実行）。", "warning", sid, eid))
                continue
            if b["x"] < -1 or b["y"] < -1 or b["x"] + b["w"] > cw + 1 or b["y"] + b["h"] > ch + 1:
                issues.append(_issue("OUT_OF_CANVAS", "要素がスライド外にはみ出しています。", "warning", sid, eid))
            t = el.get("type")
            if t in ("text", "shape") and el.get("paragraphs"):
                pad = 12 if t == "text" else 28
                need = estimate_paragraphs_height(el["paragraphs"], max(1.0, b["w"] - pad), element_font_pt(el), scale=font_scale(el))
                if b["h"] > 0 and need / b["h"] > overflow_ratio * 1.15:
                    issues.append(_issue("TEXT_OVERFLOW", f"文字量が枠に対して多く、文字切れの可能性があります（推定 {need:.0f}pt / 枠 {b['h']:.0f}pt）。", "warning", sid, eid))
            if t == "image":
                asset = assets.get(el.get("asset_id") or "", {})
                nw, nh = asset.get("width_px"), asset.get("height_px")
                if el.get("placeholder"):
                    issues.append(_issue("IMAGE_PLACEHOLDER", "取得できなかった画像の代替枠です（後で画像を差し替えてください）。", "info", sid, eid))
                elif not asset:
                    issues.append(_issue("IMAGE_ASSET_MISSING", "画像資産が見つかりません。", "error", sid, eid))
                elif nw and nh and b["w"] > 0 and b["h"] > 0 and (el.get("fit") or "contain") == "stretch":
                    r_box, r_img = b["w"] / b["h"], float(nw) / float(nh)
                    if abs(r_box - r_img) / r_img > aspect_tol:
                        issues.append(_issue("IMAGE_ASPECT_DISTORTED", f"画像の縦横比が枠と異なります（画像 {r_img:.3f} / 枠 {r_box:.3f}）。", "warning", sid, eid))
            if t == "unsupported":
                issues.append(_issue("UNSUPPORTED_ELEMENT", f"未対応要素（{el.get('original_type') or '不明'}）が含まれます。", "info", sid, eid))
        # 重なり: 文字・画像・表同士のみ（図形は背景として重なるのが普通）
        content = [el for el in elements if el.get("bbox") and el.get("type") in ("text", "image", "table")]
        for i in range(len(content)):
            for j in range(i + 1, len(content)):
                a, b2 = content[i]["bbox"], content[j]["bbox"]
                area = _overlap_area(a, b2)
                smaller = min(a["w"] * a["h"], b2["w"] * b2["h"]) or 1.0
                if area / smaller > overlap_ratio:
                    issues.append(_issue("ELEMENT_OVERLAP", f"要素が重なっています（{content[i]['id']} と {content[j]['id']}、{area / smaller:.0%}）。", "warning", sid, content[i]["id"]))
    return issues


def summarize(issues: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for i in issues:
        counts[i["severity"]] = counts.get(i["severity"], 0) + 1
    return {"total": len(issues), "by_severity": counts, "ok": counts.get("error", 0) == 0}
