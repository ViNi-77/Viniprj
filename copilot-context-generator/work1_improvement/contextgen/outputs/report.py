"""改善②: カバレッジレポート (_AI_CONTEXT_REPORT.md).

抽出結果のステータス内訳・OCR候補・エラー明細・差分・キャッシュ統計を
人間が確認できる形で出力する。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import RunConfig
from ..textutil import format_size

STATUS_LABELS = {
    'ok': '全文抽出',
    'partial': '部分抽出（一部の単位が失敗）',
    'empty': '本文なし',
    'needs_ocr': 'OCR候補（テキスト層なし）',
    'needs_conversion': '要変換（.doc）',
    'protected': 'パスワード保護',
    'unsupported': '対象外形式',
    'dedupe_excluded': '重複のため除外',
    'error': '抽出エラー',
}


@dataclass
class FileOutcome:
    relative_path: str
    extension: str
    size: int
    status: str
    reason: str = ''
    text_length: int = 0
    token_estimate: int = 0
    from_cache: bool = False
    ocr_used: bool = False
    # v3 柱1: 構成単位ごとの抽出状況
    units_total: int = 0
    units_ok: int = 0
    unit_failures: list = field(default_factory=list)
    mtime: float = 0.0  # v3 柱3: 鮮度診断用のファイル更新日時

    @property
    def coverage(self) -> float | None:
        if not self.units_total:
            return None
        return self.units_ok / self.units_total


@dataclass
class CoverageReport:
    outcomes: list[FileOutcome] = field(default_factory=list)
    skipped_temp: list[str] = field(default_factory=list)
    cloud_only_skipped: list[str] = field(default_factory=list)
    cloud_only_downloaded: list[str] = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0
    diff_lines: list[str] = field(default_factory=list)
    sensitive_mode: str = 'off'
    sensitive_findings: list = field(default_factory=list)  # (relative_path, {種類: 件数})
    sensitive_blocked_chunks: int = 0
    dedupe_mode: str = 'off'
    dedupe_groups: list = field(default_factory=list)  # [[(relative, kept, similarity), ...]]

    def add(self, outcome: FileOutcome):
        self.outcomes.append(outcome)

    def by_status(self) -> dict[str, list[FileOutcome]]:
        result: dict[str, list[FileOutcome]] = {}
        for o in self.outcomes:
            result.setdefault(o.status, []).append(o)
        return result


def write_coverage_report(config: RunConfig, report: CoverageReport, generated_at: str) -> None:
    grouped = report.by_status()
    total = len(report.outcomes)

    lines = [
        '# AIコンテキスト抽出レポート',
        '',
        f"- 生成日時: {generated_at}",
        f"- 対象ファイル数: {total}",
        f"- キャッシュ: ヒット {report.cache_hits} / 再抽出 {report.cache_misses}",
        '',
        '## ステータス内訳',
        '',
    ]

    for status, label in STATUS_LABELS.items():
        items = grouped.get(status, [])
        if not items and status not in ('ok',):
            continue
        lines.append(f"- {label}: {len(items)} 件")

    measured = [o for o in report.outcomes if o.units_total]
    if measured:
        total_units = sum(o.units_total for o in measured)
        ok_units = sum(o.units_ok for o in measured)
        rate = ok_units / total_units if total_units else 1.0
        lines.extend([
            '',
            '## 抽出カバレッジ',
            '',
            f"- 構成単位（ページ/シート/スライド/エントリ）: {total_units} 中 {ok_units} を抽出（{rate:.1%}）",
        ])

    partial = grouped.get('partial', [])
    if partial:
        lines.extend(['', '## 部分抽出（本文の一部が欠けています）', ''])
        lines.append('文書は取り込めていますが、以下の単位は解析に失敗しました。')
        for o in partial:
            lines.append(f"- `{o.relative_path}`（{o.units_ok}/{o.units_total} 単位）")
            for label, why in o.unit_failures[:5]:
                lines.append(f"    - {label}: {why}")
            if len(o.unit_failures) > 5:
                lines.append(f"    - …ほか {len(o.unit_failures) - 5} 単位")

    ocr_done = [o for o in report.outcomes if o.ocr_used]
    if ocr_done:
        lines.extend(['', '## OCR実行済み（画像PDFから本文を認識）', ''])
        for o in ocr_done:
            lines.append(f"- `{o.relative_path}` — 抽出 {o.text_length} 文字")

    ocr = grouped.get('needs_ocr', [])
    if ocr:
        lines.extend(['', '## OCR候補（テキスト層のないPDF）', ''])
        lines.append('ocr_mode=auto にすると、対応環境ではOCRで本文化できます。')
        for o in ocr:
            lines.append(f"- `{o.relative_path}` ({format_size(o.size)}) — {o.reason}")

    conv = grouped.get('needs_conversion', [])
    if conv:
        lines.extend(['', '## 要変換（.doc 形式）', ''])
        lines.append('docx 形式へ変換すると本文を収録できます。')
        for o in conv:
            lines.append(f"- `{o.relative_path}` ({format_size(o.size)})")

    protected = grouped.get('protected', [])
    if protected:
        lines.extend(['', '## パスワード保護ファイル', ''])
        for o in protected:
            lines.append(f"- `{o.relative_path}` — {o.reason}")

    errors = grouped.get('error', [])
    if errors:
        lines.extend(['', '## 抽出エラー明細', ''])
        for o in errors:
            lines.append(f"- `{o.relative_path}` — {o.reason}")

    empty = grouped.get('empty', [])
    if empty:
        lines.extend(['', '## 本文なし（正常解析・テキストゼロ）', ''])
        for o in empty:
            lines.append(f"- `{o.relative_path}`")

    if report.skipped_temp:
        lines.extend(['', '## スキップした一時ファイル', ''])
        for p in report.skipped_temp[:100]:
            lines.append(f"- `{p}`")
        if len(report.skipped_temp) > 100:
            lines.append(f"- …ほか {len(report.skipped_temp) - 100} 件")

    if report.cloud_only_skipped:
        lines.extend(['', '## クラウドのみ（未ダウンロードのためスキップ）', ''])
        lines.append('Box Drive で「オフラインで使用可能」にするか、cloud_only_mode を変更すると収録されます。')
        for p in report.cloud_only_skipped[:100]:
            lines.append(f"- `{p}`")
        if len(report.cloud_only_skipped) > 100:
            lines.append(f"- …ほか {len(report.cloud_only_skipped) - 100} 件")

    if report.cloud_only_downloaded:
        lines.extend(['', '## クラウドのみ検知（抽出によりダウンロードが発生）', ''])
        lines.append(f"- 対象: {len(report.cloud_only_downloaded)} 件")

    if report.dedupe_groups:
        lines.extend(['', f"## 類似文書グループ（モード: {report.dedupe_mode}）", ''])
        if report.dedupe_mode == 'warn':
            lines.append('検知のみ行い、すべて収録しています。dedupe_mode=exclude で最新版のみ収録できます。')
        for group in report.dedupe_groups:
            for relative, kept, similarity in group:
                if kept:
                    marker = '残置'
                elif report.dedupe_mode == 'exclude':
                    marker = '除外'
                else:
                    marker = '類似'
                lines.append(f"- [{marker}] `{relative}`（類似度 {similarity:.0%}）")
            lines.append('')

    if report.sensitive_findings or report.sensitive_blocked_chunks:
        lines.extend(['', f"## 機密情報検知（モード: {report.sensitive_mode}）", ''])
        if report.sensitive_mode == 'warn':
            lines.append('検知のみ行い、本文はそのまま収録しています。mask/block モードで自動処理できます。')
        elif report.sensitive_mode == 'mask':
            lines.append('検知箇所を伏字に置換して収録しました。')
        if report.sensitive_blocked_chunks:
            lines.append(f"- 収録から除外したチャンク: {report.sensitive_blocked_chunks} 件")
        for path, kinds in report.sensitive_findings[:200]:
            detail = ', '.join(f"{k}×{v}" for k, v in kinds.items())
            lines.append(f"- `{path}`: {detail}")
        if len(report.sensitive_findings) > 200:
            lines.append(f"- …ほか {len(report.sensitive_findings) - 200} 件")

    if report.diff_lines:
        lines.extend(['', '## 前回実行との差分', ''])
        lines.extend(report.diff_lines)

    config.report_path.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')
