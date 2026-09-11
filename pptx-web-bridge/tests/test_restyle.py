"""テンプレートの適用＝資料全体の着せ替え（Phase J）: 背景の畳み込み・色とフォントの対応・題名の枠・冪等・元に戻す。"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import restyle, template_kit, template_store
from app.main import app
from app.model import bbox, new_presentation, new_slide, paragraph, run, shape_element, simple_text_element, text_element
from app.pptx_parser import parse_pptx
from app.template_from_pptx import analyze

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def template() -> dict:
    path = ROOT / "samples" / "brand_template_ext.pptx"
    if not path.exists():
        sys.path.insert(0, str(ROOT / "samples"))
        from make_brand_template_pptx import build_extended  # type: ignore

        build_extended(path)
    t = analyze(path.read_bytes(), "brand_template_ext.pptx", template_id="restyle_tpl")["proposal"]
    yield t
    template_store.delete_template("restyle_tpl")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def deck() -> dict:
    """取り込んだ資料に近い形: 全面の白い塗り、題名、赤系の見出し、灰色の注記、表。"""
    p = new_presentation("着せ替えの試験")
    cover = new_slide("s001", 0, "title", "表紙")
    cover["elements"] = [
        shape_element("bg1", "rect", bbox(0, 0, 960, 540), fill="#FFFFFF"),
        text_element("t1", [paragraph([run("表紙の題名", color="#C00000", size_pt=40, font="Arial")])], role="title", box=bbox(100, 200, 700, 60)),
        text_element("t2", [paragraph([run("副題です", color="#808080", size_pt=18, font="Arial")])], role="subtitle", box=bbox(100, 280, 700, 30)),
    ]
    body = new_slide("s002", 1, "title_body", "中身")
    body["elements"] = [
        text_element("t3", [paragraph([run("中身の題名", color="#C00000", size_pt=32, font="Arial")])], role="title", box=bbox(40, 30, 880, 50)),
        text_element("t4", [paragraph([run("本文の行", color="#333333", size_pt=16, font="Arial")]), paragraph([run("もう 1 行", color="#333333", size_pt=16, font="Arial")])], role="body", box=bbox(40, 100, 880, 380)),
        shape_element("sh1", "rect", bbox(600, 420, 300, 100), fill="#C00000", paragraphs=[paragraph([run("囲み", color="#FFFFFF")])]),
    ]
    p["slides"] = [cover, body]
    return p


def test_full_slide_fill_is_folded_into_the_background(template: dict):
    out, report = restyle.restyle(deck(), template)
    cover = out["slides"][0]
    assert report["folded_backgrounds"] == 1
    assert all(e["id"] != "bg1" for e in cover["elements"])
    assert cover["background"]["color"] == "#FFFFFF"


def test_colors_are_mapped_to_the_template(template: dict):
    out, report = restyle.restyle(deck(), template)
    cmap = report["color_map"]
    assert cmap.get("#C00000") == template["colors"]["primary"]  # 一番よく使われている鮮やかな色 → primary
    assert cmap.get("#333333") == template["colors"]["text"]
    colors = [r.get("color") for s in out["slides"] for e in s["elements"] for q in e.get("paragraphs", []) for r in q["runs"]]
    assert template["colors"]["primary"] in colors and "#C00000" not in colors
    box = next(e for e in out["slides"][1]["elements"] if e["id"] == "sh1")
    assert box["fill"] == template["colors"]["primary"]  # 図形の塗りも置き換わる
    assert report["colors"] >= 3  # 題名の色は move_titles が先に当てるので、ここで数えるのは本文・図形の分


def test_rare_colors_are_left_alone(template: dict):
    d = deck()
    d["slides"][1]["elements"].append(simple_text_element("rare", "写真の色", box=bbox(40, 480, 200, 20), color="#7B3F00"))
    out, report = restyle.restyle(d, template)
    assert "#7B3F00" not in report["color_map"]  # 1 回しか使われていない色は触らない
    rare = next(e for e in out["slides"][1]["elements"] if e["id"] == "rare")
    assert rare["paragraphs"][0]["runs"][0]["color"] == "#7B3F00"


def test_fonts_are_unified(template: dict):
    out, report = restyle.restyle(deck(), template)
    fonts = {r.get("font") for s in out["slides"] for e in s["elements"] for q in e.get("paragraphs", []) for r in q["runs"]}
    assert fonts <= {template["fonts"]["heading"], template["fonts"]["body"]}
    assert report["fonts"] > 0


def test_titles_move_to_the_template_boxes(template: dict):
    out, report = restyle.restyle(deck(), template)
    title = next(e for e in out["slides"][0]["elements"] if e["id"] == "t1")
    spec = template["cover"]["title"]
    assert abs(title["bbox"]["y"] - spec["y"]) < 1 and abs(title["bbox"]["x"] - spec["x"]) < 1
    assert title["paragraphs"][0]["runs"][0]["size_pt"] == spec["size_pt"]
    assert title["paragraphs"][0]["runs"][0]["color"] == spec["color"]
    assert report["titles_styled"] >= 2


def test_user_moved_boxes_are_kept(template: dict):
    d = deck()
    d["slides"][0]["elements"][1]["user_bbox"] = True
    d["slides"][0]["elements"][1]["bbox"] = bbox(11, 22, 333, 44)
    out, _r = restyle.restyle(d, template)
    title = next(e for e in out["slides"][0]["elements"] if e["id"] == "t1")
    assert title["bbox"]["x"] == 11 and title["bbox"]["y"] == 22  # 位置はそのまま
    assert title["paragraphs"][0]["runs"][0]["color"] == template["cover"]["title"]["color"]  # 色は合わせる


def test_elements_are_fitted_into_the_content_area(template: dict):
    d = deck()
    d["slides"][1]["elements"][2]["bbox"] = bbox(600, 500, 340, 120)  # 本文領域からはみ出す
    out, report = restyle.restyle(d, template)
    area = template_kit.content_area(template, out["canvas"])
    for el in out["slides"][1]["elements"]:
        if el.get("role") == "title" or not el.get("bbox"):
            continue
        b = el["bbox"]
        assert b["x"] >= area["x"] - 1 and b["y"] >= area["y"] - 1
        assert b["x"] + b["w"] <= area["x"] + area["w"] + 1 and b["y"] + b["h"] <= area["y"] + area["h"] + 1
    assert report["fitted"] > 0


def test_restyle_is_idempotent(template: dict):
    once, _r = restyle.restyle(deck(), template)
    twice, report = restyle.restyle(once, template)
    assert report.get("skipped")
    assert twice["slides"] == once["slides"]


def test_unstyle_restores_everything(template: dict):
    original = deck()
    styled, _r = restyle.restyle(copy.deepcopy(original), template)
    back, report = restyle.unstyle(styled)
    assert report["restored"] > 0
    assert "restyled_with" not in back["meta"] and "original_style" not in back["meta"]
    for a, b in zip(original["slides"], back["slides"]):
        assert [e["id"] for e in a["elements"]] == [e["id"] for e in b["elements"]]  # 畳み込んだ背景図形も戻る
        for ea, eb in zip(a["elements"], b["elements"]):
            assert ea.get("bbox") == eb.get("bbox") and ea.get("fill") == eb.get("fill")
            assert ea.get("paragraphs") == eb.get("paragraphs")


def test_switching_templates_restyles_from_the_original(template: dict):
    styled, _r = restyle.restyle(deck(), template)
    other = copy.deepcopy(template)
    other["id"] = "other_tpl"
    other["colors"] = {**template["colors"], "primary": "#123456", "text": "#222222"}
    again, report = restyle.restyle(styled, other)
    assert not report.get("skipped") and again["meta"]["restyled_with"] == "other_tpl"
    # 1 回目の着せ替えを元に戻してから当て直すので、対応表は元の資料の色から作られる
    assert report["color_map"].get("#C00000") == "#123456" and report["color_map"].get("#333333") == "#222222"
    box = next(e for e in again["slides"][1]["elements"] if e["id"] == "sh1")
    assert box["fill"] == "#123456"
    body = next(e for e in again["slides"][1]["elements"] if e["id"] == "t4")
    assert body["paragraphs"][0]["runs"][0]["color"] == "#222222"


def test_template_without_parts_is_a_no_op():
    out, report = restyle.restyle(deck(), {"id": "plain", "colors": {"primary": "#000000"}, "fonts": {}})
    assert report.get("skipped") and "restyled_with" not in out.get("meta", {})


def test_real_deck_keeps_its_text(template: dict):
    pres = parse_pptx((ROOT / "samples" / "sample_deck.pptx").read_bytes(), "sample_deck.pptx")
    before = [[r.get("text") for e in s["elements"] for q in e.get("paragraphs", []) for r in q["runs"]] for s in pres["slides"]]
    out, report = restyle.restyle(pres, template)
    after = [[r.get("text") for e in s["elements"] for q in e.get("paragraphs", []) for r in q["runs"]] for s in out["slides"]]
    assert before == after  # 文字は変えない（見た目だけ）
    assert report["slides"] == len(pres["slides"])


def test_api_apply_and_unapply(client: TestClient, template: dict, sample_pptx_bytes: bytes):
    template_store.save_template(dict(template))
    pres = client.post("/api/import/pptx", files={"file": ("sample_deck.pptx", sample_pptx_bytes)}).json()["presentation"]
    r = client.post("/api/template/apply", json={"presentation": pres, "template_id": template["id"]})
    assert r.status_code == 200
    d = r.json()
    assert d["presentation"]["meta"]["restyled_with"] == template["id"] and "色" in d["summary"]
    assert d["presentation"]["theme"]["template_id"] == template["id"]
    r2 = client.post("/api/template/unapply", json={"presentation": d["presentation"]})
    assert r2.status_code == 200
    back = r2.json()["presentation"]
    assert "restyled_with" not in back["meta"]
