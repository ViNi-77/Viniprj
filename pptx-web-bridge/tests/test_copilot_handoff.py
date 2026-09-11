"""Copilot 連携（Phase D、API 不使用）: Markdown / JSON / Word への変換、プロンプト、回答（Markdown / JSON）の取込、ノート反映。"""
from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from lxml import etree

from app import copilot_handoff as ch
from app.main import app
from app.pptx_parser import parse_pptx


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def deck(sample_pptx_bytes: bytes) -> dict:
    return parse_pptx(sample_pptx_bytes, "sample_deck.pptx")


def test_markdown_has_headings_bullets_table_image_and_notes(deck: dict):
    md = ch.to_markdown(deck)
    assert md.startswith("# 業務改善提案（サンプル）")
    assert "## 2. 背景と課題" in md and "\n- 資料作成が PowerPoint と Web の二重作業になっている\n  - 同じ内容を2回作り直している" in md
    assert "| 区分 | MVP で対応 | 初期対象外 |\n| --- | --- | --- |" in md
    assert "画像: img001.png" in md and "ノート: 発表者ノート: 背景説明は2分で終える。" in md
    assert "型: 表紙" in md


def test_outline_json_and_docx(deck: dict):
    o = ch.to_outline_json(deck)
    assert o["title"] and len(o["slides"]) == 6 and o["slides"][1]["bullets"][0]["level"] == 0 and o["slides"][1]["bullets"][1]["level"] == 1
    assert o["slides"][3]["tables"][0][0] == ["区分", "MVP で対応", "初期対象外"] and o["slides"][4]["images"][0]["file"] == "img001.png"
    docx = ch.to_docx(deck)
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        names = z.namelist()
        assert {"[Content_Types].xml", "word/document.xml", "word/styles.xml", "word/numbering.xml"} <= set(names)
        root = etree.fromstring(z.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        styles = [p.get("{%s}val" % ns["w"]) for p in root.findall(".//w:pStyle", ns)]
        assert styles.count("Heading1") == 6 and "ListBullet" in styles and "Title" in styles
        assert len(root.findall(".//w:tbl", ns)) == 1
        text = "".join(root.itertext())
        assert "背景と課題" in text and "ノート: 発表者ノート" in text


def test_build_prompt_fills_placeholders_and_brand(deck: dict):
    r = ch.build_prompt(deck, "summarize", {"count": 5})
    assert "5 枚のスライド構成" in r["instruction"] and "{count}" not in r["instruction"] and "{brand}" not in r["instruction"]
    assert r["prompt"].startswith(r["instruction"].rstrip("\n")) and r["content"].startswith("# ")
    assert r["chars"] == len(r["instruction"]) + len(r["content"]) and r["truncated"] is False and r["chat_url"]
    j = ch.build_prompt(deck, "json")
    assert j["content_format"] == "json" and j["content"].startswith("```json") and '"slides"' in j["content"]
    assert ch.build_prompt(deck, "nope")["purpose"] == ch.purposes()[0]["id"]


def test_markdown_reply_becomes_slides_with_kinds_and_notes():
    reply = "```markdown\n# 提案\n\n## 1. 提案\n型: 表紙\n*副題です*\n\n## 2. 背景\n型: カード\n- 課題: 二重作業\n  - 詳細 A\n- 原因: 形式が違う\n- 対策: 共通形式\nノート: 背景は 2 分で\n\n## 3. 効果\n| 項目 | 前 | 後 |\n| --- | --- | --- |\n| 時間 | 10h | 5h |\nノート: 数字は試算\n\n## 4. 手順\n型: フロー\n1. 読む\n2. 直す\n3. 出す\n![図](chart.png)\n```"
    p = ch.import_markdown(reply)
    layouts = [(s["layout"], s["title"]) for s in p["slides"]]
    assert layouts[0] == ("title", "提案") and any(e.get("role") == "subtitle" for e in p["slides"][0]["elements"])
    assert p["slides"][1]["notes"] == "背景は 2 分で"
    cards = [e for e in p["slides"][1]["elements"] if e["type"] == "diagram"]  # 「型: カード」は図解要素になる（Phase F）
    assert len(cards) == 1 and cards[0]["diagram"]["type"] == "cards"
    items = cards[0]["diagram"]["items"]
    assert [i["title"] for i in items] == ["課題", "原因", "対策"]
    assert items[0]["text"].startswith("二重作業") and "詳細 A" in items[0]["text"]  # 下位項目は説明に足す
    assert layouts[2][0] == "table" and p["slides"][2]["notes"] == "数字は試算"
    tbl = next(e for e in p["slides"][2]["elements"] if e["type"] == "table")
    assert tbl["rows"][0][0]["text"] == "項目" and tbl["rows"][1][2]["text"] == "5h"
    s4 = p["slides"][3]
    assert any(e["type"] == "image" and e.get("placeholder") for e in s4["elements"])  # 画像は取れないので代替枠
    flow = [e for e in s4["elements"] if e["type"] == "diagram"]  # 「型: フロー」も図解要素
    assert len(flow) == 1 and flow[0]["diagram"]["type"] == "flow"
    assert [i["title"] for i in flow[0]["diagram"]["items"]] == ["読む", "直す", "出す"]


def test_roundtrip_markdown_keeps_slide_count(deck: dict):
    p = ch.import_markdown(ch.to_markdown(deck))
    assert len(p["slides"]) == len(deck["slides"])
    assert p["slides"][0]["layout"] == "title" and [s["title"] for s in p["slides"]][1:] == [s["title"] for s in deck["slides"]][1:]


def test_json_reply_and_notes_apply(deck: dict):
    kind, data = ch.parse_copilot_reply('```json\n{"title": "T", "slides": [{"n": 1, "title": "A", "layout": "カード", "bullets": ["x", {"text": "y", "level": 1}], "notes": "n1"}, {"n": 2, "title": "B", "tables": [[["a", "b"], ["1", "2"]]]}]}\n```')
    assert kind == "json"
    p = ch.import_outline_json(data)
    assert len(p["slides"]) == 2 and p["slides"][0]["layout"] == "three_column" and p["slides"][0]["notes"] == "n1"
    assert p["slides"][1]["elements"][1]["type"] == "table" and p["slides"][1]["elements"][1]["rows"][1][1]["text"] == "2"
    assert ch.parse_copilot_reply("## 1. a\n- b")[0] == "markdown"
    d2, n = ch.apply_notes(dict(deck), "## 2. 背景と課題\nノート: 二番目\n## 1. 表紙\nノート: 一番目\n")
    assert n == 2 and d2["slides"][0]["notes"] == "一番目" and d2["slides"][1]["notes"] == "二番目"
    d3, n3 = ch.apply_notes(dict(deck), '{"slides": [{"n": 3, "notes": "三番目"}]}')
    assert n3 == 1 and d3["slides"][2]["notes"] == "三番目"


def test_api_prompts_handoff_zip_docx_import(client: TestClient, deck: dict):
    r = client.get("/api/copilot/prompts")
    assert r.status_code == 200 and r.json()["chat_url"].startswith("https://") and all("prompt" not in p for p in r.json()["purposes"])
    h = client.post("/api/copilot/handoff", json={"presentation": deck, "purpose": "brand_deck"})
    assert h.status_code == 200 and "ブランドキット" in h.json()["instruction"] and h.json()["attach_hint"]
    z = client.post("/api/copilot/handoff.zip", json={"presentation": deck, "purpose": "brand_deck", "name": "テスト"})
    assert z.status_code == 200 and "copilot.zip" in z.headers["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
        assert {"prompt.txt", "outline.md", "outline.json", "outline.docx", "images/img001.png", "READ_ME.txt"} <= set(zf.namelist())
    d = client.post("/api/copilot/docx", json={"presentation": deck})
    assert d.status_code == 200 and d.content[:2] == b"PK" and d.headers["Content-Type"].endswith("wordprocessingml.document")
    imp = client.post("/api/copilot/import", json={"text": "# 新資料\n\n## 1. 一枚目\n- a\n- b\nノート: n\n\n## 2. 二枚目\n- c\n", "apply": "new"})
    assert imp.status_code == 200
    pres = imp.json()["presentation"]
    assert len(pres["slides"]) == 3 and pres["slides"][1]["notes"] == "n" and all(el.get("bbox") for s in pres["slides"] for el in s["elements"])
    assert pres["meta"]["source"]["via"] == "copilot"
    notes = client.post("/api/copilot/import", json={"text": "## 1. x\nノート: 一\n## 2. y\nノート: 二", "apply": "notes", "presentation": deck})
    assert notes.status_code == 200 and notes.json()["applied"] == 2 and notes.json()["presentation"]["slides"][1]["notes"] == "二"
    assert client.post("/api/copilot/import", json={"text": "ノートだけ", "apply": "notes"}).status_code == 400
    assert client.post("/api/copilot/import", json={"text": "   \n", "apply": "new"}).status_code in (422, 400)
