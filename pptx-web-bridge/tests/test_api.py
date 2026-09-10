"""ローカル API の試験（TestClient、実サーバ不要）。"""
import io
import json
import zipfile

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_config_and_health():
    assert client.get("/api/health").json()["ok"] is True
    c = client.get("/api/config").json()
    assert c["templates"] and "editable" in c["pptx_modes"]


def test_import_pptx_and_exports(sample_pptx_bytes):
    r = client.post("/api/import/pptx", files={"file": ("sample_deck.pptx", sample_pptx_bytes)})
    assert r.status_code == 200, r.text
    body = r.json()
    pres = body["presentation"]
    assert len(pres["slides"]) == 6 and body["schema_errors"] == []

    r = client.post("/api/preview/html", json={"presentation": pres})
    assert r.status_code == 200 and "viewer-header" in r.text

    r = client.post("/api/export/html", json={"presentation": pres, "name": "日本語名"})
    assert r.status_code == 200
    assert "filename*=UTF-8''" in r.headers["content-disposition"]
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "web/index.html" in names

    r = client.post("/api/export/pptx", json={"presentation": pres, "mode": "editable"})
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert r.headers["x-warning-count"] == "0"

    r = client.post("/api/export/json", json={"presentation": pres})
    assert r.status_code == 200 and json.loads(r.content)["schema_version"] == "1.0"


def test_import_html_zip(sample_html_files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k in ("long.html", "style.css", "assets/chart_sample.png"):
            z.writestr(k, sample_html_files[k])
    r = client.post("/api/import/html", files={"file": ("bundle.zip", buf.getvalue())}, data={"template_id": "generic_corporate_blue"})
    assert r.status_code == 200, r.text
    pres = r.json()["presentation"]
    assert pres["theme"]["template_id"] == "generic_corporate_blue"
    assert all(el["bbox"] for s in pres["slides"] for el in s["elements"])


def test_import_html_with_extra_assets(sample_html_files):
    r = client.post(
        "/api/import/html",
        files=[("file", ("slides.html", sample_html_files["slides.html"])), ("assets", ("chart_sample.png", sample_html_files["assets/chart_sample.png"]))],
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["presentation"]["assets"]) == 1


def test_bad_inputs():
    assert client.post("/api/import/pptx", files={"file": ("x.pptx", b"not a pptx")}).status_code == 422
    assert client.post("/api/import/json", files={"file": ("x.json", b"{broken")}).status_code == 422
    assert client.post("/api/import/pptx", files={"file": ("x.pptx", b"")}).status_code == 400


def test_validate_repairs():
    r = client.post("/api/validate", json={"presentation": {"slides": [{"elements": [{"type": "text", "paragraphs": [{"runs": [{"text": "a"}]}]}]}]}})
    assert r.status_code == 200
    assert r.json()["valid"] is True and r.json()["repairs"]


def test_project_save_load_delete(sample_pptx_bytes):
    pres = client.post("/api/import/pptx", files={"file": ("d.pptx", sample_pptx_bytes)}).json()["presentation"]
    r = client.post("/api/projects", json={"name": "試験 プロジェクト", "presentation": pres})
    assert r.status_code == 200
    name = r.json()["name"]
    assert any(p["name"] == name for p in client.get("/api/projects").json()["projects"])
    loaded = client.get(f"/api/projects/{name}").json()["presentation"]
    assert [s["title"] for s in loaded["slides"]] == [s["title"] for s in pres["slides"]]
    assert client.delete(f"/api/projects/{name}").json()["deleted"] is True
    assert client.get(f"/api/projects/{name}").status_code == 404
