"""ZIP アーカイブ抽出.

原本と同一のロジック・制限（300件 / 1エントリ50MB / 合計300MB）と整形。
"""
from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

from . import ExtractResult, ExtractorContext, UnitCollector
from ..config import (
    MAX_ZIP_ENTRY_BYTES,
    MAX_ZIP_FILES,
    MAX_ZIP_TOTAL_BYTES,
    ZIP_READABLE_EXTENSIONS,
)
from ..textutil import clean_filename, format_size, normalize_text


def read_zip_file(path: Path, ctx: ExtractorContext, dispatch) -> ExtractResult:
    # ZIP自体を開けない場合は全体の失敗として扱う
    try:
        if not zipfile.is_zipfile(path):
            return ExtractResult(status='error', reason='zip 形式ではありません')
        zf = zipfile.ZipFile(path)
    except Exception as e:
        return ExtractResult(status='error', reason=f"ZIP解析エラー: {e}")

    collector = UnitCollector()
    collector.append(f"# ZIP: {path.name}")
    read_count = 0
    total_bytes = 0
    inner_errors = 0

    try:
        with zf, tempfile.TemporaryDirectory(prefix='ai_context_zip_') as tmp_dir:
            for info in sorted(zf.infolist(), key=lambda item: item.filename.lower()):
                if ctx.stopped():
                    break

                if info.is_dir():
                    continue

                inner_name = info.filename.replace('\\', '/')
                inner_path = Path(inner_name)

                if not inner_path.name:
                    continue

                if inner_path.name.startswith('_AI_CONTEXT_'):
                    continue

                ext = inner_path.suffix.lower()
                if ext not in ZIP_READABLE_EXTENSIONS:
                    continue

                if read_count >= MAX_ZIP_FILES:
                    collector.append(f"...（ZIP内ファイルは{MAX_ZIP_FILES}件で抽出打ち切り）")
                    break

                if info.file_size > MAX_ZIP_ENTRY_BYTES:
                    collector.append(f"## ZIP内ファイル: {inner_name}")
                    collector.append(f"...（{format_size(info.file_size)}のため抽出スキップ）")
                    continue

                if total_bytes + info.file_size > MAX_ZIP_TOTAL_BYTES:
                    collector.append(
                        f"...（ZIP内の合計抽出サイズが{format_size(MAX_ZIP_TOTAL_BYTES)}を超えるため抽出打ち切り）"
                    )
                    break

                read_count += 1
                total_bytes += info.file_size

                # v3 柱1: エントリ単位で保護し、1件の失敗で ZIP 全体を失わない
                with collector.unit(f"ZIP内 {inner_name}"):
                    temp_name = f"{read_count:04d}_{clean_filename(inner_path.name)}"
                    temp_path = Path(tmp_dir) / temp_name

                    with zf.open(info) as src, open(temp_path, 'wb') as dst:
                        shutil.copyfileobj(src, dst)

                    inner_result = dispatch(temp_path, ctx)
                    if inner_result.status == 'error':
                        inner_errors += 1
                    inner_text = normalize_text(inner_result.text)

                    collector.append(f"## ZIP内ファイル {read_count}: {inner_name}")
                    collector.append(f"- 種別: `{ext}`")
                    collector.append(f"- サイズ: {format_size(info.file_size)}")
                    collector.append('')
                    collector.append(inner_text or ' 本文抽出不可。ZIP内ファイル名・パス・拡張子を参照。'.strip())
                    collector.append('')
    except Exception as e:
        collector.failures.append(('ZIP全体', str(e)[:200]))

    if read_count == 0:
        collector.append('対応形式のファイルはZIP内に見つかりませんでした。')

    meta = {'zip_entries_read': read_count, 'zip_inner_errors': inner_errors}
    result = collector.build(empty_reason='対応形式のファイルがZIP内にありません', meta=meta)
    if read_count == 0 and result.status == 'ok':
        result.status = 'empty'
        result.reason = '対応形式のファイルがZIP内にありません'
    return result
