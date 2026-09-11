"""差分マージ再取込。

同じ資料を直して取り込み直すとき、これまでは全部置き換わり、キャンバスで直した
座標・文字・ノートが消えていた。ここでは 3 方向マージで「自分の編集」を残す。

- base   … 前回の取込直後の記録（`meta.import_snapshot`。鍵（先頭 40 字）とハッシュだけで本文は持たない）
- ours   … いま画面にある資料（編集済み）
- theirs … 新しく取り込んだ資料

要素の対応付けは id ではなく内容の鍵（種別 + 役割 + 文字の先頭）で行う。id は取込の
たびに振り直される連番なので当てにならない。
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

_WS = re.compile(r"\s+")
DEFAULT_POLICY = {"conflict": "theirs", "keep_user_bbox": True}


# ---------------------------------------------------------------- 鍵と照合用の文字
def element_text(el: dict) -> str:
    """要素の内容を 1 つの文字列にする（照合用。書式や座標は含めない）。"""
    t = el.get("type")
    if t in ("text", "shape"):
        return "\n".join("".join(r.get("text", "") for r in p.get("runs", [])) for p in el.get("paragraphs", []))
    if t == "table":
        return "\n".join("\t".join(str(c.get("text", "")) for c in row) for row in el.get("rows", []))
    if t == "image":
        return f"{el.get('asset_id') or ''}|{el.get('alt') or ''}"
    if t == "diagram":
        spec = el.get("diagram") or {}
        items = "；".join(f"{i.get('title', '')}:{i.get('text', '')}:{i.get('value', '')}" for i in spec.get("items") or [])
        return f"{spec.get('type')}|{items}"
    if t == "line":
        return "line"
    return str(el.get("alt") or el.get("original_type") or t or "")


def normalize(text: str) -> str:
    return _WS.sub(" ", str(text or "")).strip()


def text_hash(text: str) -> str:
    return hashlib.sha1(normalize(text).encode("utf-8")).hexdigest()[:12]


def element_key(el: dict) -> str:
    """要素の鍵。種別・役割と文字の先頭 40 字で決める（id は使わない）。"""
    t = el.get("type") or "?"
    role = el.get("role") or "-"
    body = normalize(element_text(el))
    if t == "image":
        body = (el.get("asset_id") or "")[:24] or normalize(el.get("alt") or "")
    elif t == "table":
        body = normalize(body.split("\n", 1)[0])
    return f"{t}|{role}|{body[:40]}"


def slide_key(slide: dict) -> str:
    title = normalize(slide.get("title") or "")
    if not title:
        first = next((element_text(e) for e in slide.get("elements", []) if e.get("type") in ("text", "shape")), "")
        title = normalize(first)[:40]
    return f"{title}|{slide.get('continuation_of') or ''}"


# ---------------------------------------------------------------- 取込の記録
def snapshot(presentation: dict, source: dict | None = None) -> dict:
    """取込直後の資料 → 照合用の記録（鍵とハッシュだけ。本文・画像は持たないので保存しても軽い）。"""
    return {
        "source": source or dict(presentation.get("meta", {}).get("source") or {}),
        "slides": [
            {
                "key": slide_key(s),
                "notes": text_hash(s.get("notes") or ""),
                "layout": s.get("layout"),
                "elements": [{"key": element_key(e), "hash": text_hash(element_text(e))} for e in s.get("elements", [])],
            }
            for s in presentation.get("slides", [])
        ],
    }


def attach_snapshot(presentation: dict, source: dict | None = None) -> dict:
    """取込直後の資料に記録を付け、各要素・スライドへ「取り込んだときの鍵」を焼き付ける。

    利用者が文字を直すと内容の鍵は変わるので、対応付けにはこの取込時の鍵を使う。
    """
    for s in presentation.get("slides", []):
        s["import_key"] = slide_key(s)
        for el in s.get("elements", []):
            el["import_key"] = element_key(el)
    presentation.setdefault("meta", {})["import_snapshot"] = snapshot(presentation, source)
    return presentation


def _base_maps(base: dict | None) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """記録 → {スライド鍵: [要素記録]} と {スライド鍵: ノートのハッシュ}。"""
    by_slide: dict[str, list[dict]] = {}
    notes: dict[str, str] = {}
    for s in (base or {}).get("slides", []) or []:
        by_slide.setdefault(s.get("key", ""), []).extend(s.get("elements", []) or [])
        notes.setdefault(s.get("key", ""), s.get("notes", ""))
    return by_slide, notes


# ---------------------------------------------------------------- マージ
def _pair_by_key(items: list[Any], key_of) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for it in items:
        out.setdefault(key_of(it), []).append(it)
    return out


def _edited(el: dict) -> bool:
    """利用者が手を入れた形跡があるか（座標を動かした / 文字を直した印）。"""
    return bool(el.get("user_bbox") or el.get("edited"))


def merge(ours: dict, theirs: dict, base: dict | None = None, policy: dict | None = None) -> tuple[dict, dict]:
    """3 方向マージ。ours の編集を残しつつ theirs の内容差分を取り込む。"""
    pol = {**DEFAULT_POLICY, **(policy or {})}
    base = base or (ours.get("meta", {}) or {}).get("import_snapshot")
    base_elements, base_notes = _base_maps(base)
    report: dict[str, Any] = {"added": 0, "removed": 0, "updated": 0, "kept_edits": 0, "kept_deleted": 0, "conflicts": [], "slides_added": 0, "slides_removed": 0}

    ours_slides = list(ours.get("slides", []))
    used: set[int] = set()
    merged_slides: list[dict] = []
    for ts in theirs.get("slides", []):
        tkey = slide_key(ts)
        match_i = next((i for i, os_ in enumerate(ours_slides) if i not in used and os_.get("import_key") == tkey), None)
        if match_i is None:
            match_i = next((i for i, os_ in enumerate(ours_slides) if i not in used and slide_key(os_) == tkey), None)
        if match_i is None:
            report["slides_added"] += 1
            merged_slides.append(ts)
            continue
        used.add(match_i)
        merged_slides.append(_merge_slide(ours_slides[match_i], ts, base_elements.get(tkey, []), base_notes.get(tkey), pol, report))

    # ours にしか無いスライド（利用者が足したもの）は元の位置のなるべく近くに残す
    for i, os_ in enumerate(ours_slides):
        if i in used:
            continue
        if base and any(s.get("key") in (os_.get("import_key"), slide_key(os_)) for s in base.get("slides", [])):
            report["slides_removed"] += 1  # 取込側で消えた（記録にあった）→ 消す
            continue
        merged_slides.append(os_)

    out = dict(theirs)
    out["meta"] = dict(ours.get("meta") or {})
    out["meta"]["source"] = dict(theirs.get("meta", {}).get("source") or {})
    out["theme"] = ours.get("theme") or theirs.get("theme")
    out["assets"] = {**(theirs.get("assets") or {}), **(ours.get("assets") or {})}
    out["slides"] = []
    for i, s in enumerate(merged_slides):
        s = dict(s)
        s["index"] = i
        out["slides"].append(s)
    out["warnings"] = list(theirs.get("warnings") or [])
    attach_snapshot(out, dict(theirs.get("meta", {}).get("source") or {}))  # 次のマージのため、鍵を今の内容で振り直す
    out["meta"]["import_snapshot"] = snapshot(theirs)  # 記録は「取り込んだ内容」を正とする
    return out, report


def _merge_slide(os_: dict, ts: dict, base_els: list[dict], base_note: str | None, pol: dict, report: dict) -> dict:
    merged = dict(ts)
    merged["id"] = os_.get("id") or ts.get("id")
    # ノート・背景・種別は「自分が base から変えていれば自分、そうでなければ取込側」
    merged["notes"] = os_.get("notes") if base_note is not None and text_hash(os_.get("notes") or "") != base_note else ts.get("notes") or os_.get("notes")
    if os_.get("background") and os_.get("background") != ts.get("background"):
        merged["background"] = os_["background"]
    ours_by_import_key = _pair_by_key([e for e in os_.get("elements", []) if e.get("import_key")], lambda e: e["import_key"])
    ours_by_key = _pair_by_key(os_.get("elements", []), element_key)
    base_by_key = _pair_by_key(base_els, lambda r: r.get("key", ""))
    taken: set[int] = set()
    elements: list[dict] = []
    for i, te in enumerate(ts.get("elements", [])):
        key = element_key(te)
        oe, base_rec = None, None
        # 1. 取込側が変わっていない場合: 取込時の鍵がそのまま一致する
        oe = next((c for c in (ours_by_import_key.get(key) or []) if id(c) not in taken), None)
        if oe is not None:
            base_rec = _take_base(base_by_key, key)
        if oe is None:
            # 2. 取込側が変わった場合: 前回の記録の同じ位置の鍵で、こちらの要素を引く
            base_rec = base_els[i] if i < len(base_els) and not base_els[i].get("_used") else None
            if base_rec is not None:
                oe = next((c for c in (ours_by_import_key.get(base_rec.get("key", "")) or []) if id(c) not in taken and c.get("type") == te.get("type")), None)
                if oe is not None:
                    base_rec["_used"] = True
                else:
                    base_rec = None
        if oe is None:
            # 3. 記録の無い要素（利用者が足した・前の版から持ち越した）: 内容の鍵、次に似ている文字で探す
            oe = next((c for c in (ours_by_key.get(key) or []) if id(c) not in taken and not c.get("import_key")), None)
            if oe is None:
                oe = _fuzzy_match(te, os_.get("elements", []), taken)
            if oe is not None and base_rec is None:
                base_rec = _take_base(base_by_key, oe.get("import_key") or element_key(oe))
        if oe is None:
            report["added"] += 1
            elements.append(te)
            continue
        taken.add(id(oe))
        elements.append(_merge_element(oe, te, base_rec, pol, report, os_.get("id")))
    # theirs に無い ours の要素
    for oe in os_.get("elements", []):
        if id(oe) in taken:
            continue
        key = oe.get("import_key") or element_key(oe)
        in_base = bool(base_by_key.get(key))
        if in_base and not _edited(oe):
            report["removed"] += 1
            continue
        report["kept_deleted" if in_base else "kept_edits"] += 1
        elements.append(oe)
    merged["elements"] = elements
    return merged


def _take_base(base_by_key: dict[str, list[dict]], key: str) -> dict | None:
    rec = next((r for r in base_by_key.get(key, []) if not r.get("_used")), None)
    if rec is not None:
        rec["_used"] = True
    return rec


def _fuzzy_match(te: dict, ours_elements: list[dict], taken: set[int]) -> dict | None:
    """鍵が変わった要素の対応付け。同じ種別・役割で、文字が 6 割以上似ていれば同じ要素とみなす。"""
    from difflib import SequenceMatcher

    t_text = normalize(element_text(te))
    if not t_text:
        return None
    best, best_ratio = None, 0.6
    for oe in ours_elements:
        if id(oe) in taken or oe.get("type") != te.get("type") or (oe.get("role") or None) != (te.get("role") or None):
            continue
        ratio = SequenceMatcher(None, t_text, normalize(element_text(oe))).ratio()
        if ratio > best_ratio:
            best, best_ratio = oe, ratio
    return best


def _merge_element(oe: dict, te: dict, base_rec: dict | None, pol: dict, report: dict, slide_id: str | None) -> dict:
    ours_hash = text_hash(element_text(oe))
    theirs_hash = text_hash(element_text(te))
    base_hash = (base_rec or {}).get("hash")
    ours_edited = base_hash is not None and ours_hash != base_hash
    theirs_changed = base_hash is not None and theirs_hash != base_hash
    if base_hash is None:
        # 記録が無い（初回のマージなど）: 文字が同じなら ours、違えば取込側を採用して競合として残す
        ours_edited = theirs_changed = ours_hash != theirs_hash

    if not theirs_changed:
        report["kept_edits"] += 1 if ours_edited else 0
        return _with_user_layout(oe, oe, pol)
    if not ours_edited:
        report["updated"] += 1
        return _with_user_layout(te, oe, pol)

    # 両方が変わった
    report["conflicts"].append({
        "slide_id": slide_id,
        "element_id": oe.get("id"),
        "type": oe.get("type"),
        "ours": normalize(element_text(oe))[:200],
        "theirs": normalize(element_text(te))[:200],
        "applied": pol["conflict"],
    })
    report["updated"] += 1 if pol["conflict"] == "theirs" else 0
    report["kept_edits"] += 1 if pol["conflict"] == "ours" else 0
    chosen = te if pol["conflict"] == "theirs" else oe
    return _with_user_layout(chosen, oe, pol)


def _with_user_layout(chosen: dict, oe: dict, pol: dict) -> dict:
    """採用した要素に、利用者が動かした座標・書式・id を移す。"""
    out = dict(chosen)
    out["id"] = oe.get("id") or out.get("id")
    if oe.get("import_key"):
        out["import_key"] = out.get("import_key") or oe["import_key"]
    if pol.get("keep_user_bbox") and oe.get("user_bbox") and oe.get("bbox"):
        out["bbox"] = dict(oe["bbox"])
        out["user_bbox"] = True
    for key in ("z", "vertical_align", "fill", "stroke", "stroke_width_pt", "font_pt", "font_scale", "rotation_deg"):
        if oe.get(key) is not None and chosen is not oe:
            out.setdefault(key, oe[key])
    return out


def summary_text(report: dict) -> str:
    """画面に出す 1 行の要約。"""
    return (
        f"追加 {report['added']} / 更新 {report['updated']} / 編集を保持 {report['kept_edits']} / "
        f"削除 {report['removed']} / 競合 {len(report['conflicts'])}"
    )
