"""差分マージ再取込（Phase G）: 編集を残したまま、取り込み側の変更だけを反映する。"""
from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

from app import merge as mg
from app.layout import layout_presentation
from app.main import app
from app.model import new_presentation, new_slide, simple_text_element
from app.pipeline import merge_import


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def deck(slides: list[tuple[str, str]], title: str = "資料") -> dict:
    pres = new_presentation(title)
    pres["slides"] = []
    for i, (head, body) in enumerate(slides):
        s = new_slide(f"s{i + 1:03d}", i, "title_body", head)
        s["elements"] = [simple_text_element(f"e{i}a", head, role="title"), simple_text_element(f"e{i}b", body)]
        pres["slides"].append(s)
    return layout_presentation(pres)


def imported(slides: list[tuple[str, str]]) -> dict:
    """取り込み直後の資料（記録付き）。"""
    return mg.attach_snapshot(deck(slides))


def text_of(slide: dict, index: int = 1) -> str:
    return mg.element_text(slide["elements"][index])


def test_untouched_elements_take_the_new_text():
    ours = imported([("背景", "課題は二重作業")])
    theirs = deck([("背景", "課題は二重作業と転記")])
    merged, report = mg.merge(ours, theirs)
    assert text_of(merged["slides"][0]) == "課題は二重作業と転記"
    assert report["updated"] == 1 and not report["conflicts"]


def test_moved_elements_keep_their_position_and_id():
    ours = imported([("背景", "課題は二重作業")])
    el = ours["slides"][0]["elements"][1]
    el["bbox"] = {"x": 50.0, "y": 300.0, "w": 200.0, "h": 60.0}
    el["user_bbox"] = True
    merged, _report = mg.merge(ours, deck([("背景", "課題は二重作業と転記")]))
    out = merged["slides"][0]["elements"][1]
    assert out["bbox"] == {"x": 50.0, "y": 300.0, "w": 200.0, "h": 60.0}
    assert out["id"] == el["id"] and out["user_bbox"] is True


def test_edits_survive_when_the_import_did_not_change():
    ours = imported([("背景", "課題は二重作業")])
    ours["slides"][0]["elements"][1]["paragraphs"][0]["runs"][0]["text"] = "課題は私が直した"
    merged, report = mg.merge(ours, deck([("背景", "課題は二重作業")]))
    assert text_of(merged["slides"][0]) == "課題は私が直した"
    assert report["kept_edits"] == 1 and not report["conflicts"]


@pytest.mark.parametrize("policy,expected", [({"conflict": "theirs"}, "課題は取込側が直した"), ({"conflict": "ours"}, "課題は私が直した")])
def test_both_changed_is_reported_as_a_conflict(policy: dict, expected: str):
    ours = imported([("背景", "課題は二重作業")])
    ours["slides"][0]["elements"][1]["paragraphs"][0]["runs"][0]["text"] = "課題は私が直した"
    ours["slides"][0]["elements"][1]["bbox"] = {"x": 10.0, "y": 20.0, "w": 100.0, "h": 40.0}
    ours["slides"][0]["elements"][1]["user_bbox"] = True
    merged, report = mg.merge(ours, deck([("背景", "課題は取込側が直した")]), policy=policy)
    assert text_of(merged["slides"][0]) == expected
    assert len(report["conflicts"]) == 1
    c = report["conflicts"][0]
    assert c["ours"] == "課題は私が直した" and c["theirs"] == "課題は取込側が直した"
    assert merged["slides"][0]["elements"][1]["bbox"]["x"] == 10.0  # 座標は常に自分のものを残す


def test_elements_deleted_upstream_go_away_unless_they_were_edited():
    ours = imported([("背景", "課題は二重作業")])
    ours["slides"][0]["elements"].append(simple_text_element("extra1", "取込側で消える段落"))
    ours["slides"][0]["elements"].append(simple_text_element("mine1", "自分で足した段落"))
    ours["meta"]["import_snapshot"]["slides"][0]["elements"].append({"key": mg.element_key(ours["slides"][0]["elements"][2]), "hash": mg.text_hash("取込側で消える段落")})
    merged, report = mg.merge(ours, deck([("背景", "課題は二重作業")]))
    texts = [mg.element_text(e) for e in merged["slides"][0]["elements"]]
    assert "取込側で消える段落" not in texts and report["removed"] == 1
    assert "自分で足した段落" in texts and report["kept_edits"] >= 1


