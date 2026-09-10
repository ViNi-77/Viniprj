"""v3: Office文書に埋め込まれた Office ファイル（OLEオブジェクト）の抽出.

PowerPoint や Word に「オブジェクトの挿入」で貼り付けられた Excel は、
見た目は表でも python-pptx / python-docx からは本文として取り出せない。
実体は zip 内の `<prefix>/embeddings/` に**元ファイルのまま**格納されて
いるため、zip を直接開いて取り出し、通常の抽出器へ流す。

実運用のレビューで「週報PPTXに貼られた埋め込みExcelの中身が拾えない」
という報告を受けて追加した機能。

古い形式の埋め込み（oleObject*.bin = OLE複合ドキュメント）は素直に
取り出せないため、「埋め込みあり・抽出不可」として名前だけ記録する。
"""
from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

# 埋め込みが格納される場所（pptx / docx / xlsx 共通の慣習）
EMBED_DIR_MARKER = '/embeddings/'

# そのまま既存抽出器に流せる形式
EXTRACTABLE_SUFFIXES = ('.xlsx', '.xlsm', '.docx', '.pptx', '.pptm')

MAX_EMBEDDED_FILES = 20
MAX_EMBEDDED_BYTES = 20 * 1024 * 1024  # 1件あたり


def _iter_embedded_entries(zf: zipfile.ZipFile):
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = info.filename.replace('\\', '/')
        if EMBED_DIR_MARKER not in name:
            continue
        yield info, name


def extract_embedded_documents(path: Path, ctx) -> tuple[str, dict]:
    """埋め込みOfficeファイルの本文を抽出する。

    戻り値: (本文テキスト, meta)
        meta = {'embedded_extracted': n, 'embedded_unreadable': m}
    抽出できるものが無ければ ('', {}) を返す。
    """
    # 循環インポート回避のため実行時に取得
    from . import extract as dispatch

    lines: list[str] = []
    extracted = 0
    unreadable: list[str] = []

    try:
        if not zipfile.is_zipfile(path):
            return '', {}

        with zipfile.ZipFile(path) as zf:
            entries = list(_iter_embedded_entries(zf))
            if not entries:
                return '', {}

            with tempfile.TemporaryDirectory(prefix='ai_context_embed_') as tmp_dir:
                for info, name in entries:
                    if ctx.stopped():
                        break
                    if extracted >= MAX_EMBEDDED_FILES:
                        lines.append(f"...（埋め込みファイルは{MAX_EMBEDDED_FILES}件で抽出打ち切り）")
                        break

                    inner_name = Path(name).name
                    suffix = Path(inner_name).suffix.lower()

                    if suffix not in EXTRACTABLE_SUFFIXES:
                        # oleObject1.bin などの旧形式。存在だけ記録する
                        unreadable.append(inner_name)
                        continue

                    if info.file_size > MAX_EMBEDDED_BYTES:
                        unreadable.append(inner_name)
                        continue

                    temp_path = Path(tmp_dir) / f"{extracted:03d}_{inner_name}"
                    with zf.open(info) as src, open(temp_path, 'wb') as dst:
                        shutil.copyfileobj(src, dst)

                    inner = dispatch(temp_path, ctx)
                    if not inner.text.strip():
                        unreadable.append(inner_name)
                        continue

                    extracted += 1
                    lines.append(f"## 埋め込みファイル {extracted}: {inner_name}")
                    lines.append(inner.text)
                    lines.append('')
    except Exception:
        return '', {}

    if unreadable:
        lines.append('## 抽出できなかった埋め込みファイル')
        for name in unreadable:
            lines.append(f"- {name}（旧形式または非対応。元ファイルを参照）")

    if not lines:
        return '', {}

    meta = {}
    if extracted:
        meta['embedded_extracted'] = extracted
    if unreadable:
        meta['embedded_unreadable'] = len(unreadable)
    return '\n'.join(lines), meta
