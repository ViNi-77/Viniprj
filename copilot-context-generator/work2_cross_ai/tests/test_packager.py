"""crossai_packager のテスト."""
from __future__ import annotations

from pathlib import Path

from crossai_packager.cli import main
from crossai_packager.packager import Profile, load_records, pack


def test_profiles_available():
    names = Profile.available()
    assert {'m365', 'claude-projects', 'chatgpt-gpts', 'notebooklm'} <= set(names)


def test_profile_load():
    p = Profile.load('chatgpt-gpts')
    assert p.max_body_files == 19
    assert p.file_extension == '.txt'


def test_pack_basic(sample_records, tmp_path):
    profile = Profile.load('claude-projects')
    result = pack(sample_records, profile, tmp_path / 'out', source_scope='テスト')
    assert result.index_path is not None
    assert result.index_path.exists()
    assert result.overflow_chunks == 0
    assert len(result.body_paths) >= 1
    body = result.body_paths[0].read_text(encoding='utf-8')
    assert '### Source 1-1' in body
    assert 'SourcePath: folder/doc1.txt' in body
    index = result.index_path.read_text(encoding='utf-8')
    assert 'Profile: claude-projects' in index
    assert '## RequiredFiles' in index


def test_pack_respects_file_limit(sample_records, tmp_path):
    profile = Profile.load('chatgpt-gpts')
    # 1チャンク≈4KB。1ファイル5KBに絞ると 5チャンク→5ファイル…上限2で3あふれ
    profile.target_chars_per_file = 5000
    profile.max_body_files = 2
    result = pack(sample_records, profile, tmp_path / 'out')
    assert len(result.body_paths) == 2
    assert result.overflow_chunks == 3
    index = result.index_path.read_text(encoding='utf-8')
    assert 'OverflowChunkCount: 3' in index
    assert '## OverflowWarning' in index


def test_pack_upload_count_within_20_for_gpts(sample_records, tmp_path):
    profile = Profile.load('chatgpt-gpts')
    result = pack(sample_records * 30, profile, tmp_path / 'out')
    assert len(result.body_paths) + 1 <= 20


def test_cli_with_jsonl(sample_jsonl, tmp_path, capsys):
    out = tmp_path / 'pkg'
    rc = main(['--jsonl', str(sample_jsonl), '--output', str(out), '--profile', 'notebooklm'])
    assert rc == 0
    assert (out / 'NotebookLMSource_INDEX.md').exists()
    assert 'NotebookLM' in capsys.readouterr().out


def test_cli_with_source(docs_root, tmp_path, capsys):
    out = tmp_path / 'pkg2'
    rc = main(['--source', str(docs_root), '--output', str(out), '--profile', 'claude-projects'])
    assert rc == 0
    files = list(out.glob('ClaudeProjectContext_*.md'))
    assert files
    joined = '\n'.join(p.read_text(encoding='utf-8') for p in files)
    assert '設備仕様' in joined


def test_load_records(sample_jsonl):
    records = load_records(sample_jsonl)
    assert len(records) == 5
    assert records[0]['file_name'] == 'doc1.txt'
