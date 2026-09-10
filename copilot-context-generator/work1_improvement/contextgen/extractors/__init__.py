"""テキスト抽出器: 拡張子ディスパッチとステータス付き結果.

改善②: すべての抽出器が ExtractResult(text, status, reason) を返し、
「抽出失敗」と「本文なし」を区別できるようにする。
status:
    ok               本文を抽出できた
    partial          一部の構成単位だけ抽出できた（v3）
    empty            正常に解析できたが本文が空
    needs_ocr        PDF にテキスト層がない（OCR 候補）
    needs_conversion .doc で変換手段がない
    protected        パスワード保護と推定
    unsupported      対応形式でない
    error            解析中に例外
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from ..config import RunConfig


@dataclass
class ExtractResult:
    text: str = ''
    status: str = 'ok'
    reason: str = ''
    meta: dict = field(default_factory=dict)
    # v3 柱1: 構成単位（ページ/シート/スライド/エントリ）ごとの抽出状況
    units_total: int = 0
    units_ok: int = 0
    unit_failures: list = field(default_factory=list)  # [(単位名, 理由)]

    @property
    def ok(self) -> bool:
        return self.status == 'ok'

    @property
    def coverage(self) -> float | None:
        """抽出できた構成単位の割合。単位を数えていない場合は None."""
        if not self.units_total:
            return None
        return self.units_ok / self.units_total


class UnitCollector:
    """v3 柱1: 構成単位ごとに保護しながらテキストを集める。

    v2 までは抽出器全体を1つの try/except で包んでいたため、
    「1ページの解析失敗＝その文書が丸ごと0文字」になっていた
    （Excel/PDF/Word/ZIP すべてで再現を確認）。
    単位ごとに例外を捕まえ、無事な部分は必ず残す。
    """

    def __init__(self):
        self.lines: list[str] = []
        self.total = 0
        self.ok = 0
        self.failures: list[tuple[str, str]] = []

    @contextmanager
    def unit(self, label: str):
        """1つの構成単位の処理を保護する。失敗しても他の単位は続行する."""
        self.total += 1
        try:
            yield self.lines
        except Exception as e:
            self.failures.append((label, str(e)[:200]))
        else:
            self.ok += 1

    def append(self, text: str) -> None:
        self.lines.append(text)

    def build(self, empty_reason: str = '本文が空です', meta: dict | None = None) -> ExtractResult:
        text = '\n'.join(self.lines)
        meta = dict(meta or {})

        if self.failures:
            summary = ' / '.join(f"{label}: {reason}" for label, reason in self.failures[:5])
            if len(self.failures) > 5:
                summary += f" ほか{len(self.failures) - 5}件"
        else:
            summary = ''

        if not text.strip():
            status = 'error' if self.failures and self.ok == 0 else 'empty'
            reason = summary or empty_reason
        elif self.failures:
            status = 'partial'
            reason = f"{self.total}単位中{self.ok}単位を抽出（{summary}）"
        else:
            status = 'ok'
            reason = ''

        return ExtractResult(
            text=text, status=status, reason=reason, meta=meta,
            units_total=self.total, units_ok=self.ok,
            unit_failures=list(self.failures),
        )


@dataclass
class ExtractorContext:
    """抽出器へ渡す実行コンテキスト。"""
    config: RunConfig
    stop_event: threading.Event

    def stopped(self) -> bool:
        return self.stop_event.is_set()


def extract(path: Path, ctx: ExtractorContext) -> ExtractResult:
    """拡張子で抽出器へディスパッチする。"""
    from . import archive, excel, pdfdoc, plain, powerpoint, worddoc

    ext = path.suffix.lower()

    if ext == '.txt':
        return plain.read_text_file(path, ctx)
    if ext == '.docx':
        return worddoc.read_docx_file(path, ctx)
    if ext == '.doc':
        return worddoc.read_doc_file(path, ctx)
    if ext == '.pdf':
        return pdfdoc.read_pdf_file(path, ctx)
    if ext in ('.xlsx', '.xlsm'):
        return excel.read_excel_file(path, ctx)
    if ext in ('.pptx', '.pptm'):
        return powerpoint.read_pptx_file(path, ctx)
    if ext == '.zip':
        return archive.read_zip_file(path, ctx, extract)

    return ExtractResult(status='unsupported', reason=f"対応していない拡張子: {ext}")
