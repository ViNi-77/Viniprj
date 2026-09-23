"""Gitだけで取得した日本語パスの新規作業コピーからBAT・同梱OCRを実行する。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def request(base, path, *, method=None, data=None, token=None):
    headers = {"Origin": base}
    if token:
        headers["X-Contextgen-Token"] = token
    if data is not None:
        headers["Content-Type"] = "application/json"
    body = json.dumps(data).encode("utf-8") if data is not None else None
    with urllib.request.urlopen(urllib.request.Request(base + path, data=body, headers=headers, method=method), timeout=15) as response:
        return json.load(response)


def wait_for(check, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.2)
    raise AssertionError("Windows clone smoke timed out")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("build/windows-clone-smoke.json"))
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = {"platform": sys.platform, "checks": [], "user_machine_acceptance": "pending"}
    process = None
    base = token = None

    def checked(name):
        evidence["checks"].append(name)
        print(name, flush=True)

    try:
        assert os.name == "nt", "Windows only"
        project = Path(__file__).resolve().parents[1]
        repository = project.parent
        with tempfile.TemporaryDirectory(prefix="contextgen-clone-", ignore_cleanup_errors=True) as directory:
            temporary = Path(directory)
            checkout = temporary / "日本語 空白" / "Viniprj"
            checkout.parent.mkdir()
            # 実Git clone。既存.venv/build/distや未追跡のローカルOCRには依存できない。
            subprocess.run(["git", "clone", "--no-local", str(repository), str(checkout)], check=True)
            original_head = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
            cloned_head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
            assert cloned_head == original_head, "Fresh clone must test this CI checkout, including detached PR merge refs"
            evidence["source_revision"] = cloned_head
            root = checkout / "contextgen-kai"
            assert not (root / ".venv").exists()
            ocr = root / "ocr/tesseract.exe"
            assert ocr.is_file(), "OCR executable is absent from git clone"
            evidence["ocr_sha256"] = hashlib.sha256(ocr.read_bytes()).hexdigest()
            checked("git clone includes OCR executable and language files without a separate download")
            env = dict(os.environ, CONTEXTGEN_NO_PAUSE="1", PYTHONUTF8="1", PIP_NO_INPUT="1")
            for name in ("PYTHONPATH", "CONTEXTGEN_TESSERACT", "TESSDATA_PREFIX"):
                env.pop(name, None)
            cmd = os.environ.get("COMSPEC", "cmd.exe")
            command = [cmd, "/d", "/c", "start_windows.bat"]
            with output.with_suffix(".log").open("w", encoding="utf-8") as log:
                subprocess.run([*command, "--setup-only"], cwd=root, env=env, check=True,
                               stdout=log, stderr=subprocess.STDOUT, timeout=600)
                python = root / ".venv/Scripts/python.exe"
                assert python.is_file()
                marker = root / ".venv/.contextgen-dependencies.sha256"
                original_stamp = marker.read_bytes()
                checked("first BAT launch creates a Python 3.12 venv and installs pinned dependencies")
                # pipが呼ばれたら即失敗する偽モジュールを一時配置し、再起動時の追加取得ゼロを証明。
                (root / "pip.py").write_text("raise RuntimeError('Unexpected pip on an unchanged second launch')\n", encoding="utf-8")
                try:
                    offline = dict(env, PIP_NO_INDEX="1")
                    subprocess.run([*command, "--setup-only"], cwd=root, env=offline, check=True,
                                   stdout=log, stderr=subprocess.STDOUT, timeout=60)
                finally:
                    (root / "pip.py").unlink()
                assert marker.read_bytes() == original_stamp
                checked("unchanged second BAT launch succeeds with pip disabled")
                discovered = subprocess.check_output([str(python), "-c",
                    "from contextgen_kai.extractors import tesseract_path; print(tesseract_path())"],
                    cwd=root, env=env, text=True, encoding="utf-8").strip()
                assert Path(discovered).resolve() == ocr.resolve(), discovered
                checked("source runtime selects the OCR from this clone")

                from PIL import Image, ImageDraw, ImageFont
                source = temporary / "資料 フォルダ"
                source.mkdir()
                image = Image.new("RGB", (1300, 220), "white")
                ImageDraw.Draw(image).text((40, 50), "CONTEXTGEN CLONE SAFETY 123",
                    font=ImageFont.truetype(str(Path(os.environ["WINDIR"]) / "Fonts/arial.ttf"), 48), fill="black")
                image.save(source / "同梱 OCR.png")
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
                    port = sock.getsockname()[1]
                base = f"http://127.0.0.1:{port}"
                process = subprocess.Popen([*command, "--no-browser", "--state-dir", str(temporary / "利用者 保存"), "--port", str(port)],
                                           cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)

                def ready():
                    assert process.poll() is None, "BAT exited before API startup"
                    try:
                        return request(base, "/api/status")
                    except (OSError, urllib.error.URLError):
                        return None

                status = wait_for(ready)
                token = status["token"]
                from contextgen_kai import __version__
                assert status["version"] == __version__
                evidence["version"] = status["version"]
                checked("BAT launches the browser application from a Japanese and spaced clone path")
                update_attempt = subprocess.run([cmd, "/d", "/c", "更新.bat"], cwd=root, env=env,
                                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                encoding="utf-8", errors="replace", timeout=30)
                log.write(update_attempt.stdout)
                log.flush()
                assert update_attempt.returncode != 0, "Git update must not run while the application holds its lock"
                assert "アプリまたは定期更新が動作中です" in update_attempt.stdout, update_attempt.stdout
                checked("running application prevents Git update")
                library = request(base, "/api/libraries", data={"name": "Git取得OCR試験", "path": str(source)}, token=token)
                job = request(base, "/api/jobs", data={"library_id": library["id"]}, token=token)

                def finished():
                    rows = request(base, "/api/jobs")
                    return next((item for item in rows if item["id"] == job["id"] and item["state"] in {"completed", "held", "failed", "stopped"}), None)

                outcome = wait_for(finished)
                assert outcome["state"] == "completed" and outcome["errors"] == 0, outcome
                docs = request(base, "/api/documents?limit=10")["items"]
                assert len(docs) == 1 and docs[0]["status"] == "ok", docs
                detail = request(base, "/api/documents/" + docs[0]["id"])
                assert "CLONE" in detail["effective_text"], detail
                assert all(unit.get("unit_id") and unit.get("source_refs") for unit in detail["units"])
                checked("cloned app reads an image with bundled OCR and structured source units")
                from windows_smoke import verify_edit_revision_api
                verify_edit_revision_api(base, token, detail["id"], call=request)
                checked("cloned app enforces edit revisions and restores text from history")
                request(base, "/api/shutdown", data={}, token=token)
                assert process.wait(timeout=30) == 0
                process = None
                checked("app shutdown releases the Git update lock")
                subprocess.run([*command, "--setup-only"], cwd=root, env=env, check=True,
                               stdout=log, stderr=subprocess.STDOUT, timeout=60)
        evidence["status"] = "passed"
    except BaseException as error:
        evidence["status"] = "failed"
        evidence["error"] = str(error)
        raise
    finally:
        if process is not None and process.poll() is None:
            try:
                if base and token:
                    request(base, "/api/shutdown", data={}, token=token)
                    process.wait(timeout=20)
            finally:
                if process.poll() is None:
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=False, capture_output=True)
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
