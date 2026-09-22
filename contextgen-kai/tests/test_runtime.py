"""コンソールのないWindows EXE相当の標準入出力で実サーバーを起動する。"""
import json
import socket
import subprocess
import sys
import time
import urllib.request


def test_server_runs_without_console_streams(tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([
        sys.executable, '-c',
        'import sys; sys.stdout=sys.stderr=None; from contextgen_kai.__main__ import main; main()',
        '--state-dir', str(tmp_path / 'state'), '--no-browser', '--port', str(port),
    ])
    url = f'http://127.0.0.1:{port}'
    try:
        for _ in range(200):
            assert process.poll() is None, 'コンソールなしで起動に失敗しました'
            try:
                with urllib.request.urlopen(url + '/api/status', timeout=1) as response:
                    state = json.load(response)
                break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError('サーバー起動待ちが時間切れです')
        request = urllib.request.Request(url + '/api/shutdown', data=b'{}', headers={
            'Content-Type': 'application/json', 'X-Contextgen-Token': state['token'],
        })
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 200
        assert process.wait(timeout=10) == 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
