"""v2.1 F7: OCR エンジン抽象化.

needs_ocr と判定された PDF を pypdfium2 でラスタライズし、環境で使える
OCR エンジンで本文化する。エンジンが使えない環境では None を返し、
呼び出し側は従来どおり needs_ocr として扱う（機能劣化しても壊れない）。

エンジン:
- WindowsMediaOcrEngine: Windows 10/11 内蔵の Windows.Media.Ocr
  （winsdk が必要。日本語言語パックは標準搭載）
- MacVisionOcrEngine: macOS の Vision.framework（開発・検証用）
"""
from __future__ import annotations

import io
from pathlib import Path

RENDER_SCALE = 2.0  # 72dpi × 2 = 約150dpi


# ---- エンジン実装 ----

class MacVisionOcrEngine:
    name = 'macos_vision'

    def __init__(self):
        import Vision  # noqa: F401  (存在確認)
        self._vision = Vision

    def recognize(self, pil_image) -> str:
        import Foundation
        Vision = self._vision

        buf = io.BytesIO()
        pil_image.save(buf, format='PNG')
        data = Foundation.NSData.dataWithBytes_length_(buf.getvalue(), buf.tell())

        handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, {})
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLanguages_(['ja-JP', 'en-US'])
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        handler.performRequests_error_([request], None)

        lines = []
        for observation in request.results() or []:
            candidates = observation.topCandidates_(1)
            if candidates and len(candidates):
                lines.append(str(candidates[0].string()))
        return '\n'.join(lines)


class WindowsMediaOcrEngine:
    name = 'windows_media_ocr'

    def __init__(self):
        import asyncio  # noqa: F401
        import winsdk.windows.media.ocr  # noqa: F401  (存在確認)

    def recognize(self, pil_image) -> str:
        import asyncio
        return asyncio.run(self._recognize_async(pil_image))

    async def _recognize_async(self, pil_image) -> str:
        from winsdk.windows.globalization import Language
        from winsdk.windows.graphics.imaging import BitmapDecoder
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

        buf = io.BytesIO()
        pil_image.save(buf, format='PNG')

        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream.get_output_stream_at(0))
        writer.write_bytes(buf.getvalue())
        await writer.store_async()

        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()

        engine = None
        if OcrEngine.is_language_supported(Language('ja')):
            engine = OcrEngine.try_create_from_language(Language('ja'))
        if engine is None:
            engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            return ''

        result = await engine.recognize_async(bitmap)
        return '\n'.join(line.text for line in result.lines)


_ENGINE_UNSET = object()
_engine = _ENGINE_UNSET


def get_engine():
    """環境で利用可能な OCR エンジンを返す（なければ None、結果はキャッシュ）."""
    global _engine
    if _engine is _ENGINE_UNSET:
        _engine = None
        for engine_cls in (WindowsMediaOcrEngine, MacVisionOcrEngine):
            try:
                _engine = engine_cls()
                break
            except Exception:
                continue
    return _engine


def rasterize_pdf_pages(path: Path, max_pages: int):
    """(page_no, PIL.Image) を順に返す。pypdfium2 がなければ ImportError."""
    import pypdfium2

    pdf = pypdfium2.PdfDocument(str(path))
    try:
        for page_no in range(min(len(pdf), max_pages)):
            page = pdf[page_no]
            image = page.render(scale=RENDER_SCALE).to_pil()
            yield page_no + 1, image
    finally:
        pdf.close()


def ocr_pdf(path: Path, ctx) -> tuple[str, str] | None:
    """PDF 全体を OCR して (テキスト, エンジン名) を返す。不可なら None."""
    engine = get_engine()
    if engine is None:
        return None
    try:
        pages = []
        for page_no, image in rasterize_pdf_pages(path, ctx.config.ocr_max_pages):
            if ctx.stopped():
                break
            text = engine.recognize(image).strip()
            if not text:
                continue
            pages.append(f"# Page {page_no} (OCR)")
            pages.append(text)
        if not pages:
            return None
        return '\n'.join(pages), engine.name
    except ImportError:
        return None
    except Exception:
        return None
