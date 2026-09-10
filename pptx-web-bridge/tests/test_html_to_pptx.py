"""HTML → JSON → レイアウト → PPTX の試験。"""
import io

from pptx import Presentation

from app.html_parser import parse_html
from app.layout import layout_presentation
from app.pipeline import import_html
from app.pptx_generator import generate_pptx
from app.pptx_parser import parse_pptx
from app.quality_check import check_presentation
from app.validate import validate


def test_long_html_structure(sample_html_files):
    p = parse_html(sample_html_files["long.html"], "long.html", sample_html_files)
    assert validate(p) == []
    assert p["meta"]["title"] == "業務改善の進め方（長尺型サンプル）"
    assert p["slides"][0]["layout"] == "title"
    titles = [s["title"] for s in p["slides"]]
    assert "1. 現状の課題" in titles and "4. 次のステップ" in titles
    s2 = p["slides"][1]
    lists = [el for el in s2["elements"] if el["type"] == "text" and any(pp.get("bullet") for pp in el["paragraphs"])]
    assert lists and any(pp["level"] == 1 for pp in lists[0]["paragraphs"]), "入れ子リストの階層が保たれること"
    # 強調がランへ反映される
    body_runs = [r for el in s2["elements"] for pp in el.get("paragraphs", []) for r in pp["runs"]]
    assert any(r.get("bold") and r["text"].strip() == "PowerPoint" for r in body_runs)
    # 画像・表・引用
    s4 = [s for s in p["slides"] if s["title"] and s["title"].startswith("3.")][0]
    assert {el["type"] for el in s4["elements"]} >= {"image", "table"}
    assert len(p["assets"]) == 1
    # header/footer/nav は除外
    assert not any("ナビゲーション" in r["text"] for s in p["slides"] for el in s["elements"] for pp in el.get("paragraphs", []) for r in pp["runs"])


def test_cards_html_becomes_columns(sample_html_files):
    p = parse_html(sample_html_files["cards.html"], "cards.html", sample_html_files)
    s = p["slides"][1]
    assert s["layout"] == "three_column"
    cards = [el for el in s["elements"] if el.get("role") == "card"]
    assert len(cards) == 3
    lp = layout_presentation(p)
    laid = [el for el in lp["slides"][1]["elements"] if el.get("role") == "card"]
    xs = sorted(el["bbox"]["x"] for el in laid)
    assert xs[0] < xs[1] < xs[2]
    assert all(el["bbox"]["x"] + el["bbox"]["w"] <= lp["canvas"]["width_pt"] for el in laid)


def test_slides_html_sections(sample_html_files):
    p = parse_html(sample_html_files["slides.html"], "slides.html", sample_html_files)
    assert len(p["slides"]) == 5
    assert p["slides"][2]["layout"] == "two_column"


def test_layout_assigns_bbox_and_splits_overflow(sample_html_files):
    p = parse_html(sample_html_files["long.html"], "long.html", sample_html_files)
    lp = layout_presentation(p)
    assert validate(lp) == []
    assert all(el["bbox"] for s in lp["slides"] for el in s["elements"])
    assert [s["index"] for s in lp["slides"]] == list(range(len(lp["slides"])))
    # 画像はキャンバスに収まる
    for s in lp["slides"]:
        for el in s["elements"]:
            b = el["bbox"]
            assert b["y"] + b["h"] <= lp["canvas"]["height_pt"] + 0.5


def test_split_when_too_much_text():
    from app.model import new_presentation, new_slide, paragraph, run, text_element

    p = new_presentation("t")
    s = new_slide("s001", 0, title="長文")
    s["elements"].append(text_element("t", [paragraph([run("長文")], )], role="title"))
    s["elements"].append(text_element("b", [paragraph([run("あ" * 80)], bullet="bullet") for _ in range(30)], role="body"))
    p["slides"].append(s)
    lp = layout_presentation(p)
    assert len(lp["slides"]) >= 2
    assert lp["slides"][1]["title"].endswith("（続き）")
    assert any(w["code"] == "SLIDE_SPLIT" for w in lp["warnings"])


