"""v3 柱3: 文書健康診断のテスト."""
from __future__ import annotations

import os
import threading
import time

from contextgen.config import RunConfig
from contextgen.events import NullEmitter
from contextgen.outputs.health import HEALTH_FILENAME, HealthScore, compute_score
from contextgen.outputs.report import CoverageReport, FileOutcome
from contextgen.pipeline import PipelineStats
from contextgen.worker import run_all


def make_outcome(status='ok', mtime=None, **kw):
    return FileOutcome(relative_path=kw.get('path', 'a.txt'), extension='.txt',
                       size=100, status=status, mtime=mtime or time.time())


def test_score_is_perfect_for_clean_folder():
    report = CoverageReport(outcomes=[make_outcome() for _ in range(5)])
    score = compute_score(report, PipelineStats(), {'1年以内': 5, '不明': 0})
    assert score.total == 100
    assert score.grade.startswith('A')


def test_unreadable_documents_lower_the_score():
    report = CoverageReport(outcomes=[
        make_outcome('ok'), make_outcome('needs_ocr'),
        make_outcome('needs_conversion'), make_outcome('error'),
    ])
    score = compute_score(report, PipelineStats(), {'1年以内': 4, '不明': 0})
    assert score.readable == 10  # 4件中1件だけ読める
    assert score.total < 100


def test_overflow_and_sensitive_lower_the_score():
    report = CoverageReport(outcomes=[make_outcome()],
                            sensitive_findings=[('a.txt', {'電話番号': 1})])
    stats = PipelineStats(overflow_count=5)
    score = compute_score(report, stats, {'1年以内': 1, '不明': 0})
    assert score.capacity == 0
    assert score.safety < 10


def test_stale_documents_lower_freshness():
    report = CoverageReport(outcomes=[make_outcome() for _ in range(10)])
    score = compute_score(report, PipelineStats(),
                          {'1年以内': 2, '1〜3年': 0, '3年以上': 8, '不明': 0})
    assert score.freshness < 10


def test_grades():
    assert HealthScore(readable=40, freshness=20, uniqueness=15,
                       capacity=15, safety=10).grade.startswith('A')
    assert HealthScore(readable=20, freshness=10, uniqueness=8,
                       capacity=0, safety=4).grade.startswith('D')


def test_health_report_is_written_and_actionable(sample_tree, out_dirs):
    out, base = out_dirs

    # 3年以上更新されていない文書を用意する
    old = time.time() - 5 * 365 * 24 * 3600
    os.utime(sample_tree / 'メモ.txt', (old, old))

    run_all(RunConfig(search_root=sample_tree, context_output_dir=out, base_dir=base),
            NullEmitter(), threading.Event())

    path = out / HEALTH_FILENAME
    assert path.exists()

    content = path.read_text(encoding='utf-8')
    assert '# ナレッジ健康診断' in content
    assert '総合スコア' in content
    assert 'AIが読める割合' in content
    assert '鮮度（ファイル更新日）' in content
    assert 'まず手を付けるとよいこと' in content
    # サンプルには画像PDFがあるので OCR の指摘が出るはず
    assert 'OCR' in content


def test_health_report_disabled_in_legacy(sample_tree, out_dirs):
    out, base = out_dirs
    config = RunConfig(search_root=sample_tree, context_output_dir=out, base_dir=base).legacy()
    run_all(config, NullEmitter(), threading.Event())
    assert not (out / HEALTH_FILENAME).exists()
