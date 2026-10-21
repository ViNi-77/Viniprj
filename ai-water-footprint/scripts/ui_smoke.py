"""見えない水 — 画面検査（Playwright、同期 API）。

file:// で index.html を開き、3 つの視口で
  1. 横スクロールが出ない
  2. 世界カウンターが増える
  3. 「送信した」で回数が 1 増え、液面の path が変わる
  4. シナリオ切替で単価表示が変わり、累計が跳ばない
  5. スライダーで器の段が変わる（viewBox が変わる）
  6. reduced-motion で rAF が回らない（2 fps の setTimeout になる）
を確かめ、スクリーンショットを scripts/out/ に残す。

ブラウザは $PLAYWRIGHT_BROWSERS_PATH 配下の chromium-*/chrome-linux/chrome を自分で探す。
`playwright install` は実行しない（CLAUDE.md 5 節）。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "out"
URL = (ROOT / "index.html").as_uri()

VIEWPORTS = {
    "laptop125": (1093, 614),   # 1366×768 @125%
    "laptop150": (1280, 720),   # 1920×1080 @150%
    "phone": (390, 844),
}

_ARGS = ["--no-sandbox", "--disable-background-networking", "--disable-component-update",
         "--no-first-run", "--disable-sync", "--disable-default-apps", "--no-default-browser-check"]


def _candidates() -> list[str | None]:
    cands: list[str | None] = []
    env = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH")
    if env:
        cands.append(env)
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    if Path(base).exists():
        for d in sorted(Path(base).glob("chromium-*"), reverse=True):
            for rel in ("chrome-linux/chrome", "chrome-mac/Chromium.app/Contents/MacOS/Chromium",
                        "chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium", "chrome-win/chrome.exe", "chrome-win64/chrome.exe"):
                if (d / rel).exists():
                    cands.append(str(d / rel))
    cands.append(None)
    return cands


def launch(p):  # type: ignore[no-untyped-def]
    last: Exception | None = None
    for exe in _candidates():
        try:
            kw = {"args": _ARGS}
            if exe:
                kw["executable_path"] = exe
            return p.chromium.launch(**kw)
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"Chromium を起動できない: {last}")


def check(cond: bool, msg: str, fails: list[str]) -> None:
    print(("  [OK]   " if cond else "  [FAIL] ") + msg)
    if not cond:
        fails.append(msg)


def main() -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    fails: list[str] = []
    with sync_playwright() as p:
        browser = launch(p)
        for name, (w, h) in VIEWPORTS.items():
            print(f"== {name} {w}x{h}")
            ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, color_scheme="light", locale="ja-JP")
            pg = ctx.new_page()
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(URL)
            pg.wait_for_selector("#send-btn")
            pg.wait_for_timeout(600)

            sw, cw = pg.evaluate("() => [document.scrollingElement.scrollWidth, document.scrollingElement.clientWidth]")
            check(sw <= cw, f"横スクロールなし (scrollWidth {sw} <= clientWidth {cw})", fails)
            check(not errors, f"JS エラーなし {errors}", fails)

            v1 = float(pg.get_attribute("#hero-value", "data-value"))
            pg.wait_for_timeout(700)
            v2 = float(pg.get_attribute("#hero-value", "data-value"))
            check(v2 > v1 > 0, f"世界カウンターが増える ({v1:.2f} → {v2:.2f} L)", fails)

            # 幕 2: 送信
            pg.locator("#act-session").scroll_into_view_if_needed()
            pg.wait_for_timeout(300)
            d0 = pg.get_attribute("#bottle-wave", "d") or ""
            pg.click("#send-btn")
            pg.wait_for_function("() => Number(document.querySelector('#session-count').dataset.value) >= 1")
            pg.wait_for_timeout(700)
            d1 = pg.get_attribute("#bottle-wave", "d") or ""
            check(pg.get_attribute("#session-count", "data-value") == "1", "送信で回数が 1 になる", fails)
            check(d0 != d1 and len(d1) > 20, "送信で液面の path が変わる", fails)
            pg.screenshot(path=str(OUT / f"{name}-session.png"))

            # シナリオ切替: 単価が変わり、累計は跳ばない
            before = float(pg.get_attribute("#hero-value", "data-value"))
            pg.click(".seg button[data-scenario='high']")
            pg.wait_for_timeout(120)
            after = float(pg.get_attribute("#hero-value", "data-value"))
            sc = pg.get_attribute("#sc-value", "data-value")
            check(sc == "519", f"切替で単価表示が 519 になる ({sc})", fails)
            check(after >= before and (after - before) < AW_HIGH_RATE * 2.0, f"切替で累計が跳ばない ({before:.1f} → {after:.1f} L)", fails)
            pg.click(".seg button[data-scenario='mid']")

            # 幕 3: スライダーで段が変わる
            pg.locator("#act-ladder").scroll_into_view_if_needed()
            pg.wait_for_timeout(300)
            vb0 = pg.get_attribute("#stage", "viewBox")
            label0 = pg.inner_text("#stage-label")
            pg.locator("#sl-people").fill("100")  # 10,000 人
            pg.locator("#sl-days").fill("365")
            pg.wait_for_timeout(1200)
            vb1 = pg.get_attribute("#stage", "viewBox")
            label1 = pg.inner_text("#stage-label")
            if name.startswith("laptop"):
                fits = pg.evaluate("() => { const r = document.getElementById('stage').getBoundingClientRect(); return r.bottom <= window.innerHeight + 1 && r.top >= 0; }")
                check(fits, "幕 3 がノート PC の 1 画面に収まる（舞台まで見える）", fails)
            else:
                pg.locator("#stage").scroll_into_view_if_needed()
                pg.wait_for_timeout(300)
                fits = pg.evaluate("() => document.getElementById('stage').getBoundingClientRect().height <= window.innerHeight")
                check(fits, "幕 3 の舞台がスマホの 1 画面に収まる", fails)
            check(vb0 != vb1, f"スライダーで viewBox が変わる", fails)
            check(label0 != label1, f"器が変わる ({label0} → {label1})", fails)
            pg.screenshot(path=str(OUT / f"{name}-ladder.png"))

            pg.evaluate("() => window.scrollTo({ top: 0, behavior: 'instant' })")
            pg.wait_for_timeout(400)
            pg.screenshot(path=str(OUT / f"{name}-hero.png"))
            pg.screenshot(path=str(OUT / f"{name}-full.png"), full_page=True)
            ctx.close()

        # ダーク配色と reduced-motion
        print("== dark + reduced-motion 1280x720")
        ctx = browser.new_context(viewport={"width": 1280, "height": 720}, color_scheme="dark", reduced_motion="reduce", locale="ja-JP")
        pg = ctx.new_page()
        pg.goto(URL)
        pg.wait_for_selector("#send-btn")
        pg.wait_for_timeout(800)
        reduced = pg.evaluate("() => AW.state.reduced")
        check(reduced is True, "reduced-motion が state に反映される", fails)
        frames = pg.evaluate("""() => new Promise(r => { let n = 0; const t0 = performance.now();
            const orig = window.requestAnimationFrame; window.requestAnimationFrame = (f) => { n++; return orig(f); };
            setTimeout(() => r(n), 700); })""")
        check(frames == 0, f"reduced-motion では rAF を使わない ({frames} 回)", fails)
        pg.locator("#act-session").scroll_into_view_if_needed()
        pg.click("#send-btn"); pg.click("#send-btn")
        pg.wait_for_timeout(600)
        pg.screenshot(path=str(OUT / "dark-session.png"))
        pg.evaluate("() => window.scrollTo({ top: 0, behavior: 'instant' })")
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(OUT / "dark-hero.png"))
        ctx.close()
        browser.close()

    print()
    if fails:
        print(f"=== 不合格: {len(fails)} 件 ===")
        for f in fails:
            print("  - " + f)
        return 1
    print("=== 合格 ===")
    return 0


AW_HIGH_RATE = 2.5e9 * 519 / 1000 / 86400  # L/s（高シナリオ）


if __name__ == "__main__":
    sys.exit(main())