def test_html_to_pptx_editable(sample_html_files):
    res = import_html(sample_html_files["long.html"], "long.html", extra_files=sample_html_files)
    pres = res["presentation"]
    data, warns = generate_pptx(pres, "editable")
    assert not [w for w in warns if w["code"] in ("ELEMENT_WRITE_FAILED", "ELEMENT_NO_BBOX")]
    prs = Presentation(io.BytesIO(data))
    assert len(prs.slides) == len(pres["slides"])
    again = parse_pptx(data, "rt.pptx")
    # テキストが編集可能な図形として存在し、表・画像も残る
    assert again["slides"][0]["title"] == "業務改善の進め方（長尺型サンプル）"
    all_types = {el["type"] for s in again["slides"] for el in s["elements"]}
    assert {"text", "table", "image", "shape"} <= all_types
    # 箇条書きが PPTX 側でも箇条書きになっている
    s2 = again["slides"][1]
    assert any(pp.get("bullet") == "bullet" for el in s2["elements"] for pp in el.get("paragraphs", []))
    assert not [i for i in check_presentation(again) if i["severity"] == "error"]


def test_zip_import(sample_html_files):
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k in ("slides.html", "style.css", "assets/chart_sample.png"):
            z.writestr(k, sample_html_files[k])
    res = import_html(buf.getvalue(), "bundle.zip")
    assert len(res["presentation"]["slides"]) == 5
    assert len(res["presentation"]["assets"]) == 1


def test_remote_image_is_not_fetched():
    html = b"<html><body><section><h2>t</h2><img src='https://example.invalid/x.png' alt='ext'></section></body></html>"
    p = parse_html(html, "x.html", {})
    assert any(w["code"] == "REMOTE_IMAGE_SKIPPED" for w in p["warnings"])
    last = p["slides"][0]["elements"][-1]
    assert last["type"] == "image" and last.get("placeholder") is True and last.get("asset_id") is None  # 赤枠ではなく代替画像枠


def test_computed_style_from_css(sample_html_files):
    """Issue #6: 同梱 CSS の見出し色・カード背景が JSON に入る（Playwright が無い環境は警告付きで静的解析のみ）。"""
    from app import rasterize

    p = parse_html(sample_html_files["long.html"], "long.html", sample_html_files, computed_style=True)
    if not rasterize.is_available():
        assert any(w["code"] == "COMPUTED_STYLE_UNAVAILABLE" for w in p["warnings"])
        return
    title = next(el for el in p["slides"][1]["elements"] if el.get("role") == "title")
    r0 = title["paragraphs"][0]["runs"][0]
    assert r0["color"] == "#0B3D91" and "color" in r0["inherited"]  # style.css の h2 色
    cards = parse_html(sample_html_files["cards.html"], "cards.html", sample_html_files, computed_style=True)
    card = next(el for el in cards["slides"][1]["elements"] if el.get("role") == "card")
    assert card["fill"] == "#FFFFFF" and card["stroke"] == "#B9C7D8"
    assert card["paragraphs"][0]["runs"][0]["color"] == "#2A6EBB"


def test_computed_style_disabled_is_static_only(sample_html_files):
    p = parse_html(sample_html_files["long.html"], "long.html", sample_html_files, computed_style=False)
    title = next(el for el in p["slides"][1]["elements"] if el.get("role") == "title")
    assert "color" not in title["paragraphs"][0]["runs"][0]
    assert not any(w["code"] == "COMPUTED_STYLE_UNAVAILABLE" for w in p["warnings"])


