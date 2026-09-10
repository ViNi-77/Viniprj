"""パリティテスト: legacy 設定の contextgen と復元版モノリスの出力が一致すること.

復元版は bytecode 照合で原本 exe と完全一致が証明されているため、
このテストが通れば contextgen (legacy) = 原本 exe の出力互換が言える。
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

import pytest

RESTORED = Path(__file__).resolve().parents[1] / 'restored' / 'box_copy_gui_direct_context_mode_fixed.py'

TS_RE = re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')
STAMP_RE = re.compile(r'\d{8}_\d{6}')


def run_restored(source_root: Path, output_dir: Path, base_dir: Path):
    """復元版モノリスの GUI 部分を除いて実行する."""
    source = RESTORED.read_text(encoding='utf-8')
    cut = source.index('root = tk.Tk()')
    code = compile(source[:cut], str(RESTORED), 'exec')
    ns: dict = {}
    exec(code, ns)

    ns['SEARCH_ROOT'] = source_root
    ns['CONTEXT_SOURCE_DIR'] = source_root
    ns['CONTEXT_OUTPUT_DIR'] = output_dir
    ns['BASE_DIR'] = base_dir
    ns['LOG_PATH'] = base_dir / 'box_copy_gui_log.txt'
    ns['SETTINGS_PATH'] = base_dir / 'box_copy_gui_settings.json'
    ns['refresh_context_output_paths']()
    ns['backup_worker']()


def run_contextgen(source_root: Path, output_dir: Path, base_dir: Path):
    from contextgen.config import RunConfig
    from contextgen.events import NullEmitter
    from contextgen.worker import run_all

    config = RunConfig(
        search_root=source_root,
        context_output_dir=output_dir,
        base_dir=base_dir,
    ).legacy()
    run_all(config, NullEmitter(), threading.Event())


def normalize(text: str, output_dir: Path) -> str:
    text = text.replace(str(output_dir), 'OUTDIR')
    text = TS_RE.sub('TS', text)
    text = STAMP_RE.sub('STAMP', text)
    return text


def snapshot(output_dir: Path) -> dict[str, str]:
    """比較対象ファイルの {正規化名: 正規化内容} を返す."""
    result = {}
    for path in output_dir.iterdir():
        if not path.is_file():
            continue
        name = STAMP_RE.sub('STAMP', path.name)
        if not (name.startswith('M365AgentContext') or name.startswith('_AI_CONTEXT_')):
            continue
        result[name] = normalize(path.read_text(encoding='utf-8'), output_dir)
    return result


@pytest.fixture
def parity_outputs(sample_tree, tmp_path):
    out_a = tmp_path / 'out_restored'
    base_a = tmp_path / 'base_restored'
    out_b = tmp_path / 'out_contextgen'
    base_b = tmp_path / 'base_contextgen'
    for d in (out_a, base_a, out_b, base_b):
        d.mkdir()

    run_restored(sample_tree, out_a, base_a)
    run_contextgen(sample_tree, out_b, base_b)
    return out_a, out_b


def test_same_file_set(parity_outputs):
    out_a, out_b = parity_outputs
    snap_a, snap_b = snapshot(out_a), snapshot(out_b)
    assert sorted(snap_a) == sorted(snap_b)


def test_m365_files_identical(parity_outputs):
    out_a, out_b = parity_outputs
    snap_a, snap_b = snapshot(out_a), snapshot(out_b)
    for name in snap_a:
        if name.startswith('M365AgentContext'):
            assert snap_a[name] == snap_b[name], f"{name} の内容が一致しない"


def test_markdown_files_identical(parity_outputs):
    out_a, out_b = parity_outputs
    snap_a, snap_b = snapshot(out_a), snapshot(out_b)
    for name in snap_a:
        if name.endswith('.md'):
            assert snap_a[name] == snap_b[name], f"{name} の内容が一致しない"


def test_jsonl_identical(parity_outputs):
    out_a, out_b = parity_outputs
    a = (out_a / '_AI_CONTEXT_DATA.jsonl').read_text(encoding='utf-8')
    b = (out_b / '_AI_CONTEXT_DATA.jsonl').read_text(encoding='utf-8')
    assert a == b
    for line in b.splitlines():
        json.loads(line)
