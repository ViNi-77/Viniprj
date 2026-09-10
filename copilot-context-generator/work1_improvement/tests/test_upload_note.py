"""v2.1 F1: 再アップロード指示書のテスト."""
from __future__ import annotations

import threading

from contextgen.config import RunConfig
from contextgen.events import NullEmitter
from contextgen.worker import run_all

NOTE = '_AI_CONTEXT_UPLOAD.md'


def run(sample_tree, out, base, **kw):
    config = RunConfig(search_root=sample_tree, context_output_dir=out, base_dir=base, **kw)
    return run_all(config, NullEmitter(), threading.Event())


def test_first_run_all_new(sample_tree, out_dirs):
    out, base = out_dirs
    stats = run(sample_tree, out, base)
    note = (out / NOTE).read_text(encoding='utf-8')
    assert '（新規）' in note
    assert 'M365AgentContext_INDEX.txt' in note
    assert len(stats.upload_needed) == len(stats.m365_fixed_paths[''])


def test_second_run_no_reupload_needed(sample_tree, out_dirs):
    out, base = out_dirs
    run(sample_tree, out, base)
    stats = run(sample_tree, out, base)
    # 内容不変（生成時刻のみ更新）→ 全ファイル変更なし
    assert stats.upload_needed == []
    note = (out / NOTE).read_text(encoding='utf-8')
    assert '要再アップロード（0件）' in note
    assert 'ナレッジは最新の状態です' in note


def test_source_change_marks_affected_files(sample_tree, out_dirs):
    out, base = out_dirs
    run(sample_tree, out, base)
    (sample_tree / 'メモ.txt').write_text('大幅に更新された内容。\n', encoding='utf-8')
    stats = run(sample_tree, out, base)
    # サンプルは1パート構成: INDEX と 001 の両方が更新扱い
    assert 'M365AgentContext_001.txt' in stats.upload_needed
    assert 'M365AgentContext_INDEX.txt' in stats.upload_needed
    note = (out / NOTE).read_text(encoding='utf-8')
    assert '（内容更新）' in note


def test_removed_files_listed(sample_tree, out_dirs):
    out, base = out_dirs
    # サブフォルダ分割で複数パッケージ → 通常モードに戻すと削除が発生
    run(sample_tree, out, base, split_by_subfolder=True)
    stats = run(sample_tree, out, base)
    assert any(name.startswith('M365AgentContext_設備') for name in stats.upload_removed)
    note = (out / NOTE).read_text(encoding='utf-8')
    assert 'ナレッジからも削除してください' in note


def test_legacy_mode_writes_no_note(sample_tree, out_dirs):
    out, base = out_dirs
    config = RunConfig(search_root=sample_tree, context_output_dir=out, base_dir=base).legacy()
    run_all(config, NullEmitter(), threading.Event())
    assert not (out / NOTE).exists()
