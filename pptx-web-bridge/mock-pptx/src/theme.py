"""模擬 PPTX のテーマ定数（匿名化スライド仕様書 3 章）。色・フォント・余白・フッターをここで一元管理する。"""
from __future__ import annotations

THEME = {
    "name": "Generic Corporate Blue",
    "slide_width_in": 13.333,
    "slide_height_in": 7.5,
    "colors": {
        "navy": "082B5C",
        "blue": "1261A0",
        "cyan": "00A6C7",
        "ink": "243447",
        "light": "EEF4F8",
        "warning": "F39C3D",
        "success": "17845B",
        "white": "FFFFFF",
        "muted": "5B6B7C",
        "line": "C5D3E0",
        "orange_light": "FDEBD8",
        "green_light": "DFF3E8",
    },
    "font": "Arial",
    "sizes": {"title": 30, "body": 18, "small": 12, "note": 11, "kpi": 34, "card_title": 20},
    "margin_in": 0.6,
    "title_top_in": 0.45,
    "title_height_in": 0.8,
    "footer_text": "Anonymous Conversion Test / Sample Only",
    "footer_size": 10,
    "author": "Anonymous Test Generator",
}
