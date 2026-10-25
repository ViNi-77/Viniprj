"""トークンの水 — 画面検査（Playwright、同期 API）。

dist/ を http.server で配り、SwiftShader で WebGL を有効にした Chromium で 3 視口を開いて
  1. 横スクロールが出ない
  2. JS エラーがない
  3. WebGL で地球儀が描けている（または fallback の案内が出る）
  4. 「開いてから」の累計が増える
  5. トークン数を 1 億に変えると結果が変わる
  6. 前提を「高」にすると L/秒 が増える
  7. 共有カード PNG が 10 KB を超える
  8. reduced-motion では rAF を使わない
を確かめ、スクリーンショットを scripts/out/ に残す。`--no-build` で npm run build を飛ばす。
ブラウザは $PLAYWRIGHT_BROWSERS_PATH 配下を自分で探す（playwright install はしない）。
"""
from __future__ import annotations

import http.server
import os
import socket
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
OUT = ROOT / "scripts" / "out"
VIEWPORTS = {"laptop125": (1093, 614), "laptop150": (1280, 720), "phone": (390, 844)}
ARGS = ["--no-sandbox", "--disable-background-networking", "--disable-component-update", "--no-first-run", "--disable-sync",
        "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]


def candidates() -> list[str | None]:
    out: list[str | None] = []
    env = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH")
    if env:
        out.append(env)
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    if Path(base).exists():
        for d in sorted(Path(base).glob("chromium-*"), reverse=True):
            for rel in ("chrome-linux/chrome", "chrome-mac/Chromium.app/Contents/MacOS/Chromium", "chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium", "chrome-win/chrome.exe", "chrome-win64/chrome.exe"):
                if (d / rel).exists():
                    out.append(str(d / rel))
    out.append(None)
    return out


def launch(p):  # type: ignore[no-untyped-def]
    last: Exception | None = None
    for exe in candidates():
        try:
            kw = {"args": ARGS}
            if exe:
                kw["executable_path"] = exe
            return p.chromium.launch(**kw)
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"Chromium を起動できない: {last}")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a, **k):  # noqa: ANN002, ANN003
        pass


def make_fixture(root: Path) -> None:
    """/api/me 用の作り物のログ（本物のログを画面検査に使わない）"""
    import datetime as dt
    import json
    proj = root / "claude" / "projects" / "-fixture"
    proj.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    rows = [{"timestamp": now, "message": {"id": f"m{i}", "model": "claude-opus-5-5",
             "usage": {"input_tokens": 50, "cache_creation_input_tokens": 20000, "cache_read_input_tokens": 400000, "output_tokens": 3000}}} for i in range(60)]
    global FIXTURE_FILE
    FIXTURE_FILE = proj / "fixture-session.jsonl"
    FIXTURE_FILE.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    os.environ["CLAUDE_CONFIG_DIR"] = str(root / "claude")
    os.environ["AI_WATER_CACHE"] = str(root / "cache")


FIXTURE_FILE: Path | None = None


def add_fixture_rows(n: int) -> None:
    """作り物のログに応答を n 件足す（ボトルが注がれるか見る）"""
    import datetime as dt
    import json
    assert FIXTURE_FILE
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    base = sum(1 for _ in open(FIXTURE_FILE, encoding="utf-8"))
    with open(FIXTURE_FILE, "a", encoding="utf-8") as f:
        for i in range(n):
            f.write(json.dumps({"timestamp": now, "message": {"id": f"add{base + i}", "model": "claude-opus-5-5",
                    "usage": {"input_tokens": 50, "cache_creation_input_tokens": 20000, "cache_read_input_tokens": 400000, "output_tokens": 3000}}}) + "\n")


def serve(directory: Path, with_me: bool = False) -> tuple[socketserver.TCPServer, str]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    if with_me:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import serve as srvmod  # scripts/serve.py の Handler（/api/me つき）
        handler = lambda *a, **k: srvmod.Handler(*a, directory=str(directory), **k)  # noqa: E731
    else:
        handler = lambda *a, **k: Quiet(*a, directory=str(directory), **k)  # noqa: E731
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", port), handler)
    srv.allow_reuse_address = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{port}/"


