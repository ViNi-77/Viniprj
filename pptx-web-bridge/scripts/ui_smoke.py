"""画面の検査（Playwright）。サーバを起動し、実際のブラウザで 1 本道をなぞる。

なぞる道: 資料を投入 → 読み取った中身を確かめる（型を直す）→ 見た目を決める →
プロンプトをコピー / 一式をダウンロード。

- Playwright / Chromium が無い環境では skip（終了コード 0）。
- 実行: python scripts/ui_smoke.py [--screenshots DIR]

**ノート PC 2 構成（1366×768@125% = 1093×614 / 1920×1080@150% = 1280×720）で
文字とボタンが切れず、横スクロールが出ないこと**が受入条件（CLAUDE.md 6 章）。
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# ノート PC の実寸（CSS px と拡大率）
LAPTOPS = [
    ("1366x768@125%", {"width": 1093, "height": 614}, 1.25),
    ("1920x1080@150%", {"width": 1280, "height": 720}, 1.5),
]

RESULTS: list[tuple[str, bool, str]] = []


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait(url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:  # noqa: S310
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.3)
    return False


# 画像化に不要な外部通信（更新確認・同期・初回設定）を抑える
_ARGS = ["--no-sandbox", "--disable-background-networking", "--disable-component-update",
         "--no-first-run", "--disable-sync", "--disable-default-apps", "--no-default-browser-check"]


def _candidate_executables() -> list[str | None]:
    """Chromium の場所。Playwright の版とブラウザの版がずれている環境があるので、実体を自分で探す。"""
    cands: list[str | None] = []
    env = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH")
    if env:
        cands.append(env)
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if base and Path(base).exists():
        for d in sorted(Path(base).glob("chromium-*"), reverse=True):
            for rel in ("chrome-linux/chrome", "chrome-mac/Chromium.app/Contents/MacOS/Chromium",
                        "chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium",
                        "chrome-win/chrome.exe", "chrome-win64/chrome.exe"):
                if (d / rel).exists():
                    cands.append(str(d / rel))
    cands.append(None)  # Playwright 既定
    return cands


def launch(p):  # type: ignore[no-untyped-def]
    last: Exception | None = None
    for exe in _candidate_executables():
        try:
            kwargs = {"args": _ARGS}
            if exe:
                kwargs["executable_path"] = exe
            return p.chromium.launch(**kwargs)
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(str(last))


def _browser_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            launch(p).close()
        return True
    except Exception:  # noqa: BLE001 - ブラウザが入っていない環境
        return False


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"[{'OK ' if ok else 'NG '}] {name} {detail}")


def visible_and_clickable(page, selector: str) -> tuple[bool, str]:
    """画面内にあって、その場所が本当にその要素で押せるか（他の要素に覆われていないか）。"""
    el = page.query_selector(selector)
    if not el:
        return False, f"{selector}: 見つからない"
    box = el.bounding_box()
    if not box:
        return False, f"{selector}: 表示されていない"
    vw = page.viewport_size["width"]
    vh = page.viewport_size["height"]
    el.scroll_into_view_if_needed()
    box = el.bounding_box()
    inside = box["x"] >= 0 and box["y"] >= 0 and box["x"] + box["width"] <= vw + 1 and box["y"] + box["height"] <= vh + 1
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    hit = page.evaluate(
        "([x, y, sel]) => { const t = document.elementFromPoint(x, y); const want = document.querySelector(sel);"
        " return !!(t && want && (want === t || want.contains(t) || t.contains(want))); }",
        [cx, cy, selector],
    )
    state = ("画面内" if inside else "画面外") + " / " + ("押せる" if hit else "覆われている")
    return bool(inside and hit), f"{selector}: {state} ({int(box['x'])},{int(box['y'])} {int(box['width'])}×{int(box['height'])})"


def no_horizontal_scroll(page) -> tuple[bool, str]:
    got = page.evaluate("() => ({ w: document.documentElement.scrollWidth, c: document.documentElement.clientWidth })")
    return got["w"] <= got["c"] + 1, f"scrollWidth={got['w']} clientWidth={got['c']}"


DIAGRAM_HTML = """<html lang="ja"><head><meta charset="utf-8"><title>受注の流れ</title>
<style>body{background:#F7F9FC;color:#222;font-family:sans-serif}h1{color:#0B3D91}
.grid{display:flex;gap:12px}.card{background:#fff;border:1px solid #D7DEE8;border-radius:10px;padding:16px}</style>
</head><body>
<section><h1>受注から出荷まで</h1><p class="lead">現行プロセス</p>
<div class="grid"><div class="card">① 受注</div><div class="card">② 引当</div><div class="card">③ 出荷</div></div>
</section>
<section><h2>効果</h2><ul><li>62 % の削減</li><li>月 200 件</li></ul></section>
</body></html>"""


def _fixtures(tmp: Path) -> tuple[Path, Path]:
    diagram = tmp / "diagram.html"
    diagram.write_text(DIAGRAM_HTML, encoding="utf-8")
    sys.path.insert(0, str(ROOT / "samples"))
    from make_html_themes import build as build_themes  # type: ignore

    themes = {p.name: p for p in build_themes(tmp / "themes")}
    return diagram, themes["theme_vars.html"]


def main_flow(page, base: str, diagram: Path, theme: Path, shots: Path | None) -> None:
    page.goto(base, wait_until="networkidle")

    # 1. 投入
    page.set_input_files("#file-input", str(diagram))
    page.wait_for_function("() => PWB.state().spec !== null", timeout=30000)
    spec = page.evaluate("() => PWB.state().spec")
    record("資料を投入すると中身が読み取られる", spec["slide_count"] == 2, f"{spec['slide_count']} 枚")

    # 2. 中身の表
    rows = page.query_selector_all("#spec-table tbody tr")
    kinds = page.eval_on_selector_all("#spec-table tbody select", "els => els.map(e => e.value)")
    reasons = page.eval_on_selector_all("#spec-table tbody td.reason", "els => els.map(e => e.textContent.trim())")
    record("頁ごとに型と判定理由が出る", len(rows) == 2 and kinds[0] == "flow" and all(reasons),
           f"型={kinds} 理由={len(reasons)} 件")

    prompt_before = page.inner_text("#prompt")
    page.select_option("#spec-table tbody select >> nth=0", "timeline")
    page.wait_for_function(
        "(prev) => document.querySelector('#prompt').textContent !== prev", arg=prompt_before, timeout=15000)
    reason_now = page.inner_text("#spec-table tbody tr:first-child td.reason")
    record("型を画面で直せて、プロンプトに反映される", "画面で指定" in reason_now and "年表" in page.inner_text("#prompt"), reason_now)
    page.select_option("#spec-table tbody select >> nth=0", "flow")
    page.wait_for_timeout(400)

    # 3. 見た目
    record("元ファイルの配色が出る", "#0B3D91" in page.inner_text("#theme-swatches"),
           page.inner_text("#theme-swatches").split("\n")[0][:30])
    page.check("input[name='theme-src'][value='upload']")
    page.wait_for_selector("#theme-upload:not([hidden])")
    page.set_input_files("#theme-input", str(theme))
    page.wait_for_function("() => PWB.state().uploadedTheme !== null", timeout=30000)
    page.wait_for_function("() => document.querySelector('#prompt').textContent.includes('#6C3CE0')", timeout=15000)
    record("テーマを読み込むと、その配色がプロンプトに入る", True, "#6C3CE0")

    page.check("input[name='theme-src'][value='none']")
    page.wait_for_function("() => !document.querySelector('#prompt').textContent.includes('#')", timeout=15000)
    record("見た目を指示しない選択ができる", True, "色の指示なし")
    page.check("input[name='theme-src'][value='source']")
    page.wait_for_timeout(400)

    # 4. 渡す
    dirs = page.eval_on_selector_all(".direction .d-name", "els => els.map(e => e.textContent.trim())")
    record("渡す向きを 2 つから選べる", len(dirs) == 2, " / ".join(dirs))
    prompt = page.inner_text("#prompt")
    record("プロンプトに文言がそのまま載る",
           all(w in prompt for w in ("受注から出荷まで", "① 受注", "62 % の削減")), f"{len(prompt)} 字")
    record("型ごとの作り方が書かれている", "フロー:" in prompt and "矢印" in prompt)
    record("何をどこに貼るかが画面に出ている", bool(page.inner_text("#direction-how").strip()),
           page.inner_text("#direction-how")[:40])

    page.click("input[name='direction'][value='to_html']")
    page.wait_for_function("() => document.querySelector('#prompt').textContent.includes('HTML ファイル')", timeout=15000)
    record("向きを変えるとプロンプトが差し替わる", True, "to_html")
    page.click("input[name='direction'][value='to_pptx']")
    page.wait_for_timeout(400)

    with page.expect_download(timeout=30000) as dl:
        page.click("[data-action='pack']")
    name = dl.value.suggested_filename
    record("一式（ZIP）をダウンロードできる", name.endswith(".zip"), name)

    # 警告（中身の無い頁）
    empty = diagram.parent / "empty.html"
    empty.write_text('<html lang="ja"><head><meta charset="utf-8"><title>空</title></head><body><section><h1>題名だけ</h1></section></body></html>', encoding="utf-8")
    page.set_input_files("#file-input", str(empty))
    page.wait_for_function("() => PWB.state().spec && PWB.state().spec.slide_count === 1", timeout=30000)
    page.wait_for_selector("#warn-card:not([hidden])", timeout=15000)
    record("読み取れなかったものが画面に出る", "SLIDE_HAS_NO_CONTENT" in page.inner_text("#warn-list"),
           page.inner_text("#warn-list")[:60])

    errors = page.evaluate("() => window.__jsErrors || []")
    record("JavaScript エラーなし", not errors, "; ".join(errors[:2]))
    if shots:
        page.screenshot(path=str(shots / "main.png"), full_page=True)


def laptop_checks(page, base: str, label: str, diagram: Path, theme: Path, shots: Path | None) -> None:
    page.goto(base, wait_until="networkidle")
    ok, detail = no_horizontal_scroll(page)
    record(f"[{label}] 画面全体がはみ出さない（横スクロール無し）", ok, detail)

    for sel in ("header.app-head h1", "#dropzone"):
        ok, detail = visible_and_clickable(page, sel)
        record(f"[{label}] 最初の画面に投入口が見えている", ok, detail)
        break

    page.set_input_files("#file-input", str(diagram))
    page.wait_for_function("() => PWB.state().spec !== null", timeout=30000)
    ok, detail = no_horizontal_scroll(page)
    record(f"[{label}] 中身が出ても横スクロールが出ない", ok, detail)

    for sel in ("#spec-table tbody select", "[data-action='copy']", "[data-action='pack']", "#version-badge"):
        ok, detail = visible_and_clickable(page, sel)
        record(f"[{label}] {sel} が切れずに押せる", ok, detail)

    page.check("input[name='theme-src'][value='upload']")
    page.wait_for_selector("#theme-upload:not([hidden])")
    ok, detail = visible_and_clickable(page, "#theme-dropzone")
    record(f"[{label}] テーマの投入口が切れずに押せる", ok, detail)

    page.click("[data-action='version']")
    page.wait_for_selector("#version-dialog[open]")
    ok, detail = visible_and_clickable(page, "[data-action='version-close']")
    record(f"[{label}] ダイアログの「閉じる」が見えて押せる", ok, detail)
    page.click("[data-action='version-close']")

    errors = page.evaluate("() => window.__jsErrors || []")
    record(f"[{label}] JavaScript エラーなし", not errors, "; ".join(errors[:2]))
    if shots:
        page.screenshot(path=str(shots / f"laptop_{label.replace('%', '').replace('@', '_')}.png"), full_page=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshots", default="")
    args = ap.parse_args()

    if not _browser_available():
        print("[SKIP] Playwright / ブラウザが無いため画面検査を省略")
        return 0
    from playwright.sync_api import sync_playwright

    shots = Path(args.screenshots) if args.screenshots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="pwb_ui_"))
    diagram, theme = _fixtures(tmp)
    cfg = json.loads((ROOT / "config" / "app_config.json").read_text(encoding="utf-8"))
    cfg["paths"]["logs_dir"] = str(tmp / "logs")
    (tmp / "app_config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    port = _free_port()
    env = dict(os.environ, PPTX_WEB_BRIDGE_CONFIG=str(tmp / "app_config.json"))
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT / "backend"), env=env)
    base = f"http://127.0.0.1:{port}/"
    try:
        if not _wait(base + "api/health"):
            print("[NG ] サーバが起動しなかった")
            return 1
        with sync_playwright() as p:
            browser = launch(p)
            try:
                ctx = browser.new_context(accept_downloads=True)
                page = ctx.new_page()
                page.add_init_script("window.__jsErrors = []; window.addEventListener('error', e => window.__jsErrors.push(String(e.message)));")
                main_flow(page, base, diagram, theme, shots)
                ctx.close()

                for label, size, scale in LAPTOPS:
                    ctx = browser.new_context(viewport=size, device_scale_factor=scale, accept_downloads=True)
                    page = ctx.new_page()
                    page.add_init_script("window.__jsErrors = []; window.addEventListener('error', e => window.__jsErrors.push(String(e.message)));")
                    laptop_checks(page, base, label, diagram, theme, shots)
                    ctx.close()
            finally:
                browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    ok = sum(1 for _n, o, _d in RESULTS if o)
    total = len(RESULTS)
    print(f"\n総合: {'合格' if ok == total else '不合格'}（{ok} / {total}）")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
