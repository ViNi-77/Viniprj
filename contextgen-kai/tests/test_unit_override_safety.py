"""原本更新・再抽出・復元の後に古い採否を黙って適用しない。"""
import copy
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
import openpyxl
import pytest

from contextgen_kai.api import CollectionInput, create_app
from contextgen_kai.backups import make_backup, restore_backup
from contextgen_kai.curation import override_basis, prepare_document, render_unit
from contextgen_kai.exporting import activate_export, build_export
from contextgen_kai.jobs import JobManager
from contextgen_kai.scheduling import Scheduler
from contextgen_kai.storage import Store


def document(*texts):
    units = [{"unit_id": f"row-{index}", "locator": f"行 {index}", "text": text,
              "kind": "table_row", "clean_text": "整理済み表示", "hidden": True} for index, text in enumerate(texts, 1)]
    raw = "\n\n".join(render_unit(unit) for unit in units)
    return dict(id="document", source_hash="a" * 64, units=units, original_text=raw, effective_text=raw,
                edited_text=None, conflict=False, status="ok")


@pytest.mark.parametrize("change", ["source_hash", "text", "missing_basis"])
def test_stale_choice_keeps_raw_even_with_hidden_and_cleanup_options(change):
    doc = document("元の原文", "別の行")
    key = "document:row-1"
    settings = dict(cleanup="standard", include_hidden=False, unit_overrides={key: "exclude"},
                    unit_override_bases={key: override_basis(doc, doc["units"][0])})
    if change == "source_hash":
        doc["source_hash"] = "b" * 64
    elif change == "text":
        doc["units"][0]["text"] = "同じ原本の再OCRで認識が改善した原文"
    else:
        settings.pop("unit_override_bases")
    result = prepare_document(doc, settings)
    assert result["requires_confirmation"] and result["pending_overrides"] == [key]
    assert len(result["units"]) == 1
    assert result["units"][0]["text"] == doc["units"][0]["text"]
    assert result["raw_units"][0]["confirmation_pending"]
    assert result["raw_units"][0]["override_basis"] == override_basis(doc, doc["units"][0])
    assert any(c["kind"] == "override_confirmation_required" and not c["missing_unit"] for c in result["changes"])


def test_disappeared_unit_requires_explicit_removal_and_plain_save_does_not_rebase():
    doc = document("対象", "残存")
    key = "document:row-1"
    settings = dict(unit_overrides={key: "include"}, unit_override_bases={key: override_basis(doc, doc["units"][0])})
    original_settings = copy.deepcopy(settings)
    doc["units"].pop(0)
    result = prepare_document(doc, settings)
    assert settings == original_settings
    assert result["pending_overrides"] == [key]
    assert any(c["missing_unit"] for c in result["changes"])
    settings["unit_overrides"].pop(key)
    settings["unit_override_bases"].pop(key)
    assert not prepare_document(doc, settings)["requires_confirmation"]


