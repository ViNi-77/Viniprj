"""Presentation JSON → 図解仕様（AI に渡す中間データ）。

このアプリは図解を描かない。描くのは Copilot。
代わりに「この資料はどんな図解なのか」を **文章と構造に分けて** 書き出し、
AI が読める形にする。これがプロンプトの中身になる。

設計:
- 文章は一字も変えない。要約・言い換え・並べ替えはしない（それは Copilot の仕事）。
- 型（フロー / カード / 比較 / 数値 / 年表 / 表 / 箇条書き / 画像+説明）は推定する。
  **推定は必ず外れる前提**（CLAUDE.md 9 章）なので、
  なぜそう判定したか（`kind_reason`）を必ず添えて、画面で変えられるようにする。
- 落としたものは黙って消さず `warnings` に残す（Phase L で決めた原則）。
- 表示・プロンプト埋め込みは `to_yaml()`。JSON をそのまま貼るより AI が読みやすく、字数も減る。
"""
from __future__ import annotations

import re
from typing import Any

from . import diagrams
from .logging_setup import get_logger
from .model import element_plain_text, slide_title, warning

log = get_logger("spec_builder")

# 図解の型。画面の選択肢もプロンプトの語彙もここだけを見る。
KINDS: dict[str, str] = {
    "flow": "フロー（手順・流れ）",
    "cards": "カード（要点を並べる）",
    "compare": "比較（Before / After・左右対比）",
    "kpi": "数値（指標を大きく見せる）",
    "timeline": "年表（時系列）",
    "table": "表",
    "bullets": "箇条書き",
    "image_text": "画像 + 説明",
    "image": "画像だけ",
    "title_only": "題名だけ",
}

# 型を言葉から当てるための辞書。既存の図解部品の語彙（diagrams.TYPES）をそのまま使う。
_WORDS: dict[str, tuple[str, ...]] = {k: tuple(w for w in v.get("words", []) if w) for k, v in diagrams.TYPES.items()}
_STEP_MARKS = re.compile(r"(^|\s)([①-⑳]|[0-9]{1,2}\s*[.．)）]|STEP\s*[0-9]|第\s*[0-9]+\s*(段|歩|ステップ))", re.I)
_ARROWS = ("→", "⇒", "▶", "->", "=>")
_NUMBER_LINE = re.compile(r"[0-9０-９][0-9０-９,，.．]*\s*(%|％|件|人|時間|分|秒|日|週|月|年|円|万|億|倍|点|個|台|本|回|kg|km|GB|MB)")
_YEAR_LINE = re.compile(r"(19|20)[0-9]{2}\s*(年|/|-)")
# 2 つ並んだ枠を「比較」と見なす条件。対の言葉が無ければただのカード 2 枚。
_COMPARE_WORDS = re.compile(r"(before|after|as[-\s]?is|to[-\s]?be|現行|現状|導入前|導入後|改善前|改善後|従来|新方式|旧|新)", re.I)


def _texts(el: dict) -> list[str]:
    return [ln for ln in element_plain_text(el).splitlines() if ln.strip()]


def _joined(slide: dict) -> str:
    return "\n".join(element_plain_text(el) for el in slide.get("elements", []))


def _word_hit(text: str) -> str | None:
    """題名・本文に型の名前が書かれていればそれを採用する（一番外れにくい手掛かり）。"""
    low = text.lower()
    for kind, words in _WORDS.items():
        for w in words:
            if w and w.lower() in low:
                return kind
    return None


def _card_like(slide: dict) -> list[dict]:
    """横並びの箱。html_parser は role='card'、pptx_parser は文字入りの図形として出す。"""
    cards = [e for e in slide.get("elements", []) if e.get("role") == "card"]
    if cards:
        return cards
    boxes = [e for e in slide.get("elements", []) if e.get("type") == "shape" and _texts(e)]
    if len(boxes) < 2:
        return []
    heights = [float((e.get("bbox") or {}).get("h") or 0) for e in boxes]
    if not all(heights):
        return boxes
    lo, hi = min(heights), max(heights)
    return boxes if hi <= lo * 1.6 else []


def _looks_like_kpi(lines: list[str]) -> bool:
    if not lines:
        return False
    hits = sum(1 for ln in lines if _NUMBER_LINE.search(ln))
    return hits >= 2 and hits >= len(lines) * 0.5


def _looks_like_timeline(lines: list[str]) -> bool:
    return sum(1 for ln in lines if _YEAR_LINE.search(ln)) >= 2


def _looks_like_flow(text: str, cards: list[dict]) -> bool:
    if any(a in text for a in _ARROWS):
        return True
    marked = sum(1 for c in cards if _STEP_MARKS.search(" ".join(_texts(c))))
    return marked >= 2


