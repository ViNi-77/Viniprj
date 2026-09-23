"""移行・選択・生成前検査・復元をまたぐ回帰試験。"""
import json
import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from contextgen_kai.api import CollectionInput, create_app
from contextgen_kai.backups import make_backup, restore_backup
from contextgen_kai.exporting import activate_export, build_export
from contextgen_kai.jobs import JobManager
from contextgen_kai.review import record_handoff, preview_collection
from contextgen_kai.scheduling import Scheduler
from contextgen_kai.storage import Store


@pytest.fixture
def setup(tmp_path):
    source = tmp_path / "日本語 資料"
    source.mkdir()
    (source / "a.txt").write_text("点検する場所 A", encoding="utf-8")
    store = Store(tmp_path / "state")
    lib = store.add_library("業務資料", str(source))
    manager = JobManager(store, use_process=False)
    assert manager.wait(manager.start(lib["id"])["id"])["state"] == "completed"
    yield source, store, lib, manager
    manager.close()


def coll(store, lib, **kw):
    return store.save_collection(dict(name="案件A", library_id=lib["id"], **kw))


def test_old_collection_migrates_without_cleanup(setup):
    _, store, lib, _ = setup
    c = coll(store, lib)
    store.execute("DELETE FROM collection_options WHERE collection_id=?", (c["id"],))
    reopened = Store(store.root)
    assert reopened.collection(c["id"])["cleanup"] == "none"
    assert reopened.collection(c["id"])["library_ids"] == [lib["id"]]


def test_fixed_selection_is_stable_when_search_text_changes(setup):
    _, store, lib, _ = setup
    doc = store.one("SELECT * FROM documents")
    fixed = coll(store, lib, document_ids=[doc["id"]], query="存在しない検索語", selection_mode="fixed")
    assert preview_collection(store, fixed)["total"] == 1
    dynamic = coll(store, lib, document_ids=[doc["id"]], query="存在しない検索語", selection_mode="dynamic")
    assert preview_collection(store, dynamic)["total"] == 0


def test_simultaneous_edits_have_one_winner(setup):
    _, store, _, _ = setup
    doc = store.one("SELECT * FROM documents")
    def edit(text):
        try:
            store.edit_document(doc["id"], dict(text=text, expected_revision=0, expected_hash=doc["source_hash"]))
            return "saved"
        except RuntimeError:
            return "conflict"
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(edit, ["一つ目", "二つ目"])) == ["conflict", "saved"]
    assert store.document(doc["id"])["revision"] == 1


def test_export_refresh_detects_equal_size_equal_mtime_change(setup):
    source, store, lib, manager = setup
    c = coll(store, lib)
    path = source / "a.txt"
    st = path.stat()
    path.write_text("点検する場所 B", encoding="utf-8")
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    job = manager.start(lib["id"], kind="export", collection_id=c["id"], refresh_sources=True)
    result = manager.wait(job["id"])
    assert result["state"] == "completed", result
    doc = store.one("SELECT * FROM documents")
    assert "場所 B" in doc["original_text"]


@pytest.mark.parametrize("change", ["source", "edit", "settings", "new_file"])
def test_activation_rejects_generation_that_became_stale(setup, change):
    source, store, lib, _ = setup
    c = coll(store, lib)
    previous = build_export(store, c["id"])
    candidate = build_export(store, c["id"])
    activate_export(store, previous["id"])
    if change == "source":
        (source / "a.txt").write_text("内容が変わりました", encoding="utf-8")
    elif change == "new_file":
        (source / "追加.txt").write_text("追加資料", encoding="utf-8")
    elif change == "edit":
        doc = store.one("SELECT * FROM documents")
        store.edit_document(doc["id"], dict(text="確認した本文", expected_hash=doc["source_hash"]))
    else:
        store.save_collection(dict(c, audience="別の利用者"), c["id"])
    with pytest.raises(ValueError, match="再生成"):
        activate_export(store, candidate["id"], verify_sources=True)
    assert store.one("SELECT id FROM exports WHERE is_active=1")["id"] == previous["id"]


