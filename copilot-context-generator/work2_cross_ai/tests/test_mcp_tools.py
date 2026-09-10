"""folder-context MCP サーバのツール関数テスト（直接呼び出し）."""
from __future__ import annotations

import pytest

from mcp_server import folder_context_server as srv


@pytest.fixture(autouse=True)
def set_root(docs_root, tmp_path, monkeypatch):
    monkeypatch.setattr(srv, '_root', docs_root.resolve())
    # キャッシュDBをテスト用ホームに隔離
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setattr(srv.Path, 'home', classmethod(lambda cls: tmp_path / 'home'))
    yield


def test_search_files_all():
    out = srv.search_files()
    assert '設備仕様.txt' in out
    assert '会議メモ.txt' in out
    assert '過去資料.zip' in out
    assert '写真.png' not in out       # 対象外形式
    assert '~$lock.docx' not in out    # 一時ファイル


def test_search_files_query_and_ext():
    out = srv.search_files(query='メモ')
    assert '会議メモ.txt' in out
    assert '設備仕様.txt' not in out
    out2 = srv.search_files(extensions='.zip')
    assert '過去資料.zip' in out2
    assert '会議メモ.txt' not in out2


def test_read_document():
    out = srv.read_document('設備仕様.txt')
    assert '12000rpm' in out


def test_read_document_pagination():
    full = srv.read_document('設備仕様.txt')
    head = srv.read_document('設備仕様.txt', max_chars=10)
    assert head.startswith(full[:10])
    assert 'offset_chars=10' in head


def test_read_document_outside_root_rejected():
    with pytest.raises(ValueError):
        srv.read_document('../outside.txt')


def test_get_summary():
    out = srv.get_summary('設備仕様.txt')
    assert 'Status: ok' in out
    assert '設備仕様' in out


def test_search_content():
    out = srv.search_content('歩留まり')
    assert '会議メモ.txt' in out
    # ZIP内のテキストにもヒットする
    out2 = srv.search_content('停止記録')
    assert '過去資料.zip' in out2


def test_list_recent_changes():
    out = srv.list_recent_changes(days=1)
    assert '設備仕様.txt' in out
