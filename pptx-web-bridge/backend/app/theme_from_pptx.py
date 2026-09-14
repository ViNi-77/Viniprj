"""PowerPoint → プロンプトに書ける「見た目の指示」。

`theme_from_html` と**同じ形**を返す。プロンプト側が入力の種類を気にしなくて済むようにするため。

中身は Phase N までに作った `pptx_styles.ThemeInfo`（`a:clrScheme` / `a:fontScheme` を読む）を
そのまま使う。描画器を畳んでも、**実ファイルの色とフォントを読む力だけは残す**という判断
（`docs/99`）に基づく。`presentation["theme"]` はアプリ既定のテンプレート色であって
実ファイルの色ではないので、そちらは使わない。
"""
from __future__ import annotations

import io
from typing import Any

from pptx import Presentation

from .logging_setup import get_logger
from .model import warning
from .pptx_styles import ThemeInfo, apply_brightness

log = get_logger("theme_from_pptx")


def extract_theme(data: bytes, filename: str = "deck.pptx") -> dict:
    """PPTX のスライドマスターからテーマ色・フォントを読む。"""
    warnings: list[dict] = []
    colors: dict[str, str] = {}
    fonts: dict[str, str] = {}
    palette: list[str] = []
    sources: dict[str, str] = {}

    try:
        prs = Presentation(io.BytesIO(data))
        masters = list(prs.slide_masters)
    except Exception as exc:  # noqa: BLE001
        return {
            "name": filename, "filename": filename, "colors": {}, "fonts": {}, "decoration": {},
            "kinds": [], "palette": [], "sources": {},
            "warnings": [warning("theme_from_pptx", "THEME_PPTX_UNREADABLE", f"PowerPoint のテーマを読めませんでした: {exc}", fallback="配色の指示なしでプロンプトを作ります")],
        }

    if not masters:
        warnings.append(warning("theme_from_pptx", "THEME_NO_MASTER", "スライドマスターがありませんでした。", fallback="配色の指示なしでプロンプトを作ります"))
    else:
        if len(masters) > 1:
            warnings.append(warning("theme_from_pptx", "THEME_MULTIPLE_MASTERS", f"スライドマスターが {len(masters)} 個あります。1 個目の配色を使います。", fallback="1 個目のマスターを採用"))
        info = ThemeInfo(masters[0])
        c = info.colors
        palette = [v for v in c.values() if isinstance(v, str) and v.startswith("#")]
        if c:
            dk1, lt1 = c.get("dk1", "#222222"), c.get("lt1", "#FFFFFF")
            lt2 = c.get("lt2", "#E7E6E6")
            colors = {
                "background": lt1,
                "text": dk1,
                "heading": c.get("accent1") or c.get("dk2") or dk1,
                "card": lt1,
                "line": apply_brightness(lt2, -0.15),
                "muted": apply_brightness(dk1, 0.35),
                "accent": c.get("accent2") or c.get("accent1") or dk1,
            }
            sources = {k: "スライドマスターのテーマ色（a:clrScheme）" for k in colors}
        else:
            warnings.append(warning("theme_from_pptx", "THEME_NO_COLORS", "この PowerPoint からはテーマ色を読み取れませんでした。", fallback="配色の指示なしでプロンプトを作ります"))
        head = info.fonts.get("major_ea") or info.fonts.get("major_latin")
        body = info.fonts.get("minor_ea") or info.fonts.get("minor_latin")
        if head:
            fonts["heading"] = head
        if body:
            fonts["body"] = body
        if not fonts:
            warnings.append(warning("theme_from_pptx", "THEME_NO_FONTS", "テーマフォントの指定が見つかりませんでした。", fallback="フォントの指示なしでプロンプトを作ります"))

    theme: dict[str, Any] = {
        "name": filename,
        "filename": filename,
        "colors": colors,
        "fonts": fonts,
        "decoration": {},
        "kinds": [],
        "palette": palette[:12],
        "sources": sources,
        "warnings": warnings,
    }
    log.info("PPTX テーマ抽出: %s 色=%s フォント=%s 警告=%s", filename, len(colors), len(fonts), len(warnings))
    return theme
