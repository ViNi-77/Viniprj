"""見た目の読み取り: HTML 図解テーマと PowerPoint のテーマ色。

ここで守りたいのは「当たること」より **嘘を書かないこと**。
読めなかったら読めなかったと言う（黙ってアプリ既定の色を渡さない）。
"""
from __future__ import annotations

from app import theme_from_html, theme_from_pptx


def _t(html_themes, name):
    return theme_from_html.extract_theme(html_themes[name], name)


def test_plain_css_gives_colours_fonts_and_decoration(html_themes):
    t = _t(html_themes, "theme_cards.html")
    assert t["colors"]["background"] == "#F7F9FC"
    assert t["colors"]["text"] == "#222222"
    assert t["colors"]["heading"] == "#0B3D91"
    assert t["colors"]["card"] == "#FFFFFF"
    assert t["fonts"] == {"body": "Noto Sans JP", "heading": "Meiryo"}
    assert t["decoration"]["radius_px"] == 12.0
    assert t["decoration"]["shadow"] is True
    assert t["name"] == "要点カード テーマ"


def test_css_variables_are_resolved(html_themes):
    """`:root { --brand: }` は AI が書く HTML で一番多い。ここを飛ばすと色が 1 つも取れない。"""
    t = _t(html_themes, "theme_vars.html")
    assert t["colors"]["heading"] == "#6C3CE0"
    assert t["colors"]["background"] == "#FBFAFF"
    assert t["colors"]["line"] == "#E2DCF5"
    assert t["fonts"]["heading"] == "Hiragino Kaku Gothic ProN"
    assert t["decoration"]["radius_px"] == 16.0


def test_inline_style_is_also_collected(html_themes):
    t = _t(html_themes, "theme_flow.html")
    assert "#00A05B" in t["palette"], "style 属性に書かれた色も拾う"


def test_a_dark_theme_keeps_its_own_light_text(html_themes):
    t = _t(html_themes, "theme_kpi.html")
    assert t["colors"]["background"] == "#101828"
    assert t["colors"]["text"] == "#F2F4F7"
    assert t["colors"]["accent"] == "#12B76A"


def test_external_css_is_reported_not_silently_ignored(html_themes):
    t = _t(html_themes, "theme_external.html")
    codes = {w["code"] for w in t["warnings"]}
    assert "THEME_EXTERNAL_CSS" in codes
    assert "THEME_NO_COLORS" in codes and "THEME_NO_FONTS" in codes
    assert t["colors"] == {} and t["fonts"] == {}


def test_where_each_colour_came_from_is_recorded(html_themes):
    t = _t(html_themes, "theme_cards.html")
    assert t["sources"]["background"].startswith("body")
    assert "color" in t["sources"]["text"]


def test_the_kinds_in_a_theme_are_listed(html_themes):
    assert _t(html_themes, "theme_cards.html")["kinds"] == ["cards"]
    assert _t(html_themes, "theme_compare.html")["kinds"] == ["compare"]
    assert _t(html_themes, "theme_flow.html")["kinds"] == ["flow"]


def test_prompt_lines_are_words_not_selectors(html_themes):
    lines = theme_from_html.to_prompt_lines(_t(html_themes, "theme_cards.html"))
    text = "\n".join(lines)
    assert "背景: #F7F9FC" in text and "見出しのフォント" not in text
    assert "角丸 12.0px" in text
    assert "{" not in text and "body" not in text, "CSS そのものは渡さない（言葉で伝える）"


def test_pptx_theme_comes_from_the_file_not_the_app_default(sample_pptx_bytes):
    t = theme_from_pptx.extract_theme(sample_pptx_bytes, "sample_deck.pptx")
    assert t["colors"], "スライドマスターのテーマ色が読めている"
    # アプリ既定テンプレートの色（#1F3A5F 等）がそのまま出てきたら、実ファイルを読めていない
    assert t["colors"]["heading"] != "#1F3A5F"
    assert t["fonts"].get("body")


def test_a_broken_pptx_reports_instead_of_raising():
    t = theme_from_pptx.extract_theme(b"not a pptx at all", "broken.pptx")
    assert t["colors"] == {}
    assert any(w["code"] == "THEME_PPTX_UNREADABLE" for w in t["warnings"])


def test_both_extractors_return_the_same_shape(html_themes, sample_pptx_bytes):
    """プロンプト側が入力の種類を気にしなくて済むこと。"""
    a = _t(html_themes, "theme_cards.html")
    b = theme_from_pptx.extract_theme(sample_pptx_bytes, "sample_deck.pptx")
    assert set(a) == set(b)
