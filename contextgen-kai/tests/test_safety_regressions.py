"""原本と保存領域の境界に関する統合回帰試験。"""
import json
import os
import subprocess

import pytest
from pathlib import Path

from fastapi.testclient import TestClient

from contextgen_kai.api import create_app
from contextgen_kai.jobs import JobManager
from contextgen_kai.storage import Store


def test_queued_document_replaced_by_outside_symlink_is_not_read(tmp_path, monkeypatch):
    import contextgen_kai.extractors as extraction
    source = tmp_path / 'source'
    source.mkdir()
    first, second = source / 'a.txt', source / 'b.txt'
    first.write_text('first source document', encoding='utf-8')
    second.write_text('second source document', encoding='utf-8')
    secret = tmp_path / 'outside.txt'
    secret.write_text('OUTSIDE_PRIVATE_CONTENT', encoding='utf-8')
    probe = source / 'symlink-probe'
    try:
        probe.symlink_to(secret)
        probe.unlink()
    except OSError:
        pytest.skip('This account cannot create symbolic links')
    store = Store(tmp_path / 'state')
    library = store.add_library('source', str(source))
    original = extraction.extract_document
    def replace_after_first(path, **kwargs):
        result = original(path, **kwargs)
        if path == first:
            second.unlink()
            second.symlink_to(secret)
        return result
    monkeypatch.setattr(extraction, 'extract_document', replace_after_first)
    jobs = JobManager(store, use_process=False)
    try:
        job = jobs.start(library['id'])
        assert jobs.wait(job['id'])['state'] == 'completed'
        doc = store.one('SELECT * FROM documents WHERE relative_path=?', ('b.txt',))
        assert 'OUTSIDE_PRIVATE_CONTENT' not in doc['effective_text']
        assert doc['status'] not in ('ok', 'empty')
    finally:
        jobs.close()


def test_backup_collection_id_cannot_escape_output_directory(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'memo.txt').write_text('source text', encoding='utf-8')
    app = create_app(tmp_path / 'state', use_process=False, enable_scheduler=False)
    with TestClient(app) as client:
        token = client.get('/api/status').json()['token']
        response = client.post('/api/restore', headers={'X-Contextgen-Token': token}, files={'file': ('backup.json', json.dumps({
            'schema_version': 1, 'application': 'contextgen-kai',
            'libraries': [{'id': 'library-safe', 'name': 'source', 'path': str(source)}],
            'collections': [{'id': '../../outside-export', 'name': 'unsafe', 'library_id': 'library-safe'}],
        }), 'application/json')})
        assert response.status_code == 400
        assert client.get('/api/libraries').json() == []


@pytest.mark.skipif(os.name != 'nt', reason='Windows directory junction acceptance')
def test_windows_junction_outside_library_is_not_traversed(tmp_path):
    source = tmp_path / 'source'
    outside = tmp_path / 'outside'
    source.mkdir()
    outside.mkdir()
    (source / 'normal.txt').write_text('normal source', encoding='utf-8')
    (outside / 'private.txt').write_text('OUTSIDE_PRIVATE_CONTENT', encoding='utf-8')
    junction = source / 'linked'
    made = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(junction), str(outside)], capture_output=True)
    assert made.returncode == 0, made.stderr.decode(errors='replace')
    store = Store(tmp_path / 'state')
    library = store.add_library('source', str(source))
    jobs = JobManager(store, use_process=False)
    try:
        job = jobs.start(library['id'])
        assert jobs.wait(job['id'])['state'] == 'completed'
        documents = store.all('SELECT effective_text FROM documents')
        assert len(documents) == 1
        assert all('OUTSIDE_PRIVATE_CONTENT' not in row['effective_text'] for row in documents)
    finally:
        jobs.close()
        junction.rmdir()
