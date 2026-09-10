"""M365 パッケージングのテスト（改善⑤）."""
from __future__ import annotations

from contextgen.config import M365_CONTEXT_MAX_BODY_FILES, RunConfig
from contextgen.events import NullEmitter
from contextgen.outputs.m365 import M365Packer, cleanup_m365_fixed_files, write_m365_package


def make_config(tmp_path, **kw):
    return RunConfig(
        search_root=tmp_path / 'src',
        context_output_dir=tmp_path / 'out',
        base_dir=tmp_path / 'base',
        **kw,
    )


def entry(i, chunk=1, count=1):
    return {
        'index': i, 'chunk_index': chunk, 'chunk_count': count,
        'file_name': f"f{i}.txt", 'relative_path': f"f{i}.txt",
    }


def test_sequential_matches_legacy_behavior(tmp_path):
    config = make_config(tmp_path)
    packer = M365Packer(config)
    # 30,000字の容量に 20,000字 ×2 → 2パート目ができる
    packer.append('a' * 20000, entry(1))
    packer.append('b' * 20000, entry(2))
    assert len(packer.parts) == 2
    assert packer.entries[0]['m365_part'] == 1
    assert packer.entries[1]['m365_part'] == 2


def test_sequential_overflow_after_19_parts(tmp_path):
    config = make_config(tmp_path)
    packer = M365Packer(config)
    for i in range(40):
        packer.append('x' * 20000, entry(i))
    assert len(packer.parts) == M365_CONTEXT_MAX_BODY_FILES
    assert packer.overflow_count == 40 - M365_CONTEXT_MAX_BODY_FILES
    assert len(packer.overflow_entries) == packer.overflow_count


def test_bestfit_packs_denser_than_sequential(tmp_path):
    sizes = [18000, 18000, 11000, 11000]  # sequential: 4パート / bestfit: 2パート
    seq = M365Packer(make_config(tmp_path))
    for i, s in enumerate(sizes):
        seq.append('x' * s, entry(i))
    best = M365Packer(make_config(tmp_path, m365_packing='bestfit'))
    for i, s in enumerate(sizes):
        best.append('x' * s, entry(i))
    assert len(best.parts) < len(seq.parts)


def test_token_capacity_mode(tmp_path):
    config = make_config(tmp_path, m365_capacity_mode='tokens', token_chars_per_token=1.0)
    packer = M365Packer(config)
    # capacity = 21000トークン、1文字=1トークン設定
    packer.append('a' * 15000, entry(1))
    packer.append('b' * 15000, entry(2))
    assert len(packer.parts) == 2


def test_write_package_files_and_index(tmp_path):
    config = make_config(tmp_path)
    config.context_output_dir.mkdir(parents=True)
    packer = M365Packer(config)
    packer.append('内容A', entry(1))
    packer.append('内容B', entry(2))

    emitter = NullEmitter()
    cleanup_m365_fixed_files(config.context_output_dir, emitter)
    index_path, fixed_paths, _, _ = write_m365_package(
        config, packer, '2026-01-01 00:00:00', '20260101_000000', emitter,
    )

    assert index_path.exists()
    assert len(fixed_paths) == 1
    index_text = index_path.read_text(encoding='utf-8')
    assert 'BodyFileCount: 1' in index_text
    assert 'M365AgentContext_001.txt: 2 chunks' in index_text
    assert 'UploadLimitPolicy: 1 index file + up to 19 body files = 20 files' in index_text
    body_text = fixed_paths[0].read_text(encoding='utf-8')
    assert '内容A' in body_text and '内容B' in body_text
    # Archive にも同名+スタンプで保存
    archive = config.context_output_dir / 'Archive'
    assert list(archive.glob('*_INDEX.txt'))


def test_cleanup_removes_fixed_files_only(tmp_path):
    config = make_config(tmp_path)
    out = config.context_output_dir
    out.mkdir(parents=True)
    (out / 'M365AgentContext_001.txt').write_text('x', encoding='utf-8')
    (out / 'M365AgentContext_INDEX.txt').write_text('x', encoding='utf-8')
    (out / 'M365AgentContext_設備_002.txt').write_text('x', encoding='utf-8')
    (out / 'M365AgentContext_other.txt').write_text('keep', encoding='utf-8')
    (out / 'unrelated.txt').write_text('keep', encoding='utf-8')

    cleanup_m365_fixed_files(out, NullEmitter())

    assert not (out / 'M365AgentContext_001.txt').exists()
    assert not (out / 'M365AgentContext_INDEX.txt').exists()
    assert not (out / 'M365AgentContext_設備_002.txt').exists()
    assert (out / 'M365AgentContext_other.txt').exists()
    assert (out / 'unrelated.txt').exists()
