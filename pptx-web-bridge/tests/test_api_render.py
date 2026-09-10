"""編集 UI 用 API（Phase B）: スライド断片の描画、1 枚だけの自動配置、内容に合わせる、利用者が動かした枠の尊重。"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.model import bbox, new_presentation, new_slide, paragraph, run, text_element
from app.pipeline import prepare
from app.web_renderer import build_bundle, viewer_css

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def imported(client: TestClient, sample_pptx_bytes: bytes) -> dict:
    r = client.post("/api/import/pptx", files={"file": ("sample_deck.pptx", sample_pptx_bytes)})
    assert r.status_code == 200
    return r.json()["presentation"]


def test_render_slides_returns_fragments_and_prepared_presentation(client: TestClient, imported: dict):
    r = client.post("/api/render/slides", json={"presentation": imported, "indices": [0, 2]})
    assert r.status_code == 200
    d = r.json()
    assert set(d["slides"].keys()) == {"0", "2"}
    frag = d["slides"]["0"]
    assert 'class="slide kind-' in frag and 'class="slide-wrap"' in frag
    for el in imported["slides"][0]["elements"]:
        assert f'id="{el["id"]}"' in frag
    assert "<aside" not in frag  # ノートは断片に含めない
    assert d["theme_css"].startswith(":root{")
    assert d["canvas"]["width_pt"] == imported["canvas"]["width_pt"]
    # prepare 後の資料: 文字サイズが確定している
    assert all(el.get("font_pt") for s in d["presentation"]["slides"] for el in s["elements"] if el["type"] in ("text", "shape"))


def test_render_slides_default_is_all(client: TestClient, imported: dict):
    r = client.post("/api/render/slides", json={"presentation": imported})
    assert r.status_code == 200
    assert len(r.json()["slides"]) == len(imported["slides"])


def test_layout_slide_only_touches_target(client: TestClient):
    p = new_presentation("t")
    s1 = new_slide("s001", 0)
    s1["elements"] = [text_element("a", [paragraph([run("固定")])], role="title", box=bbox(36, 36, 888, 64))]
    s2 = new_slide("s002", 1)
    s2["elements"] = [text_element("h", [paragraph([run("題名")])], role="title"), text_element("b", [paragraph([run("か" * 90)]) for _ in range(30)], role="body")]
    p["slides"] = [s1, s2]
    r = client.post("/api/layout/slide", json={"presentation": p, "index": 1, "scope": "unplaced"})
    assert r.status_code == 200
    d = r.json()
    assert d["count"] >= 2  # 分割される
    slides = d["presentation"]["slides"]
    assert slides[0]["id"] == "s001" and slides[0]["elements"][0]["bbox"]["x"] == 36  # 他スライドは不変
    assert [s["index"] for s in slides] == list(range(len(slides)))
    assert slides[2]["continuation_of"] == "s002"


def test_layout_slide_scope_all_resets_user_bbox(client: TestClient):
    p = new_presentation("t")
    s = new_slide("s001", 0)
    el = text_element("a", [paragraph([run("本文")])], role="body", box=bbox(500, 400, 100, 30))
    el["user_bbox"] = True
    el["font_scale"] = 0.9
    s["elements"] = [text_element("h", [paragraph([run("題名")])], role="title", box=bbox(36, 36, 888, 64)), el]
    p["slides"] = [s]
    r = client.post("/api/layout/slide", json={"presentation": p, "index": 0, "scope": "all"})
    out = r.json()["presentation"]["slides"][0]["elements"]
    body = next(e for e in out if e["id"] == "a")
    assert body["bbox"]["x"] == 36 and "user_bbox" not in body and "font_scale" not in body
    r2 = client.post("/api/layout/slide", json={"presentation": p, "index": 5, "scope": "all"})
    assert r2.status_code == 400


def test_layout_fit_returns_height(client: TestClient):
    p = new_presentation("t")
    s = new_slide("s001", 0)
    s["elements"] = [text_element("a", [paragraph([run("あ" * 200)])], role="body", box=bbox(36, 100, 400, 20))]
    p["slides"] = [s]
    r = client.post("/api/layout/fit", json={"presentation": p, "index": 0, "element_id": "a"})
    assert r.status_code == 200
    assert r.json()["h"] > 100  # 400pt 幅に 200 文字 → 複数行
    assert client.post("/api/layout/fit", json={"presentation": p, "index": 0, "element_id": "nope"}).status_code == 404


def test_template_keeps_user_moved_cover_title():
    p = new_presentation("t", template_id="corporate_standard")
    s = new_slide("s001", 0, layout="title")
    t = text_element("t", [paragraph([run("題名")])], role="title", box=bbox(300, 300, 300, 40))
    t["user_bbox"] = True
    u = text_element("u", [paragraph([run("副題")])], role="subtitle", box=bbox(10, 10, 300, 40))
    s["elements"] = [t, u]
    p["slides"] = [s]
    out, _e, _f = prepare(p)
    els = {e["id"]: e for e in out["slides"][0]["elements"]}
    assert els["t"]["bbox"]["x"] == 300 and els["t"]["bbox"]["y"] == 300  # 利用者の位置を保つ
    assert els["u"]["bbox"]["x"] != 10  # 触っていない副題はテンプレート位置へ


def test_bundle_and_static_css_include_slide_rules(client: TestClient, imported: dict):
    files = build_bundle(imported)
    css = files["viewer.css"].decode("utf-8")
    assert ".el-text" in css and ".viewer-header" in css
    assert viewer_css() == css
    assert client.get("/viewer/slide.css").status_code == 200
    assert client.get("/static/canvas.js").status_code == 200
    index = client.get("/").text
    assert "/viewer/slide.css" in index and "canvas-area" in index and "<iframe" not in index


def test_export_html_zip_still_has_viewer_css(client: TestClient, imported: dict):
    r = client.post("/api/export/html", json={"presentation": imported})
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        names = z.namelist()
        assert "web/index.html" in names and "web/viewer.css" in names and "web/viewer.js" in names
        assert b".el-text" in z.read("web/viewer.css")
