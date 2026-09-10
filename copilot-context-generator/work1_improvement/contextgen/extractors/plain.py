"""テキストファイル抽出.

改善②: charset-normalizer による文字コード自動判定（CP932/UTF-16 対応）。
text_encoding_mode='legacy' で原本挙動（utf-8-sig を errors='ignore' で読む）。
"""
from __future__ import annotations

from pathlib import Path

from . import ExtractResult, ExtractorContext

try:
    from charset_normalizer import from_bytes
except Exception:  # pragma: no cover
    from_bytes = None


def read_text_file_legacy(path: Path) -> str:
    for enc in ('utf-8-sig', 'cp932', 'utf-8'):
        try:
            return path.read_text(encoding=enc, errors='ignore')
        except Exception:
            continue
    return ''


def read_text_file(path: Path, ctx: ExtractorContext) -> ExtractResult:
    mode = getattr(ctx.config, 'text_encoding_mode', 'auto')
    if mode == 'legacy' or from_bytes is None:
        text = read_text_file_legacy(path)
        status = 'ok' if text.strip() else 'empty'
        return ExtractResult(text=text, status=status)

    try:
        raw = path.read_bytes()
    except Exception as e:
        return ExtractResult(status='error', reason=f"読み取りエラー: {e}")

    if not raw.strip():
        return ExtractResult(status='empty', reason='空ファイル')

    # まず UTF-8 系→CP932 を厳密に試し、ダメなら charset-normalizer で判定
    # （日本の社内テキストは CP932 が多く、厳密デコード成功なら誤判定リスクが低い）
    for enc in ('utf-8-sig', 'utf-8', 'cp932'):
        try:
            text = raw.decode(enc)
            return ExtractResult(text=text, status='ok' if text.strip() else 'empty',
                                 meta={'encoding': enc})
        except UnicodeDecodeError:
            pass

    best = from_bytes(raw).best()
    if best is None:
        # 判定不能: 従来どおり utf-8 ignore で救済
        text = raw.decode('utf-8', errors='ignore')
        return ExtractResult(text=text, status='ok' if text.strip() else 'error',
                             reason='文字コード判定不能（utf-8 ignore で読込）',
                             meta={'encoding': 'unknown'})

    text = str(best)
    return ExtractResult(text=text, status='ok' if text.strip() else 'empty',
                         meta={'encoding': best.encoding})
