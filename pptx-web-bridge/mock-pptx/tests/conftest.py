"""模擬 PPTX 試験の共通設定。生成物が無ければ生成してから試験する。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUTPUT = ROOT / "output"


@pytest.fixture(scope="session")
def pptx_path() -> Path:
    p = OUTPUT / "mock_bidirectional_conversion_12slides.pptx"
    if not p.exists():
        from generate_mock_pptx import build

        build()
    return p


@pytest.fixture(scope="session")
def manifest(pptx_path) -> dict:
    import json

    return json.loads((OUTPUT / "mock_bidirectional_conversion_manifest.json").read_text(encoding="utf-8"))
