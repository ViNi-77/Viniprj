"""PDF 抽出.

原本と同一の整形（# Page N マーカー）。
改善②: 暗号化 PDF を protected、テキスト層なしを needs_ocr として分類。
v3 柱1: ページ単位で保護し、1ページの解析失敗で文書全体を失わない。
"""
from __future__ import annotations

from pathlib import Path

from . import ExtractResult, ExtractorContext, UnitCollector

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


def read_pdf_file(path: Path, ctx: ExtractorContext) -> ExtractResult:
    if PdfReader is None:
        return ExtractResult(status='error', reason='pypdf が利用できません')

    # PdfReader の生成やパスワード判定の失敗は、文書全体の失敗として扱う
    try:
        reader = PdfReader(str(path))

        if reader.is_encrypted:
            try:
                if not reader.decrypt(''):
                    return ExtractResult(status='protected', reason='パスワード保護PDF')
            except Exception:
                return ExtractResult(status='protected', reason='パスワード保護PDF')

        page_count = len(reader.pages)
    except Exception as e:
        return ExtractResult(status='error', reason=f"PDF解析エラー: {e}")

    collector = UnitCollector()
    text_pages = 0

    for page_index in range(1, page_count + 1):
        if ctx.stopped():
            break
        with collector.unit(f"p.{page_index}"):
            page = reader.pages[page_index - 1]
            text = page.extract_text() or ''
            if text.strip():
                text_pages += 1
                collector.append(f"# Page {page_index}")
                collector.append(text)

    meta = {'pages': page_count, 'text_pages': text_pages}

    # 全ページにテキスト層が無い（かつ解析自体は成功している）ならOCR候補
    if page_count > 0 and text_pages == 0 and not collector.failures:
        if ctx.config.ocr_mode == 'auto':
            from . import ocr
            ocr_result = ocr.ocr_pdf(path, ctx)
            if ocr_result is not None:
                ocr_text, engine_name = ocr_result
                meta.update({'ocr': True, 'ocr_engine': engine_name})
                return ExtractResult(text=ocr_text, status='ok', meta=meta,
                                     units_total=page_count, units_ok=page_count)
        return ExtractResult(
            status='needs_ocr',
            reason=f"全{page_count}ページにテキスト層がありません（スキャン/画像PDFの可能性）",
            meta=meta, units_total=page_count, units_ok=page_count,
        )

    return collector.build(empty_reason='本文なし', meta=meta)
