"""抽出器のステータス分類と本文抽出のテスト（改善②）."""
from __future__ import annotations

import threading

import pytest

from contextgen.config import RunConfig
from contextgen.extractors import ExtractorContext, extract


@pytest.fixture
def ctx(sample_tree, out_dirs):
    out, base = out_dirs
    config = RunConfig(search_root=sample_tree, context_output_dir=out, base_dir=base,
                       enable_doc_conversion=False)
    return ExtractorContext(config=config, stop_event=threading.Event())


def test_utf8_txt(sample_tree, ctx):
    result = extract(sample_tree / 'メモ.txt', ctx)
    assert result.status == 'ok'
    assert '生産ラインA' in result.text


def test_cp932_txt_auto_detected(sample_tree, ctx):
    result = extract(sample_tree / '設備' / '旧形式レポート.txt', ctx)
    assert result.status == 'ok'
    assert 'シフトJIS' in result.text
    assert result.meta.get('encoding', '').lower() in ('cp932', 'shift_jis', 'sjis', 'cp_932')


def test_cp932_txt_legacy_mode_is_lossy(sample_tree, out_dirs):
    out, base = out_dirs
    config = RunConfig(search_root=sample_tree, context_output_dir=out, base_dir=base,
                       text_encoding_mode='legacy')
    ctx = ExtractorContext(config=config, stop_event=threading.Event())
    result = extract(sample_tree / '設備' / '旧形式レポート.txt', ctx)
    # レガシーは utf-8 ignore で読むため日本語が失われる（改善②の動機）
    assert 'シフトJIS' not in result.text


def test_docx(sample_tree, ctx):
    result = extract(sample_tree / '設備' / '点検手順書.docx', ctx)
    assert result.status == 'ok'
    assert '始業前点検' in result.text
    assert '油圧 | 5MPa以上' in result.text


def test_xlsx(sample_tree, ctx):
    result = extract(sample_tree / '品質' / '測定データ.xlsx', ctx)
    assert result.status == 'ok'
    assert '# Sheet: 測定' in result.text
    assert 'A1=品番' in result.text
    assert 'A2=A-100' in result.text


def test_pptx(sample_tree, ctx):
    result = extract(sample_tree / '品質' / '品質会議.pptx', ctx)
    assert result.status == 'ok'
    assert '# Slide 1' in result.text
    assert '月次品質報告' in result.text
    assert '## Notes' in result.text
    assert '来月は目標0.2%' in result.text


def test_text_pdf(sample_tree, ctx):
    result = extract(sample_tree / '設備' / '仕様書.pdf', ctx)
    assert result.status == 'ok'
    assert '# Page 1' in result.text
    assert 'Spec sheet' in result.text


def test_imageonly_pdf_is_ocr_candidate(sample_tree, ctx):
    result = extract(sample_tree / '品質' / 'スキャン報告書.pdf', ctx)
    assert result.status == 'needs_ocr'
    assert result.text == ''


def test_doc_needs_conversion(sample_tree, ctx):
    result = extract(sample_tree / '古い報告書.doc', ctx)
    assert result.status == 'needs_conversion'
    assert result.text == ''


def test_zip_inner_text(sample_tree, ctx):
    result = extract(sample_tree / '過去資料.zip', ctx)
    assert result.status == 'ok'
    assert '# ZIP: 過去資料.zip' in result.text
    assert '議事録2024.txt' in result.text
    assert '歩留まり改善' in result.text


def test_unsupported_extension(sample_tree, ctx):
    result = extract(sample_tree / '品質' / '写真.png', ctx)
    assert result.status == 'unsupported'