def test_backup_roundtrip_preserves_options_history_handoff_and_disables_schedules(setup, tmp_path):
    _, store, lib, _ = setup
    doc = store.one("SELECT * FROM documents")
    store.edit_document(doc["id"], dict(text="修正その1", expected_hash=doc["source_hash"]))
    store.edit_document(doc["id"], dict(text="修正その2", expected_hash=doc["source_hash"]))
    c = coll(store, lib, target="studio", cleanup="standard", include_notes=False, audience="保全部門",
             evaluation_questions=[dict(question="注意点は？", expected_response="停止確認", source="a.txt")])
    generation = build_export(store, c["id"])
    manifest = json.loads(generation["manifest"])
    first = next(iter(manifest["knowledge_files"]))
    record_handoff(store, generation, dict(files=[first]))
    scheduler = Scheduler(store.root, lambda _: "unused")
    scheduler.save(dict(library_id=lib["id"], collection_id=c["id"], enabled=True))
    payload = json.loads(make_backup(store, scheduler))
    target = Store(tmp_path / "restored")
    restored_scheduler = Scheduler(target.root, lambda _: "unused")
    restore_backup(target, restored_scheduler, payload, CollectionInput)
    assert target.collection(c["id"])["evaluation_questions"] == c["evaluation_questions"]
    assert not target.collection(c["id"])["include_notes"]
    assert target.document(doc["id"])["edited_text"] == "修正その2"
    assert target.document(doc["id"])["revision"] == 2
    assert target.all("SELECT * FROM edit_history ORDER BY revision") == store.all("SELECT * FROM edit_history ORDER BY revision")
    assert target.handoff(c["id"], "studio")["files"] == {first: manifest["knowledge_files"][first]}
    assert not restored_scheduler.list()[0]["enabled"]


def test_invalid_schedule_rolls_back_all_restore_tables(setup, tmp_path):
    _, store, lib, _ = setup
    scheduler = Scheduler(store.root, lambda _: "unused")
    payload = json.loads(make_backup(store, scheduler))
    payload["schedules"] = [dict(library_id=lib["id"]), dict(library_id="missing")]
    target = Store(tmp_path / "restore-failure")
    target_scheduler = Scheduler(target.root, lambda _: "unused")
    with pytest.raises(ValueError):
        restore_backup(target, target_scheduler, payload, CollectionInput)
    assert target.all("SELECT * FROM libraries") == []
    assert target.all("SELECT * FROM documents") == []
    assert target_scheduler.list() == []


def test_legacy_backup_restores_with_cleanup_disabled(setup, tmp_path):
    _, store, lib, _ = setup
    c = coll(store, lib)
    scheduler = Scheduler(store.root, lambda _: "unused")
    payload = json.loads(make_backup(store, scheduler))
    payload["schema_version"] = 1
    payload["collections"] = [dict(id=c["id"], name=c["name"], library_id=lib["id"])]
    target = Store(tmp_path / "legacy")
    restore_backup(target, Scheduler(target.root, lambda _: "unused"), payload, CollectionInput)
    assert target.collection(c["id"])["cleanup"] == "none"


def test_legacy_set_update_does_not_enable_new_cleanup(setup):
    _, store, lib, _ = setup
    c = coll(store, lib, target="studio", cleanup="none", audience="現場の利用者")
    app = create_app(store.root, use_process=False, enable_scheduler=False)
    with TestClient(app) as client:
        token = client.get("/api/status").json()["token"]
        response = client.put("/api/collections/" + c["id"], headers={"X-Contextgen-Token": token}, json=dict(name="名前だけ改訂", library_id=lib["id"]))
        assert response.status_code == 200
        assert response.json()["cleanup"] == "none"
        assert response.json()["target"] == "studio"
        assert response.json()["audience"] == "現場の利用者"
