"""Copilot エージェント一式（Phase E、API 不使用）: 指示文・宣言型エージェント定義・ナレッジの書き出し。"""
from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import copilot_agent_kit as kit
from app.config import get_config
from app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def kit_zip() -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(kit.build_kit_zip()))


def test_zip_has_definition_instructions_knowledge_and_readme(kit_zip: zipfile.ZipFile):
    names = kit_zip.namelist()
    assert "declarativeAgent.json" in names
    assert "instructions.md" in names
    assert "kit.json" in names
    assert "READ_ME.txt" in names
    knowledge = [n for n in names if n.startswith("knowledge/")]
    assert f"knowledge/{kit.KNOWLEDGE_PREFIX}_INDEX.txt" in knowledge
    assert len(knowledge) >= 3


def test_index_lists_every_body_file_and_bodies_fit_the_limit(kit_zip: zipfile.ZipFile):
    index = kit_zip.read(f"knowledge/{kit.KNOWLEDGE_PREFIX}_INDEX.txt").decode("utf-8")
    bodies = [n for n in kit_zip.namelist() if n.startswith("knowledge/") and "INDEX" not in n]
    assert len(bodies) <= kit.MAX_FILES
    for name in bodies:
        text = kit_zip.read(name).decode("utf-8")
        assert 0 < len(text) <= kit.MAX_CHARS
        assert name.split("/")[-1] in index  # 目次に載っている
    assert f"本文ファイル: {len(bodies)} 件" in index


def test_manifest_is_json_and_points_at_instructions_file(kit_zip: zipfile.ZipFile):
    manifest = json.loads(kit_zip.read("declarativeAgent.json").decode("utf-8"))
    assert manifest["instructions"] == "$[file('instructions.md')]"
    assert manifest["$schema"] == kit.MANIFEST_SCHEMA
    assert manifest["name"] and manifest["description"]
    starters = manifest["conversation_starters"]
    assert 1 <= len(starters) <= int(get_config().copilot_prompts().get("agent", {}).get("starters_max", 6))
    for s in starters:
        assert s["title"] and s["text"]
        assert "{" not in s["text"]  # 差込語（{title} など）が残っていない


def test_instructions_and_knowledge_carry_the_format_contract():
    instructions = kit.build_instructions()
    assert "## 番号. 題名" in instructions and "ノート:" in instructions
    for p in get_config().copilot_prompts()["purposes"]:
        assert p["id"] in instructions
    texts = {r["file_name"]: r["text"] for r in kit.collect_sources()}
    assert "型: カード" in texts["markdown_contract.md"]
    assert "three_column" in texts["json_format.md"]
    assert all(p["id"] in texts["purposes.md"] for p in get_config().copilot_prompts()["purposes"])


def test_template_colours_reach_the_knowledge_and_instructions():
    template = get_config().template(None)
    primary = template["colors"]["primary"]
    texts = {r["file_name"]: r["text"] for r in kit.collect_sources(template["id"])}
    assert primary in texts["template.md"]
    assert primary in kit.build_instructions(template=template)


def test_long_records_are_split_into_several_files_within_the_cap():
    records = [{"file_name": "long.md", "summary": "長文", "text": ("段落です。\n\n" * 400)}]
    packed = kit.pack_knowledge(records, max_chars=1000, max_files=19)
    bodies = packed[1:]
    assert len(bodies) > 1
    assert all(len(text) <= 1000 for _name, text in bodies)
    assert "".join(text for _n, text in bodies).replace("\n", "") == records[0]["text"].replace("\n", "")


def test_pack_knowledge_reports_overflow_when_over_the_file_limit():
    records = [{"file_name": f"r{i}.md", "summary": f"記録 {i}", "text": "本文"} for i in range(5)]
    packed = kit.pack_knowledge(records, max_chars=1000, max_files=3)
    assert len(packed) == 4  # INDEX + 3
    assert "2 件を省きました" in packed[0][1]


def test_api_preview_and_zip(client: TestClient):
    r = client.get("/api/copilot/agent-kit/preview")
    assert r.status_code == 200
    data = r.json()
    assert data["agent"]["name"] and data["instructions"].startswith("# 役割")
    assert any(f["name"].endswith("_INDEX.txt") for f in data["files"])

    r2 = client.post("/api/copilot/agent-kit", json={"agent_name": "社内資料の相棒"})
    assert r2.status_code == 200 and r2.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r2.content))
    assert json.loads(z.read("declarativeAgent.json").decode("utf-8"))["name"] == "社内資料の相棒"
