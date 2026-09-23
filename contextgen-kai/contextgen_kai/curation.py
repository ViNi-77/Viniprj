"""原文を保持する決定的な資料整理。類似度やAIによる本文の削除は行わない。"""
from __future__ import annotations

import copy
import hashlib
import json


def _list(value):
    if isinstance(value, str):
        value = json.loads(value or "[]")
    return value if isinstance(value, list) else []


def _refs(unit):
    refs = list(unit.get("source_refs") or [])
    locator = unit.get("locator", "文書全体")
    if locator not in refs:
        refs.append(locator)
    return refs


def render_unit(unit):
    """抽出時と同じ区切りを使い、原文の改行・空白を保持する。"""
    if unit.get("document_level"):
        return unit["text"]
    return f"[{unit['locator']}]\n{unit['text']}"


def override_basis(doc, unit):
    """採否を確認した原本と原文単位。内容変更や再OCR結果の変化を検知する。"""
    return {"source_hash": doc.get("source_hash") or "",
            "text_hash": hashlib.sha256(str(unit.get("text") or "").encode("utf-8")).hexdigest()}


def prepare_document(doc, collection):
    """プレビューと出力で共用する、原本に書き込まない整理処理。"""
    doc = dict(doc)
    original = doc.get("original_text", "")
    effective = doc.get("effective_text", original)
    changes = []
    edited = doc.get("edited_text") is not None and not doc.get("conflict")
    raw_units = copy.deepcopy(_list(doc.get("units", [])))
    if edited or not raw_units:
        raw_units = [{"unit_id": "document", "locator": "文書全体（本文修正・位置未特定）" if edited else "文書全体",
                      "text": effective, "status": doc.get("status", "ok"), "kind": "body", "document_level": True}]
        if edited:
            changes.append({"kind": "document_edit", "unit_ids": [f"{doc['id']}:document"],
                            "detail": "全文修正のためページ・シート等の位置は未特定です。原本と確認してください。",
                            "before_chars": len(original), "after_chars": len(effective)})
    overrides = collection.get("unit_overrides") or {}
    bases = collection.get("unit_override_bases") or {}
    pending_overrides = []
    standard = collection.get("cleanup", "none") == "standard"
    units = []
    normalized_units = []
    grouped = {}
    for index, unit in enumerate(raw_units, 1):
        unit.setdefault("unit_id", f"unit-{index:06d}")
        unit.setdefault("locator", "文書全体")
        unit.setdefault("kind", "body")
        unit.setdefault("status", "ok")
        unit.setdefault("hidden", False)
        unit["unit_key"] = f"{doc['id']}:{unit['unit_id']}"
        unit["source_refs"] = _refs(unit)
        unit["source_unit_ids"] = [unit["unit_key"]]
        original_unit_text = str(unit.get("text") or "")
        unit["original_text"] = original_unit_text
        unit["override_basis"] = override_basis(doc, unit)
        override = overrides.get(unit["unit_key"])
        pending = override is not None and bases.get(unit["unit_key"]) != unit["override_basis"]
        unit["confirmation_pending"] = pending
        if pending:
            pending_overrides.append(unit["unit_key"])
            changes.append({"kind": "override_confirmation_required", "requires_confirmation": True,
                            "unit_ids": [unit["unit_key"]], "missing_unit": False,
                            "detail": f"採否の再確認が必要: {unit['locator']}。原本または読み取り結果が変わったか、確認基準がありません。現在の原文を保持しています。",
                            "before_chars": len(original_unit_text), "after_chars": len(original_unit_text)})
            # 非表示等の一括設定や標準整理も適用せず、確認前の新本文を落とさない。
            override = "include"
        normalized_units.append({**copy.deepcopy(unit), "key": unit["unit_key"]})
        excluded = override == "exclude" or (override != "include" and (
            (unit["hidden"] and not collection.get("include_hidden", True)) or
            ((unit["kind"] == "note" or unit.get("note")) and not collection.get("include_notes", True)) or
            ((unit["kind"] == "embedded" or unit.get("embedded"))
             and not collection.get("include_embedded", True))))
        if excluded:
            changes.append({"kind": "excluded", "unit_ids": [unit["unit_key"]], "detail": f"利用者の設定で除外: {unit['locator']}",
                            "before_chars": len(original_unit_text), "after_chars": 0})
            continue
        unit["text"] = str(unit["clean_text"]) if standard and not pending and unit.get("clean_text") is not None else original_unit_text
        if unit["text"] != original_unit_text:
            changes.append({"kind": "structured_text", "unit_ids": [unit["unit_key"]], "detail": f"構造化した表示を使用: {unit['locator']}",
                            "before_chars": len(original_unit_text), "after_chars": len(unit["text"])})
        # 完全一致の構造メタデータ、同一画像かつ同一OCR文字列だけを集約する。
        # 同じ画像でも読み取り結果が異なるときは両方を保持する。
        group = None
        if standard and override != "include":
            if unit["kind"] == "metadata" and unit["text"]:
                group = ("metadata", unit.get("role", ""), unit["text"])
            elif unit.get("image_hash"):
                group = ("image", unit["image_hash"], unit.get("image_frame", 0), unit["text"])
        if group and group in grouped:
            previous = grouped[group]
            for ref in unit["source_refs"]:
                if ref not in previous["source_refs"]:
                    previous["source_refs"].append(ref)
            previous["source_unit_ids"].append(unit["unit_key"])
            changes.append({"kind": "consolidated", "unit_ids": [previous["unit_key"], unit["unit_key"]],
                            "detail": "完全一致を集約しました。すべての出典位置を保持しています。",
                            "before_chars": len(unit["text"]), "after_chars": 0})
            continue
        if group:
            grouped[group] = unit
        units.append(unit)
    current_keys = {unit["unit_key"] for unit in normalized_units}
    for key in overrides:
        if key.startswith(f"{doc['id']}:") and key not in current_keys:
            pending_overrides.append(key)
            changes.append({"kind": "override_confirmation_required", "requires_confirmation": True,
                            "unit_ids": [key], "missing_unit": True,
                            "detail": "以前に採否を指定した位置が現在の原文に見つかりません。旧指定を解除し、必要なら現在の位置で指定し直してください。",
                            "before_chars": 0, "after_chars": 0})
    text = "\n\n".join(render_unit(unit) for unit in units if unit["text"])
    return {"original_text": original, "text": text, "units": units, "raw_units": normalized_units, "changes": changes,
            "before_chars": len(original), "after_chars": len(text),
            "requires_confirmation": bool(pending_overrides), "pending_overrides": pending_overrides}
