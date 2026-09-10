"""v2.1 F3: Teams通知のテスト（ローカルHTTPサーバで受信検証）."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from contextgen.config import RunConfig
from contextgen.events import NullEmitter
from contextgen.notify import build_summary_text, send_teams_notification
from contextgen.pipeline import PipelineStats
from contextgen.worker import run_all


@pytest.fixture
def webhook_server():
    received: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get('Content-Length', 0))
            received.append(json.loads(self.rfile.read(length)))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'1')

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/webhook", received
    server.shutdown()


def test_send_notification(webhook_server):
    url, received = webhook_server
    ok = send_teams_notification(url, 'テスト本文', NullEmitter())
    assert ok
    assert received[0] == {'text': 'テスト本文'}


def test_send_failure_does_not_raise():
    ok = send_teams_notification('http://127.0.0.1:1/unreachable', 'x', NullEmitter())
    assert ok is False


def test_summary_text_contents(tmp_path):
    config = RunConfig(search_root=tmp_path, context_output_dir=tmp_path / 'out')
    stats = PipelineStats(
        total_files=12, jsonl_records=30, cache_hits=10, cache_misses=2,
        overflow_count=3,
        status_counts={'ok': 10, 'error': 1, 'needs_ocr': 1},
        upload_needed=['M365AgentContext_INDEX.txt', 'M365AgentContext_002.txt'],
    )
    text = build_summary_text(config, stats)
    assert '対象ファイル: 12' in text
    assert '抽出エラー: 1 件' in text
    assert 'OCR候補: 1 件' in text
    assert '上限あふれ: 3' in text
    assert '要再アップロード: 2 件' in text


def test_worker_sends_notification(sample_tree, out_dirs, webhook_server):
    url, received = webhook_server
    out, base = out_dirs
    config = RunConfig(search_root=sample_tree, context_output_dir=out, base_dir=base,
                       teams_webhook_url=url)
    run_all(config, NullEmitter(), threading.Event())
    assert len(received) == 1
    assert 'コンテキスト生成 完了' in received[0]['text']
    assert '要再アップロード' in received[0]['text']


def test_worker_no_webhook_no_notification(sample_tree, out_dirs, webhook_server):
    url, received = webhook_server
    out, base = out_dirs
    config = RunConfig(search_root=sample_tree, context_output_dir=out, base_dir=base)
    run_all(config, NullEmitter(), threading.Event())
    assert received == []
