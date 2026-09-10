"""v2.1 F7: OCR のテスト.

FakeEngine で結線を検証し、Vision が使える macOS では実 OCR のスモークも行う。
"""
from __future__ import annotations

import threading

import pytest

from contextgen.config import RunConfig
from contextgen.extractors import ExtractorContext, extract
from contextgen.extractors import ocr as ocr_module


class FakeEngine:
    name = 'fake'

    def recognize(self, pil_image):
        return '偽OCR結果テキスト'


@pytest.fixture
def ctx_factory(sample_tree, out_dirs):
    out, base = out_dirs

    def make(**kw):
        config = RunConfig(search_root=sample_tree, context_output_dir=out, base_dir=base, **kw)
        return ExtractorContext(config=config, stop_event=threading.Event())

    return make


def test_ocr_off_keeps_needs_ocr(sample_tree, ctx_factory):
    result = extract(sample_tree / '品質' / 'スキャン報告書.pdf', ctx_factory(ocr_mode='off'))
    assert result.status == 'needs_ocr'


def test_ocr_auto_with_fake_engine(sample_tree, ctx_factory, monkeypatch):
    monkeypatch.setattr(ocr_module, 'get_engine', lambda: FakeEngine())
    result = extract(sample_tree / '品質' / 'スキャン報告書.pdf', ctx_factory(ocr_mode='auto'))
    assert result.status == 'ok'
    assert result.meta.get('ocr') is True
    assert result.meta.get('ocr_engine') == 'fake'
    assert '# Page 1 (OCR)' in result.text
    assert '偽OCR結果テキスト' in result.text


def test_ocr_auto_without_engine_falls_back(sample_tree, ctx_factory, monkeypatch):
    monkeypatch.setattr(ocr_module, 'get_engine', lambda: None)
    result = extract(sample_tree / '品質' / 'スキャン報告書.pdf', ctx_factory(ocr_mode='auto'))
    assert result.status == 'needs_ocr'


def test_ocr_engine_returning_empty_falls_back(sample_tree, ctx_factory, monkeypatch):
    class EmptyEngine:
        name = 'empty'

        def recognize(self, pil_image):
            return ''

    monkeypatch.setattr(ocr_module, 'get_engine', lambda: EmptyEngine())
    result = extract(sample_tree / '品質' / 'スキャン報告書.pdf', ctx_factory(ocr_mode='auto'))
    assert result.status == 'needs_ocr'


def _make_image_pdf(path):
    """テキストを画像として描画した PDF（テキスト層なし）を作る."""
    from PIL import Image, ImageDraw

    image = Image.new('RGB', (1200, 400), 'white')
    draw = ImageDraw.Draw(image)
    try:
        from PIL import ImageFont
        font = ImageFont.load_default(size=64)
    except Exception:
        font = None
    draw.text((60, 150), 'HELLO OCR 12345', fill='black', font=font)
    image.save(str(path), 'PDF')


@pytest.mark.skipif(ocr_module.get_engine() is None, reason='OCRエンジンが利用できない環境')
def test_real_ocr_smoke(sample_tree, ctx_factory, tmp_path):
    pdf_path = sample_tree / 'スキャン文書.pdf'
    _make_image_pdf(pdf_path)

    result = extract(pdf_path, ctx_factory(ocr_mode='auto'))
    assert result.status == 'ok'
    assert result.meta.get('ocr') is True
    compact = result.text.replace(' ', '')
    assert 'HELLO' in compact.upper()
    assert '12345' in compact
