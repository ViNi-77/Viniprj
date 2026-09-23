"""実際のローカルサーバーに接続し、日本語画面の通し操作とノートPC表示を検証する。

合成資料・アプリの保存先は一時ディレクトリに隔離する。APIのモックや利用者の
設定変更は行わない。画面検証に使うブラウザは配布物には含めない。
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def browser_path() -> str | None:
    """既存の実行ファイルを探す。ブラウザを自動ダウンロードしない。"""
    explicit = os.environ.get("CONTEXTGEN_BROWSER")
    if explicit:
        return explicit
    candidates = [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/usr/bin/chromium"),
        Path("/usr/bin/chromium-browser"),
        Path("/usr/bin/google-chrome"),
    ]
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        if os.environ.get(env):
            candidates.append(Path(os.environ[env]) / "Google/Chrome/Application/chrome.exe")
    for cache in (Path("/opt/pw-browsers"), Path.home() / "Library/Caches/ms-playwright", Path.home() / ".cache/ms-playwright"):
        if cache.exists():
            for pattern in ("**/chrome", "**/headless_shell", "**/chrome.exe", "**/Chromium"):
                candidates.extend(cache.glob(pattern))
    return str(next((path for path in candidates if path.is_file()), "")) or None


def reserve_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_server(base: str, proc: subprocess.Popen, log: Path):
    """起動成功はHTTPヘルス応答で確認し、失敗時はログを添えて終了する。"""
    for _ in range(200):
        if proc.poll() is not None:
            raise RuntimeError(f"アプリが起動せず終了しました。\n{log.read_text(errors='replace')}")
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, TimeoutError):
            pass
        time.sleep(0.1)
    raise RuntimeError(f"アプリ起動待ちがタイムアウトしました。\n{log.read_text(errors='replace')}")


def wait_jobs(page, expected_docs: int | None = None):
    """実ジョブが完了するまで待つ。件数を偽装せず実際のSQLite集計を確認する。"""
    page.wait_for_function(
        """async expected => {
          const result = await fetch('/api/status'); const data = await result.json();
          return data.jobs.length > 0 && data.jobs.every(j => ['completed','held','failed','stopped'].includes(j.state))
            && (expected === null || data.counts.total >= expected);
        }""",
        arg=expected_docs,
        timeout=120000,
    )
    data = page.request.get("/api/status").json()
    failed = [job for job in data["jobs"] if job["state"] == "failed"]
    assert not failed, failed


def assert_laptop(page, label: str):
    """ページと開いたダイアログの横溢れ・フッター操作の見切れを検出する。"""
    values = page.evaluate("""() => {
      const root = document.documentElement;
      const dialog = document.querySelector('dialog[open]');
      const footer = dialog?.querySelector('.dialog-footer')?.getBoundingClientRect();
      return {width: root.clientWidth, scroll: root.scrollWidth,
        dialogScroll: dialog ? dialog.scrollWidth : 0, dialogWidth: dialog ? dialog.clientWidth : 0,
        footerBottom: footer?.bottom || 0, height: window.innerHeight};
    }""")
    assert values["scroll"] <= values["width"] + 1, (label, values)
    assert values["dialogScroll"] <= values["dialogWidth"] + 1, (label, values)
    assert values["footerBottom"] <= values["height"] + 1, (label, values)


def verify_selection_and_override_review(page):
    """削除済み固定対象・登録解除・古い採否を実ファイルと実APIで再現する。"""
    token = page.request.get("/api/status").json()["token"]
    headers = {"X-Contextgen-Token": token}

    def put_collection(value):
        response = page.request.put(f"/api/collections/{value['id']}", data=value, headers=headers)
        assert response.status == 200, response.text()
        return response.json()

    def open_collection(name):
        page.locator('[data-view="exports"]').click()
        page.locator("#refresh-exports").click()
        page.locator(".collection-card").filter(has_text=name).get_by_role("button", name="編集", exact=True).click()

    def open_cleanup(name, filename):
        open_collection(name)
        page.locator("#preview-collection").click()
        page.locator("#collection-preview .candidate-row").filter(has=page.get_by_text(filename, exact=True)).get_by_role("button", name="整理前後").click()
        details = page.locator("#cleanup-units").locator("..")
        if not details.evaluate("el => el.open"):
            details.locator("summary").click()

    def close_cleanup():
        page.locator("#cleanup-dialog [data-close]").first.click()
        page.locator("#collection-dialog [data-close]").first.click()

    mixed = next(item for item in page.request.get("/api/collections").json() if item["name"] == "複数フォルダの案件")
    key = next(iter(mixed["unit_overrides"]))
    document_id = key.split(":", 1)[0]
    document = page.request.get(f"/api/documents/{document_id}").json()
    source = Path(document["source_path"])
    source.write_text(source.read_text(encoding="utf-8") + "\n原本更新後に採否を確認するための追記です。\n", encoding="utf-8")
    response = page.request.post(f"/api/documents/{document_id}/reextract", data={}, headers=headers)
    assert response.status == 200, response.text()
    wait_jobs(page)
    open_cleanup(mixed["name"], document["relative_path"])
    expect(page.locator("#cleanup-units")).to_contain_text("原本更新のため確認が必要")
    old_basis = mixed["unit_override_bases"][key]
    # 普通に保存するだけでは古い採否を再承認しない。
    page.locator("#save-unit-overrides").click()
    expect(page.locator("#save-unit-overrides")).to_be_enabled()
    expect(page.locator("#cleanup-units")).to_contain_text("原本更新のため確認が必要")
    saved = next(item for item in page.request.get("/api/collections").json() if item["id"] == mixed["id"])
    assert saved["unit_override_bases"][key] == old_basis
    page.locator("#cleanup-units").get_by_role("button", name="採否を再確認").click()
    page.locator("#save-unit-overrides").click()
    expect(page.locator("#cleanup-units").get_by_role("button", name="採否を再確認")).to_have_count(0)
    expect(page.locator("#cleanup-units")).not_to_contain_text("原本更新のため確認が必要")
    saved = next(item for item in page.request.get("/api/collections").json() if item["id"] == mixed["id"])
    assert saved["unit_override_bases"][key] != old_basis
    close_cleanup()

    # なくなったページへの保存済み指定も画面で解除できる。
    missing_key = f"{document_id}:removed-page"
    saved["unit_overrides"][missing_key] = "exclude"
    saved["unit_override_bases"][missing_key] = old_basis
    put_collection(saved)
    open_cleanup(mixed["name"], document["relative_path"])
    page.locator("#cleanup-units").get_by_role("button", name="旧指定を解除").click()
    page.locator("#save-unit-overrides").click()
    expect(page.locator("#cleanup-units").get_by_role("button", name="旧指定を解除")).to_have_count(0)
    expect(page.locator("#cleanup-units")).not_to_contain_text("原本から見つからない指定")
    close_cleanup()
    mixed = next(item for item in page.request.get("/api/collections").json() if item["id"] == mixed["id"])
    assert missing_key not in mixed["unit_overrides"]

    # フォルダ解除時は、そのフォルダの固定選択と個別除外を両方整理する。
    excluded_id = mixed["excluded_document_ids"][0]
    excluded = page.request.get(f"/api/documents/{excluded_id}").json()
    other_id = next(lib for lib in mixed["library_ids"] if lib != excluded["library_id"])
    other = page.request.get(f"/api/documents?library_id={other_id}").json()["items"][0]
    put_collection({**mixed, "selection_mode": "fixed", "document_ids": [excluded_id, other["id"]]})
    open_collection(mixed["name"])
    removed_checkbox = page.locator(f'#collection-libraries input[value="{excluded["library_id"]}"]')
    removed_checkbox.uncheck()
    expect(page.locator("#collection-selection")).to_have_value("1 件を個別に指定")
    expect(removed_checkbox).to_be_enabled()
    page.locator("#collection-form button[type=submit]").click()
    expect(page.locator("#collection-dialog")).not_to_be_visible()
    narrowed = next(item for item in page.request.get("/api/collections").json() if item["id"] == mixed["id"])
    assert narrowed["document_ids"] == [other["id"]] and not narrowed["excluded_document_ids"]
    put_collection(mixed)

    # 原本削除後でも固定選択の対象が残り、明示して外せる。
    documents = page.request.get("/api/documents?limit=100").json()["items"]
    selected_library = next(lib for lib in mixed["library_ids"] if sum(item["library_id"] == lib for item in documents) >= 3)
    chosen = [item for item in documents if item["library_id"] == selected_library and item["id"] != excluded_id][:2]
    fixed_response = page.request.post("/api/collections", data={"name": "固定対象の削除確認", "library_ids": [selected_library], "selection_mode": "fixed", "document_ids": [item["id"] for item in chosen]}, headers=headers)
    assert fixed_response.status == 200, fixed_response.text()
    fixed = fixed_response.json()
    removed_document = page.request.get(f'/api/documents/{chosen[0]["id"]}').json()
    removed_path = Path(removed_document["source_path"])
    original = removed_path.read_bytes()
    try:
        removed_path.unlink()
        response = page.request.post("/api/jobs", data={"library_id": selected_library}, headers=headers)
        assert response.status == 200, response.text()
        wait_jobs(page)
        open_collection(fixed["name"])
        page.locator("#preview-collection").click()
        expect(page.locator("#collection-preview .candidate-row")).to_have_count(2)
        missing = page.locator("#collection-preview .candidate-row").filter(has_text="固定選択の原本が削除済み")
        expect(missing).to_have_count(1)
        missing.locator("input").uncheck()
        page.locator("#collection-form button[type=submit]").click()
        expect(page.locator("#collection-dialog")).not_to_be_visible()
        changed = next(item for item in page.request.get("/api/collections").json() if item["id"] == fixed["id"])
        assert changed["document_ids"] == [chosen[1]["id"]]
    finally:
        removed_path.write_bytes(original)
        response = page.request.post("/api/jobs", data={"library_id": selected_library}, headers=headers)
        assert response.status == 200, response.text()
        wait_jobs(page, 57)


def run(output: Path, exe: Path | None = None) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    screenshots = []
    with tempfile.TemporaryDirectory(prefix="contextgen-kai-ui-") as temp_name:
        temp = Path(temp_name)
        fixtures = temp / "日本語 資料"
        fixtures.mkdir()
        for index in range(55):
            (fixtures / f"業務資料_{index:03d}.txt").write_text(
                f"# 合成資料 {index}\n確認番号 TEST-{index:03d}\n安全な試験用の本文です。\n備品の点検結果を記録します。\n",
                encoding="utf-8",
            )
        # 悪意ある文字列がHTMLとして実行されないことを実際の抽出と表示で確認する。
        (fixtures / "入力文字列の確認.txt").write_text('<img src=x onerror="window.__injected=1">\n入力は文字列として扱います。', encoding="utf-8")
        upload = temp / "今回だけの資料.txt"
        upload.write_text("単発資料の取り込み検証\nローカルの実ファイルを読み取ります。", encoding="utf-8")
        port = reserve_port()
        base = f"http://127.0.0.1:{port}"
        log = temp / "server.log"
        with log.open("w", encoding="utf-8") as log_file:
            runtime = [str(exe.resolve())] if exe else [sys.executable, "-m", "contextgen_kai"]
            env = dict(os.environ)
            if exe:
                if not exe.is_file():
                    raise FileNotFoundError(exe)
                for key in ("PYTHONPATH", "CONTEXTGEN_TESSERACT", "TESSDATA_PREFIX"):
                    env.pop(key, None)
                if os.name == "nt":
                    env["PATH"] = os.environ["SystemRoot"] + "\\System32;" + os.environ["SystemRoot"]
            proc = subprocess.Popen(
                [*runtime, "--state-dir", str(temp / "state"), "--port", str(port), "--no-browser"],
                cwd=ROOT, env=env, stdout=log_file, stderr=subprocess.STDOUT,
            )
            try:
                wait_server(base, proc, log)
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=browser_path(), headless=True)
                    context = browser.new_context(base_url=base, viewport={"width": 1280, "height": 720}, accept_downloads=True, locale="ja-JP")
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    accept_dialog = lambda dialog: dialog.accept()
                    page.on("dialog", accept_dialog)
                    page.goto(base, wait_until="networkidle")
                    expect(page.locator("#connection")).to_contain_text("ローカル接続中")
                    expect(page.get_by_role("heading", name="資料を、使える知識に。")).to_be_visible()
                    assert_laptop(page, "empty-home")
                    assert page.locator("body").evaluate("el => getComputedStyle(el).fontSize") == "16px"
                    page.locator("#font-size").select_option("large")
                    page.reload(wait_until="networkidle")
                    expect(page.locator("#font-size")).to_have_value("large")
                    assert page.locator("body").evaluate("el => getComputedStyle(el).fontSize") == "18px"
                    assert_laptop(page, "large-font-home")
                    page.locator("#font-size").select_option("standard")
                    page.screenshot(path=str(output / "01-home-empty.png"), full_page=True)
                    screenshots.append("01-home-empty.png")

                    # 登録から実ファイルの読み取りまで、画面上の操作で実行する。
                    page.locator("#add-library").click()
                    page.locator("#library-name").fill("合成資料の検証")
                    page.locator("#library-path").fill(str(fixtures))
                    assert_laptop(page, "library-dialog")
                    page.locator("#library-form button[type=submit]").click()
                    expect(page.locator("#library-dialog")).not_to_be_visible()
                    wait_jobs(page, 56)
                    page.locator("#refresh-status").click()
                    expect(page.locator("#stat-total")).to_contain_text("56")

                    # 資料フォルダを実際に移動し、画面から参照先を変更する。
                    moved = temp / "移動後 日本語 資料"
                    fixtures.rename(moved)
                    fixtures = moved
                    page.locator("#libraries").get_by_role("button", name="変更", exact=True).first.click()
                    page.locator("#library-path").fill(str(fixtures))
                    page.locator("#library-form button[type=submit]").click()
                    expect(page.locator("#library-dialog")).not_to_be_visible()
                    wait_jobs(page, 56)
                    page.locator("#refresh-status").click()
                    expect(page.locator("#libraries")).to_contain_text("移動後 日本語 資料")

                    # ページ送り・検索・本文の修正・除外と再収録。
                    page.locator('[data-view="documents"]').click()
                    expect(page.locator("#documents tr")).to_have_count(50)
                    page.locator("#documents input[type=checkbox]").first.check()
                    page.locator(".page-size").first.select_option("25")
                    expect(page.locator("#documents tr")).to_have_count(25)
                    expect(page.locator("#selection-count")).to_contain_text("1 件")
                    page.locator(".page-number").first.fill("3")
                    page.locator(".page-jump").first.locator("button").click()
                    expect(page.locator("#documents tr")).to_have_count(6)
                    expect(page.locator("#next-page")).to_be_disabled()
                    expect(page.locator("#document-result-count")).to_be_focused()
                    page.locator(".page-size").first.select_option("50")
                    expect(page.locator("#documents tr")).to_have_count(50)
                    expect(page.locator("#documents input[type=checkbox]").first).to_be_checked()
                    page.locator("#documents input[type=checkbox]").first.uncheck()
                    page.locator("#next-page").click()
                    expect(page.locator("#documents tr")).to_have_count(6)
                    page.locator("#previous-page").click()
                    page.locator("#document-query").fill("TEST-003")
                    page.locator("#search-form button[type=submit]").click()
                    expect(page.locator("#documents tr")).to_have_count(1)
                    page.locator(".doc-title-button").click()
                    expect(page.locator("#original-text")).to_have_value(re.compile("TEST-003"))
                    page.locator("#edited-text").fill("まだ保存しない入力 TEST-003")
                    # バックグラウンドの再走査・定期取得が編集欄とスクロールを動かさない。
                    live = page.request.get("/api/status").json()
                    page.request.post("/api/jobs", data={"library_id": live["libraries"][0]["id"]}, headers={"X-Contextgen-Token": live["token"]})
                    page.locator("#document-dialog .dialog-body").evaluate("el => el.scrollTop = 40")
                    saved_scroll = page.locator("#document-dialog .dialog-body").evaluate("el => el.scrollTop")
                    page.wait_for_timeout(3500)
                    expect(page.locator("#edited-text")).to_be_focused()
                    assert page.locator("#document-dialog .dialog-body").evaluate("el => el.scrollTop") == saved_scroll
                    page.remove_listener("dialog", accept_dialog)
                    page.once("dialog", lambda dialog: dialog.dismiss())
                    page.locator("#document-dialog [data-close]").first.click()
                    expect(page.locator("#document-dialog")).to_be_visible()
                    expect(page.locator("#edited-text")).to_have_value("まだ保存しない入力 TEST-003")
                    page.on("dialog", accept_dialog)
                    page.locator("#edited-text").fill("修正済みの点検結果です。検証番号 TEST-003。")
                    page.locator("#document-excluded").check()
                    assert_laptop(page, "document-dialog")
                    page.screenshot(path=str(output / "02-document-review.png"))
                    screenshots.append("02-document-review.png")
                    page.locator("#save-document").click()
                    expect(page.locator("#document-dialog")).not_to_be_visible()
                    expect(page.locator("#documents")).to_contain_text("収録対象外")
                    expect(page.locator(".doc-title-button")).to_be_focused()
                    page.locator(".doc-title-button").click()
                    expect(page.locator("#edited-text")).to_have_value("修正済みの点検結果です。検証番号 TEST-003。")
                    page.locator("#document-excluded").uncheck()
                    page.locator("#save-document").click()
                    expect(page.locator("#document-dialog")).not_to_be_visible()

                    # 別画面の保存との競合は上書きせず、履歴から明示して戻せる。
                    page.locator(".doc-title-button").click()
                    current_id = page.request.get("/api/documents?q=TEST-003").json()["items"][0]["id"]
                    current_doc = page.request.get(f"/api/documents/{current_id}").json()
                    token = page.request.get("/api/status").json()["token"]
                    alternate = page.request.put(f"/api/documents/{current_id}", data={"text": "別画面で保存した本文 TEST-003", "expected_hash": current_doc["source_hash"], "expected_revision": current_doc["revision"]}, headers={"X-Contextgen-Token": token})
                    assert alternate.status == 200, alternate.text()
                    page.locator("#edited-text").fill("この画面で編集中の本文 TEST-003")
                    page.locator("#save-document").click()
                    expect(page.locator("#document-dialog .form-error")).not_to_have_text("")
                    expect(page.locator("#edited-text")).to_have_value("この画面で編集中の本文 TEST-003")
                    assert page.request.get(f"/api/documents/{current_id}").json()["edited_text"] == "別画面で保存した本文 TEST-003"
                    page.locator("#document-dialog [data-close]").first.click()
                    page.locator(".doc-title-button").click()
                    page.locator("#history-details summary").click()
                    history = page.locator(".history-row").filter(has_text="修正済みの点検結果").first
                    history.get_by_role("button", name="この本文を復元").click()
                    expect(page.locator("#edited-text")).to_have_value("修正済みの点検結果です。検証番号 TEST-003。")
                    page.locator("#reextract-document").click()
                    expect(page.locator("#document-dialog")).not_to_be_visible()
                    wait_jobs(page)
                    page.locator("#search-form button[type=submit]").click()
                    expect(page.locator("#documents tr")).to_have_count(1)

                    # 個別選択した資料から用途別セットを作成し、実出力のZIPを検査。
                    page.locator("#documents input[type=checkbox]").check()
                    page.locator("#collection-from-selection").click()
                    page.locator("#collection-name").fill("点検結果の確認用")
                    page.locator("#collection-purpose").select_option("questions")
                    page.locator("#collection-instructions").fill("未確認の事項を出典付きで整理してください。")
                    expect(page.locator("#collection-target")).to_have_value("studio")
                    expect(page.locator("#collection-cleanup")).to_have_value("standard")
                    page.locator("#collection-advanced summary").click()
                    page.locator("#collection-audience").fill("設備点検の担当者")
                    page.locator("#add-evaluation").click()
                    page.locator('[data-evaluation="question"]').fill("点検結果は何ですか？")
                    page.locator('[data-evaluation="expected_response"]').fill("資料の確認番号と出典を示す")
                    page.locator("#preview-collection").click()
                    expect(page.locator("#collection-preview .candidate-row")).to_have_count(1)
                    expect(page.locator("#collection-preview input:checked")).to_have_count(1)
                    assert_laptop(page, "collection-dialog")
                    page.locator("#collection-form button[type=submit]").click()
                    expect(page.locator("#collection-dialog")).not_to_be_visible()
                    expect(page.locator("#collections")).to_contain_text("点検結果の確認用")
                    page.get_by_role("button", name="ナレッジを生成", exact=True).click()
                    expect(page.locator("#preflight-dialog")).to_be_visible()
                    page.locator("#confirm-export").click()
                    wait_jobs(page)
                    page.locator("#refresh-exports").click()
                    expect(page.get_by_role("link", name="一式をダウンロード")).to_be_visible(timeout=15000)
                    with page.expect_download() as download_info:
                        page.get_by_role("link", name="一式をダウンロード").first.click()
                    download_path = temp / "knowledge.zip"
                    download_info.value.save_as(download_path)
                    with zipfile.ZipFile(download_path) as archive:
                        assert any(name.endswith("context.md") for name in archive.namelist())
                        md_name = next(name for name in archive.namelist() if name.endswith("context.md"))
                        assert "修正済みの点検結果" in archive.read(md_name).decode("utf-8")
                    page.get_by_role("button", name="指示文", exact=True).first.click()
                    expect(page.locator("#prompt-text")).not_to_have_value("")
                    assert_laptop(page, "prompt-dialog")
                    page.locator("#prompt-dialog [data-close]").first.click()
                    page.get_by_role("button", name="登録状況", exact=True).first.click()
                    expect(page.locator("#handoff-files input")).not_to_have_count(0)
                    page.locator("#handoff-files input").first.check()
                    page.locator("#save-handoff").click()
                    expect(page.locator("#handoff-dialog")).not_to_be_visible()

                    # 予約の作成・変更・停止・手動実行・削除。Windowsの本物のタスクは作らない。
                    page.locator('[data-view="schedules"]').click()
                    page.locator("#add-schedule").click()
                    page.locator("#schedule-name").fill("試験用の定期更新")
                    page.locator("#schedule-frequency").select_option("weekly")
                    page.locator("#schedule-time").fill("23:58")
                    assert_laptop(page, "schedule-dialog")
                    page.locator("#schedule-form button[type=submit]").click()
                    expect(page.locator("#schedule-dialog")).not_to_be_visible()
                    expect(page.locator("#schedules")).to_contain_text("試験用の定期更新")
                    page.locator("#schedules").get_by_role("button", name="停止", exact=True).click()
                    expect(page.locator("#schedules")).to_contain_text("停止中")
                    page.locator("#schedules").get_by_role("button", name="編集", exact=True).click()
                    page.locator("#schedule-frequency").select_option("interval")
                    page.locator("#schedule-interval").fill("120")
                    page.locator("#schedule-form button[type=submit]").click()
                    expect(page.locator("#schedule-dialog")).not_to_be_visible()
                    expect(page.locator("#schedules")).to_contain_text("120 分ごと")
                    page.locator("#schedules").get_by_role("button", name="今すぐ実行", exact=True).click()
                    wait_jobs(page)

                    # バックアップは実JSONとして開けることまで確認。
                    with page.expect_download() as backup_info:
                        page.get_by_role("link", name="バックアップを保存").click()
                    backup_path = temp / "backup.json"
                    backup_info.value.save_as(backup_path)
                    backup = json.loads(backup_path.read_text(encoding="utf-8"))
                    assert isinstance(backup, dict) and backup

                    # 単発ファイルも実際にアップロードする。
                    page.locator('[data-view="home"]').click()
                    page.locator("#upload-files").set_input_files(upload)
                    wait_jobs(page, 57)
                    page.locator("#refresh-status").click()
                    expect(page.locator("#stat-total")).to_contain_text("57")

                    # 複数フォルダにまたがる案件セットと、セット内だけの除外。
                    page.locator('[data-view="exports"]').click()
                    page.locator("#add-collection").click()
                    page.locator("#collection-name").fill("複数フォルダの案件")
                    for choice in page.locator("#collection-libraries input").all():
                        choice.check()
                    page.locator("#preview-collection").click()
                    expect(page.locator("#collection-preview .candidate-row")).to_have_count(57)
                    page.locator("#collection-preview input").first.uncheck()
                    page.locator("#collection-form button[type=submit]").click()
                    expect(page.locator("#collection-dialog")).not_to_be_visible()
                    collections = page.request.get("/api/collections").json()
                    mixed = next(item for item in collections if item["name"] == "複数フォルダの案件")
                    assert len(mixed["library_ids"]) == 2 and len(mixed["excluded_document_ids"]) == 1
                    card = page.locator(".collection-card").filter(has_text="複数フォルダの案件")
                    card.get_by_role("button", name="編集", exact=True).click()
                    page.locator("#preview-collection").click()
                    expect(page.locator("#collection-preview .candidate-row")).to_have_count(57)
                    candidate = page.locator("#collection-preview .candidate-row").filter(has=page.locator("input:checked")).first
                    candidate.get_by_role("button", name="整理前後").click()
                    expect(page.locator("#cleanup-before")).not_to_have_value("")
                    before_cleanup = page.locator("#cleanup-after").input_value()
                    page.locator("#cleanup-units").locator("..").locator("summary").click()
                    page.locator("#cleanup-units select").first.select_option("exclude")
                    page.locator("#save-unit-overrides").click()
                    expect(page.locator("#cleanup-after")).to_have_value("")
                    expect(page.locator("#cleanup-units select")).to_have_count(1)
                    page.locator("#cleanup-units select").first.select_option("include")
                    page.locator("#save-unit-overrides").click()
                    expect(page.locator("#cleanup-after")).to_have_value(before_cleanup)
                    assert_laptop(page, "cleanup-dialog")
                    page.screenshot(path=str(output / "03-cleanup-review.png"))
                    screenshots.append("03-cleanup-review.png")
                    page.locator("#cleanup-dialog [data-close]").first.click()
                    page.locator("#collection-dialog [data-close]").first.click()
                    verify_selection_and_override_review(page)
                    # 複数登録元セットは予約選択肢から除かれる。
                    page.locator('[data-view="schedules"]').click()
                    page.locator("#add-schedule").click()
                    assert "複数フォルダの案件" not in page.locator("#schedule-collection").inner_text()
                    page.locator("#schedule-dialog [data-close]").first.click()

                    # 通知が消えた通常状態を撮影する。
                    expect(page.locator(".toast")).to_have_count(0, timeout=15000)

                    # 全4画面を125%・150%相当のCSS画面サイズで検査する。
                    for width, height in [(1093, 614), (1280, 720)]:
                        page.set_viewport_size({"width": width, "height": height})
                        for view in ("home", "documents", "exports", "schedules"):
                            page.locator(f'[data-view="{view}"]').click()
                            expect(page.locator(f"#view-{view}")).to_be_visible()
                            assert_laptop(page, f"{view}-{width}x{height}")
                            name = f"{view}-{width}x{height}.png"
                            page.screenshot(path=str(output / name), full_page=True)
                            screenshots.append(name)
                        page.locator("#add-schedule").click()
                        assert_laptop(page, f"schedule-dialog-{width}")
                        page.locator("#schedule-dialog [data-close]").first.click()

                    # 大きめ文字でも4画面とフッターの操作を隠さない。
                    page.set_viewport_size({"width": 1093, "height": 614})
                    page.locator("#font-size").select_option("large")
                    for view in ("home", "documents", "exports", "schedules"):
                        page.locator(f'[data-view="{view}"]').click()
                        assert_laptop(page, f"large-font-{view}")
                    page.locator("#font-size").select_option("standard")

                    # 文字サイズ200%は実CSS rootを32pxへ拡大して検査。OSのDPI変更の代替とはしない。
                    page.evaluate("document.documentElement.style.setProperty('font-size', '32px', 'important')")
                    assert page.locator("body").evaluate("el => getComputedStyle(el).fontSize") == "32px"
                    for view in ("home", "documents", "exports", "schedules"):
                        page.locator(f'[data-view="{view}"]').click()
                        assert_laptop(page, f"text-200-percent-{view}")
                    for view, opener, dialog in [("home", "#add-library", "#library-dialog"), ("exports", "#add-collection", "#collection-dialog"), ("schedules", "#add-schedule", "#schedule-dialog")]:
                        page.locator(f'[data-view="{view}"]').click()
                        page.locator(opener).click()
                        assert_laptop(page, f"text-200-percent-{dialog}")
                        submit = page.locator(f"{dialog} [type=submit]")
                        submit.click(trial=True)
                        page.locator(f"{dialog} [data-close]").first.click()
                    page.locator('[data-view="documents"]').click()
                    title_metrics = page.locator(".doc-title-button").first.evaluate("el => ({width:el.getBoundingClientRect().width,font:parseFloat(getComputedStyle(el).fontSize)})")
                    assert title_metrics["width"] >= title_metrics["font"] * 6, title_metrics
                    page.locator(".doc-title-button").first.click()
                    assert_laptop(page, "text-200-percent-document-dialog")
                    page.locator("#save-document").click(trial=True)
                    page.locator("#document-dialog [data-close]").first.click()
                    page.screenshot(path=str(output / "04-text-200-percent.png"), full_page=True)
                    screenshots.append("04-text-200-percent.png")
                    page.evaluate("document.documentElement.style.removeProperty('font-size')")

                    # 悪意ある本文を詳細表示してもイベントが実行されない。
                    page.locator('[data-view="documents"]').click()
                    page.locator("#document-query").fill("入力文字列の確認")
                    page.locator("#search-form button[type=submit]").click()
                    expect(page.locator("#documents tr")).to_have_count(1)
                    page.locator(".doc-title-button").click()
                    expect(page.locator("#original-text")).to_have_value(re.compile("<img"))
                    assert not page.evaluate("Boolean(window.__injected)")
                    page.locator("#document-dialog [data-close]").first.click()
                    page.locator('[data-view="schedules"]').click()
                    page.locator("#schedules").get_by_role("button", name="削除", exact=True).click()
                    expect(page.locator("#schedules")).to_contain_text("定期更新はまだ設定されていません")
                    # 通信失敗時は一覧・現在ページを保持し、一覧先頭へ移動しない。
                    page.locator('[data-view="documents"]').click()
                    page.locator("#document-query").fill("")
                    page.locator("#search-form button[type=submit]").click()
                    page.locator(".page-size").first.select_option("25")
                    expect(page.locator("#documents tr")).to_have_count(25)
                    expect(page.locator("#page-info")).to_have_text("1 / 3 ページ")
                    proc.terminate()
                    proc.wait(timeout=10)
                    page.locator("#next-page").click()
                    expect(page.locator(".toast.error")).not_to_have_count(0)
                    expect(page.locator("#page-info")).to_have_text("1 / 3 ページ")
                    expect(page.locator("#documents tr")).to_have_count(25)
                    expect(page.locator("#next-page")).to_be_focused()
                    assert not errors, errors
                    browser.close()
                result = {"result": "passed", "source": "real packaged EXE HTTP API with synthetic files; no mocks" if exe else "real local HTTP API with synthetic files; no mocks", "documents": 57, "viewports": ["1093x614", "1280x720"], "screenshots": screenshots, "browser_errors": errors, "limits": ["125/150 percent display represented by CSS viewport sizes; actual Windows PC DPI acceptance remains pending"], "checks": ["font-size-persistence", "top-bottom-pagination-selection-focus", "dirty-close-guard", "poll-retains-editor-focus-scroll", "edit-revision-conflict", "history-restore", "document-reextract", "studio-export-preflight", "partial-handoff", "multiple-library-collection", "collection-exclusion", "unit-exclude-include", "stale-unit-explicit-reconfirmation", "missing-unit-override-removal", "library-deselect-clears-document-references", "deleted-fixed-selection-removal", "multiple-library-schedule-filter", "large-font-four-views", "200-percent-text-four-views-and-dialog-controls", "request-failure-retains-page"]}
                (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                return result
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
                # 不具合診断用ログには合成データだけが含まれる。
                (output / "server.log").write_text(log.read_text(errors="replace"), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/ui")
    parser.add_argument("--exe", type=Path, help="配布EXEを起動し、開発用Python PATHを外して同じ画面試験を実行")
    args = parser.parse_args()
    print(json.dumps(run(args.output.resolve(), args.exe), ensure_ascii=False, indent=2))
