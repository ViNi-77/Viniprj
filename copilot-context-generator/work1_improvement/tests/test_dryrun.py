"""v2.1 F2: ドライラン+容量予測のテスト."""
from __future__ import annotations

import threading

from contextgen.config import RunConfig
from contextgen.events import NullEmitter
from contextgen.worker import run_all


class LogCapture(NullEmitter):
    def __init__(self):
        super().__init__()
        self.logs = []

    def log(self, message):
        self.logs.append(message)


def make_config(sample_tree, out, base, **kw):
    return RunConfig(search_root=sample_tree, context_output_dir=out, base_dir=base, **kw)


def test_dry_run_writes_nothing(sample_tree, out_dirs):
    out, base = out_dirs
    config = make_config(sample_tree, out, base, dry_run=True)
    stats = run_all(config, NullEmitter(), threading.Event())

    assert stats is not None and stats.dry_run
    assert stats.total_files > 0
    # 出力ファイルは一切作られない
    generated = [p for p in out.iterdir() if p.is_file()]
    assert generated == []
    assert not (out / 'Archive').exists()


def test_dry_run_estimates(sample_tree, out_dirs):
    out, base = out_dirs
    emitter = LogCapture()
    config = make_config(sample_tree, out, base, dry_run=True)
    stats = run_all(config, emitter, threading.Event())

    assert stats.estimated_total_tokens > 0
    assert stats.jsonl_records > 0
    assert stats.m365_parts_needed.get('') == 1  # サンプルは1パートに収まる
    assert stats.overflow_count == 0
    joined = '\n'.join(emitter.logs)
    assert 'ドライラン見積' in joined
    assert '収まる見込み' in joined
    assert '抽出ステータス内訳' in joined


def test_dry_run_warms_cache_for_real_run(sample_tree, out_dirs):
    out, base = out_dirs
    dry = run_all(make_config(sample_tree, out, base, dry_run=True),
                  NullEmitter(), threading.Event())
    assert dry.cache_misses == dry.total_files

    real = run_all(make_config(sample_tree, out, base),
                   NullEmitter(), threading.Event())
    # ドライランで温めたキャッシュが本実行で効く
    assert real.cache_hits == real.total_files
    assert (out / 'M365AgentContext_INDEX.txt').exists()


def test_dry_run_does_not_advance_diff_baseline(sample_tree, out_dirs):
    out, base = out_dirs
    run_all(make_config(sample_tree, out, base), NullEmitter(), threading.Event())

    # ファイルを変更してからドライラン → 差分基準は進まないはず
    (sample_tree / 'メモ.txt').write_text('変更後の内容\n', encoding='utf-8')
    run_all(make_config(sample_tree, out, base, dry_run=True), NullEmitter(), threading.Event())

    # 本実行の差分レポートに「変更」が残っている
    run_all(make_config(sample_tree, out, base), NullEmitter(), threading.Event())
    report = (out / '_AI_CONTEXT_REPORT.md').read_text(encoding='utf-8')
    assert '[変更]' in report and 'メモ.txt' in report


def test_cli_dry_run(sample_tree, tmp_path, capsys):
    from contextgen.cli import main
    out = tmp_path / 'dry_out'
    rc = main([
        '--source', str(sample_tree),
        '--output', str(out),
        '--base-dir', str(tmp_path / 'dry_base'),
        '--dry-run',
    ])
    assert rc == 0
    assert 'ドライラン見積' in capsys.readouterr().out
    assert not (out / 'M365AgentContext_INDEX.txt').exists()
