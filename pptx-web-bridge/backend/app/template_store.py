"""ユーザーテンプレート（PowerPoint から作成したもの）の保存・削除。

- 定義: `paths.user_templates_file`（既定 config/user_templates.json。exe 版では exe の隣）
- 画像・土台 PPTX: `paths.user_template_assets_dir`/<id>/（既定 config/template_assets/user/<id>/）
- 組込テンプレート（config/templates.json）は触らない。ID が組込と重なる保存は拒否する。
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .config import ROOT_DIR, get_config

_ID_RE = re.compile(r"[^a-z0-9_]+")
_REQUIRED_KEYS = ("id", "name", "fonts", "colors")


def safe_id(raw: str, default: str = "user_template") -> str:
    """テンプレート ID を英小文字・数字・下線に正規化する（ファイル名にも使う）。"""
    s = _ID_RE.sub("_", str(raw or "").strip().lower()).strip("_")
    return (s or default)[:48]


def templates_file() -> Path:
    return get_config().path("user_templates_file")


def assets_dir(template_id: str) -> Path:
    d = get_config().path("user_template_assets_dir") / safe_id(template_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def rel_path(p: Path) -> str:
    """画像パスをテンプレート定義に書く形へ。リポジトリ（exe の隣）配下なら相対、そうでなければ絶対。"""
    p = Path(p).resolve()
    try:
        return p.relative_to(ROOT_DIR.resolve()).as_posix()
    except ValueError:
        return str(p)


def _read() -> dict:
    path = templates_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("templates"), list) else {"templates": []}
    except (OSError, json.JSONDecodeError):
        return {"templates": []}


def _write(data: dict) -> None:
    path = templates_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_templates() -> list[dict]:
    return [t for t in _read()["templates"] if isinstance(t, dict) and t.get("id")]


def get_template(template_id: str) -> dict | None:
    for t in list_templates():
        if t.get("id") == template_id:
            return t
    return None


def is_builtin(template_id: str) -> bool:
    return any(t.get("id") == template_id and t.get("source") == "builtin" for t in get_config().templates())


def validate_template(t: dict) -> list[str]:
    """保存前の最低限の検査。問題があれば日本語メッセージの一覧を返す。"""
    errors: list[str] = []
    if not isinstance(t, dict):
        return ["テンプレートはオブジェクトである必要があります。"]
    for k in _REQUIRED_KEYS:
        if k not in t:
            errors.append(f"'{k}' がありません。")
    if t.get("id") != safe_id(str(t.get("id", ""))):
        errors.append("ID は英小文字・数字・下線のみ使えます。")
    if is_builtin(str(t.get("id", ""))):
        errors.append("組込テンプレートと同じ ID は使えません。")
    for part in ("cover", "content", "closing"):
        p = t.get(part)
        if p is None:
            continue
        if not isinstance(p, dict):
            errors.append(f"'{part}' はオブジェクトである必要があります。")
            continue
        for key, spec in p.items():
            if isinstance(spec, dict):
                for c in ("x", "y", "w", "h"):
                    if c in spec and spec[c] is not None:
                        try:
                            float(spec[c])
                        except (TypeError, ValueError):
                            errors.append(f"'{part}.{key}.{c}' が数値ではありません。")
    colors = t.get("colors")
    if isinstance(colors, dict):
        for k, v in colors.items():
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(v)):
                errors.append(f"colors.{k} は #RRGGBB 形式で指定してください。")
    return errors


def save_template(t: dict) -> dict:
    """検証して保存（同じ ID があれば置き換え）。保存した定義を返す。"""
    errors = validate_template(t)
    if errors:
        raise ValueError(" / ".join(errors))
    t = dict(t)
    t["source"] = "user"
    data = _read()
    data["templates"] = [x for x in data["templates"] if isinstance(x, dict) and x.get("id") != t["id"]] + [t]
    _write(data)
    return t


def delete_template(template_id: str) -> bool:
    """定義と画像フォルダを削除する。組込は削除しない。"""
    if is_builtin(template_id):
        return False
    data = _read()
    before = len(data["templates"])
    data["templates"] = [x for x in data["templates"] if not (isinstance(x, dict) and x.get("id") == template_id)]
    if len(data["templates"]) != before:
        _write(data)
    d = get_config().path("user_template_assets_dir") / safe_id(template_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    return len(data["templates"]) != before


def rename_assets(old_id: str, new_id: str, t: dict) -> dict:
    """ID を変えて保存するとき、画像フォルダを移して定義内のパスを書き換える。"""
    if old_id == new_id:
        return t
    src = get_config().path("user_template_assets_dir") / safe_id(old_id)
    dst = get_config().path("user_template_assets_dir") / safe_id(new_id)
    if src.exists():
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        shutil.move(str(src), str(dst))
    old_rel, new_rel = rel_path(src), rel_path(dst)
    text = json.dumps(t, ensure_ascii=False).replace(old_rel, new_rel)
    return json.loads(text)
