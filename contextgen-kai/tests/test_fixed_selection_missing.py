"""固定選択した資料の原本削除を黙って取りこぼさない。"""
import json
from pathlib import Path

import pytest

from contextgen_kai.exporting import activate_export, build_export
from contextgen_kai.jobs import JobManager
from contextgen_kai.review import preflight_collection, preview_collection
from contextgen_kai.storage import Store


def test_fixed_deleted_source_is_visible_held_and_preserves_active_generation(tmp_path):
    store = Store(tmp_path / "state")
    manager = JobManager(store, use_process=False)
    try:
        libraries = []
        for index in range(2):
            root = tmp_path / f"資料{index}"
            root.mkdir()
            for number in range(3):
                (root / f"{number}.txt").write_text(f"工程{index}-{number}の手順は個別に確認します", encoding="utf-8")
            library = store.add_library(f"登録{index}", str(root))
            libraries.append(library)
            assert manager.wait(manager.start(library["id"])["id"])["state"] == "completed"
        documents = store.all("SELECT * FROM documents ORDER BY library_id,relative_path")
        fixed = store.save_collection(dict(name="固定対象", library_ids=[lib["id"] for lib in libraries],
                                           selection_mode="fixed", document_ids=[doc["id"] for doc in documents]))
        previous = build_export(store, fixed["id"], verify_sources=True)
        assert previous["state"] == "published" and previous["document_count"] == 6
        deleted = documents[0]
        Path(deleted["source_path"]).unlink()
        job = manager.start(fixed["library_id"], kind="export", collection_id=fixed["id"], refresh_sources=True)
        completed = manager.wait(job["id"])
        assert completed["state"] == "held", completed
        generation = store.one("SELECT * FROM exports WHERE id=?", (completed["export_id"],))
        assert generation["document_count"] == 5  # 50%減少しなくても削除を検出する。
        assert "削除" in generation["reason"]
        assert store.one("SELECT id FROM exports WHERE is_active=1")["id"] == previous["id"]
        manifest = json.loads(generation["manifest"])
        assert manifest["missing"] == 1 and manifest["omitted"] == 1
        assert len(manifest["source_snapshot"]) == 6
        snapshot = next(doc for doc in manifest["source_snapshot"] if doc["id"] == deleted["id"])
        assert snapshot["active"] == 0
        sources = [json.loads(line) for line in (Path(generation["path"]) / "sources.jsonl").read_text(encoding="utf-8").splitlines()]
        assert "原本が削除済み" in next(doc for doc in sources if doc["id"] == deleted["id"])["omitted_reason"]
        assert not any(item["document_id"] == deleted["id"] for item in manifest["assignments"])
        preview = preview_collection(store, fixed)
        assert (preview["total"], preview["included"], preview["missing"]) == (6, 5, 1)
        missing_item = next(doc for doc in preview["items"] if doc["id"] == deleted["id"])
        assert not missing_item["included"] and missing_item["status"] == "deleted"
        preflight = preflight_collection(store, fixed)
        assert (preflight["total"], preflight["included"], preflight["issues"]) == (6, 5, 1)
        assert any(doc["document_id"] == deleted["id"] for doc in preflight["files"])
        assert preview_collection(store, {**fixed, "selection_mode": "dynamic"})["total"] == 5
        with pytest.raises(ValueError, match="再生成"):
            activate_export(store, previous["id"], verify_sources=True)
        # 削除を把握して生成した候補を利用者が確認した場合には確定できる。
        assert activate_export(store, generation["id"], verify_sources=True)["state"] == "published"
        # 復帰を再走査した後は、削除時の世代へ戻す操作も止める。
        Path(deleted["source_path"]).write_text("原本が復帰しました", encoding="utf-8")
        assert manager.wait(manager.start(deleted["library_id"])["id"])["state"] == "completed"
        with pytest.raises(ValueError, match="再生成"):
            activate_export(store, generation["id"], verify_sources=True)
    finally:
        manager.close()


def test_intentionally_excluded_missing_document_does_not_hold(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    (root / "keep.txt").write_text("残す資料", encoding="utf-8")
    (root / "omit.txt").write_text("選択から外した資料", encoding="utf-8")
    store = Store(tmp_path / "state")
    library = store.add_library("資料", str(root))
    manager = JobManager(store, use_process=False)
    try:
        manager.wait(manager.start(library["id"])["id"])
        documents = store.all("SELECT id,relative_path FROM documents")
        excluded_id = next(d["id"] for d in documents if d["relative_path"] == "omit.txt")
        collection = store.save_collection(dict(name="明示除外あり", library_id=library["id"], selection_mode="fixed",
                                                document_ids=[d["id"] for d in documents], excluded_document_ids=[excluded_id]))
        (root / "omit.txt").unlink()
        manager.wait(manager.start(library["id"])["id"])
        generation = build_export(store, collection["id"], verify_sources=True)
        assert generation["state"] == "published"
        assert json.loads(generation["manifest"])["missing"] == 0
    finally:
        manager.close()
