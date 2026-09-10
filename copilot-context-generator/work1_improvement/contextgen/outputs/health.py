"""v3 柱3: 文書健康診断 (_AI_CONTEXT_HEALTH.md).

フォルダ全体の状態を1枚にまとめる。
「AIを導入する前に、まず自部署のナレッジを診断する」ための入口で、
経営層・情シスに見せる想定。

すべて既存の集計結果（抽出ステータス・カバレッジ・重複・機密・上限あふれ）
から作るため、追加の解析コストはほぼゼロ。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..config import M365_CONTEXT_MAX_BODY_FILES, RunConfig
from ..textutil import format_size

HEALTH_FILENAME = '_AI_CONTEXT_HEALTH.md'

# AIが本文を読めているとみなすステータス
READABLE_STATUSES = ('ok', 'partial')
STALE_YEARS = 3


@dataclass
class HealthScore:
    readable: int = 0        # 40点: AIが読める割合
    freshness: int = 0       # 20点: 3年以内に更新された割合
    uniqueness: int = 0      # 15点: 重複していない割合
    capacity: int = 0        # 15点: 20ファイル上限に収まっているか
    safety: int = 0          # 10点: 機密検知が無いか

    @property
    def total(self) -> int:
        return self.readable + self.freshness + self.uniqueness + self.capacity + self.safety

    @property
    def grade(self) -> str:
        total = self.total
        if total >= 85:
            return 'A（良好）'
        if total >= 70:
            return 'B（おおむね良好）'
        if total >= 50:
            return 'C（要改善）'
        return 'D（要対応）'


def _age_buckets(outcomes, today: datetime) -> dict[str, int]:
    buckets = {'1年以内': 0, '1〜3年': 0, '3年以上': 0, '不明': 0}
    for outcome in outcomes:
        if not outcome.mtime:
            buckets['不明'] += 1
            continue
        years = (today - datetime.fromtimestamp(outcome.mtime)).days / 365.25
        if years < 1:
            buckets['1年以内'] += 1
        elif years < STALE_YEARS:
            buckets['1〜3年'] += 1
        else:
            buckets['3年以上'] += 1
    return buckets


def compute_score(report, stats, buckets: dict[str, int]) -> HealthScore:
    outcomes = report.outcomes
    total = len(outcomes) or 1

    readable = sum(1 for o in outcomes if o.status in READABLE_STATUSES)
    score = HealthScore()
    score.readable = round(40 * readable / total)

    dated = total - buckets.get('不明', 0)
    if dated > 0:
        fresh = buckets.get('1年以内', 0) + buckets.get('1〜3年', 0)
        score.freshness = round(20 * fresh / dated)
    else:
        score.freshness = 20

    duplicated = sum(len(group) - 1 for group in report.dedupe_groups)
    score.uniqueness = round(15 * max(0.0, 1 - duplicated / total))

    score.capacity = 0 if stats.overflow_count else 15
    score.safety = 10 if not report.sensitive_findings else 4
    return score


def write_health_report(config: RunConfig, report, stats, generated_at: str,
                        today: datetime | None = None):
    today = today or datetime.now()
    outcomes = report.outcomes
    total = len(outcomes)
    if total == 0:
        return None

    grouped = report.by_status()
    buckets = _age_buckets(outcomes, today)
    score = compute_score(report, stats, buckets)

    readable = sum(1 for o in outcomes if o.status in READABLE_STATUSES)
    unreadable = total - readable
    total_bytes = sum(o.size for o in outcomes)

    lines = [
        '# ナレッジ健康診断',
        '',
        f"- 診断日時: {generated_at}",
        f"- 対象フォルダ: `{config.search_root}`",
        f"- 対象文書: {total} 件 / {format_size(total_bytes)}",
        '',
        f"## 総合スコア: {score.total} / 100　{score.grade}",
        '',
        '| 観点 | 配点 | 得点 |',
        '|---|---|---|',
        f"| AIが読める割合 | 40 | {score.readable} |",
        f"| 鮮度（3年以内） | 20 | {score.freshness} |",
        f"| 重複の少なさ | 15 | {score.uniqueness} |",
        f"| 上限内に収まっている | 15 | {score.capacity} |",
        f"| 機密リスクの低さ | 10 | {score.safety} |",
        '',
        '## AIが読める割合',
        '',
        f"- 読める: {readable} 件（{readable / total:.0%}）",
        f"- 読めない: {unreadable} 件",
    ]

    for status, label in (('needs_ocr', 'OCR候補（スキャンPDF）'),
                          ('needs_conversion', '要変換（.doc）'),
                          ('protected', 'パスワード保護'),
                          ('error', '抽出エラー'),
                          ('empty', '本文なし')):
        count = len(grouped.get(status, []))
        if count:
            lines.append(f"    - {label}: {count} 件")

    if unreadable:
        lines.append('')
        lines.append('> 読めない文書は、AIから見ると**存在しないのと同じ**です。')

    measured = [o for o in outcomes if o.units_total]
    if measured:
        total_units = sum(o.units_total for o in measured)
        ok_units = sum(o.units_ok for o in measured)
        lines.extend([
            '',
            f"- 構成単位のカバレッジ: {total_units} 中 {ok_units}（{ok_units / total_units:.0%}）",
        ])

    lines.extend(['', '## 鮮度（ファイル更新日）', ''])
    for label, count in buckets.items():
        if count:
            mark = '  ⚠' if label == '3年以上' and count / total >= 0.3 else ''
            lines.append(f"- {label}: {count} 件（{count / total:.0%}）{mark}")

    lines.extend(['', '## 重複', ''])
    if report.dedupe_groups:
        duplicated = sum(len(group) - 1 for group in report.dedupe_groups)
        lines.append(f"- 類似グループ: {len(report.dedupe_groups)} 組（重複側 {duplicated} 件）")
        lines.append('- `--dedupe exclude` で最新版のみを収録できます')
    else:
        lines.append('- 重複は検出されませんでした')

    lines.extend(['', '## 機密情報', ''])
    if report.sensitive_findings:
        lines.append(f"- 検知: {len(report.sensitive_findings)} 件（詳細は抽出レポート）")
        lines.append('- `--sensitive mask` で伏字化、`block` で収録除外ができます')
    else:
        lines.append(f"- 検知なし（モード: {report.sensitive_mode}）")

    lines.extend(['', '## Copilotナレッジの容量', ''])
    parts = sum(stats.m365_parts_needed.values()) if stats.m365_parts_needed else 0
    lines.append(f"- 本文ファイル: {parts} / {M365_CONTEXT_MAX_BODY_FILES}")
    if stats.overflow_count:
        lines.append(f"- ⚠ 上限あふれ: {stats.overflow_count} チャンクが未収録")
        lines.append('- `--sort mtime_desc` / `--priority-folder` / `--split-by-subfolder` を検討してください')
    else:
        lines.append('- 上限に収まっています')

    lines.extend(['', '## まず手を付けるとよいこと', ''])
    todo = []
    if grouped.get('needs_ocr'):
        todo.append(f"- スキャンPDF {len(grouped['needs_ocr'])} 件に OCR を有効化する（`--ocr auto`）")
    if grouped.get('needs_conversion'):
        todo.append(f"- .doc 形式 {len(grouped['needs_conversion'])} 件を .docx へ変換する")
    if buckets.get('3年以上', 0) / total >= 0.3:
        todo.append(f"- 3年以上更新されていない {buckets['3年以上']} 件の要否を棚卸しする")
    if report.dedupe_groups:
        todo.append('- 類似文書を整理し、最新版のみを残す')
    if stats.overflow_count:
        todo.append('- 収録対象を絞るか、サブフォルダ別にエージェントを分ける')
    lines.extend(todo or ['- 大きな問題は見つかりませんでした'])

    path = config.context_output_dir / HEALTH_FILENAME
    path.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')
    return path