def infer_kind(slide: dict) -> tuple[str, str]:
    """スライド 1 枚の型を当てる。返り値は (型, なぜそう判定したか)。

    確信の持てる手掛かりから順に見る。外れる前提なので理由を必ず返す。
    """
    els = slide.get("elements", [])
    for el in els:
        if el.get("type") == "diagram":
            t = str(el.get("diagram_type") or el.get("diagram", {}).get("type") or "cards")
            return (t if t in KINDS else "cards"), "図解部品としてそのまま作られている"

    text = _joined(slide)
    tables = [e for e in els if e.get("type") == "table"]
    images = [e for e in els if e.get("type") == "image"]
    body_lines = _body_lines(slide)
    cards = _card_like(slide)

    hit = _word_hit(slide_title(slide))
    if hit:
        return hit, f"題名に「{next(w for w in _WORDS[hit] if w.lower() in slide_title(slide).lower())}」と書かれている"

    if tables:
        return "table", f"表が {len(tables)} 個ある"
    if cards:
        if _looks_like_flow(text, cards):
            return "flow", f"横並びの枠が {len(cards)} 個あり、矢印か番号が付いている"
        if len(cards) == 2 and _COMPARE_WORDS.search(" ".join(w for c in cards for w in _texts(c))):
            return "compare", "横並びの枠が 2 つあり、Before / After のような対の言葉が入っている"
        return "cards", f"同じくらいの大きさの枠が {len(cards)} 個並んでいる"
    if _looks_like_timeline(body_lines):
        return "timeline", "本文に年が 2 つ以上ある"
    if _looks_like_kpi(body_lines):
        return "kpi", "本文の過半数の行が数字と単位で出来ている"
    if images and body_lines:
        return "image_text", f"画像 {len(images)} 枚と本文がある"
    if images:
        return "image", f"画像 {len(images)} 枚だけで本文が無い"
    if body_lines:
        return "bullets", f"本文が {len(body_lines)} 行ある"
    return "title_only", "題名以外に中身が無い"


def _slide_images(slide: dict, presentation: dict) -> list[dict]:
    out = []
    assets = presentation.get("assets", {})
    for el in slide.get("elements", []):
        if el.get("type") != "image":
            continue
        aid = el.get("asset_id")
        a = assets.get(aid) or {}
        out.append({
            "asset_id": aid,
            "filename": a.get("filename") or "",
            "mime": a.get("mime") or "",
            "alt": el.get("alt") or "",
            "available": bool(a.get("data_base64") or a.get("data")),
        })
    return out


def _slide_items(slide: dict) -> list[dict]:
    """カード・フローの 1 項目ずつ。見出しと説明に分ける（文言は変えない）。"""
    items = []
    for el in _card_like(slide):
        lines = _texts(el)
        if not lines:
            continue
        items.append({"heading": lines[0], "body": " ".join(lines[1:])} if len(lines) > 1 else {"heading": lines[0], "body": ""})
    return items


def _slide_table(slide: dict) -> dict | None:
    for el in slide.get("elements", []):
        if el.get("type") != "table":
            continue
        rows = [[c.get("text", "") for c in row] for row in el.get("rows", [])]
        if not rows:
            continue
        hdr = int(el.get("header_rows") or 0)
        return {"header": rows[0] if hdr else [], "rows": rows[hdr:] if hdr else rows}
    return None


def _lead_element(slide: dict) -> dict | None:
    """リード文に使う要素。**1 行だけ**の副題・キャプションに限る。

    複数行あるものは中身（箇条書き）であってリードではない。ここを雑にすると、
    見出しの直後に置かれた箇条書きが丸ごと仕様から消える。
    """
    for el in slide.get("elements", []):
        if el.get("role") in ("subtitle", "caption") and len(_texts(el)) == 1:
            return el
    return None


def _body_lines(slide: dict) -> list[str]:
    """題名とリード以外の文字。役割名ではなく「リードに使ったかどうか」で分ける。"""
    lead = _lead_element(slide)
    out: list[str] = []
    for el in slide.get("elements", []):
        if el is lead or el.get("type") != "text" or el.get("role") == "title":
            continue
        out.extend(_texts(el))
    return out


def _slide_bullets(slide: dict, used: list[dict]) -> list[str]:
    used_ids = {id(e) for e in used}
    lead = _lead_element(slide)
    out: list[str] = []
    for el in slide.get("elements", []):
        if id(el) in used_ids or el is lead or el.get("type") != "text":
            continue
        if el.get("role") == "title":
            continue
        out.extend(_texts(el))
    return out


def _slide_lead(slide: dict) -> str:
    el = _lead_element(slide)
    return _texts(el)[0] if el else ""


