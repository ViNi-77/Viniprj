"""アプリの版と、入っている機能の一覧。

「更新したのに画面が変わらない」を切り分けられるようにするための情報源。
版・ビルド時刻・git のコミットに加え、その版に入っている機能の印（フェーズ名）を返す。
exe 版では git が無いので、埋め込み値（`_BUILD_INFO`）か「不明」を返す。
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from .config import ROOT_DIR, resource_path
from .model import SCHEMA_VERSION

APP_VERSION = "0.3.0"

# 画面に出す「この版に入っている機能」。増えた機能はここに足す（UI はこれをそのまま並べる）
FEATURES: list[dict[str, str]] = [
    {"id": "layout_quality", "phase": "A", "name": "レイアウト品質", "hint": "文字サイズの帯域・画像の横並び・分割の抑制"},
    {"id": "edit_ui", "phase": "B", "name": "編集 UI", "hint": "プレビュー上でドラッグ・リサイズ・取り消し"},
    {"id": "template_from_pptx", "phase": "C", "name": "PPTX からテンプレート作成", "hint": "表紙・中身・最終ページの 3 枚を読んで部品を推定"},
    {"id": "copilot_handoff", "phase": "D", "name": "Copilot に頼む", "hint": "Markdown / Word / 一式を渡し、回答を資料に戻す"},
    {"id": "copilot_agent_kit", "phase": "E", "name": "Copilot エージェント一式", "hint": "定義・指示文・ナレッジを ZIP で書き出す"},
    {"id": "diagrams", "phase": "F", "name": "図解部品", "hint": "フロー / カード / 比較 / 数値 / 年表"},
    {"id": "merge_import", "phase": "G", "name": "差分マージ再取込", "hint": "編集を残して変わったところだけ反映"},
]

_BUILD_INFO_NAME = "build_info.json"


def _read_build_info() -> dict:
    """PyInstaller で同梱した build_info.json（あれば）。exe 版はこれを使う。"""
    for path in (resource_path(_BUILD_INFO_NAME), ROOT_DIR / _BUILD_INFO_NAME):
        try:
            if Path(path).is_file():
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def _git(*args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(ROOT_DIR), *args], capture_output=True, text=True, timeout=3, check=False)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


@lru_cache(maxsize=1)
def build_info() -> dict:
    """版・コミット・日時。git があればそこから、無ければ同梱の build_info.json から。"""
    info = _read_build_info()
    commit = info.get("commit") or _git("rev-parse", "--short=7", "HEAD")
    commit_date = info.get("commit_date") or _git("log", "-1", "--format=%cI")
    branch = info.get("branch") or _git("rev-parse", "--abbrev-ref", "HEAD")
    dirty = bool(_git("status", "--porcelain")) if not info else bool(info.get("dirty"))
    return {
        "version": info.get("version") or APP_VERSION,
        "schema_version": SCHEMA_VERSION,
        "commit": commit or "不明",
        "commit_date": commit_date or "",
        "branch": branch or "",
        "dirty": dirty,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def version_info() -> dict:
    """/api/version の中身。画面のバージョン表示はこれだけを見る。"""
    return {**build_info(), "features": FEATURES}


def label() -> str:
    """`v0.3.0 (a1b2c3d)` の形。ログとヘッダーに出す。"""
    info = build_info()
    commit = info["commit"]
    return f"v{info['version']}" + (f" ({commit}{'+変更あり' if info['dirty'] else ''})" if commit != "不明" else "")


@lru_cache(maxsize=1)
def asset_tag() -> str:
    """画面ファイル（frontend / viewer）の中身から作る短い印。

    ブラウザが古い JS・CSS を握ったままだと「更新したのに画面が変わらない」が起きる。
    この印を URL に付けて、中身が変わったら必ず取り直させる。
    """
    import hashlib

    h = hashlib.sha1()
    for base in (resource_path("frontend"), resource_path("backend/app/viewer")):
        base = Path(base)
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file():
                st = p.stat()
                h.update(f"{p.name}:{int(st.st_mtime)}:{st.st_size};".encode())
    h.update(f"{APP_VERSION}:{build_info()['commit']}".encode())
    return h.hexdigest()[:8]
