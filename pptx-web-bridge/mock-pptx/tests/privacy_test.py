"""匿名化検査: 実在情報の禁止語、プロパティ、絶対パス、認証情報らしき文字列が無いこと。"""
from __future__ import annotations

import re
import zipfile

from pptx import Presentation

# 禁止語リスト。実在の社名・製品名・個人名等は追加して運用する（ここには一般的な検知パターンのみ置く）。
FORBIDDEN_PATTERNS = [
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",  # メールアドレス
    r"/Users/[A-Za-z0-9_.-]+",  # macOS の絶対パス
    r"[A-Z]:\\\\Users\\\\",  # Windows の絶対パス
    r"AKIA[0-9A-Z]{16}",  # クラウド鍵らしき文字列
    r"(api[_-]?key|secret|password|token)\s*[:=]",  # 認証情報
    r"株式会社(?!（架空）)",  # 架空明記の無い社名
    r"Corporation|Inc\.|Co\., Ltd\.",  # 実在企業表記
    r"https?://",  # 外部リンク
]
FORBIDDEN_WORDS_FILE_HINT = "mock-pptx/tests/forbidden_words.txt（任意）に実在名を 1 行 1 語で追加すると検査対象になる"


def _all_text(pptx_path) -> str:
    prs = Presentation(str(pptx_path))
    parts = []
    for slide in prs.slides:
        for sh in slide.shapes:
            if sh.has_text_frame:
                parts.append(sh.text_frame.text)
            if getattr(sh, "has_table", False) and sh.has_table:
                for row in sh.table.rows:
                    for cell in row.cells:
                        parts.append(cell.text)
        if slide.has_notes_slide:
            parts.append(slide.notes_slide.notes_text_frame.text)
    cp = prs.core_properties
    parts += [cp.author or "", cp.last_modified_by or "", cp.title or "", cp.subject or "", cp.comments or "", cp.keywords or ""]
    return "\n".join(parts)


def test_no_forbidden_patterns(pptx_path):
    text = _all_text(pptx_path)
    for pat in FORBIDDEN_PATTERNS:
        assert not re.search(pat, text), f"禁止パターンに一致: {pat}"


def test_optional_forbidden_words(pptx_path):
    from pathlib import Path

    words_file = Path(__file__).resolve().parent / "forbidden_words.txt"
    if not words_file.exists():
        return
    text = _all_text(pptx_path)
    for w in [x.strip() for x in words_file.read_text(encoding="utf-8").splitlines() if x.strip() and not x.startswith("#")]:
        assert w not in text, f"禁止語を検出: {w}"


def test_properties_anonymized(pptx_path):
    cp = Presentation(str(pptx_path)).core_properties
    assert cp.author == "Anonymous Test Generator" and cp.last_modified_by == "Anonymous Test Generator"
    assert not cp.comments and not cp.keywords


def test_xml_has_no_paths_or_urls(pptx_path):
    with zipfile.ZipFile(pptx_path) as z:
        for n in z.namelist():
            if n.endswith((".xml", ".rels")):
                data = z.read(n).decode("utf-8", "ignore")
                assert "/Users/" not in data and "C:\\\\" not in data
                # 標準スキーマ URL 以外の http を禁止
                for m in re.findall(r"https?://[^\"'<> ]+", data):
                    assert "schemas." in m or "purl.org" in m or "w3.org" in m, f"外部 URL を検出: {m}"


def test_numbers_are_marked_as_sample(pptx_path):
    """数値データ（件数・日数・割合・ページ数など単位付きの数値）を含む文には「仮」「例示」「サンプル」「架空」のいずれかを付ける（仕様 2 章）。"""
    text = _all_text(pptx_path)
    unit_number = re.compile(r"\d+\s*(件|日|%|％|時間|ページ|形式|円|人|倍|割|台|回)")
    for ln in text.splitlines():
        if unit_number.search(ln):
            assert re.search(r"仮|例示|サンプル|架空", ln), f"数値データに注記がありません: {ln}"
