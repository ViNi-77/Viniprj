"""利用者の操作をまたぐ永続化・差分更新・非破壊出力の受入試験。"""
from collections import Counter
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from contextgen_kai import extractors
from contextgen_kai.api import create_app
from contextgen_kai.exporting import activate_export, build_export
from contextgen_kai.jobs import JobManager
from contextgen_kai.storage import Store


@pytest.fixture
def workspace(tmp_path):
    sources = tmp_path / "日本語 資料"
    sources.mkdir()
    store = Store(tmp_path / "state")
    library = store.add_library("日常業務", str(sources))
    manager = JobManager(store, use_process=False)
    yield sources, store, library, manager
    manager.close()


def scan(manager, library_id):
    job = manager.start(library_id)
    final = manager.wait(job["id"], timeout=30)
    assert final["state"] == "completed", final
    return final


def document(store, library, relative):
    doc_id = store.one("SELECT id FROM documents WHERE library_id=? AND relative_path=?", (library["id"], relative))["id"]
    return store.document(doc_id)


def collection(store, library, **overrides):
    return store.save_collection({"name": "設備確認", "library_id": library["id"], "purpose": "overview", **overrides})


def test_only_changed_files_are_reextracted_and_deleted_files_deactivated(workspace, monkeypatch):
    sources, store, library, manager = workspace
    for name, text in {"first.txt": "第一資料:点検", "second.txt": "第二資料:製造", "third.txt": "第三資料:設備"}.items():
        (sources / name).write_text(text, encoding="utf-8")
    actual = extractors.extract_document
    calls = Counter()

    def counted(path, **kwargs):
        calls[path.name] += 1
        return actual(path, **kwargs)

    monkeypatch.setattr(extractors, "extract_document", counted)
    initial = scan(manager, library["id"])
    assert initial["processed"] == initial["total"] == 3
    assert calls == {"first.txt": 1, "second.txt": 1, "third.txt": 1}
    scan(manager, library["id"])
    assert sum(calls.values()) == 3
    (sources / "second.txt").write_text("第二資料:製造工程 改訂版", encoding="utf-8")
    (sources / "third.txt").unlink()
    scan(manager, library["id"])
    assert calls == {"first.txt": 1, "second.txt": 2, "third.txt": 1}
    assert store.counts()["total"] == 2
    assert store.list_documents(library["id"], query="改訂版")["total"] == 1
    assert document(store, library, "third.txt")["active"] == 0


def test_edits_exclusions_and_conflicts_survive_restart_without_touching_source(workspace):
    sources, store, library, manager = workspace
    source = sources / "note.txt"
    source.write_text("原本のOCR誤字", encoding="utf-8")
    scan(manager, library["id"])
    doc = document(store, library, "note.txt")
    store.edit_document(doc["id"], {"text": "修正した本文", "expected_hash": doc["source_hash"], "excluded": True})
    assert source.read_text(encoding="utf-8") == "原本のOCR誤字"
    with pytest.raises(RuntimeError, match="原本が更新"):
        store.edit_document(doc["id"], {"text": "古い画面からの保存", "expected_hash": "stale"})
    manager.close()
    restarted_store = Store(store.root)
    restarted = JobManager(restarted_store, use_process=False)
    try:
        scan(restarted, library["id"])
        unchanged = restarted_store.document(doc["id"])
        assert unchanged["effective_text"] == "修正した本文"
        assert unchanged["excluded"] and not unchanged["conflict"]
        source.write_text("更新後の原本本文", encoding="utf-8")
        scan(restarted, library["id"])
        changed = restarted_store.document(doc["id"])
        assert changed["conflict"] and changed["excluded"]
        assert changed["edited_text"] == "修正した本文"
        assert "更新後の原本本文" in changed["effective_text"]
        assert "修正した本文" not in changed["effective_text"]
        resolved = restarted_store.edit_document(doc["id"], {"text": "更新後を確認した修正", "expected_hash": changed["source_hash"], "excluded": False})
        assert not resolved["conflict"] and not resolved["excluded"]
        assert restarted_store.list_documents(library["id"], query="確認した修正")["total"] == 1
        reverted = restarted_store.edit_document(doc["id"], {"text": None})
        assert reverted["edited_text"] is None and reverted["effective_text"] == reverted["original_text"]
    finally:
        restarted.close()


