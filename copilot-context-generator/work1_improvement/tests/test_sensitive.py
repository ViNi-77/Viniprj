"""v2.1 F5: 機密情報スキャンのテスト."""
from __future__ import annotations

import json
import threading

from contextgen.config import RunConfig
from contextgen.events import NullEmitter
from contextgen.sensitive import SensitiveScanner
from contextgen.worker import run_all


def make_scanner(tmp_path, dictionary: str | None = None):
    base = tmp_path / 'base'
    base.mkdir(exist_ok=True)
    if dictionary is not None:
        (base / 'sensitive_patterns.txt').write_text(dictionary, encoding='utf-8')
    config = RunConfig(search_root=tmp_path, context_output_dir=tmp_path / 'out', base_dir=base)
    return SensitiveScanner(config)


def test_builtin_patterns(tmp_path):
    scanner = make_scanner(tmp_path)
    findings = scanner.scan(
        '連絡先: 052-123-4567 / mail: tanaka@example.co.jp\n'
        '個人番号 123456789012 を記載しない。\n'
        'カード 4111-1111-1111-1111 は伏せる。'
    )
    assert findings['電話番号'] == 1
    assert findings['メールアドレス'] == 1
    assert findings['マイナンバー疑い'] == 1
    assert findings['クレジットカード番号疑い'] == 1


def test_no_false_positive_on_plain_numbers(tmp_path):
    scanner = make_scanner(tmp_path)
    findings = scanner.scan('図番 A-100 の寸法は 25.01mm、公差は 0.05。ロット 20260514。')
    assert findings == {}


def test_dictionary_literal_and_regex(tmp_path):
    scanner = make_scanner(tmp_path, dictionary='取引先A株式会社\nregex:社外秘|極秘\n# コメント\n')
    findings = scanner.scan('本件は取引先A株式会社との共同開発。資料は社外秘。')
    assert findings['辞書'] == 2


def test_mask(tmp_path):
    scanner = make_scanner(tmp_path)
    masked, findings = scanner.mask('TEL: 052-123-4567 まで')
    assert '052-123-4567' not in masked
    assert '＜伏字＞' in masked
    assert findings['電話番号'] == 1


def run_pipeline(sample_tree, out, base, mode):
    config = RunConfig(search_root=sample_tree, context_output_dir=out, base_dir=base,
                       sensitive_scan=mode)
    return run_all(config, NullEmitter(), threading.Event())


def read_records(out):
    return [json.loads(line) for line in
            (out / '_AI_CONTEXT_DATA.jsonl').read_text(encoding='utf-8').splitlines()]


def test_pipeline_warn_reports_but_keeps_text(sample_tree, out_dirs):
    out, base = out_dirs
    (sample_tree / '連絡網.txt').write_text('緊急連絡先: 052-123-4567', encoding='utf-8')
    run_pipeline(sample_tree, out, base, 'warn')
    report = (out / '_AI_CONTEXT_REPORT.md').read_text(encoding='utf-8')
    assert '機密情報検知（モード: warn）' in report
    assert '連絡網.txt' in report and '電話番号×1' in report
    records = read_records(out)
    target = [r for r in records if r['file_name'] == '連絡網.txt']
    assert '052-123-4567' in target[0]['text']  # warn は本文を変えない


def test_pipeline_mask_replaces_text(sample_tree, out_dirs):
    out, base = out_dirs
    (sample_tree / '連絡網.txt').write_text('緊急連絡先: 052-123-4567', encoding='utf-8')
    run_pipeline(sample_tree, out, base, 'mask')
    records = read_records(out)
    target = [r for r in records if r['file_name'] == '連絡網.txt']
    assert '052-123-4567' not in target[0]['text']
    assert '＜伏字＞' in target[0]['text']
    # M365 パッケージにも値が出ない
    body = (out / 'M365AgentContext_001.txt').read_text(encoding='utf-8')
    assert '052-123-4567' not in body


def test_pipeline_block_excludes_chunk(sample_tree, out_dirs):
    out, base = out_dirs
    (sample_tree / '連絡網.txt').write_text('緊急連絡先: 052-123-4567', encoding='utf-8')
    stats = run_pipeline(sample_tree, out, base, 'block')
    assert stats.sensitive_blocked_chunks >= 1
    records = read_records(out)
    assert not any(r['file_name'] == '連絡網.txt' for r in records)
    body = (out / 'M365AgentContext_001.txt').read_text(encoding='utf-8')
    assert '052-123-4567' not in body
    report = (out / '_AI_CONTEXT_REPORT.md').read_text(encoding='utf-8')
    assert '収録から除外したチャンク: 1 件' in report


def test_pipeline_off_mode(sample_tree, out_dirs):
    out, base = out_dirs
    (sample_tree / '連絡網.txt').write_text('緊急連絡先: 052-123-4567', encoding='utf-8')
    run_pipeline(sample_tree, out, base, 'off')
    report = (out / '_AI_CONTEXT_REPORT.md').read_text(encoding='utf-8')
    assert '機密情報検知' not in report
