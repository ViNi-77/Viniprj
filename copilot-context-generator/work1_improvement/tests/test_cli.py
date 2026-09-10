"""CLI のテスト（改善④）."""
from __future__ import annotations

from contextgen.cli import main


def test_cli_full_run(sample_tree, tmp_path, capsys):
    out = tmp_path / 'cli_out'
    rc = main([
        '--source', str(sample_tree),
        '--output', str(out),
        '--base-dir', str(tmp_path / 'cli_base'),
    ])
    assert rc == 0
    assert (out / 'M365AgentContext_INDEX.txt').exists()
    captured = capsys.readouterr()
    assert 'AI用コンテキスト生成完了' in captured.out


def test_cli_missing_source(tmp_path, capsys):
    rc = main([
        '--source', str(tmp_path / 'nonexistent'),
        '--output', str(tmp_path / 'out'),
    ])
    assert rc == 2
    assert '参照元フォルダが存在しません' in capsys.readouterr().err


def test_cli_source_inside_output_rejected(tmp_path, capsys):
    out = tmp_path / 'out'
    src = out / 'sub'
    src.mkdir(parents=True)
    rc = main(['--source', str(src), '--output', str(out)])
    assert rc == 2
    assert '参照元に指定できません' in capsys.readouterr().err


def test_cli_legacy_flag(sample_tree, tmp_path):
    out = tmp_path / 'legacy_out'
    rc = main([
        '--source', str(sample_tree),
        '--output', str(out),
        '--base-dir', str(tmp_path / 'legacy_base'),
        '--legacy',
    ])
    assert rc == 0
    assert not (out / '_AI_CONTEXT_REPORT.md').exists()
