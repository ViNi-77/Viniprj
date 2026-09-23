"""API経由の実処理と非破壊性。テストは利用者資料・OS予約を変更しない。"""
import io
import json
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from contextgen_kai.api import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "state", use_process=False, enable_scheduler=False)
    with TestClient(app) as client:
        token = client.get("/api/status").json()["token"]
        client.headers["X-Contextgen-Token"] = token
        yield client


def seed(client, tmp_path):
    folder = tmp_path / "日本語 資料"
    folder.mkdir(exist_ok=True)
    (folder / "説明.txt").write_text("点検基準\n設備の確認手順\n数値は42です", encoding="utf-8")
    response = client.post("/api/libraries", json=dict(name="点検資料", path=str(folder)))
    assert response.status_code == 200, response.text
    library = response.json()
    job = client.post("/api/jobs", json=dict(library_id=library["id"])).json()
    done = client.app.state.jobs.wait(job["id"])
    assert done["state"] == "completed", done
    return library, folder


def test_scan_edit_export_api(client, tmp_path):
    library, folder = seed(client, tmp_path)
    docs = client.get("/api/documents", params={"q": "設備"}).json()
    assert docs["total"] == 1
    doc = client.get("/api/documents/" + docs["items"][0]["id"]).json()
    assert "42" in doc["original_text"]
    edited = client.put("/api/documents/" + doc["id"], json={"text": "数値を43に訂正", "expected_hash": doc["source_hash"]})
    assert edited.status_code == 200
    collection = client.post("/api/collections", json={"name": "点検用", "library_id": library["id"], "purpose": "questions"}).json()
    job = client.post("/api/exports", json={"collection_id": collection["id"]}).json()
    result = client.app.state.jobs.wait(job["id"])
    assert result["state"] == "completed", result
    response = client.get(f"/api/exports/{result['export_id']}/download")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "43" in archive.read("context.md").decode()
        assert "M365/set_001/M365AgentContext_INDEX.txt" in archive.namelist()
        assert "確認するときの質問" in archive.read("prompt.txt").decode()
    assert "42" in (folder / "説明.txt").read_text()


