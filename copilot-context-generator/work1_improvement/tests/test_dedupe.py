"""v2.1 F6: 重複・類似文書検出のテスト."""
from __future__ import annotations

import json
import os
import threading

from contextgen.config import RunConfig
from contextgen.dedupe import estimate_jaccard, find_similar_groups, make_signature
from contextgen.events import NullEmitter
from contextgen.worker import run_all

BASE_TEXT = 'アルミ加工ラインの点検手順書。\n' + '\n'.join(
    f"手順{i}: 主軸の状態を確認し、油圧が基準値5MPa以上であることを記録する。工具摩耗のチェックも行う。"
    for i in range(30)
)


def test_identical_texts_similarity_1():
    a, b = make_signature(BASE_TEXT), make_signature(BASE_TEXT)
    assert a.sha256 == b.sha256
    assert estimate_jaccard(a, b) == 1.0


def test_near_identical_above_threshold():
    edited = BASE_TEXT.replace('手順5:', '手順5(改訂):') + '\n末尾に1行追記。'
    a, b = make_signature(BASE_TEXT), make_signature(edited)
    assert a.sha256 != b.sha256
    assert estimate_jaccard(a, b) >= 0.90


def test_different_texts_below_threshold():
    other = '品質会議の月次議事録。不良率の推移と対策について議論した。' * 20
    similarity = estimate_jaccard(make_signature(BASE_TEXT), make_signature(other))
    assert similarity < 0.5


def test_find_similar_groups():
    sigs = [
        make_signature(BASE_TEXT),
        make_signature(BASE_TEXT + '\n追記'),
        make_signature('全く別の内容です。' * 50),
    ]
    groups = find_similar_groups(sigs, threshold=0.9)
    assert groups == [[0, 1]]


def prepare_duplicates(sample_tree):
    old = sample_tree / '設備' / '点検手順_v1.txt'
    new = sample_tree / '設備' / '点検手順_v2.txt'
    old.write_text(BASE_TEXT, encoding='utf-8')
    new.write_text(BASE_TEXT + '\n改訂: 手順31を追加。', encoding='utf-8')
    now = 1_750_000_000
    os.utime(old, (now - 86400, now - 86400))  # v1 は1日古い
    os.utime(new, (now, now))
    return old, new


def run(sample_tree, out, base, **kw):
    config = RunConfig(search_root=sample_tree, context_output_dir=out, base_dir=base, **kw)
    return run_all(config, NullEmitter(), threading.Event())


def test_pipeline_warn_reports_groups(sample_tree, out_dirs):
    out, base = out_dirs
    prepare_duplicates(sample_tree)
    stats = run(sample_tree, out, base, dedupe_mode='warn')
    assert stats.dedupe_groups == 1
    assert stats.dedupe_excluded_files == 0
    report = (out / '_AI_CONTEXT_REPORT.md').read_text(encoding='utf-8')
    assert '類似文書グループ（モード: warn）' in report
    assert '点検手順_v1.txt' in report and '点検手順_v2.txt' in report
    # warn では両方収録される
    records = [json.loads(line) for line in
               (out / '_AI_CONTEXT_DATA.jsonl').read_text(encoding='utf-8').splitlines()]
    names = {r['file_name'] for r in records}
    assert {'点検手順_v1.txt', '点検手順_v2.txt'} <= names


def test_pipeline_exclude_keeps_newest(sample_tree, out_dirs):
    out, base = out_dirs
    prepare_duplicates(sample_tree)
    stats = run(sample_tree, out, base, dedupe_mode='exclude')
    assert stats.dedupe_excluded_files == 1

    records = [json.loads(line) for line in
               (out / '_AI_CONTEXT_DATA.jsonl').read_text(encoding='utf-8').splitlines()]
    names = {r['file_name'] for r in records}
    assert '点検手順_v2.txt' in names       # 新しい方を残置
    assert '点検手順_v1.txt' not in names   # 古い方を除外

    report = (out / '_AI_CONTEXT_REPORT.md').read_text(encoding='utf-8')
    assert '[除外] `設備/点検手順_v1.txt`' in report
    assert '[残置] `設備/点検手順_v2.txt`' in report

    index = (out / 'M365AgentContext_INDEX.txt').read_text(encoding='utf-8')
    assert '## ExcludedFiles' in index
    assert '点検手順_v1.txt → 残置: 設備/点検手順_v2.txt' in index


def test_pipeline_off_mode_no_prepass(sample_tree, out_dirs):
    out, base = out_dirs
    prepare_duplicates(sample_tree)
    stats = run(sample_tree, out, base, dedupe_mode='off')
    assert stats.dedupe_groups == 0
    report = (out / '_AI_CONTEXT_REPORT.md').read_text(encoding='utf-8')
    assert '類似文書グループ' not in report