def test_stop_resume_keeps_completed_cache_and_error_count(workspace, monkeypatch):
    sources, store, library, manager = workspace
    (sources / "00-legacy.doc").write_bytes(b"legacy")
    for index in range(1, 6):
        (sources / f"{index:02d}.txt").write_text(f"document {index}", encoding="utf-8")
    actual = extractors.extract_document
    calls = Counter()

    def stop_after_two(path, **kwargs):
        calls[path.name] += 1
        result = actual(path, **kwargs)
        if sum(calls.values()) == 2:
            running = store.one("SELECT id FROM jobs WHERE state='extracting'")
            manager.stop(running["id"])
        return result

    monkeypatch.setattr(extractors, "extract_document", stop_after_two)
    job = manager.start(library["id"])
    stopped = manager.wait(job["id"])
    assert stopped["state"] == "stopped" and stopped["processed"] == 2
    assert stopped["errors"] == 1
    manager.resume(job["id"])
    completed = manager.wait(job["id"])
    assert completed["state"] == "completed"
    assert completed["processed"] == completed["total"] == 6
    assert calls == {"00-legacy.doc": 1, "01.txt": 1, "02.txt": 1, "03.txt": 1, "04.txt": 1, "05.txt": 1}
    assert completed["errors"] == 1


def test_unavailable_library_does_not_remove_cached_documents(workspace):
    sources, store, library, manager = workspace
    (sources / "data.txt").write_text("保管しておく本文", encoding="utf-8")
    scan(manager, library["id"])
    original = document(store, library, "data.txt")
    sources.rename(sources.with_name("offline"))
    job = manager.start(library["id"])
    failed = manager.wait(job["id"])
    assert failed["state"] == "failed"
    after = store.document(original["id"])
    assert after["active"] and after["source_hash"] == original["source_hash"]
    assert after["effective_text"] == original["effective_text"]


