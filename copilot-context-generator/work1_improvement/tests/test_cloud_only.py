"""v2.1 F4: Box Drive オンラインオンリー制御のテスト."""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from contextgen import scanner
from contextgen.config import RunConfig
from contextgen.events import NullEmitter
from contextgen.scanner import (
    FILE_ATTRIBUTE_OFFLINE,
    FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS,
    is_cloud_only,
    scan,
)
from contextgen.worker import run_all


def test_is_cloud_only_attributes():
    assert is_cloud_only(SimpleNamespace(st_file_attributes=FILE_ATTRIBUTE_OFFLINE))
    assert is_cloud_only(SimpleNamespace(st_file_attributes=FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS))
    assert not is_cloud_only(SimpleNamespace(st_file_attributes=0x20))  # ARCHIVE のみ
    # macOS/Linux の stat には属性がない → False
    assert not is_cloud_only(SimpleNamespace())


@pytest.fixture
def fake_cloud(monkeypatch):
    """「設備」フォルダ配下のファイルをクラウドのみ扱いにする."""
    def fake_is_cloud_only(st):
        return getattr(st, '_fake_cloud', False)

    original_stat = scanner.os.scandir
    monkeypatch.setattr(scanner, 'is_cloud_only', lambda st: st._fake_cloud)

    class StatWrapper:
        def __init__(self, st, cloud):
            self._st = st
            self._fake_cloud = cloud

        def __getattr__(self, name):
            return getattr(self._st, name)

    real_scandir = scanner.os.scandir

    class EntryWrapper:
        def __init__(self, entry):
            self._entry = entry

        def stat(self, follow_symlinks=True):
            st = self._entry.stat(follow_symlinks=follow_symlinks)
            return StatWrapper(st, '設備' in self._entry.path)

        def __getattr__(self, name):
            return getattr(self._entry, name)

    class ScandirWrapper:
        def __init__(self, path):
            self._it = real_scandir(path)

        def __enter__(self):
            self._it.__enter__()
            return self

        def __exit__(self, *args):
            return self._it.__exit__(*args)

        def __iter__(self):
            return (EntryWrapper(e) for e in self._it)

    monkeypatch.setattr(scanner.os, 'scandir', ScandirWrapper)


def make_config(sample_tree, out, base, mode):
    return RunConfig(search_root=sample_tree, context_output_dir=out, base_dir=base,
                     cloud_only_mode=mode)


def test_skip_mode_excludes_cloud_files(sample_tree, out_dirs, fake_cloud):
    out, base = out_dirs
    config = make_config(sample_tree, out, base, 'skip')
    result = scan(config, NullEmitter(), threading.Event())
    assert result.cloud_only_skipped
    assert all('設備' in p for p in result.cloud_only_skipped)
    assert not any('設備' in str(p) for p in result.files)


def test_warn_mode_includes_but_records(sample_tree, out_dirs, fake_cloud):
    out, base = out_dirs
    config = make_config(sample_tree, out, base, 'warn')
    result = scan(config, NullEmitter(), threading.Event())
    assert result.cloud_only_downloaded
    assert any('設備' in str(p) for p in result.files)


def test_download_mode_is_legacy_behavior(sample_tree, out_dirs, fake_cloud):
    out, base = out_dirs
    config = make_config(sample_tree, out, base, 'download')
    result = scan(config, NullEmitter(), threading.Event())
    assert result.cloud_only_skipped == []
    assert result.cloud_only_downloaded == []
    assert any('設備' in str(p) for p in result.files)


def test_report_lists_cloud_skipped(sample_tree, out_dirs, fake_cloud):
    out, base = out_dirs
    config = make_config(sample_tree, out, base, 'skip')
    run_all(config, NullEmitter(), threading.Event())
    report = (out / '_AI_CONTEXT_REPORT.md').read_text(encoding='utf-8')
    assert 'クラウドのみ（未ダウンロードのためスキップ）' in report
    assert '設備' in report