def build_spec(presentation: dict, kind_overrides: dict[str, str] | None = None) -> dict:
    """Presentation JSON → 図解仕様。

    `kind_overrides` は {スライド番号(1始まりの文字列): 型} で、画面で直した型を上書きする。
    """
    overrides = {str(k): v for k, v in (kind_overrides or {}).items() if v in KINDS}
    meta = presentation.get("meta", {})
    src = meta.get("source", {}) or {}
    spec: dict[str, Any] = {
        "title": meta.get("title") or "",
        "source": {"type": src.get("type") or "", "filename": src.get("filename") or ""},
        "slide_count": len(presentation.get("slides", [])),
        "slides": [],
        "warnings": list(presentation.get("warnings", [])),
    }

    for i, slide in enumerate(presentation.get("slides", [])):
        no = str(i + 1)
        kind, reason = infer_kind(slide)
        if no in overrides:
            kind, reason = overrides[no], "画面で指定された"
        cards = _card_like(slide)
        entry: dict[str, Any] = {
            "no": i + 1,
            "title": slide_title(slide),
            "kind": kind,
            "kind_label": KINDS[kind],
            "kind_reason": reason,
        }
        lead = _slide_lead(slide)
        if lead:
            entry["lead"] = lead
        items = _slide_items(slide)
        if items:
            entry["items"] = items
        table = _slide_table(slide)
        if table:
            entry["table"] = table
        bullets = _slide_bullets(slide, cards)
        if bullets:
            entry["bullets"] = bullets
        images = _slide_images(slide, presentation)
        if images:
            entry["images"] = images
        if slide.get("notes"):
            entry["notes"] = str(slide["notes"])
        if not (items or table or bullets or images):
            spec["warnings"].append(warning("spec_builder", "SLIDE_HAS_NO_CONTENT", f"{i + 1} 枚目は題名以外に読み取れる中身がありませんでした。", slide_id=slide.get("id"), fallback="題名だけを渡します"))
        spec["slides"].append(entry)

    log.info("図解仕様: %s 枚 型=%s", spec["slide_count"], ",".join(s["kind"] for s in spec["slides"]))
    return spec


# ---- YAML 風の書き出し（プロンプトに埋める形） -------------------------------

def _q(v: Any) -> str:
    """YAML の値。改行やコロンを含む文字列は壊れるので必ず引用する。"""
    s = str(v)
    if s == "":
        return '""'
    if re.search(r'[:\-#\[\]{}&*!|>%@`"\n]', s) or s.strip() != s:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'
    return s


def to_yaml(spec: dict) -> str:
    """図解仕様を YAML 風のテキストにする。プロンプトにも画面にもこれを使う。

    **見た目（配色・フォント）はここに入れない。** `presentation["theme"]` はアプリ既定の
    テンプレート色であって実ファイルの色ではなく、書くと嘘になる。見た目は
    `theme_from_html` / `theme_from_pptx` が実ファイルから取り、プロンプト側で 1 箇所にまとめる。
    """
    L: list[str] = []
    L.append(f"資料: {_q(spec.get('title') or '（題名なし）')}")
    src = spec.get("source") or {}
    if src.get("filename"):
        L.append(f"出典: {_q(src['filename'])}")
    L.append(f"枚数: {spec.get('slide_count', 0)}")
    L.append("ページ:")
    for s in spec.get("slides", []):
        L.append(f"  - 番号: {s['no']}")
        L.append(f"    題名: {_q(s.get('title') or '')}")
        L.append(f"    型: {_q(s.get('kind_label') or s.get('kind'))}")
        if s.get("lead"):
            L.append(f"    リード: {_q(s['lead'])}")
        if s.get("items"):
            L.append("    項目:")
            for it in s["items"]:
                L.append(f"      - 見出し: {_q(it.get('heading') or '')}")
                if it.get("body"):
                    L.append(f"        説明: {_q(it['body'])}")
        if s.get("bullets"):
            L.append("    箇条書き:")
            for b in s["bullets"]:
                L.append(f"      - {_q(b)}")
        if s.get("table"):
            L.append("    表:")
            if s["table"].get("header"):
                L.append(f"      見出し: [{', '.join(_q(c) for c in s['table']['header'])}]")
            L.append("      行:")
            for row in s["table"].get("rows", []):
                L.append(f"        - [{', '.join(_q(c) for c in row)}]")
        if s.get("images"):
            L.append("    画像:")
            for im in s["images"]:
                name = im.get("filename") or im.get("asset_id") or "画像"
                L.append(f"      - ファイル: {_q(name)}" + (f"  # {im['alt']}" if im.get("alt") else ""))
        if s.get("notes"):
            L.append(f"    ノート: {_q(s['notes'])}")
    return "\n".join(L) + "\n"


def kind_options() -> list[dict]:
    """画面の型セレクタ用。"""
    return [{"id": k, "label": v} for k, v in KINDS.items()]
