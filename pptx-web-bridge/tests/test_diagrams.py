"""図解部品（Phase F）: 5 型の展開・レイアウト・Markdown 往復・PPTX 往復・品質検査。"""
from __future__ import annotations

import pytest

from app import copilot_handoff as ch
from app import diagrams as dg
from app.layout import layout_presentation
from app.model import new_presentation, new_slide, simple_text_element
from app.pptx_parser import parse_pptx
from app.pipeline import export_pptx
from app.quality_check import check_presentation
from app.validate import validate_and_repair
from app.web_renderer import element_html

BOX = {"x": 36.0, "y": 120.0, "w": 648.0, "h": 200.0}
SAMPLES = {
    "flow": [{"title": "受付", "text": "窓口で受け取る"}, {"title": "審査", "text": "担当が確認"}, {"title": "完了", "text": "通知する"}],
    "cards": [{"title": "課題", "text": "二重作業"}, {"title": "原因", "text": "形式が違う"}, {"title": "対策", "text": "共通形式"}],
    "compare": [{"title": "Before", "text": "二重作業"}, {"title": "After", "text": "一度で済む"}],
    "kpi": [{"title": "作業時間の削減", "value": "40%"}, {"title": "月に浮く時間", "value": "12h"}],
    "timeline": [{"title": "2024", "text": "試験導入"}, {"title": "2025", "text": "全社展開"}],
}


def _deck(dtype: str, items: list[dict] | None = None) -> dict:
    pres = new_presentation("図解の資料")
    slide = new_slide("s001", 0, "title_body", "図解")
    slide["elements"] = [simple_text_element("e1", "図解", role="title"), dg.diagram_element("e2", dtype, items or SAMPLES[dtype])]
    pres["slides"] = [slide]
    return pres


@pytest.mark.parametrize("dtype", sorted(SAMPLES))
def test_children_stay_inside_the_parent_box(dtype: str):
    el = dg.diagram_element("d1", dtype, SAMPLES[dtype], BOX)
    children = dg.expand_diagram(el, None)
    assert children, "子要素が作られていない"
    for c in children:
        b = c["bbox"]
        assert b["x"] >= BOX["x"] - 0.5 and b["y"] >= BOX["y"] - 0.5
        assert b["x"] + b["w"] <= BOX["x"] + BOX["w"] + 0.5
        assert b["y"] + b["h"] <= BOX["y"] + BOX["h"] + 0.5
        assert c["type"] in ("shape", "text", "line")


def test_template_colours_are_used_for_children():
    el = dg.diagram_element("d1", "flow", SAMPLES["flow"], BOX)
    children = dg.expand_diagram(el, {"colors": {"primary": "#123456", "accent": "#ABCDEF"}})
    fills = {c.get("fill") for c in children}
    assert "#123456" in fills and "#ABCDEF" in fills


@pytest.mark.parametrize("dtype", sorted(SAMPLES))
def test_markdown_roundtrip_keeps_type_and_items(dtype: str):
    pres = layout_presentation(_deck(dtype))
    md = ch.to_markdown(pres)
    assert f"型: {dg.word_of(dtype)}" in md
    back = layout_presentation(ch.import_markdown(md))
    diagrams_back = [e for s in back["slides"] for e in s["elements"] if e["type"] == "diagram"]
    assert len(diagrams_back) == 1
    assert diagrams_back[0]["diagram"]["type"] == dtype
    assert [i["title"] for i in diagrams_back[0]["diagram"]["items"]] == [i["title"] for i in SAMPLES[dtype]]


@pytest.mark.parametrize("dtype", sorted(SAMPLES))
def test_pptx_roundtrip_restores_the_diagram(dtype: str):
    data, _pres, warnings = export_pptx(_deck(dtype))
    assert not [w for w in warnings if w["code"] == "ELEMENT_NO_BBOX"]
    back = parse_pptx(data, "diagram.pptx")
    restored = [e for e in back["slides"][0]["elements"] if e["type"] == "diagram"]
    assert len(restored) == 1
    assert restored[0]["diagram"]["type"] == dtype
    assert [i["title"] for i in restored[0]["diagram"]["items"]] == [i["title"] for i in SAMPLES[dtype]]


def test_layout_places_the_diagram_without_splitting_the_slide():
    pres = layout_presentation(_deck("cards"))
    assert len(pres["slides"]) == 1
    el = [e for e in pres["slides"][0]["elements"] if e["type"] == "diagram"][0]
    assert el["bbox"]["w"] > 400 and el["bbox"]["h"] >= 100
    assert not [w for w in pres.get("warnings", []) if w["code"] == "SLIDE_SPLIT"]


def test_too_many_items_are_trimmed_and_reported():
    pres = _deck("compare", [{"title": f"項目 {i}"} for i in range(5)])
    fixed, _errors, fixes = validate_and_repair(pres)
    assert "DIAGRAM_ITEMS_TRIMMED" in [f["code"] for f in fixes]
    assert len(fixed["slides"][0]["elements"][1]["diagram"]["items"]) == 2


def test_quality_check_reports_a_squashed_diagram():
    pres = layout_presentation(_deck("flow"))
    el = [e for e in pres["slides"][0]["elements"] if e["type"] == "diagram"][0]
    el["bbox"]["h"] = 40.0
    codes = [i["code"] for i in check_presentation(pres)]
    assert "DIAGRAM_TOO_SMALL" in codes


def test_web_render_nests_children_and_marks_the_type():
    pres = layout_presentation(_deck("timeline"))
    el = [e for e in pres["slides"][0]["elements"] if e["type"] == "diagram"][0]
    html = element_html(el, pres, True)
    assert 'class="el el-diagram"' in html and 'data-diagram="timeline"' in html
    assert html.count('class="el ') >= 4  # 親 + 子
    assert "2024" in html and "試験導入" in html


def test_kpi_markdown_uses_the_value_separator():
    el = dg.from_bullets("d1", "数値", ["40%｜作業時間の削減", "12h|月に浮く時間"])
    assert el["diagram"]["type"] == "kpi"
    assert el["diagram"]["items"][0] == {"title": "作業時間の削減", "value": "40%", "text": ""} or el["diagram"]["items"][0]["value"] == "40%"
    assert dg.to_bullets(el)[0] == "40%｜作業時間の削減"


def test_unknown_words_do_not_become_diagrams():
    assert dg.type_from_word("表紙") is None
    assert dg.type_from_word("") is None
    assert dg.type_from_word("フロー") == "flow"
