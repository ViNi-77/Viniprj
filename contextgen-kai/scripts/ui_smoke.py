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


def run(output: Path) -> dict:
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
            proc = subprocess.Popen(
                [sys.executable, "-m", "contextgen_kai", "--state-dir", str(temp / "state"), "--port", str(port), "--no-browser"],
                cwd=ROOT, stdout=log_file, stderr=subprocess.STDOUT,
            )
            try:
                wait_server(base, proc, log)
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=browser_path(), headless=True)
                    context = browser.new_context(base_url=base, viewport={"width": 1280, "height": 720}, accept_downloads=True, locale="ja-JP")
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("dialog", lambda dialog: dialog.accept())
                    page.goto(base, wait_until="networkidle")
                    expect(page.locator("#connection")).to_contain_text("ローカル接続中")
                    expect(page.get_by_role("heading", name="資料を、使える知識に。")).to_be_visible()
                    assert_laptop(page, "empty-home")
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
                    page.locator("#next-page").click()
                    expect(page.locator("#documents tr")).to_have_count(6)
                    page.locator("#previous-page").click()
                    page.locator("#document-query").fill("TEST-003")
                    page.locator("#search-form button[type=submit]").click()
                    expect(page.locator("#documents tr")).to_have_count(1)
                    page.locator(".doc-title-button").click()
                    expect(page.locator("#original-text")).to_have_value(re.compile("TEST-003"))
                    page.locator("#edited-text").fill("修正済みの点検結果です。検証番号 TEST-003。")
                    page.locator("#document-excluded").check()
                    assert_laptop(page, "document-dialog")
                    page.screenshot(path=str(output / "02-document-review.png"))
                    screenshots.append("02-document-review.png")
                    page.locator("#save-document").click()
                    expect(page.locator("#document-dialog")).not_to_be_visible()
                    expect(page.locator("#documents")).to_contain_text("収録対象外")
                    page.locator(".doc-title-button").click()
                    expect(page.locator("#edited-text")).to_have_value("修正済みの点検結果です。検証番号 TEST-003。")
                    page.locator("#document-excluded").uncheck()
                    page.locator("#save-document").click()
                    expect(page.locator("#document-dialog")).not_to_be_visible()

                    # 個別選択した資料から用途別セットを作成し、実出力のZIPを検査。
                    page.locator("#documents input[type=checkbox]").check()
                    page.locator("#collection-from-selection").click()
                    page.locator("#collection-name").fill("点検結果の確認用")
                    page.locator("#collection-purpose").select_option("questions")
                    page.locator("#collection-instructions").fill("未確認の事項を出典付きで整理してください。")
                    page.locator("#collection-form button[type=submit]").click()
                    expect(page.locator("#collection-dialog")).not_to_be_visible()
                    expect(page.locator("#collections")).to_contain_text("点検結果の確認用")
                    page.get_by_role("button", name="ナレッジを生成", exact=True).click()
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
                    assert not errors, errors
                    browser.close()
                result = {"result": "passed", "source": "real local HTTP API with synthetic files; no mocks", "documents": 57, "viewports": ["1093x614", "1280x720"], "screenshots": screenshots, "browser_errors": errors}
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
    args = parser.parse_args()
    print(json.dumps(run(args.output.resolve()), ensure_ascii=False, indent=2))
