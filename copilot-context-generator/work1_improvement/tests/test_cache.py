"""差分キャッシュのテスト（改善①）."""
from __future__ import annotations

from contextgen.cache import ExtractCache
from contextgen.extractors import ExtractResult


def fake_now():
    return '2026-01-01 00:00:00'


def test_cache_hit_and_miss(tmp_path):
    db = tmp_path / 'cache.db'
    with ExtractCache(db, fake_now) as cache:
        cache.begin_run()
        assert cache.get(tmp_path / 'a.txt', 10, 1.0) is None
        cache.put(tmp_path / 'a.txt', 10, 1.0, ExtractResult(text='hello', status='ok'))
        hit = cache.get(tmp_path / 'a.txt', 10, 1.0)
        assert hit is not None and hit.text == 'hello'
        # サイズ・mtime が変わればミス
        assert cache.get(tmp_path / 'a.txt', 11, 1.0) is None
        assert cache.get(tmp_path / 'a.txt', 10, 2.0) is None


def test_cache_persists_across_open(tmp_path):
    db = tmp_path / 'cache.db'
    with ExtractCache(db, fake_now) as cache:
        cache.begin_run()
        cache.put(tmp_path / 'a.txt', 10, 1.0, ExtractResult(text='v1', status='ok'))
    with ExtractCache(db, fake_now) as cache:
        cache.begin_run()
        hit = cache.get(tmp_path / 'a.txt', 10, 1.0)
        assert hit is not None and hit.text == 'v1'


def test_diff_added_changed_removed(tmp_path):
    db = tmp_path / 'cache.db'
    with ExtractCache(db, fake_now) as cache:
        cache.begin_run()
        cache.record_inventory([('a.txt', 10, 1.0), ('b.txt', 20, 1.0)])
        diff = cache.diff_from_previous()
        assert not diff.has_previous

    with ExtractCache(db, fake_now) as cache:
        cache.begin_run()
        cache.record_inventory([('a.txt', 10, 2.0), ('c.txt', 5, 1.0)])
        diff = cache.diff_from_previous()
        assert diff.has_previous
        assert diff.changed == ['a.txt']
        assert diff.added == ['c.txt']
        assert diff.removed == ['b.txt']


def test_cleanup_drops_stale_cache_rows(tmp_path):
    db = tmp_path / 'cache.db'
    with ExtractCache(db, fake_now) as cache:
        cache.begin_run()
        cache.put(tmp_path / 'gone.txt', 1, 1.0, ExtractResult(text='x', status='ok'))
        cache.put(tmp_path / 'kept.txt', 2, 1.0, ExtractResult(text='y', status='ok'))
        cache.record_inventory([(str(tmp_path / 'kept.txt'), 2, 1.0)])
        cache.cleanup()
    with ExtractCache(db, fake_now) as cache:
        cache.begin_run()
        assert cache.get(tmp_path / 'gone.txt', 1, 1.0) is None
        assert cache.get(tmp_path / 'kept.txt', 2, 1.0) is not None
