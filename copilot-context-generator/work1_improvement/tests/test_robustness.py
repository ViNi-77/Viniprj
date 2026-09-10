"""v3: 実行の頑健性に関する回帰テスト（B4 / B5 / B6）."""
from __future__ import annotations

import json
import threading
import time

from contextgen.config import RunConfig
from contextgen.events import NullEmitter
from contextgen.worker import run_all


def make_config(sample_tree, out, base, **kw):
    return RunConfig(search_root=sample_tree, context_output_dir=out, base_dir=base, **kw)


def run(config):
    return run_all(config, NullEmitter(), threading.Event())


def read_records(out):
    text = (out / '_AI_CONTEXT_DATA.jsonl').read_text(encoding='utf-8')
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# ---- B4: 重複検出のプリパスで二重抽出しないこと ----

def count_extractions(monkeypatch):
    import contextgen.pipeline as pipeline

    original = pipeline.extract
    calls = {'n': 0}

    def counting(path, ctx):
        calls['n'] += 1
        return original(path, ctx)

    monkeypatch.setattr(pipeline, 'extract', counting)
    return calls


def test_no_double_extraction_with_cache(sample_tree, out_dirs, monkeypatch):
    out, base = out_dirs
    calls = count_extractions(monkeypatch)
    stats = run(make_config(sample_tree, out, base))
    assert calls['n'] <= stats.total_files


def test_no_double_extraction_without_cache(sample_tree, out_dirs, monkeypatch):
    """--no-cache でも重複検出プリパスと本ループで2回抽出しないこと."""
    out, base = out_dirs
    calls = count_extractions(monkeypatch)
    stats = run(make_config(sample_tree, out, base, use_cache=False))
    assert calls['n'] <= stats.total_files, '二重抽出が発生している'


def test_no_double_extraction_with_full_rescan(sample_tree, out_dirs, monkeypatch):
    """--full-rescan でも同様（今回抽出し直した分は再利用してよい）."""
    out, base = out_dirs
    run(make_config(sample_tree, out, base))

    calls = count_extractions(monkeypatch)
    stats = run(make_config(sample_tree, out, base, full_rescan=True))
    assert calls['n'] <= stats.total_files, '二重抽出が発生している'


def test_full_rescan_still_ignores_previous_cache(sample_tree, out_dirs, monkeypatch):
    """--full-rescan は前回までのキャッシュを使わないこと（意味が壊れていない）."""
    out, base = out_dirs
    run(make_config(sample_tree, out, base))

    calls = count_extractions(monkeypatch)
    stats = run(make_config(sample_tree, out, base, full_rescan=True))
    assert calls['n'] == stats.total_files, '全ファイルを抽出し直していない'


# ---- B5: 1ファイルのハングで実行全体が止まらないこと ----

def test_timeout_does_not_stall_whole_run(sample_tree, out_dirs, monkeypatch):
    import contextgen.pipeline as pipeline

    original = pipeline.extract

    def hanging(path, ctx):
        if path.name == 'メモ.txt':
            time.sleep(3)
        return original(path, ctx)

    monkeypatch.setattr(pipeline, 'extract', hanging)

    started = time.time()
    stats = run(make_config(sample_tree, out_dirs[0], out_dirs[1],
                            extract_timeout_seconds=1, dedupe_mode='off'))
    elapsed = time.time() - started

    assert elapsed < 15, 'ハングしたファイルで実行全体が止まっている'
    assert stats.total_files > 1
    assert stats.jsonl_records > 0, '他のファイルまで失われている'


def test_timeout_is_reported_as_error(sample_tree, out_dirs, monkeypatch):
    import contextgen.pipeline as pipeline

    original = pipeline.extract

    def hanging(path, ctx):
        if path.name == 'メモ.txt':
            time.sleep(3)
        return original(path, ctx)

    monkeypatch.setattr(pipeline, 'extract', hanging)
    out, base = out_dirs
    run(make_config(sample_tree, out, base, extract_timeout_seconds=1, dedupe_mode='off'))

    report = (out / '_AI_CONTEXT_REPORT.md').read_text(encoding='utf-8')
    assert '秒を超えたため打ち切りました' in report, 'タイムアウトが記録されていない'


# ---- B6: JSONL の本文二重保存 ----

def test_excerpt_is_truncated_for_long_text(sample_tree, out_dirs):
    out, base = out_dirs
    long_text = 'これは長い本文です。' * 200
    (sample_tree / '長文資料.txt').write_text(long_text, encoding='utf-8')

    run(make_config(sample_tree, out, base))
    records = [r for r in read_records(out) if r['file_name'] == '長文資料.txt']

    assert records
    for record in records:
        assert len(record['text_excerpt']) < len(record['text']), '本文が複製されている'
        assert record['text_excerpt'].endswith('...')


def test_legacy_keeps_full_excerpt(sample_tree, out_dirs):
    """原本互換モードでは従来どおり本文全体を複製すること."""
    out, base = out_dirs
    (sample_tree / '長文資料.txt').write_text('これは長い本文です。' * 200, encoding='utf-8')

    run(make_config(sample_tree, out, base).legacy())
    records = [r for r in read_records(out) if r['file_name'] == '長文資料.txt']

    assert records
    for record in records:
        assert record['text_excerpt'] == record['text']
