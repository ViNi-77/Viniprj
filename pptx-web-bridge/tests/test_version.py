"""版の表示: /api/version と、画面ファイルのキャッシュ無効化。"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app import version as version_mod
from app.main import app
from app.model import SCHEMA_VERSION


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_version_api_reports_build_and_features(client: TestClient):
    v = client.get("/api/version").json()
    assert v["version"] == version_mod.APP_VERSION
    assert v["schema_version"] == SCHEMA_VERSION
    assert v["commit"]
    ids = [f["id"] for f in v["features"]]
    assert {"diagrams", "merge_import", "copilot_agent_kit"} <= set(ids)
    for f in v["features"]:
        assert f["phase"] and f["name"] and f["hint"]


def test_config_also_carries_the_build(client: TestClient):
    build = client.get("/api/config").json()["build"]
    assert build["version"] == version_mod.APP_VERSION and build["commit"]


def test_page_marks_assets_with_the_build_tag(client: TestClient):
    r = client.get("/")
    assert r.headers["cache-control"] == "no-store, must-revalidate"
    refs = re.findall(r'(?:src|href)="(/(?:static|viewer)/[^"]+)"', r.text)
    assert refs, "画面ファイルの参照が見つからない"
    tag = version_mod.asset_tag()
    assert all(ref.endswith(f"?v={tag}") for ref in refs), refs[:3]


def test_asset_tag_changes_when_a_screen_file_changes(tmp_path, monkeypatch):
    version_mod.asset_tag.cache_clear()
    first = version_mod.asset_tag()
    target = version_mod.resource_path("frontend") / "app.js"
    original = target.stat().st_mtime
    try:
        import os

        os.utime(target, (original + 10, original + 10))
        version_mod.asset_tag.cache_clear()
        assert version_mod.asset_tag() != first
    finally:
        import os

        os.utime(target, (original, original))
        version_mod.asset_tag.cache_clear()


def test_label_is_readable():
    label = version_mod.label()
    assert label.startswith(f"v{version_mod.APP_VERSION}")


def _run_server_module():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    import run_server

    return run_server


def test_port_in_use_is_detected_and_a_free_one_is_picked():
    """前に起動したサーバーが残っていると、新しい方は別のポートへ逃げる（黙って古い画面を見せない）。"""
    import logging
    import socket

    run_server = _run_server_module()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        port = busy.getsockname()[1]
        assert run_server.port_in_use("127.0.0.1", port) is True
        picked = run_server.pick_port("127.0.0.1", port, logging.getLogger("test"))
        assert picked != port and not run_server.port_in_use("127.0.0.1", picked)


def test_a_free_port_is_used_as_is():
    import logging
    import socket

    run_server = _run_server_module()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert run_server.pick_port("127.0.0.1", port, logging.getLogger("test")) == port
