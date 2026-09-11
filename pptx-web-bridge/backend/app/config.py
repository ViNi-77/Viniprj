"""設定読込モジュール。

設計方針（基本設計基準書の継承）:
- 値をコードへ固定しない。すべて config/*.json から読み込む。
- 設定ファイルが欠けても既定値で起動できる（フォールバック）。
- リポジトリ直下を基準ディレクトリとし、相対パスはそこから解決する。
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import sys


def _is_frozen() -> bool:
    """PyInstaller で exe 化されているか。"""
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")


# 書き込み用の基準ディレクトリ: 開発時はリポジトリ直下、exe 化時は exe と同じフォルダ
#   （projects / output / logs はここに作られる。利用者が見つけやすく、削除も容易）
ROOT_DIR = Path(sys.executable).resolve().parent if _is_frozen() else Path(__file__).resolve().parents[2]
# 同梱リソースの基準ディレクトリ: exe 化時は PyInstaller の展開先（sys._MEIPASS）
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", ROOT_DIR)) if _is_frozen() else ROOT_DIR


def resource_path(rel: str | Path) -> Path:
    """同梱リソース（config / frontend / schema / samples 等）の実パス。

    exe と同じフォルダに同名ファイルがあればそちらを優先する（利用者がテンプレートや設定を差し替えられる）。
    無ければ同梱（sys._MEIPASS）を使う。基本設計基準書 8 章の get_resource_path に相当。
    """
    rel = Path(rel)
    if rel.is_absolute():
        return rel
    external = ROOT_DIR / rel
    if external.exists():
        return external
    return BUNDLE_DIR / rel

# 設定ファイルが無い場合の最小既定値。config/app_config.json と同じ構造を保つ。
_DEFAULT_CONFIG: dict[str, Any] = {
    "server": {"host": "127.0.0.1", "port": 8765, "open_browser": True},
    "paths": {
        "projects_dir": "projects",
        "output_dir": "output",
        "logs_dir": "logs",
        "templates_file": "config/templates.json",
        "font_fallback_file": "config/font_fallback.json",
        "schema_file": "schema/presentation.schema.json",
        "user_templates_file": "config/user_templates.json",
        "user_template_assets_dir": "config/template_assets/user",
        "copilot_prompts_file": "config/copilot_prompts.json",
    },
    "limits": {"max_upload_mb": 50, "max_slides": 300, "max_elements_per_slide": 200},
    "canvas": {"default_width_pt": 960, "default_height_pt": 540, "aspect": "16:9"},
    "layout": {
        "margin_pt": 36,
        "gutter_pt": 18,
        "title_height_pt": 64,
        "title_font_pt": 28,
        "body_font_pt": 16,
        "caption_font_pt": 12,
        "line_height_ratio": 1.35,
        "cjk_char_width_ratio": 1.0,
        "latin_char_width_ratio": 0.55,
        "max_columns": 3,
        "size_bands": {"title": [24, 36], "subtitle": [16, 24], "body": [12, 20], "caption": [9, 14], "card": [11, 18]},
        "image_max_height_ratio": 0.45,
        "image_min_height_pt": 120,
        "image_side_weight": 0.4,
        "autofit_steps": [1.0, 0.95, 0.9, 0.85],
        "autofit_min_scale": 0.85,
        "split_min_remaining_ratio": 0.25, "diagram_min_height_pt": 140, "diagram_max_height_ratio": 0.55,
        "band_max_chars": 80,
        "keep_with_next_max_chars": 40,
    },
    "pptx_export": {"default_mode": "editable", "modes": ["editable", "visual", "hybrid"], "visual_render_scale": 2},
    "html_import": {"use_computed_style": True, "viewport_width": 1280, "viewport_height": 900, "render_timeout_ms": 10000},
    "web_export": {"bundle_dir_name": "web", "viewer_title_suffix": " | Web図解", "flow_breakpoint_px": 720},
    "quality": {"text_overflow_ratio_warn": 1.0, "overlap_area_ratio_warn": 0.15, "image_aspect_tolerance": 0.03},
    "logging": {"level": "INFO", "file_name": "app.log", "max_bytes": 2000000, "backup_count": 3},
    "copilot": {"chat_url": "https://m365.cloud.microsoft/chat", "max_chars": 60000, "image_note": True, "agent_name": "資料づくりの相棒", "agent_description": "PowerPoint・Web 図解 双方向変換アプリと同じ書式で、資料の構成を整えるエージェント。", "agent_starters_max": 6},
}


def _deep_merge(base: dict, override: dict) -> dict:
    """既定値の上に設定ファイルの値を重ねる（欠けたキーは既定値が残る）。"""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _read_json(path: Path) -> dict:
    """JSONを読む。存在しない・壊れている場合は空辞書を返し、呼び出し側で既定値へフォールバックさせる。"""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


class AppConfig:
    """設定コンテナ。`get("layout.margin_pt")` のようにドット区切りで参照できる。"""

    def __init__(self, config_path: Path | None = None):
        env_path = os.environ.get("PPTX_WEB_BRIDGE_CONFIG")
        self.config_path = Path(config_path or env_path or resource_path("config/app_config.json"))
        file_data = _read_json(self.config_path)
        self.data = _deep_merge(_DEFAULT_CONFIG, file_data)
        self.loaded_from_file = bool(file_data)

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    # 書き込み先（exe の隣に作る）と、同梱リソース（exe の隣 → 同梱 の順で探す）を区別する
    _WRITABLE_KEYS = {"projects_dir", "output_dir", "logs_dir", "user_templates_file", "user_template_assets_dir"}

    def path(self, key: str) -> Path:
        """paths.* の値を絶対パスへ変換する。書き込み先は ROOT_DIR 基準、リソースは resource_path で解決。"""
        rel = self.get(f"paths.{key}")
        if rel is None:
            raise KeyError(f"paths.{key} が設定にありません")
        p = Path(rel)
        if p.is_absolute():
            return p
        return ROOT_DIR / p if key in self._WRITABLE_KEYS else resource_path(p)

    def templates(self) -> list[dict]:
        """組込テンプレート（config/templates.json）とユーザーテンプレート（PPTX から作成、config/user_templates.json）を結合して返す。

        各要素に `source`（builtin / user）を付ける。ID が重なる場合は組込を優先する。
        """
        builtin = [dict(t, source="builtin") for t in self._builtin_templates()]
        seen = {t.get("id") for t in builtin}
        user = _read_json(self.path("user_templates_file")).get("templates") or []
        for t in user:
            if isinstance(t, dict) and t.get("id") and t["id"] not in seen:
                builtin.append(dict(t, source="user"))
                seen.add(t["id"])
        return builtin

    def _builtin_templates(self) -> list[dict]:
        data = _read_json(self.path("templates_file"))
        templates = data.get("templates") if isinstance(data, dict) else None
        if not templates:
            # テンプレート設定が無い場合の最小フォールバック
            return [
                {
                    "id": "plain",
                    "name": "プレーン（既定）",
                    "fonts": {"heading": "Meiryo", "body": "Meiryo"},
                    "colors": {
                        "primary": "#1F3A5F",
                        "secondary": "#4F6D8F",
                        "accent": "#E07A1F",
                        "background": "#FFFFFF",
                        "surface": "#F4F6F9",
                        "text": "#222222",
                        "muted": "#666666",
                        "line": "#C9D1DB",
                    },
                    "footer": {"enabled": False, "text": "", "show_page_number": True},
                    "confidential_mark": {"enabled": False, "text": ""},
                }
            ]
        return templates

    def template(self, template_id: str | None) -> dict:
        """ID でテンプレートを引く。見つからなければ先頭（既定）を返す。"""
        templates = self.templates()
        for t in templates:
            if t.get("id") == template_id:
                return t
        return templates[0]

    def copilot_prompts(self) -> dict:
        """「Copilot に頼む」の用途プリセット（config/copilot_prompts.json）。無ければ最小の 1 件。"""
        data = _read_json(self.path("copilot_prompts_file"))
        if not data.get("purposes"):
            data = {"chat_url": self.get("copilot.chat_url"), "purposes": [{"id": "summarize", "name": "要約する", "description": "", "content_format": "markdown", "options": {"count": 8}, "prompt": "次の資料を {count} 枚に要約してください。\n\n---\n"}]}
        data.setdefault("chat_url", self.get("copilot.chat_url"))
        data.setdefault("agent", {"name": self.get("copilot.agent_name"), "description": self.get("copilot.agent_description"), "starters_max": self.get("copilot.agent_starters_max", 6)})
        return data

    def font_fallback(self) -> dict:
        data = _read_json(self.path("font_fallback_file"))
        if not data:
            data = {"default_heading": "Meiryo", "default_body": "Meiryo", "web_font_stack": "sans-serif", "aliases": {}}
        return data


_config_singleton: AppConfig | None = None


def get_config() -> AppConfig:
    """プロセス内で共有する設定インスタンスを返す。"""
    global _config_singleton
    if _config_singleton is None:
        _config_singleton = AppConfig()
    return _config_singleton


def reload_config() -> AppConfig:
    global _config_singleton
    _config_singleton = AppConfig()
    return _config_singleton
