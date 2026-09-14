"""ローカル API。投入 → 型直し → 見た目 → プロンプト / 一式、の 1 本道。"""
from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import app

HTML = """<html lang="ja"><head><title>受注の流れ</title>
<style>body{background:#F7F9FC;color:#222} h1{color:#0B3D91} .card{background:#fff;border-radius:10px}</style>
</head><body>
<section><h1>受注から出荷まで</h1>
<div class="grid"><div class="card">① 受注</div><div class="card">② 引当</div><div class="card">③ 出荷</div></div>
</section></body></html>"""

THEME = """<html lang="ja"><head><title>紫のテーマ</title>
<style>:root{--brand:#6C3CE0;--bg:#FBFAFF}body{background:var(--bg);color:#241C3B}h1{color:var(--brand)}
.card{background:#FFF;border-radius:16px}</style></head><body>
<section><h1>見出し</h1><div class="card"><h3>A</h3><p>x</p></div><div class="card"><h3>B</h3><p>y</p></div></section>
</body></html>"""


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _analyze_html(client: TestClient) -> dict:
    r = client.post("/api/analyze", files={"file": ("flow.html", HTML.encode("utf-8"), "text/html")})
    assert r.status_code == 200, r.text
    return r.json()


def test_config_lists_directions_and_kinds(client: TestClient):
    cfg = client.get("/api/config").json()
    assert {d["id"] for d in cfg["directions"]} == {"to_pptx", "to_html"}
    assert any(k["id"] == "flow" for k in cfg["kinds"])


def test_analyze_html_returns_spec_theme_and_a_suggested_direction(client: TestClient):
    got = _analyze_html(client)
    assert got["kind"] == "html"
    assert got["spec"]["slide_count"] == 1
    assert got["spec"]["slides"][0]["kind"] == "flow"
    assert got["theme"]["colors"]["heading"] == "#0B3D91"
    assert got["suggested_direction"] == "to_pptx"
    assert got["session_id"]


def test_analyze_pptx_suggests_the_other_direction(client: TestClient, sample_pptx_bytes):
    r = client.post("/api/analyze", files={"file": ("d.pptx", sample_pptx_bytes, "application/vnd.openxmlformats-officedocument.presentationml.presentation")})
    got = r.json()
    assert got["kind"] == "pptx" and got["suggested_direction"] == "to_html"
    assert got["images"], "画像は添付できるように一覧で返す"


def test_changing_a_kind_rebuilds_the_spec(client: TestClient):
    got = _analyze_html(client)
    r = client.post("/api/spec", json={"session_id": got["session_id"], "kind_overrides": {"1": "timeline"}})
    assert r.status_code == 200
    s = r.json()["spec"]["slides"][0]
    assert s["kind"] == "timeline" and s["kind_reason"] == "画面で指定された"


def test_prompt_uses_the_source_theme_by_default(client: TestClient):
    got = _analyze_html(client)
    b = client.post("/api/prompt", json={"session_id": got["session_id"], "direction": "to_pptx"}).json()
    assert "#0B3D91" in b["prompt"]
    assert b["chars"] > 0


def test_an_uploaded_theme_replaces_the_source_one(client: TestClient):
    got = _analyze_html(client)
    t = client.post("/api/theme", files={"file": ("theme.html", THEME.encode("utf-8"), "text/html")}).json()
    assert t["theme"]["colors"]["heading"] == "#6C3CE0"
    b = client.post("/api/prompt", json={"session_id": got["session_id"], "direction": "to_pptx", "theme_id": t["theme_id"]}).json()
    assert "#6C3CE0" in b["prompt"] and "#0B3D91" not in b["prompt"]


def test_asking_for_no_theme_leaves_colours_out(client: TestClient):
    got = _analyze_html(client)
    b = client.post("/api/prompt", json={"session_id": got["session_id"], "direction": "to_pptx", "use_source_theme": False}).json()
    assert "#" not in b["prompt"]


def test_the_pack_downloads_as_a_zip_with_a_readable_name(client: TestClient, sample_pptx_bytes):
    got = client.post("/api/analyze", files={"file": ("d.pptx", sample_pptx_bytes, "application/octet-stream")}).json()
    r = client.post("/api/pack.zip", json={"session_id": got["session_id"], "direction": "to_html"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert "filename*=UTF-8''" in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert "プロンプト.txt" in z.namelist()


def test_an_unknown_session_says_so_instead_of_crashing(client: TestClient):
    r = client.post("/api/prompt", json={"session_id": "deadbeef", "direction": "to_pptx"})
    assert r.status_code == 404 and "もう一度" in r.json()["detail"]


def test_an_unknown_theme_id_is_refused(client: TestClient):
    got = _analyze_html(client)
    r = client.post("/api/prompt", json={"session_id": got["session_id"], "theme_id": "nope"})
    assert r.status_code == 404


def test_a_file_that_is_neither_is_rejected_with_a_readable_reason(client: TestClient):
    r = client.post("/api/analyze", files={"file": ("x.txt", b"just text", "text/plain")})
    assert r.status_code == 422
    assert "PowerPoint" in r.json()["detail"]


def test_an_empty_file_is_rejected(client: TestClient):
    r = client.post("/api/analyze", files={"file": ("x.pptx", b"", "application/octet-stream")})
    assert r.status_code == 400


def test_a_pptx_sent_as_html_is_told_apart_by_its_content(client: TestClient, sample_pptx_bytes):
    """拡張子は当てにならないので中身で判断する。"""
    got = client.post("/api/analyze", files={"file": ("mislabelled.html", sample_pptx_bytes, "text/html")}).json()
    assert got["kind"] == "pptx"


def test_warnings_reach_the_screen(client: TestClient):
    empty = b'<html lang="ja"><head><title>from</title></head><body><section><h1>only a title</h1></section></body></html>'
    got = client.post("/api/analyze", files={"file": ("e.html", empty, "text/html")}).json()
    assert any(w["code"] == "SLIDE_HAS_NO_CONTENT" for w in got["warnings"])


def test_health_and_loglevel(client: TestClient):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.post("/api/loglevel", json={"level": "DEBUG"}).json()["level"] == "DEBUG"
    assert client.post("/api/loglevel", json={"level": "うるさい"}).status_code == 400
    client.post("/api/loglevel", json={"level": "INFO"})
