"""図解仕様: 文章と構造を分けて取り出せているか。

型の推定は必ず外れる（CLAUDE.md 9 章）。だからここで見るのは
「当たること」ではなく **「理由が必ず付くこと」「画面で直せること」「黙って中身を落とさないこと」**。
"""
from __future__ import annotations

from app import spec_builder
from app.html_parser import parse_html
from app.pptx_parser import parse_pptx


def _spec_from_html(html: str, name: str = "t.html", **kw):
    return spec_builder.build_spec(parse_html(html.encode("utf-8"), name), **kw)


CARDS = """<html lang="ja"><head><title>要点</title></head><body><section>
<h1>導入の効果</h1><p class="lead">3 つの観点</p>
<div class="grid">
  <div class="card"><h3>時間</h3><p>二重作成が消える</p></div>
  <div class="card"><h3>品質</h3><p>体裁がそろう</p></div>
  <div class="card"><h3>安心</h3><p>外に出さない</p></div>
</div></section></body></html>"""

FLOW = """<html lang="ja"><head><title>手順</title></head><body><section>
<h1>申請の進み方</h1>
<div class="grid">
  <div class="card">① 申請</div><div class="card">② 承認</div><div class="card">③ 振込</div>
</div></section></body></html>"""

COMPARE = """<html lang="ja"><head><title>対比</title></head><body><section>
<h1>入れ替えると何が変わるか</h1>
<div class="grid">
  <div class="card"><h3>Before</h3><p>手で二重管理</p></div>
  <div class="card"><h3>After</h3><p>一度で済む</p></div>
</div></section></body></html>"""

KPI = """<html lang="ja"><head><title>効果</title></head><body><section>
<h1>入れ替えた結果</h1>
<ul><li>62 % 削減</li><li>月 200 件</li><li>16 時間の短縮</li></ul>
</section></body></html>"""

TIMELINE = """<html lang="ja"><head><title>あゆみ</title></head><body><section>
<h1>これまでの経過</h1>
<ul><li>2023年: 試作</li><li>2024年: 試験導入</li><li>2025年: 全社展開</li></ul>
</section></body></html>"""

TABLE = """<html lang="ja"><head><title>一覧</title></head><body><section>
<h1>対応の範囲</h1>
<table><tr><th>区分</th><th>対応</th></tr><tr><td>文字</td><td>する</td></tr></table>
</section></body></html>"""

EMPTY = """<html lang="ja"><head><title>空</title></head><body><section><h1>題名だけ</h1></section></body></html>"""


def test_cards_are_read_as_items_with_a_reason():
    s = _spec_from_html(CARDS)["slides"][0]
    assert s["kind"] == "cards"
    assert s["kind_reason"], "なぜその型にしたかが必ず付く"
    assert [i["heading"] for i in s["items"]] == ["時間", "品質", "安心"]
    assert s["lead"] == "3 つの観点"


def test_numbered_boxes_become_a_flow():
    s = _spec_from_html(FLOW)["slides"][0]
    assert s["kind"] == "flow" and "番号" in s["kind_reason"]


def test_two_boxes_need_paired_words_to_be_a_comparison():
    assert _spec_from_html(COMPARE)["slides"][0]["kind"] == "compare"
    two_plain = COMPARE.replace("Before", "赤").replace("After", "青")
    assert _spec_from_html(two_plain)["slides"][0]["kind"] == "cards"


def test_numbers_and_years_are_told_apart():
    assert _spec_from_html(KPI)["slides"][0]["kind"] == "kpi"
    assert _spec_from_html(TIMELINE)["slides"][0]["kind"] == "timeline"


def test_table_rows_survive_with_their_header():
    s = _spec_from_html(TABLE)["slides"][0]
    assert s["kind"] == "table"
    assert s["table"]["header"] == ["区分", "対応"]
    assert s["table"]["rows"] == [["文字", "する"]]


def test_a_slide_with_no_content_is_reported_not_dropped():
    spec = _spec_from_html(EMPTY)
    assert spec["slides"][0]["kind"] == "title_only"
    assert any(w["code"] == "SLIDE_HAS_NO_CONTENT" for w in spec["warnings"]), "中身が無いことを黙って流さない"


def test_the_kind_can_be_overridden_from_the_screen():
    spec = _spec_from_html(CARDS, kind_overrides={"1": "timeline"})
    assert spec["slides"][0]["kind"] == "timeline"
    assert spec["slides"][0]["kind_reason"] == "画面で指定された"


def test_an_unknown_override_is_ignored_rather_than_crashing():
    spec = _spec_from_html(CARDS, kind_overrides={"1": "そんな型はない"})
    assert spec["slides"][0]["kind"] == "cards"


def test_wording_is_never_rewritten():
    """要約・言い換えはこのアプリの仕事ではない（Copilot の仕事）。"""
    s = _spec_from_html(CARDS)["slides"][0]
    assert s["items"][0]["body"] == "二重作成が消える"
    assert s["title"] == "導入の効果"


def test_yaml_is_readable_and_quotes_dangerous_values():
    spec = _spec_from_html(TABLE)
    y = spec_builder.to_yaml(spec)
    assert "ページ:" in y and "型: 表" in y and "区分" in y
    # コロンを含む値が素の YAML を壊さないこと
    tricky = _spec_from_html(TABLE.replace("対応の範囲", "対応: 範囲"))
    assert '"対応: 範囲"' in spec_builder.to_yaml(tricky)


def test_yaml_never_claims_a_colour_scheme():
    """`presentation["theme"]` はアプリ既定の色。実ファイルの色ではないので仕様に書かない。"""
    y = spec_builder.to_yaml(_spec_from_html(CARDS))
    assert "見た目" not in y and "#" not in y


def test_pptx_images_are_listed_with_their_filenames(sample_pptx_bytes):
    spec = spec_builder.build_spec(parse_pptx(sample_pptx_bytes, "sample_deck.pptx"))
    images = [im for s in spec["slides"] for im in s.get("images", [])]
    assert images and all(im["filename"] for im in images)
    assert all(im["available"] for im in images), "実体が取れている画像だけ available=True"


def test_every_kind_has_a_label_for_the_screen():
    opts = spec_builder.kind_options()
    assert {o["id"] for o in opts} == set(spec_builder.KINDS)
    assert all(o["label"] for o in opts)