def check(cond: bool, msg: str, fails: list[str]) -> None:
    print(("  [OK]   " if cond else "  [FAIL] ") + msg)
    if not cond:
        fails.append(msg)


def main() -> int:
    from playwright.sync_api import sync_playwright

    if "--no-build" not in sys.argv:
        print("== npm run build")
        r = subprocess.run(["npm", "run", "build", "--silent"], cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-2000:], r.stderr[-2000:])
            return 1
    OUT.mkdir(parents=True, exist_ok=True)
    import tempfile
    fixture = tempfile.TemporaryDirectory()
    make_fixture(Path(fixture.name))
    srv, url = serve(DIST, with_me=True)
    srv_static, url_static = serve(DIST, with_me=False)
    fails: list[str] = []
    try:
        with sync_playwright() as p:
            browser = launch(p)
            for name, (w, h) in VIEWPORTS.items():
                print(f"== {name} {w}x{h}")
                ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, locale="ja-JP")
                pg = ctx.new_page()
                errors: list[str] = []
                pg.on("pageerror", lambda e: errors.append(str(e)))
                pg.goto(url)
                pg.wait_for_function("() => window.__awl && document.querySelector('#tk-since').dataset.value")
                pg.wait_for_timeout(1500)
                sw, cw = pg.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                check(sw <= cw, f"横スクロールなし (scrollWidth {sw} <= clientWidth {cw})", fails)
                check(not errors, f"JS エラーなし {errors[:2]}", fails)
                webgl = pg.evaluate("() => window.__awl.webgl")
                fallback = pg.evaluate("() => !document.getElementById('no-webgl').hidden")
                check(webgl or fallback, f"WebGL で描けている（webgl={webgl}）か、案内が出る（{fallback}）", fails)
                if webgl:
                    # 地球儀が実際に描かれている: canvas 中央付近に背景色以外の画素がある
                    nonblank = pg.evaluate("() => window.__awl.readCenter()")
                    check(nonblank > 50, f"地球儀の中央に描画がある（{nonblank} / 4096 画素）", fails)
                # あなたの水（/api/me あり）
                pg.wait_for_selector("#me-card:not([hidden])", timeout=8000)
                me_l = float(pg.get_attribute("#me-today", "data-value"))
                check(me_l > 1, f"あなたの今日が出る（{me_l:.1f} L）", fails)
                if webgl and name.startswith("laptop"):
                    pos = pg.evaluate("""() => { const c = document.getElementById('globe').getBoundingClientRect(); const m = document.getElementById('me-card').getBoundingClientRect(); const t = document.getElementById('ticker').getBoundingClientRect(); const p = document.getElementById('panel').getBoundingClientRect(); return { c: [c.width, c.height], cardTop: m.top, tickerBottom: t.bottom, p: p.left }; }""")
                    hub = pg.evaluate("() => window.__awl.hubScreen('tyo')")
                    ok = hub and hub["visible"] and pos["tickerBottom"] < hub["y"] < pos["cardTop"] and hub["x"] < pos["p"]
                    check(bool(ok), f"開いた直後、自分の地域（東京）がカードとパネルに隠れず見えている {hub}", fails)
                v1 = float(pg.get_attribute("#tk-since", "data-value"))
                pg.wait_for_timeout(1200)
                v2 = float(pg.get_attribute("#tk-since", "data-value"))
                check(v2 > v1 > 0, f"開いてからの累計が増える ({v1:.1f} → {v2:.1f} L)", fails)
                pg.screenshot(path=str(OUT / f"{name}-main.png"))

                # 実ログから → 入力欄と結果が変わる
                pg.click("[data-me='today']")
                pg.wait_for_timeout(200)
                from_me = float(pg.get_attribute("#yt-total", "data-value"))
                check(from_me > 0 and pg.input_value("#yt-tokens") != "100億", f"「実ログから・今日」で結果が変わる ({from_me:.1f} L)", fails)
                # あなたのトークン: 1 億
                before = float(pg.get_attribute("#yt-total", "data-value"))
                pg.fill("#yt-tokens", "1億")
                pg.dispatch_event("#yt-tokens", "input")
                pg.wait_for_timeout(200)
                after = float(pg.get_attribute("#yt-total", "data-value"))
                check(after != before and after > 0, f"1 億トークンで結果が変わる ({before:.0f} → {after:.0f} L)", fails)
                # 共有カード
                png = pg.evaluate("""() => new Promise((resolve) => {
                    const a = document.getElementById('yt-download');
                    const btn = document.getElementById('yt-share');
                    const orig = URL.createObjectURL; URL.createObjectURL = (b) => { resolve(b.size); return orig(b); };
                    btn.click(); setTimeout(() => resolve(-1), 4000); })""")
                check(png > 10000, f"共有カード PNG が 10 KB を超える ({png} bytes)", fails)
                pg.screenshot(path=str(OUT / f"{name}-your.png"))

                # 前提: 高
                lps0 = float(pg.get_attribute("#tk-lps", "data-value"))
                pg.click(".tabs [data-tab='assumptions']")
                pg.click("[data-preset='high']")
                pg.wait_for_timeout(300)
                lps1 = float(pg.get_attribute("#tk-lps", "data-value"))
                check(lps1 > lps0, f"前提「高」で L/秒 が増える ({lps0:.0f} → {lps1:.0f})", fails)
                pg.screenshot(path=str(OUT / f"{name}-assumptions.png"))
                pg.click("[data-preset='mid']")
                pg.click(".tabs [data-tab='method']")
                pg.wait_for_timeout(200)
                pg.screenshot(path=str(OUT / f"{name}-method.png"))
                sw, cw = pg.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                check(sw <= cw, f"方法タブでも横スクロールなし ({sw} <= {cw})", fails)
                ctx.close()

            print("== ボトル画面（/api/me あり）")
            for name, (w, h) in VIEWPORTS.items():
                ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, locale="ja-JP")
                pg = ctx.new_page()
                errors = []
                pg.on("pageerror", lambda e: errors.append(str(e)))
                pg.goto(url)
                pg.wait_for_selector("#me-card:not([hidden])", timeout=8000)
                pg.click(".view-switch [data-view='bottle']")
                pg.wait_for_function("() => window.__awl.bottle() && Number(document.getElementById('bv-liters').dataset.value) > 0", timeout=8000)
                pg.wait_for_timeout(1500)
                check(not errors, f"{name}: ボトル画面に JS エラーなし {errors[:2]}", fails)
                drawn = pg.evaluate("() => window.__awl.readCenter()")
                check(drawn > 300, f"{name}: ボトルが描かれている（{drawn} 点）", fails)
                sw, cw = pg.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                check(sw <= cw, f"{name}: ボトル画面で横スクロールなし ({sw} <= {cw})", fails)
                pg.screenshot(path=str(OUT / f"{name}-bottle.png"))
                if name == "laptop150":
                    # 作り物のログに応答を 3 件足す → 2 秒ごとの取得で注がれる
                    l0 = pg.evaluate("() => window.__awl.bottle().scene.displayLiters()")
                    add_fixture_rows(3)
                    pg.wait_for_function(f"() => window.__awl.bottle().scene.displayLiters() > {l0} + 0.1", timeout=9000)
                    pg.wait_for_timeout(600)
                    last = pg.inner_text("#bv-last")
                    check("応答 3 件" in last, f"実ログが増えると注がれる（{l0:.1f} L → {pg.evaluate('() => window.__awl.bottle().scene.displayLiters()'):.1f} L、{last}）", fails)
                    pg.screenshot(path=str(OUT / f"{name}-bottle-pour.png"))
                    for sc, want in (("week", "棚"), ("year", None), ("world", "東京ドーム")):
                        pg.click(f".bv-scales [data-scale='{sc}']")
                        pg.wait_for_function("() => window.__awl.bottle().scene.cameraDone()", timeout=15000)
                        pg.wait_for_timeout(400)
                        eq = pg.inner_text("#bv-eq") + pg.inner_text("#bv-sub")
                        if want:
                            check(want in eq, f"目盛り「{sc}」: {eq[:40]}…", fails)
                        pg.screenshot(path=str(OUT / f"{name}-bottle-{sc}.png"))
                ctx.close()

            print("== 静的配信（/api/me なし）1093x614")
            ctx = browser.new_context(viewport={"width": 1093, "height": 614}, locale="ja-JP")
            pg = ctx.new_page()
            pg.goto(url_static)
            pg.wait_for_selector("#me-hint:not([hidden])", timeout=8000)
            check(pg.is_hidden("#me-card"), "静的配信ではカードを出さない", fails)
            check("serve.py" in pg.inner_text("#me-hint"), "静的配信では案内を 1 行出す（黙って消さない）", fails)
            check(pg.is_hidden("#yt-me"), "静的配信では「実ログから」を出さない", fails)
            pg.click(".view-switch [data-view='bottle']")
            pg.wait_for_selector("#bv-manual:not([hidden])", timeout=8000)
            l0 = pg.evaluate("() => window.__awl.bottle().scene.displayLiters()")
            pg.click("#bv-send"); pg.click("#bv-send")
            try:
                pg.wait_for_function(f"() => window.__awl.bottle().scene.displayLiters() >= {l0} + 2 * window.__awl.exampleResponseL - 0.005", timeout=8000)
            except Exception:  # noqa: BLE001
                pass
            l1 = pg.evaluate("() => window.__awl.bottle().scene.displayLiters()")
            per = pg.evaluate("() => window.__awl.exampleResponseL")
            check(abs(l1 - l0 - 2 * per) < 0.01, f"静的配信では「注ぐ」2 回で作例の 2 応答ぶん（{2 * per:.2f} L）注がれる ({l0:.2f} → {l1:.2f} L)", fails)
            pg.screenshot(path=str(OUT / "static-bottle.png"))
            pg.click(".view-switch [data-view='globe']")
            sw, cw = pg.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
            check(sw <= cw, f"静的配信でも横スクロールなし ({sw} <= {cw})", fails)
            pg.screenshot(path=str(OUT / "static-main.png"))
            ctx.close()

            print("== reduced-motion 1280x720")
            ctx = browser.new_context(viewport={"width": 1280, "height": 720}, reduced_motion="reduce", locale="ja-JP")
            pg = ctx.new_page()
            pg.goto(url)
            pg.wait_for_function("() => window.__awl")
            pg.wait_for_timeout(1500)
            check(pg.evaluate("() => window.__awl.state.reduced") is True, "reduced-motion が state に反映される", fails)
            check(pg.evaluate("() => window.__awl.rafActive()") is False, "reduced-motion では rAF を使わない", fails)
            v1 = float(pg.get_attribute("#tk-since", "data-value"))
            pg.wait_for_timeout(2200)
            v2 = float(pg.get_attribute("#tk-since", "data-value"))
            check(v2 > v1, f"reduced-motion でも累計は進む ({v1:.0f} → {v2:.0f})", fails)
            pg.screenshot(path=str(OUT / "reduced-main.png"))
            ctx.close()

            print("== methodology.html")
            ctx = browser.new_context(viewport={"width": 1093, "height": 614}, locale="ja-JP")
            pg = ctx.new_page()
            errors2: list[str] = []
            pg.on("pageerror", lambda e: errors2.append(str(e)))
            pg.goto(url + "methodology.html")
            pg.wait_for_selector("#src-L1")
            check(not errors2, "方法ページに JS エラーなし", fails)
            pg.screenshot(path=str(OUT / "methodology.png"), full_page=True)
            ctx.close()
            browser.close()
    finally:
        srv.shutdown()
        srv_static.shutdown()
        fixture.cleanup()

    print()
    if fails:
        print(f"=== 不合格: {len(fails)} 件 ===")
        for f in fails:
            print("  - " + f)
        return 1
    print("=== 合格 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