def test_computed_style_via_api(sample_html_files):
    """レビュー指摘: API（async エンドポイント）経由でも Computed Style が動く。"""
    import io
    import zipfile

    from fastapi.testclient import TestClient

    from app import rasterize
    from app.main import app

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k in ("long.html", "style.css"):
            z.writestr(k, sample_html_files[k])
    r = TestClient(app).post("/api/import/html", files={"file": ("bundle.zip", buf.getvalue())}, data={"computed_style": "true"})
    assert r.status_code == 200, r.text
    res = r.json()
    if not rasterize.is_available():
        assert any(w["code"] == "COMPUTED_STYLE_UNAVAILABLE" for w in res["warnings"])
        return
    assert not any(w["code"] == "COMPUTED_STYLE_UNAVAILABLE" for w in res["warnings"]), [w["message"] for w in res["warnings"]]
    title = next(el for el in res["presentation"]["slides"][1]["elements"] if el.get("role") == "title")
    assert title["paragraphs"][0]["runs"][0]["color"] == "#0B3D91"


def test_computed_style_ignores_scripts_and_body_defaults(sample_html_files):
    """レビュー指摘: 取込 HTML のスクリプトは実行しない。body と同じ色・サイズは既定として書かない。"""
    from app import rasterize

    if not rasterize.is_available():
        return
    html = """<html><head><style>body{color:#333333;font-size:18px} h2{color:#0B3D91}</style></head><body>
    <section><h2 id="t">見出し</h2><p>本文</p><script>document.getElementById('t').style.color='#FF0000';</script></section></body></html>""".encode("utf-8")
    p = parse_html(html, "js.html", {}, computed_style=True)
    els = p["slides"][0]["elements"]
    title = next(el for el in els if el.get("role") == "title")
    body = next(el for el in els if el.get("role") == "body")
    assert title["paragraphs"][0]["runs"][0]["color"] == "#0B3D91"  # スクリプトによる赤化は起きない
    body_run = body["paragraphs"][0]["runs"][0]
    assert "color" not in body_run  # body と同じ色は既定として書かない
    assert body_run["size_pt"] == 13.5 and "size_pt" in body_run["inherited"]  # サイズは常に継承値として持ち、帯域で整える


def test_computed_style_no_network_requests(sample_html_files):
    """レビュー指摘: 外部 URL の CSS / 画像 / @import に対して実際の HTTP 要求が 1 件も出ない。"""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from app import rasterize

    if not rasterize.is_available():
        return
    hits: list[str] = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):  # noqa: D102
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        html = f"""<html><head><link rel="stylesheet" href="http://127.0.0.1:{port}/x.css"><style>@import url(http://127.0.0.1:{port}/i.css);</style></head>
        <body><section><h2>t</h2><img src="http://127.0.0.1:{port}/a.png"><p style="background:url(http://127.0.0.1:{port}/b.png)">p</p></section></body></html>"""
        from bs4 import BeautifulSoup

        from app.html_parser import tag_elements

        soup = BeautifulSoup(html, "lxml")
        tag_elements(soup)  # 収集は data-pwb-id 付きの HTML を前提とする
        styles, reason = rasterize.collect_computed_styles(str(soup), {}, "ext.html")
        assert styles and reason is None
    finally:
        srv.shutdown()
    assert hits == [], f"外部通信が発生しました: {hits}"


def test_computed_style_blocks_network(sample_html_files, monkeypatch):
    """外部 URL の CSS/画像は取りに行かない（通信遮断）。取得失敗でも変換は続く。"""
    html = b"<html><head><link rel='stylesheet' href='https://example.invalid/x.css'></head><body><section><h2 style='color:#123456'>t</h2><img src='https://example.invalid/a.png'></section></body></html>"
    p = parse_html(html, "ext.html", {}, computed_style=True)
    title = next(el for el in p["slides"][0]["elements"] if el.get("role") == "title")
    assert title["paragraphs"][0]["runs"][0]["color"] == "#123456"  # インライン style は静的解析で取れる
    assert any(w["code"] == "REMOTE_IMAGE_SKIPPED" for w in p["warnings"])
