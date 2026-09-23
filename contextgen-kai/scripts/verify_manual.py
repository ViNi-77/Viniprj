"""ソース版または--exeで指定した配布版のマニュアルを実ブラウザで検証する。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

from playwright.sync_api import expect, sync_playwright
from pypdf import PdfReader

from ui_smoke import ROOT, browser_path, reserve_port, wait_server


def verify(output: Path, exe: Path | None = None):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if exe is not None:
        exe = exe.resolve()
        if not exe.is_file():
            raise FileNotFoundError(f"配布EXEが見つかりません: {exe}")
    manual_root = exe.parent if exe is not None else ROOT
    manual = manual_root / "contextgen改_操作マニュアル.html"
    if not manual.is_file():
        raise FileNotFoundError(f"操作マニュアルが見つかりません: {manual}")
    image_prefix = "_internal/manual/images/" if exe is not None else "images/"
    command = [str(exe)] if exe is not None else [sys.executable, "-m", "contextgen_kai"]
    external = []
    errors = []
    widths = []
    allowed_origin = None
    phase = "file"
    console_errors = {"file": [], "http": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=browser_path(), headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, locale="ja-JP")
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: console_errors[phase].append(message.text) if message.type == "error" else None)

        def resources(route):
            url = urlsplit(route.request.url)
            if url.scheme in ("http", "https") and f"{url.scheme}://{url.netloc}" != allowed_origin:
                external.append(route.request.url)
                route.abort()
            else:
                route.continue_()

        page.route("**/*", resources)
        page.goto(manual.as_uri(), wait_until="networkidle")
        expect(page.get_by_role("heading", level=1)).to_contain_text("contextgen 改 操作マニュアル")
        figures = page.locator("main img")
        image_count = figures.count()
        assert image_count >= 10
        # 遅延読込画像もすべて実際に表示し、画像実体を確認する。
        for picture in figures.all():
            picture.scroll_into_view_if_needed()
            picture.evaluate("img => img.loading = 'eager'")
            page.wait_for_function("img => img.complete && img.naturalWidth >= 1000", arg=picture.element_handle())
            relative = picture.get_attribute("src")
            assert relative.startswith(image_prefix) and (manual_root / relative).is_file(), relative
        links = page.locator("a[href]").evaluate_all("items => items.map(a => a.getAttribute('href'))")
        for href in links:
            if href.startswith("#"):
                assert page.locator(f'[id="{href[1:]}"]').count() == 1, href
            elif not href.startswith(("https://", "http://")):
                assert (manual_root / unquote(href)).is_file(), href
        for width, height in [(1440, 1000), (1280, 720), (1093, 614), (760, 900), (390, 844)]:
            page.set_viewport_size({"width": width, "height": height})
            page.evaluate("window.scrollTo({top:0, behavior:'instant'})")
            expect(page.locator('.sidebar nav a.active')).to_have_attribute("href", "#intro")
            values = page.evaluate("({viewport:document.documentElement.clientWidth,content:document.documentElement.scrollWidth})")
            assert values["content"] <= values["viewport"] + 1, (width, values)
            widths.append({"width": width, "height": height, **values})
            page.screenshot(path=str(output / f"manual-{width}.png"))
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.locator(".screenshot").first.click()
        expect(page.locator("#image-viewer")).to_be_visible()
        page.wait_for_function("document.querySelector('#image-large').naturalWidth >= 1000")
        page.screenshot(path=str(output / "manual-zoom.png"))
        page.get_by_role("button", name="閉じる", exact=True).click()
        expect(page.locator("#image-viewer")).not_to_be_visible()
        page.locator("#schedule").scroll_into_view_if_needed()
        page.screenshot(path=str(output / "manual-schedule.png"))
        # 画面で閉じたFAQも印刷時に本文を出せることを確認する。
        first_faq = page.locator("details.faq").first
        first_faq.locator("summary").click()
        assert first_faq.get_attribute("open") is None
        page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
        assert first_faq.get_attribute("open") is not None
        page.pdf(path=str(output / "manual-print.pdf"), print_background=True, prefer_css_page_size=True)
        # Chromiumの印刷イベント発火有無にかかわらず画面の状態を戻す。
        page.evaluate("window.dispatchEvent(new Event('afterprint'))")
        assert first_faq.get_attribute("open") is None
        # file://だけではCSPの不具合を検出できないため、配信APIでも実操作する。
        assert not console_errors["file"], console_errors["file"]
        phase = "http"
        with tempfile.TemporaryDirectory(prefix="contextgen-manual-http-") as directory:
            temp = Path(directory)
            port = reserve_port()
            base = f"http://127.0.0.1:{port}"
            allowed_origin = base
            log = temp / "server.log"
            with log.open("w", encoding="utf-8") as stream:
                proc = subprocess.Popen([*command, "--state-dir", str(temp / "state"), "--port", str(port), "--no-browser"], cwd=manual_root, stdout=stream, stderr=subprocess.STDOUT)
                try:
                    wait_server(base, proc, log)
                    page.goto(base + "/manual/", wait_until="networkidle")
                    expect(page.locator("main img")).to_have_count(image_count)
                    for picture in page.locator("main img").all():
                        picture.scroll_into_view_if_needed()
                        picture.evaluate("img => img.loading = 'eager'")
                        page.wait_for_function("img => img.complete && img.naturalWidth >= 1000", arg=picture.element_handle())
                        assert picture.get_attribute("src").startswith(image_prefix)
                    page.locator(".screenshot").first.click()
                    expect(page.locator("#image-viewer")).to_be_visible()
                    page.wait_for_function("document.querySelector('#image-large').naturalWidth >= 1000")
                    page.locator("#image-close").click()
                    expect(page.locator("#image-viewer")).not_to_be_visible()
                    for href in links:
                        if not href.startswith(("#", "https://", "http://")):
                            response = page.request.get(base + "/manual/" + href)
                            assert response.ok, (href, response.status)
                    assert not console_errors["http"], console_errors["http"]
                finally:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
        browser.close()
    assert not errors, errors
    assert not external, external
    pdf = PdfReader(output / "manual-print.pdf")
    pdf_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    for text in ("資料を、使える知識に", "困ったとき", "原本", "OCR"):
        assert text in pdf_text, text
    result = {"mode": "packaged" if exe is not None else "source", "manual": manual.name, "image_prefix": image_prefix, "server_runtime": str(exe) if exe is not None else "source Python", "images_loaded": image_count, "local_links_verified": len(links), "viewports": widths, "page_errors": errors, "external_requests": external, "image_zoom": "passed", "http_images_links_zoom": "passed", "file_console_errors": console_errors["file"], "http_console_errors": console_errors["http"], "print_pdf_pages": len(pdf.pages), "print_text": "passed"}
    (output / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/manual")
    parser.add_argument("--exe", type=Path, help="配布EXE。同じフォルダのHTMLと同梱画像を検証し、このEXEからサーバーを起動する")
    args = parser.parse_args()
    verify(args.output, args.exe)
