"""Windows配布用検査自体を実APIで検証する。EXE実行の合格とは区別する。"""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import time
import urllib.error

from fastapi.testclient import TestClient
import pytest

from contextgen_kai.api import create_app

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("distribution_smoke", ROOT / "scripts/windows_smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def wait_job(client, identifier):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        job = next(item for item in client.get("/api/jobs").json() if item["id"] == identifier)
        if job["state"] in {"completed", "held", "failed", "stopped"}:
            assert job["state"] == "completed", job
            return job
        time.sleep(.02)
    raise AssertionError("Test job did not complete")


@pytest.mark.parametrize("target", ["builder", "studio"])
def test_packaged_smoke_contracts_against_real_api(tmp_path, target):
    source = tmp_path / "原本 資料"
    source.mkdir()
    (source / "点検手順.txt").write_text("設備点検は毎日実施します。点検手順の試験資料です。", encoding="utf-8")
    app = create_app(tmp_path / "state", use_process=False, enable_scheduler=False)
    with TestClient(app) as client:
        token = client.get("/api/status").json()["token"]
        headers = {"X-Contextgen-Token": token}

        def call(base, route, *, method="GET", data=None, token=None):
            response = client.request(method, route, json=data, headers=headers)
            if response.status_code >= 400:
                raise urllib.error.HTTPError(base + route, response.status_code, response.text, response.headers, io.BytesIO(response.content))
            return response.json() if "json" in response.headers.get("content-type", "") else response.content

        library = client.post("/api/libraries", json={"name": "配布契約試験", "path": str(source)}, headers=headers).json()
        job = client.post("/api/jobs", json={"library_id": library["id"]}, headers=headers).json()
        wait_job(client, job["id"])
        document = client.get("/api/documents").json()["items"][0]
        smoke.verify_edit_revision_api("http://testserver", token, document["id"], call=call)
        collection = client.post("/api/collections", json={"name": "検証セット", "library_ids": [library["id"]], "target": target,
            "evaluation_questions": [{"question": "点検頻度は？", "expected_response": "毎日", "source": "点検手順.txt"}]}, headers=headers).json()
        smoke.verify_collection_preview_api("http://testserver", token, collection, document, call=call)
        export = client.post("/api/exports", json={"collection_id": collection["id"]}, headers=headers).json()
        completed = wait_job(client, export["id"])
        generation = next(item for item in client.get("/api/exports").json() if item["id"] == completed["export_id"])
        archive = client.get(f"/api/exports/{generation['id']}/download").content
        smoke.verify_knowledge_archive(archive, generation, target)