def test_changed_excel_row_holds_until_explicit_confirmation_and_roundtrips_backup(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    path = source / "資料.xlsx"
    book = openpyxl.Workbook()
    book.active.append(["列名"])
    book.active.append(["以前の行2"])
    book.active.append(["常に必要な行3"])
    book.save(path)
    store = Store(tmp_path / "state")
    library = store.add_library("資料", str(source))
    jobs = JobManager(store, use_process=False)
    try:
        jobs.wait(jobs.start(library["id"])["id"])
        doc = store.document(store.one("SELECT id FROM documents")["id"])
        unit = next(u for u in doc["units"] if "行 2" in u["locator"])
        key = f"{doc['id']}:{unit['unit_id']}"
        collection = store.save_collection(dict(name="案件", library_id=library["id"], cleanup="standard",
                                                unit_overrides={key: "exclude"}, unit_override_bases={key: override_basis(doc, unit)}))
        previous = build_export(store, collection["id"], verify_sources=True)
        assert previous["state"] == "published"
        assert "以前の行2" not in (Path(previous["path"]) / "context.md").read_text(encoding="utf-8")
        book.active.insert_rows(2)
        book.active["A2"] = "追加された重要な前提条件"
        book.save(path)
        jobs.wait(jobs.start(library["id"])["id"])
        updated = store.document(doc["id"])
        store.save_collection({**collection, "audience": "対象者だけ変更"}, collection["id"])
        preserved = store.collection(collection["id"])
        assert preserved["unit_override_bases"] == collection["unit_override_bases"]
        held = build_export(store, collection["id"], force=True, verify_sources=True)
        assert held["state"] == "held"  # forceでも古い採否を確定しない。
        assert "追加された重要な前提条件" in (Path(held["path"]) / "context.md").read_text(encoding="utf-8")
        assert json.loads(held["manifest"])["pending_override_confirmations"] == [key]
        assert store.one("SELECT id FROM exports WHERE is_active=1")["id"] == previous["id"]
        with pytest.raises(ValueError, match="再確認"):
            activate_export(store, held["id"], verify_sources=True)
        preview = prepare_document(updated, preserved)
        basis = next(u["override_basis"] for u in preview["raw_units"] if u["unit_key"] == key)
        preserved["unit_override_bases"][key] = basis
        confirmed = store.save_collection(preserved, collection["id"])
        assert not prepare_document(updated, confirmed)["requires_confirmation"]
        published = build_export(store, collection["id"], verify_sources=True)
        assert published["state"] == "published"
        payload = json.loads(make_backup(store, Scheduler(store.root, lambda _: "unused")))
        restored = Store(tmp_path / "restored")
        restore_backup(restored, Scheduler(restored.root, lambda _: "unused"), payload, CollectionInput)
        assert restored.collection(collection["id"])["unit_override_bases"] == confirmed["unit_override_bases"]
        # 基準がない旧バックアップも読むが、再確認なしでは採否を適用しない。
        legacy = copy.deepcopy(payload)
        legacy["collections"][0].pop("unit_override_bases")
        older = Store(tmp_path / "legacy")
        restore_backup(older, Scheduler(older.root, lambda _: "unused"), legacy, CollectionInput)
        assert older.collection(collection["id"])["unit_override_bases"] == {}
        assert prepare_document(updated, older.collection(collection["id"]))["requires_confirmation"]
    finally:
        jobs.close()


def test_preview_api_provides_basis_and_rejects_malformed_basis(tmp_path):
    app = create_app(tmp_path / "api-state", use_process=False, enable_scheduler=False)
    with TestClient(app) as client:
        source = tmp_path / "api-source"
        source.mkdir()
        path = source / "資料.txt"
        path.write_text("確認すべき内容", encoding="utf-8")
        library = app.state.store.add_library("資料", str(source))
        app.state.jobs.wait(app.state.jobs.start(library["id"])["id"])
        doc = app.state.store.document(app.state.store.one("SELECT id FROM documents")["id"])
        collection = app.state.store.save_collection(dict(name="API確認", library_id=library["id"]))
        headers = {"X-Contextgen-Token": app.state.token}
        preview = client.post(f"/api/collections/{collection['id']}/preview-document", headers=headers, json={"document_id": doc["id"]}).json()
        unit = preview["raw_units"][0]
        assert unit["override_basis"] == {"source_hash": hashlib.sha256(path.read_bytes()).hexdigest(),
                                            "text_hash": hashlib.sha256(unit["text"].encode()).hexdigest()}
        saved = client.put(f"/api/collections/{collection['id']}", headers=headers,
                           json={**collection, "unit_overrides": {unit["unit_key"]: "include"}, "unit_override_bases": {unit["unit_key"]: unit["override_basis"]}})
        assert saved.status_code == 200, saved.text
        malformed = {**saved.json(), "unit_override_bases": {unit["unit_key"]: {"source_hash": "invalid", "text_hash": ""}}}
        assert client.put(f"/api/collections/{collection['id']}", headers=headers, json=malformed).status_code == 400
