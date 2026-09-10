"""プロジェクト（Presentation JSON）の保存・読込と、成果物の書き出し。

保存先はすべて設定の paths.* 配下。ファイル名は安全な文字だけに正規化する。
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

from .config import get_config
from .web_renderer import build_bundle

_SAFE = re.compile(r"[^0-9A-Za-z_\-぀-ヿ一-鿿０-ｚ]+")


def safe_name(name: str, default: str = "project") -> str:
    name = _SAFE.sub("_", (name or "").strip()).strip("_")
    return name[:80] or default


def _projects_dir() -> Path:
    d = get_config().path("projects_dir")
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_project(name: str, presentation: dict) -> Path:
    path = _projects_dir() / f"{safe_name(name)}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(presentation, f, ensure_ascii=False, indent=2)
    return path


def load_project(name: str) -> dict:
    path = _projects_dir() / f"{safe_name(name)}.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def list_projects() -> list[dict]:
    out = []
    for p in sorted(_projects_dir().glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            with p.open("r", encoding="utf-8") as f:
                head = json.load(f)
            title = head.get("meta", {}).get("title", "")
            slides = len(head.get("slides", []))
        except (OSError, json.JSONDecodeError):
            title, slides = "(読込不可)", 0
        out.append({"name": p.stem, "title": title, "slides": slides, "updated_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"), "size": p.stat().st_size})
    return out


def delete_project(name: str) -> bool:
    path = _projects_dir() / f"{safe_name(name)}.json"
    if path.exists():
        path.unlink()
        return True
    return False


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def bundle_zip(presentation: dict) -> bytes:
    files = build_bundle(presentation)
    buf = io.BytesIO()
    root = get_config().get("web_export.bundle_dir_name", "web")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, data in files.items():
            z.writestr(f"{root}/{rel}", data)
    return buf.getvalue()


def write_output(kind: str, base_name: str, data: bytes, ext: str) -> Path:
    out_dir = get_config().path("output_dir")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{safe_name(base_name)}_{timestamp()}.{ext}"
    path.write_bytes(data)
    return path


def write_web_dir(presentation: dict, base_name: str) -> Path:
    out_dir = get_config().path("output_dir") / f"{safe_name(base_name)}_{timestamp()}_web"
    for rel, data in build_bundle(presentation).items():
        target = out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return out_dir
