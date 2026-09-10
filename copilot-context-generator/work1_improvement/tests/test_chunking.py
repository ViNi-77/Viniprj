"""チャンク分割・要約・トークン推定のテスト（改善③）."""
from __future__ import annotations

from contextgen.config import RunConfig
from contextgen.textutil import (
    heading_summary,
    simple_summary,
    split_text_for_context,
    split_text_semantic,
)


def test_legacy_split_line_based():
    text = '\n'.join(f"line{i:02d} " + 'x' * 20 for i in range(20))
    chunks = split_text_for_context(text, max_chars=100)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)
    # レガシーはオーバーラップなし: 結合すれば元と同じ行集合
    joined = '\n'.join(chunks)
    for i in range(20):
        assert f"line{i:02d}" in joined


def test_legacy_split_oversized_line():
    text = 'y' * 250
    chunks = split_text_for_context(text, max_chars=100)
    assert chunks == ['y' * 100, 'y' * 100, 'y' * 50]


def test_semantic_split_respects_headings():
    sections = []
    for n in range(1, 4):
        sections.append(f"# Page {n}\n" + f"content page {n} " * 20)
    text = '\n'.join(sections)
    chunks = split_text_semantic(text, max_chars=400, overlap_ratio=0.1)
    assert len(chunks) >= 3
    # 各ページ見出しはチャンクの先頭付近（=境界がページで切れている）
    for n in range(2, 4):
        starts = [c for c in chunks if f"# Page {n}" in c]
        assert starts, f"# Page {n} を含むチャンクがない"
    assert all(len(c) <= 400 for c in chunks)


def test_semantic_split_has_overlap():
    text = '\n'.join(f"para{i} " + 'z' * 60 for i in range(12))
    chunks = split_text_semantic(text, max_chars=300, overlap_ratio=0.2)
    assert len(chunks) >= 2
    # 2番目のチャンクの先頭部分は1番目のチャンクの末尾の再掲（オーバーラップ）
    head = chunks[1].splitlines()[0]
    assert head
    assert chunks[0].endswith(head)


def test_semantic_split_empty():
    assert split_text_semantic('') == ['']


def test_heading_summary_lists_headings():
    text = '# Page 1\n概要の説明文です。\n# Page 2\n詳細の説明。\n## Notes\n補足メモ'
    summary = heading_summary(text)
    assert '見出し:' in summary
    assert 'Page 1' in summary and 'Page 2' in summary
    assert '概要の説明文です。' in summary


def test_heading_summary_fallback_no_headings():
    text = '見出しのないプレーンな文書。\n2行目。'
    summary = heading_summary(text)
    assert '見出しのないプレーン' in summary


def test_simple_summary_legacy_head20():
    text = '\n'.join(f"L{i}" for i in range(40))
    summary = simple_summary(text)
    assert summary.splitlines() == [f"L{i}" for i in range(20)]


def test_token_estimate():
    config = RunConfig(search_root='.', context_output_dir='./out')
    assert config.estimate_tokens('') == 0
    assert config.estimate_tokens('あ' * 140) == 100
