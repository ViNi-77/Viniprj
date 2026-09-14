"""プロンプトと受け渡し一式。

このアプリの成果物はプロンプトそのものなので、ここが一番厚い試験になる。
見るのは 3 つ: **言葉が変わらないこと**、**型ごとの作り方が必ず入ること**、
**入り切らなかったら黙って落とさないこと**。
"""
from __future__ import annotations

import io
import zipfile

import pytest

from app import handoff_pack, prompt_builder, spec_builder, theme_from_html, theme_from_pptx
from app.html_parser import parse_html
from app.pptx_parser import parse_pptx

HTML = """<html lang="ja"><head><title>受注の流れ</title></head><body>
<section><h1>受注から出荷まで</h1><p class="lead">現行プロセス</p>
<div class="grid">
  <div class="card">① 受注</div><div class="card">② 引当</div><div class="card">③ 出荷</div>
</div></section>
<section><h2>効果</h2><ul><li>62 % 削減</li><li>月 200 件</li></ul></section>
</body></html>"""


@pytest.fixture(scope="module")
def html_spec():
    return spec_builder.build_spec(parse_html(HTML.encode("utf-8"), "flow.html"))


@pytest.fixture(scope="module")
def pptx_bits(sample_pptx_bytes):
    pres = parse_pptx(sample_pptx_bytes, "sample_deck.pptx")
    return pres, spec_builder.build_spec(pres), theme_from_pptx.extract_theme(sample_pptx_bytes, "sample_deck.pptx")


def test_to_pptx_prompt_targets_copilot_in_powerpoint(html_spec):
    b = prompt_builder.build(html_spec, None, "to_pptx")
    assert b["target"] == "Copilot in PowerPoint"
    assert "PowerPoint のスライドを作ってください" in b["prompt"]
    assert "全 2 枚。増やさない・減らさない" in b["prompt"]


def test_to_html_prompt_targets_a_normal_chat(pptx_bits):
    _pres, spec, theme = pptx_bits
    b = prompt_builder.build(spec, theme, "to_html")
    assert b["target"] == "ふつうの Copilot チャット"
    assert "HTML ファイル 1 つだけを出力する" in b["prompt"]
    assert "CDN" in b["prompt"], "外部読み込みを禁じておく（この環境では塞がれている）"


def test_the_recipe_for_every_kind_used_is_included(html_spec):
    b = prompt_builder.build(html_spec, None, "to_pptx")
    assert "フロー:" in b["prompt"] and "矢印" in b["prompt"]
    assert "数値:" in b["prompt"]
    assert "年表:" not in b["prompt"], "使っていない型の説明で薄めない"


def test_wording_is_carried_over_untouched(html_spec):
    b = prompt_builder.build(html_spec, None, "to_pptx")
    for word in ("受注から出荷まで", "① 受注", "62 % 削減", "現行プロセス"):
        assert word in b["prompt"]
    assert "文言は一字も変えない" in b["prompt"]


def test_theme_is_the_only_place_that_talks_about_looks(html_spec, html_themes):
    theme = theme_from_html.extract_theme(html_themes["theme_vars.html"], "theme_vars.html")
    b = prompt_builder.build(html_spec, theme, "to_pptx")
    assert "#6C3CE0" in b["instruction"]
    assert "#" not in b["spec_yaml"], "仕様側に色を書かない（2 か所に書くと食い違う）"


def test_without_a_theme_no_colour_is_invented(html_spec):
    b = prompt_builder.build(html_spec, None, "to_pptx")
    assert "見た目は次に合わせて" not in b["prompt"]
    assert "#" not in b["prompt"]


def test_a_theme_that_read_nothing_adds_no_instruction(html_spec, html_themes):
    empty = theme_from_html.extract_theme(html_themes["theme_external.html"], "theme_external.html")
    b = prompt_builder.build(html_spec, empty, "to_pptx")
    assert "配色（16 進数）" not in b["prompt"]
    assert any(w["code"] == "THEME_EXTERNAL_CSS" for w in b["warnings"]), "読めなかった理由は持ち回る"


def test_too_long_a_spec_is_cut_and_said_so(html_spec):
    b = prompt_builder.build(html_spec, None, "to_pptx", {"max_chars": 200})
    assert b["dropped_slides"] >= 1
    codes = {w["code"] for w in b["warnings"]}
    assert "PROMPT_TRUNCATED" in codes, "黙って落とさない"


def test_images_are_referenced_by_name_not_embedded(pptx_bits):
    _pres, spec, theme = pptx_bits
    b = prompt_builder.build(spec, theme, "to_html")
    assert b["has_images"] is True
    assert "img001.png" in b["prompt"]
    assert "base64" not in b["prompt"]


def test_an_unknown_direction_falls_back_rather_than_raising(html_spec):
    b = prompt_builder.build(html_spec, None, "そんな向きはない")
    assert b["direction"] == "to_pptx"


def test_both_directions_are_offered_with_an_outcome():
    ds = prompt_builder.directions()
    assert {d["id"] for d in ds} == {"to_pptx", "to_html"}
    assert all(d["outcome"] and d["how"] and d["target"] for d in ds)


# ---- 受け渡し一式 ----

def test_pack_contains_prompt_spec_word_and_images(pptx_bits):
    pres, spec, theme = pptx_bits
    b = prompt_builder.build(spec, theme, "to_html")
    z = zipfile.ZipFile(io.BytesIO(handoff_pack.build_zip(b, spec, pres)))
    names = z.namelist()
    assert "プロンプト.txt" in names and "図解仕様.yaml" in names and "構成.docx" in names
    assert "はじめにお読みください.txt" in names
    assert any(n.startswith("画像/") for n in names)
    assert z.read("プロンプト.txt").decode("utf-8") == b["prompt"]


def test_the_readme_tells_how_many_images_to_attach(pptx_bits):
    pres, spec, theme = pptx_bits
    b = prompt_builder.build(spec, theme, "to_html")
    z = zipfile.ZipFile(io.BytesIO(handoff_pack.build_zip(b, spec, pres)))
    readme = z.read("はじめにお読みください.txt").decode("utf-8")
    assert "1 個の画像" in readme
    assert "外部に送信しません" in readme


def test_the_word_file_opens_as_a_real_docx(pptx_bits):
    _pres, spec, _theme = pptx_bits
    blob = handoff_pack.to_docx(spec)
    z = zipfile.ZipFile(io.BytesIO(blob))
    assert "word/document.xml" in z.namelist()
    doc = z.read("word/document.xml").decode("utf-8")
    assert "業務改善提案" in doc and "背景と課題" in doc


def test_a_japanese_title_survives_in_the_zip_name(pptx_bits):
    _pres, spec, theme = pptx_bits
    b = prompt_builder.build(spec, theme, "to_html")
    name = handoff_pack.pack_name(spec, b)
    assert name.startswith("業務改善提案") and name.endswith("_to_html.zip")


def test_a_deck_without_images_still_packs(html_spec):
    b = prompt_builder.build(html_spec, None, "to_pptx")
    z = zipfile.ZipFile(io.BytesIO(handoff_pack.build_zip(b, html_spec, None)))
    assert not [n for n in z.namelist() if n.startswith("画像/")]
    assert "プロンプト.txt" in z.namelist()
