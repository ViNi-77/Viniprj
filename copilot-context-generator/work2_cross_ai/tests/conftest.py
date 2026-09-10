"""work2 テスト用フィクスチャ."""
from __future__ import annotations

import json
import zipfile

import pytest


@pytest.fixture
def sample_records():
    """contextgen の JSONL 相当のレコード列."""
    records = []
    for i in range(1, 6):
        records.append({
            'index': i,
            'chunk_index': 1,
            'chunk_count': 1,
            'file_name': f"doc{i}.txt",
            'relative_path': f"folder/doc{i}.txt",
            'extension': '.txt',
            'size_bytes': 100,
            'size_text': '100 B',
            'summary': f"要約{i}",
            'text_length': 4000,
            'text_excerpt': f"本文{i} " + 'x' * 4000,
            'text': f"本文{i} " + 'x' * 4000,
        })
    return records


@pytest.fixture
def sample_jsonl(tmp_path, sample_records):
    path = tmp_path / '_AI_CONTEXT_DATA.jsonl'
    with open(path, 'w', encoding='utf-8') as f:
        for r in sample_records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    return path


@pytest.fixture
def docs_root(tmp_path):
    """MCP サーバ用の資料フォルダ."""
    root = tmp_path / 'docs'
    (root / 'メモ').mkdir(parents=True)
    (root / '設備仕様.txt').write_text(
        '# 設備仕様\nX-200 加工機の仕様概要。\n最大回転数 12000rpm。\n', encoding='utf-8'
    )
    (root / 'メモ' / '会議メモ.txt').write_text(
        '2026年7月の定例。歩留まり改善の進捗を確認。\n', encoding='utf-8'
    )
    with zipfile.ZipFile(root / '過去資料.zip', 'w') as zf:
        zf.writestr('old/レポート.txt', '旧ラインの停止記録。')
    (root / '写真.png').write_bytes(b'\x89PNG')  # 対象外
    (root / '~$lock.docx').write_bytes(b'lock')  # 一時ファイル
    return root