def test_rejects_cross_origin_and_missing_token(client):
    assert client.post("/api/libraries", json={"path": "/"}, headers={"X-Contextgen-Token": ""}).status_code == 403
    assert client.get("/api/status", headers={"Origin": "https://example.com"}).status_code == 403
    assert client.get("/api/status", headers={"Host": "example.com"}).status_code == 403
    assert client.get("/api/backup", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_upload_and_unregister_does_not_delete_original(client, tmp_path):
    response = client.post("/api/uploads", files=[("files", ("資料.txt", "取り込み内容".encode(), "text/plain"))])
    assert response.status_code == 200, response.text
    library = response.json()
    from pathlib import Path
    source = Path(library["path"]) / "資料.txt"
    assert source.exists()
    assert client.delete("/api/libraries/" + library["id"]).status_code == 200
    assert source.exists()


def test_backup_restore_edits_and_disabled_schedule(client, tmp_path):
    library, _ = seed(client, tmp_path)
    doc = client.get("/api/documents").json()["items"][0]
    detail = client.get("/api/documents/" + doc["id"]).json()
    client.put("/api/documents/" + doc["id"], json={"text": "訂正を保持", "expected_hash": detail["source_hash"]})
    schedule = client.post("/api/schedules", json={"name": "朝の更新", "library_id": library["id"], "mode": "app"})
    assert schedule.status_code == 200, schedule.text
    backup = client.get("/api/backup").content
    other = create_app(tmp_path / "restored", use_process=False, enable_scheduler=False)
    with TestClient(other) as restored:
        restored.headers["X-Contextgen-Token"] = restored.get("/api/status").json()["token"]
        response = restored.post("/api/restore", files={"file": ("backup.json", backup, "application/json")})
        assert response.status_code == 200, response.text
        assert restored.get("/api/schedules").json()[0]["enabled"] is False
        job = restored.post("/api/jobs", json={"library_id": library["id"]}).json()
        assert other.state.jobs.wait(job["id"])["state"] == "completed"
        detail = restored.get("/api/documents/" + doc["id"]).json()
        assert detail["effective_text"] == "訂正を保持"
        assert detail["conflict"] == 0
        assert restored.post("/api/restore", files={"file": ("backup.json", backup)}).status_code == 400


def test_edit_hash_conflict(client, tmp_path):
    seed(client, tmp_path)
    doc = client.get("/api/documents").json()["items"][0]
    assert client.put("/api/documents/" + doc["id"], json={"text": "stale", "expected_hash": "wrong"}).status_code == 409


def test_collection_cannot_select_other_library(client, tmp_path):
    library, _ = seed(client, tmp_path)
    response = client.post("/api/collections", json={"name": "不正", "library_id": library["id"], "document_ids": ["missing"]})
    assert response.status_code == 400


def test_unknown_preview_rejected(client, tmp_path):
    seed(client, tmp_path)
    doc = client.get("/api/documents").json()["items"][0]
    assert client.get("/api/documents/" + doc["id"] + "/preview").status_code == 400
    assert client.get("/api/documents/missing/preview").status_code == 404


def test_deleted_documents_filter(client, tmp_path):
    library, folder = seed(client, tmp_path)
    (folder / "説明.txt").unlink()
    job = client.post("/api/jobs", json={"library_id": library["id"]}).json()
    client.app.state.jobs.wait(job["id"])
    assert client.get("/api/documents").json()["total"] == 0
    assert client.get("/api/documents?status=deleted").json()["total"] == 1


def test_restore_invalid_path_rolls_back(client, tmp_path):
    backup = {"schema_version": 1, "application": "contextgen-kai", "libraries": [{"id": "a", "name": "a", "path": str(tmp_path)}], "documents": [{"id": "b", "library_id": "a", "relative_path": "../escape.txt", "source_hash": ""}]}
    response = client.post("/api/restore", files={"file": ("backup.json", json.dumps(backup).encode())})
    assert response.status_code == 400
    assert client.get("/api/libraries").json() == []


def test_real_process_extraction(tmp_path):
    from contextgen_kai.storage import Store
    from contextgen_kai.jobs import JobManager
    root = tmp_path / "inputs"
    root.mkdir()
    (root / "sample.txt").write_text("実プロセスで読み取り", encoding="utf-8")
    store = Store(tmp_path / "state")
    library = store.add_library("test", str(root))
    manager = JobManager(store)
    try:
        job = manager.start(library["id"])
        finished = manager.wait(job["id"], timeout=30)
        assert finished["state"] == "completed", finished
        assert store.list_documents()["total"] == 1
        assert store.one("SELECT original_text FROM documents")["original_text"].strip().endswith("実プロセスで読み取り")
    finally:
        manager.close()


def test_manual_serves_only_bundled_documents_and_images(client):
    """画面から開く手引きの相対画像が読め、同階層の実装・原本は公開されない。"""
    import re
    from urllib.parse import unquote
    response = client.get('/manual/')
    assert response.status_code == 200
    assert 'text/html' in response.headers['content-type']
    paths = re.findall(r'<img\b[^>]*\bsrc=["\']([^"\']+)', response.text)
    assert len(paths) >= 4
    for path in paths:
        assert path.startswith('images/')
        image = client.get('/manual/' + unquote(path))
        assert image.status_code == 200, path
        assert image.headers['content-type'].startswith('image/')
        assert len(image.content) > 1000
    for name in ['仕様書兼要件定義書.md', 'アプリ概要とバージョン履歴.md', 'アプリ基本設計基準書.md']:
        assert client.get('/manual/' + name).status_code == 200
    for path in ['/manual/pyproject.toml', '/manual/api.py', '/manual/images/%2e%2e/pyproject.toml']:
        assert client.get(path).status_code == 404
    # Windows配布試験と同じHTML解析・画像/JS/文書照合を実APIでも通す。
    import importlib.util
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('windows_smoke', root / 'scripts/windows_smoke.py')
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    assert smoke.verify_manual_assets(root, lambda route: client.get(route).content) == len(paths)


def test_packaged_manual_uses_executable_sibling_directory(tmp_path, monkeypatch):
    import sys
    bundle = tmp_path / '日本語 配布'
    bundle.mkdir()
    (bundle / 'contextgen改_操作マニュアル.html').write_text('<h1>bundled manual</h1>', encoding='utf-8')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(bundle / 'ContextgenKai.exe'))
    app = create_app(tmp_path / 'state', use_process=False, enable_scheduler=False)
    with TestClient(app) as client:
        assert client.get('/manual/').text == '<h1>bundled manual</h1>'
