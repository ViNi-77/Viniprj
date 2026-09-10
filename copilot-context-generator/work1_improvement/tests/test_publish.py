"""v3 柱0: 原子的公開の回帰テスト.

夜間バッチ運用で「壊れた新版が既存ナレッジを上書きする」事故を防ぐ。
v2 では中断・空フォルダのいずれでも既存ナレッジが破壊されていた。
"""
from __future__ import annotations

import threading

from contextgen.config import RunConfig
from contextgen.events import NullEmitter
from contextgen.publish import HOLD_NOTICE_FILENAME, STAGING_PREFIX, published_chunk_count
from contextgen.worker import run_all

INDEX = 'M365AgentContext_INDEX.txt'


def make_config(sample_tree, out, base, **kw):
    return RunConfig(search_root=sample_tree, context_output_dir=out, base_dir=base, **kw)


def run(config):
    return run_all(config, NullEmitter(), threading.Event())


def chunk_count(out):
    return published_chunk_count(out) or 0


class StopAfterNFiles(NullEmitter):
    """N件処理した時点で停止要求を出すエミッタ."""

    def __init__(self, event, n=2):
        super().__init__()
        self.event = event
        self.n = n
        self.seen = 0

    def emit(self, event_type, data):
        if event_type == 'current' and 'AIコンテキスト生成中' in str(data):
            self.seen += 1
            if self.seen >= self.n:
                self.event.set()


def test_first_run_publishes(sample_tree, out_dirs):
    out, base = out_dirs
    stats = run(make_config(sample_tree, out, base))
    assert stats.published
    assert (out / INDEX).exists()
    assert chunk_count(out) > 0


def test_interruption_preserves_existing_knowledge(sample_tree, out_dirs):
    """中断しても既存ナレッジが部分内容で上書きされないこと（B1）."""
    out, base = out_dirs
    run(make_config(sample_tree, out, base))
    before = chunk_count(out)
    assert before > 2

    event = threading.Event()
    stats = run_all(make_config(sample_tree, out, base), StopAfterNFiles(event), event)

    assert stats.published is False
    assert '中断' in stats.publish_hold_reason
    assert chunk_count(out) == before, '中断で既存ナレッジが破壊された'


def test_empty_source_preserves_existing_knowledge(sample_tree, out_dirs, tmp_path):
    """参照元が空でも既存ナレッジが消えないこと（B2 / Box未同期を想定）."""
    out, base = out_dirs
    run(make_config(sample_tree, out, base))
    before = chunk_count(out)

    empty = tmp_path / 'empty_source'
    empty.mkdir()
    stats = run(make_config(empty, out, base))

    assert stats.published is False
    assert chunk_count(out) == before, '空フォルダで既存ナレッジが消えた'
    assert (out / HOLD_NOTICE_FILENAME).exists(), '保留の通知が出ていない'


def test_large_drop_is_held(sample_tree, out_dirs):
    """収録量が前回比で大幅に減った場合は公開を保留すること."""
    out, base = out_dirs
    run(make_config(sample_tree, out, base))
    before = chunk_count(out)

    for path in list(sample_tree.rglob('*')):
        if path.is_file() and path.suffix.lower() in ('.txt', '.pdf', '.docx', '.xlsx', '.pptx', '.zip'):
            path.unlink()

    stats = run(make_config(sample_tree, out, base))
    assert stats.published is False
    assert chunk_count(out) == before


def test_force_publish_overrides_hold(sample_tree, out_dirs, tmp_path):
    """意図した削除は --force-publish で反映でき、保留通知も消えること."""
    out, base = out_dirs
    run(make_config(sample_tree, out, base))
    before = chunk_count(out)

    empty = tmp_path / 'empty_source2'
    empty.mkdir()
    run(make_config(empty, out, base))
    assert (out / HOLD_NOTICE_FILENAME).exists()

    stats = run(make_config(sample_tree, out, base, force_publish=True))
    assert stats.published
    assert chunk_count(out) == before
    assert not (out / HOLD_NOTICE_FILENAME).exists(), '公開成功時に保留通知が消えていない'


def test_no_staging_left_behind(sample_tree, out_dirs, tmp_path):
    """成功時も保留時もステージングが残らないこと."""
    out, base = out_dirs
    run(make_config(sample_tree, out, base))
    assert not list(out.glob(f"{STAGING_PREFIX}*"))

    empty = tmp_path / 'empty_source3'
    empty.mkdir()
    run(make_config(empty, out, base))
    assert not list(out.glob(f"{STAGING_PREFIX}*"))


def test_held_run_does_not_pollute_archive(sample_tree, out_dirs, tmp_path):
    """保留された実行がArchiveに壊れた版を残さないこと."""
    out, base = out_dirs
    run(make_config(sample_tree, out, base))
    archive = out / 'Archive'
    before = len(list(archive.glob('*.txt')))

    empty = tmp_path / 'empty_source4'
    empty.mkdir()
    run(make_config(empty, out, base))

    assert len(list(archive.glob('*.txt'))) == before, 'Archiveに保留版が混入した'


def test_staging_path_does_not_leak_into_content(sample_tree, out_dirs):
    """生成物の本文にステージングの内部パスが混入しないこと."""
    out, base = out_dirs
    run(make_config(sample_tree, out, base))
    for path in out.glob('*.md'):
        assert STAGING_PREFIX not in path.read_text(encoding='utf-8')
    for path in out.glob('M365AgentContext*.txt'):
        assert STAGING_PREFIX not in path.read_text(encoding='utf-8')


def test_legacy_mode_always_publishes(sample_tree, out_dirs, tmp_path):
    """原本互換モードは従来どおり常に上書きすること."""
    out, base = out_dirs
    config = make_config(sample_tree, out, base).legacy()
    run(config)
    assert (out / INDEX).exists()

    empty = tmp_path / 'empty_legacy'
    empty.mkdir()
    stats = run(make_config(empty, out, base).legacy())
    assert stats.published, 'legacy は原本と同じく常に公開する想定'