def test_export_preserves_sources_deduplicates_and_obeys_twenty_file_sets(workspace):
    sources, store, library, manager = workspace
    (sources / "large.txt").write_text("Large distinctive record. " * 28_000, encoding="utf-8")
    (sources / "same-a.txt").write_text("同じ資料の本文", encoding="utf-8")
    (sources / "same-b.txt").write_text("同じ資料の本文", encoding="utf-8")
    (sources / "exclude.txt").write_text("対象から外す本文", encoding="utf-8")
    scan(manager, library["id"])
    excluded = document(store, library, "exclude.txt")
    store.edit_document(excluded["id"], {"excluded": True})
    target = collection(store, library, purpose="compare", instructions="今回と前回の違いを確認")
    result = build_export(store, target["id"])
    assert result["state"] == "published" and result["is_active"]
    assert result["document_count"] == 2
    root = Path(result["path"])
    manifest = json.loads(result["manifest"])
    assert manifest["duplicates"] == 1 and manifest["omitted"] == 1
    refs = [json.loads(line) for line in (root / "sources.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(refs) == 4
    assert next(r for r in refs if r["source"] == "same-b.txt")["duplicate_of"] == "same-a.txt"
    assert next(r for r in refs if r["source"] == "exclude.txt")["omitted_reason"] == "利用者が除外"
    sets = list((root / "M365").glob("set_*"))
    assert len(sets) >= 2
    assert all(len(list(folder.glob("*.txt"))) <= 20 for folder in sets)
    assert all((folder / "M365AgentContext_INDEX.txt").is_file() for folder in sets)
    for entry in manifest["assignments"]:
        body = root / "M365" / f"set_{entry['set']:03d}" / entry["file"]
        assert body.is_file() and entry["source"] in body.read_text(encoding="utf-8")
    blocks = [json.loads(line) for line in (root / "context.jsonl").read_text(encoding="utf-8").splitlines()]
    original = document(store, library, "large.txt")["effective_text"]
    assert "".join(b["text"] for b in blocks if b["source"] == "large.txt") == original
    prompt = (root / "prompt.txt").read_text(encoding="utf-8")
    assert "比較" in prompt and "今回と前回の違いを確認" in prompt


def test_warning_conflict_and_large_drop_hold_previous_generation(workspace):
    sources, store, library, manager = workspace
    for index in range(3):
        (sources / f"source-{index}.txt").write_text(f"資料 {index} の初版本文", encoding="utf-8")
    scan(manager, library["id"])
    target = collection(store, library)
    first = build_export(store, target["id"])
    assert first["is_active"]
    (sources / "source-1.txt").unlink()
    (sources / "source-2.txt").unlink()
    scan(manager, library["id"])
    drop = build_export(store, target["id"])
    assert drop["state"] == "held" and "50%未満" in drop["reason"]
    assert store.one("SELECT id FROM exports WHERE is_active=1")["id"] == first["id"]
    assert Path(first["path"]).is_dir()
    confirmed = activate_export(store, drop["id"])
    assert confirmed["is_active"]
    doc = document(store, library, "source-0.txt")
    store.edit_document(doc["id"], {"text": "修正本文", "expected_hash": doc["source_hash"]})
    (sources / "source-0.txt").write_text("更新した原本", encoding="utf-8")
    scan(manager, library["id"])
    conflict = build_export(store, target["id"])
    assert conflict["state"] == "held" and "競合" in conflict["reason"]
    assert store.one("SELECT id FROM exports WHERE is_active=1")["id"] == drop["id"]
    doc = document(store, library, "source-0.txt")
    store.edit_document(doc["id"], {"text": None})
    (sources / "protected.doc").write_bytes(b"old format")
    scan(manager, library["id"])
    warning = build_export(store, target["id"])
    assert warning["state"] == "held" and "読取警告" in warning["reason"]


def test_text_volume_drop_holds_even_when_file_and_chunk_counts_do_not_change(workspace):
    sources, store, library, manager = workspace
    path = sources / "source.txt"
    path.write_text("設備の保全点検記録。" * 100, encoding="utf-8")
    scan(manager, library["id"])
    target = collection(store, library)
    first = build_export(store, target["id"])
    path.write_text("短い抽出結果", encoding="utf-8")
    scan(manager, library["id"])
    second = build_export(store, target["id"])
    assert second["document_count"] == first["document_count"] == 1
    assert second["chunk_count"] == first["chunk_count"] == 1
    assert second["state"] == "held" and "50%未満" in second["reason"]
    assert store.one("SELECT id FROM exports WHERE is_active=1")["id"] == first["id"]


def test_corrupt_or_failed_new_export_never_replaces_previous(workspace, monkeypatch):
    from contextgen_kai import exporting
    sources, store, library, manager = workspace
    (sources / "source.txt").write_text("保持する本文", encoding="utf-8")
    scan(manager, library["id"])
    target = collection(store, library)
    first = build_export(store, target["id"])
    # 正常出力に警告資料を足して保留にし、改ざんを検証してから有効化する。
    (sources / "old.xls").write_bytes(b"legacy")
    scan(manager, library["id"])
    candidate = build_export(store, target["id"])
    (Path(candidate["path"]) / "prompt.txt").write_text("broken", encoding="utf-8")
    with pytest.raises(ValueError, match="変更されています"):
        activate_export(store, candidate["id"])
    assert store.one("SELECT id FROM exports WHERE is_active=1")["id"] == first["id"]
    actual_write = exporting._write

    def disk_full(path, text):
        if path.name == "prompt.txt":
            raise OSError("No space left on device")
        return actual_write(path, text)

    monkeypatch.setattr(exporting, "_write", disk_full)
    with pytest.raises(OSError, match="No space"):
        build_export(store, target["id"])
    assert store.one("SELECT id FROM exports WHERE is_active=1")["id"] == first["id"]
    assert not list((store.root / "exports").rglob(".staging-*"))
    assert (Path(first["path"]) / "manifest.json").is_file()


def test_backup_restores_reference_edit_and_exclusion_then_reextracts(tmp_path):
    sources = tmp_path / "原本フォルダ"
    sources.mkdir()
    original_path = sources / "原本.txt"
    original_path.write_text("原本の内容", encoding="utf-8")
    first_app = create_app(tmp_path / "first", use_process=False, enable_scheduler=False)
    with TestClient(first_app) as client:
        store = first_app.state.store
        library = store.add_library("資料", str(sources))
        scan(first_app.state.jobs, library["id"])
        doc = document(store, library, "原本.txt")
        store.edit_document(doc["id"], {"text": "校正した本文", "expected_hash": doc["source_hash"], "excluded": True})
        target = collection(store, library)
        backup = client.get("/api/backup").json()
        assert "原本資料・抽出キャッシュ" in backup["note"]
        assert "original_text" not in backup["documents"][0]
    restored_app = create_app(tmp_path / "restored", use_process=False, enable_scheduler=False)
    with TestClient(restored_app) as client:
        token = client.get("/api/status").json()["token"]
        response = client.post("/api/restore", files={"file": ("backup.json", json.dumps(backup).encode(), "application/json")}, headers={"X-Contextgen-Token": token})
        assert response.status_code == 200, response.text
        restored = restored_app.state.store.document(doc["id"])
        assert restored["source_path"] == str(original_path.resolve())
        assert restored["status"] == "pending" and restored["original_text"] == ""
        assert restored["edited_text"] == "校正した本文" and restored["excluded"]
        assert restored_app.state.store.collections()[0]["id"] == target["id"]
        scan(restored_app.state.jobs, library["id"])
        after = restored_app.state.store.document(doc["id"])
        assert after["effective_text"] == "校正した本文" and not after["conflict"]
        assert original_path.read_text(encoding="utf-8") == "原本の内容"


def test_restart_recovers_queued_and_active_jobs_for_manual_resume(workspace):
    from contextgen_kai.storage import identifier, now
    sources, store, library, manager = workspace
    (sources / "source.txt").write_text("再開する資料", encoding="utf-8")
    manager.close()
    identifiers = []
    for state in ("queued", "scanning", "extracting", "exporting"):
        job_id = identifier()
        identifiers.append(job_id)
        store.execute("INSERT INTO jobs(id,library_id,kind,state,created_at,updated_at,payload) VALUES(?,?,?,?,?,?,?)", (job_id, library["id"], "scan", state, now(), now(), "{}"))
    restarted = JobManager(store, use_process=False)
    try:
        for job_id in identifiers:
            assert store.one("SELECT state FROM jobs WHERE id=?", (job_id,))["state"] == "stopped"
        restarted.resume(identifiers[0])
        complete = restarted.wait(identifiers[0])
        assert complete["state"] == "completed" and complete["processed"] == 1
    finally:
        restarted.close()


def _nonresponding_extraction_worker(connection):
    """停止しない解析ライブラリを別プロセス内で再現する。"""
    import time
    try:
        connection.recv()
        time.sleep(30)
    finally:
        connection.close()


def test_extraction_process_timeout_and_stop_are_recoverable(tmp_path, monkeypatch):
    import threading
    from contextgen_kai import jobs
    path = tmp_path / "source.txt"
    path.write_text("解析プロセスを再起動して読み取る", encoding="utf-8")
    actual_loop = jobs._extract_loop
    monkeypatch.setattr(jobs, "_extract_loop", _nonresponding_extraction_worker)
    event = threading.Event()
    worker = jobs.ExtractionWorker(event)
    try:
        failed = worker.extract(path, timeout=0.2)
        assert failed["status"] == "error" and "制限時間" in failed["warnings"][0]
        assert worker.process is None
        timer = threading.Timer(0.05, event.set)
        timer.start()
        try:
            with pytest.raises(InterruptedError):
                worker.extract(path, timeout=5)
        finally:
            timer.cancel()
        assert worker.process is None
        event.clear()
        monkeypatch.setattr(jobs, "_extract_loop", actual_loop)
        recovered = worker.extract(path, timeout=15)
        assert recovered["status"] == "ok"
        assert "解析プロセスを再起動して読み取る" in recovered["text"]
    finally:
        worker.close()


def test_stopping_inside_cached_batch_persists_progress_for_resume(workspace, monkeypatch):
    sources, store, library, manager = workspace
    for number in range(60):
        (sources / f"source-{number:02d}.txt").write_text(f"cache {number}", encoding="utf-8")
    scan(manager, library["id"])
    actual_stat = Path.stat
    cached_paths = set()

    def interrupt_stat(path, *args, **kwargs):
        result = actual_stat(path, *args, **kwargs)
        if path.parent == sources and path.suffix == ".txt" and kwargs.get("follow_symlinks", True):
            running = store.one("SELECT id FROM jobs WHERE state='extracting'")
            if running and path not in cached_paths:
                cached_paths.add(path)
                if len(cached_paths) == 7:
                    manager.stop(running["id"])
        return result

    def no_extraction_expected(path, **kwargs):
        raise AssertionError("A completed unchanged file must use its extraction cache")

    monkeypatch.setattr(Path, "stat", interrupt_stat)
    monkeypatch.setattr(extractors, "extract_document", no_extraction_expected)
    job = manager.start(library["id"])
    stopped = manager.wait(job["id"])
    assert stopped["state"] == "stopped"
    assert stopped["processed"] == 7
    assert store.one("SELECT count(*) n FROM job_files WHERE job_id=? AND processed=1", (job["id"],))["n"] == 7
    manager.resume(job["id"])
    final = manager.wait(job["id"])
    assert final["state"] == "completed" and final["processed"] == 60 and final["errors"] == 0
