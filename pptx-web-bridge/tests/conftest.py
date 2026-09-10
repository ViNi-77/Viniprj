"""pytest 共通フィクスチャ。試験用の一時ディレクトリを保存先にして、リポジトリの projects/output を汚さない。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import config as app_config  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def isolated_config(tmp_path_factory: pytest.TempPathFactory):
    """paths.* を一時ディレクトリへ向けた設定で全試験を実行する。"""
    tmp = tmp_path_factory.mktemp("cfg")
    base = json.loads((ROOT / "config" / "app_config.json").read_text(encoding="utf-8"))
    base["paths"]["projects_dir"] = str(tmp / "projects")
    base["paths"]["output_dir"] = str(tmp / "output")
    base["paths"]["logs_dir"] = str(tmp / "logs")
    base["paths"]["user_templates_file"] = str(tmp / "user_templates.json")
    base["paths"]["user_template_assets_dir"] = str(tmp / "template_assets_user")
    cfg_path = tmp / "app_config.json"
    cfg_path.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    app_config._config_singleton = app_config.AppConfig(cfg_path)
    yield app_config._config_singleton


@pytest.fixture(scope="session")
def sample_pptx_bytes() -> bytes:
    path = ROOT / "samples" / "sample_deck.pptx"
    if not path.exists():
        sys.path.insert(0, str(ROOT / "samples"))
        from make_sample_pptx import build  # type: ignore

        build(path)
    return path.read_bytes()


@pytest.fixture(scope="session")
def sample_html_files() -> dict[str, bytes]:
    base = ROOT / "samples" / "sample_html"
    return {str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*") if p.is_file()}
