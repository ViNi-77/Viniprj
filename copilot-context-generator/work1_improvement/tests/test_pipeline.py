"""パイプライン統合テスト（改善①②③⑤の結線確認）."""
from __future__ import annotations

import json
import threading

from contextgen.config import RunConfig
from contextgen.events import NullEmitter
from contextgen.worker import run_all


def run(config):
    return run_all(config, NullEmitter(), threading.Event())


def make_config(sample_tree, out, base, **kw):
    return RunConfig(search_root=sample_tree, context_output_dir=out, base_dir=base, **kw)


def test_full_run_outputs(sample_tree, out_dirs):
    out, base = out_dirs
    config = make_config(sample_tree, out, base)
    stats = run(config)

    assert stats is not None
    assert stats.total_files > 0
    assert (out / 'M365AgentContext_INDEX.txt').exists()
    assert (out / 'M365AgentContext_001.txt').exists()
    assert (out / '_AI_CONTEXT_DATA.jsonl').exists()
    assert (out / '_AI_CONTEXT_SUMMARY.md').exists()
    assert (out / '_AI_CONTEXT_REPORT.md').exists()

    # 改善③: JSONL レコードにトークン推定とステータス
    records = [json.loads(line) for line in
               (out / '_AI_CONTEXT_DATA.jsonl').read_text(encoding='utf-8').splitlines()]
    assert all('token_estimate' in r and 'extract_status' in r for r in records)

    # 除外フォルダ「管理」の中身は収録されない
    assert not any('内部メモ' in r['file_name'] for r in records)
    # ロックファイル ~$ は収録されない
    assert not any(r['file_name'].startswith('~$') for r in records)


def test_report_contents(sample_tree, out_dirs):
    out, base = out_dirs
    config = make_config(sample_tree, out, base, enable_doc_conversion=False)
    run(config)
    report = (out / '_AI_CONTEXT_REPORT.md').read_text(encoding='utf-8')
    assert 'OCR候補' in report
    assert 'スキャン報告書.pdf' in report
    assert '要変換（.doc 形式）' in report
    assert '古い報告書.doc' in report
    assert 'ステータス内訳' in report


def test_second_run_uses_cache_and_diff(sample_tree, out_dirs):
    out, base = out_dirs
    config = make_config(sample_tree, out, base)
    stats1 = run(config)
    assert stats1.cache_hits == 0

    stats2 = run(config)
    assert stats2.cache_hits == stats1.total_files  # 全件キャッシュヒット
    assert stats2.cache_misses == 0

    # ファイルを変更すると再抽出される
    (sample_tree / 'メモ.txt').write_text('更新された内容。\n', encoding='utf-8')
    stats3 = run(config)
    assert stats3.cache_misses == 1
    report = (out / '_AI_CONTEXT_REPORT.md').read_text(encoding='utf-8')
    assert '[変更]' in report and 'メモ.txt' in report


def test_full_rescan_ignores_cache(sample_tree, out_dirs):
    out, base = out_dirs
    config = make_config(sample_tree, out, base)
    run(config)
    stats = run(make_config(sample_tree, out, base, full_rescan=True))
    assert stats.cache_hits == 0
    assert stats.cache_misses == stats.total_files


def test_index_enriched_sections(sample_tree, out_dirs):
    out, base = out_dirs
    run(make_config(sample_tree, out, base))
    index = (out / 'M365AgentContext_INDEX.txt').read_text(encoding='utf-8')
    assert '## FileSummaries' in index
    assert '## LastDiff' in index


def test_split_by_subfolder(sample_tree, out_dirs):
    out, base = out_dirs
    run(make_config(sample_tree, out, base, split_by_subfolder=True))
    names = {p.name for p in out.glob('M365AgentContext*_INDEX.txt')}
    assert 'M365AgentContext_設備_INDEX.txt' in names
    assert 'M365AgentContext_品質_INDEX.txt' in names
    assert 'M365AgentContext__root_INDEX.txt' in names


def test_priority_folder_ordering(sample_tree, out_dirs):
    out, base = out_dirs
    run(make_config(sample_tree, out, base, priority_folders=['品質']))
    records = [json.loads(line) for line in
               (out / '_AI_CONTEXT_DATA.jsonl').read_text(encoding='utf-8').splitlines()]
    first_file_paths = [r['relative_path'] for r in records if r['index'] == 1]
    assert first_file_paths[0].startswith('品質')


def test_legacy_mode_produces_no_extras(sample_tree, out_dirs):
    out, base = out_dirs
    config = make_config(sample_tree, out, base).legacy()
    run(config)
    assert not (out / '_AI_CONTEXT_REPORT.md').exists()
    index = (out / 'M365AgentContext_INDEX.txt').read_text(encoding='utf-8')
    assert '## FileSummaries' not in index
    records = [json.loads(line) for line in
               (out / '_AI_CONTEXT_DATA.jsonl').read_text(encoding='utf-8').splitlines()]
    assert all('token_estimate' not in r for r in records)
