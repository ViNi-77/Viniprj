"""Word 文書 (.docx / .doc) 抽出.

.docx: python-docx（本文段落 + 表。原本と同一の整形）。
.doc: 改善② — 変換プラグイン（Windows: Word COM / macOS: textutil）を試し、
      変換できない環境では needs_conversion として報告する。
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from . import ExtractResult, ExtractorContext, UnitCollector

try:
    import docx
except Exception:  # pragma: no cover
    docx = None


def _heading_level(paragraph) -> int:
    """段落が見出しなら 1〜4 のレベルを返す（見出しでなければ 0）."""
    try:
        name = (paragraph.style.name or '')
    except Exception:
        return 0
    lowered = name.lower()
    if lowered.startswith('heading') or name.startswith('見出し'):
        digits = ''.join(ch for ch in name if ch.isdigit())
        return int(digits) if digits else 1
    if lowered in ('title', 'subtitle') or name in ('表題', '副題'):
        return 1
    return 0


def read_docx_file(path: Path, ctx: ExtractorContext) -> ExtractResult:
    if docx is None:
        return ExtractResult(status='error', reason='python-docx が利用できません')

    # 文書自体を開けない場合は全体の失敗として扱う
    try:
        document = docx.Document(str(path))
    except Exception as e:
        reason = str(e)
        if 'password' in reason.lower() or 'encrypted' in reason.lower():
            return ExtractResult(status='protected', reason=reason)
        return ExtractResult(status='error', reason=f"docx解析エラー: {reason}")

    # v3 柱1: 本文・表・埋め込みを別単位として保護する
    collector = UnitCollector()

    mark_headings = getattr(ctx.config, 'mark_docx_headings', False)

    with collector.unit('本文'):
        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            # v3: 見出しスタイルを構造マーカーとして残す。
            # 目次抽出（読解キット）とセマンティック分割の両方で効く
            if mark_headings:
                level = _heading_level(paragraph)
                if level:
                    collector.append('#' * min(level, 4) + ' ' + text)
                    continue
            collector.append(text)

    with collector.unit('表'):
        for table_index, table in enumerate(document.tables, start=1):
            with collector.unit(f"表{table_index}"):
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if cells:
                        collector.append(' | '.join(cells))

    meta: dict = {}
    with collector.unit('埋め込みオブジェクト'):
        # 貼り付けられた埋め込みExcel等（python-docx では本文にならない）
        from .embedded import extract_embedded_documents
        embedded_text, embedded_meta = extract_embedded_documents(path, ctx)
        if embedded_text:
            collector.append('# 埋め込みオブジェクト')
            collector.append(embedded_text)
            meta.update(embedded_meta)

    return collector.build(meta=meta)


def read_doc_file(path: Path, ctx: ExtractorContext) -> ExtractResult:
    if not ctx.config.enable_doc_conversion:
        return ExtractResult(status='needs_conversion',
                             reason='.doc は本文抽出対象外（変換オフ）')

    if sys.platform == 'darwin':
        return _convert_with_textutil(path)
    if sys.platform == 'win32':
        return _convert_with_word_com(path, ctx)
    return ExtractResult(status='needs_conversion',
                         reason='.doc を変換する手段がこの環境にありません（docx への変換を推奨）')


def _convert_with_textutil(path: Path) -> ExtractResult:
    """macOS: textutil で .doc → プレーンテキスト."""
    try:
        proc = subprocess.run(
            ['textutil', '-convert', 'txt', '-stdout', str(path)],
            capture_output=True, timeout=60,
        )
        if proc.returncode != 0:
            return ExtractResult(status='error',
                                 reason=f"textutil 変換失敗: {proc.stderr.decode('utf-8', 'ignore')[:200]}")
        text = proc.stdout.decode('utf-8', 'ignore')
        return ExtractResult(text=text, status='ok' if text.strip() else 'empty',
                             meta={'converter': 'textutil'})
    except Exception as e:
        return ExtractResult(status='error', reason=f"textutil 変換エラー: {e}")


def _convert_with_word_com(path: Path, ctx: ExtractorContext) -> ExtractResult:
    """Windows: Word COM で .doc → .docx に変換して読む."""
    try:
        import win32com.client  # type: ignore
    except Exception:
        return ExtractResult(status='needs_conversion',
                             reason='.doc 変換には Word (pywin32) が必要です')
    word = None
    try:
        with tempfile.TemporaryDirectory(prefix='ai_context_doc_') as tmp_dir:
            out_path = Path(tmp_dir) / (path.stem + '.docx')
            word = win32com.client.Dispatch('Word.Application')
            word.Visible = False
            word.DisplayAlerts = 0
            document = word.Documents.Open(str(path), ReadOnly=True)
            document.SaveAs2(str(out_path), FileFormat=16)  # wdFormatXMLDocument
            document.Close(False)
            result = read_docx_file(out_path, ctx)
            result.meta['converter'] = 'word_com'
            return result
    except Exception as e:
        return ExtractResult(status='error', reason=f"Word COM 変換エラー: {e}")
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