def test_new_elements_are_added_and_laid_out():
    ours = imported([("背景", "課題は二重作業")])
    theirs = copy.deepcopy(deck([("背景", "課題は二重作業")]))
    theirs["slides"][0]["elements"].append(simple_text_element("new1", "取込側で増えた段落", box=None))
    result = merge_import(ours, theirs)
    added = [e for e in result["presentation"]["slides"][0]["elements"] if mg.element_text(e) == "取込側で増えた段落"]
    assert len(added) == 1 and added[0]["bbox"] and added[0]["bbox"]["w"] > 0
    assert result["report"]["added"] == 1


def test_slide_added_removed_and_order_follows_the_import():
    ours = imported([("背景", "A"), ("効果", "B")])
    ours["slides"].append(new_slide("mine", 2, "title_body", "自分のページ"))
    ours["slides"][2]["elements"] = [simple_text_element("m1", "自分のページ", role="title")]
    merged, report = mg.merge(ours, deck([("効果", "B"), ("背景", "A"), ("新規", "C")]))
    assert [s["title"] for s in merged["slides"]] == ["効果", "背景", "新規", "自分のページ"]
    assert report["slides_added"] == 1
    assert [s["index"] for s in merged["slides"]] == [0, 1, 2, 3]


def test_notes_and_theme_of_the_current_deck_are_kept():
    ours = imported([("背景", "課題は二重作業")])
    ours["slides"][0]["notes"] = "自分のノート"
    ours["theme"]["template_id"] = "corporate_standard"
    theirs = deck([("背景", "課題は二重作業と転記")])
    theirs["slides"][0]["notes"] = "取込側のノート"
    merged, _report = mg.merge(ours, theirs)
    assert merged["slides"][0]["notes"] == "自分のノート"
    assert merged["theme"]["template_id"] == "corporate_standard"


def test_same_title_slides_are_matched_in_order():
    ours = imported([("手順", "1 つ目"), ("手順", "2 つ目")])
    merged, report = mg.merge(ours, deck([("手順", "1 つ目（改）"), ("手順", "2 つ目")]))
    assert [text_of(s) for s in merged["slides"]] == ["1 つ目（改）", "2 つ目"]
    assert report["updated"] == 1 and not report["conflicts"]


def test_snapshot_is_small_and_refreshed_after_a_merge():
    ours = imported([("背景", "課題は二重作業")])
    snap = ours["meta"]["import_snapshot"]
    dumped = json.dumps(snap, ensure_ascii=False)
    assert "paragraphs" not in dumped and "data_base64" not in dumped  # 本文・画像は持たない（鍵は先頭 40 字まで）
    assert len(dumped) < len(json.dumps(ours, ensure_ascii=False)) / 4
    merged, _r = mg.merge(ours, deck([("背景", "課題は二重作業と転記")]))
    assert merged["meta"]["import_snapshot"]["slides"][0]["elements"][1]["hash"] == mg.text_hash("課題は二重作業と転記")


def test_api_merge_keeps_edits_and_reports(client: TestClient):
    html = "<html><body><section><h2>背景</h2><p>課題は二重作業</p></section></body></html>".encode()
    r = client.post("/api/import/html", files={"file": ("a.html", html, "text/html")})
    pres = r.json()["presentation"]
    assert pres["meta"].get("import_snapshot")
    body_el = pres["slides"][0]["elements"][-1]
    body_el["user_bbox"] = True
    body_el["bbox"] = {"x": 50.0, "y": 300.0, "w": 200.0, "h": 60.0}
    html2 = "<html><body><section><h2>背景</h2><p>課題は二重作業と転記</p></section></body></html>".encode()
    r2 = client.post("/api/import/merge", files={"file": ("a.html", html2, "text/html")}, data={"presentation": json.dumps(pres)})
    assert r2.status_code == 200
    out = r2.json()
    kept = [e for e in out["presentation"]["slides"][0]["elements"] if e.get("user_bbox")]
    assert kept and kept[0]["bbox"]["x"] == 50.0
    assert "課題は二重作業と転記" in json.dumps(out["presentation"], ensure_ascii=False)
    assert out["report"]["updated"] == 1 and "更新 1" in out["summary"]


def test_api_merge_requires_a_current_deck(client: TestClient):
    html = "<html><body><p>x</p></body></html>".encode()
    r = client.post("/api/import/merge", files={"file": ("a.html", html, "text/html")}, data={"presentation": json.dumps({"slides": []})})
    assert r.status_code == 400


def test_copilot_reply_can_be_applied_as_a_difference(client: TestClient):
    ours = imported([("背景", "課題は二重作業")])
    reply = "# 資料\n\n## 1. 背景\n- 課題は二重作業と転記\n"
    r = client.post("/api/copilot/import", json={"text": reply, "apply": "merge", "presentation": ours})
    assert r.status_code == 200
    out = r.json()
    assert out["mode"] == "merge"
    assert "課題は二重作業と転記" in json.dumps(out["presentation"], ensure_ascii=False)
