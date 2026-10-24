"""補完機 — 画面検査（Playwright、同期 API）。

file:// で completion-machine.html を開き、3 つの視口で
  1. 横スクロールが出ない
  2. JS エラーが出ない
  3. 押せるボタンは次の工程だけ（①だけ有効）
  4. ①を押すと工程が進み、読み出しがモデルと一致する
  5. 工程の途中では次のボタンが押せない（順番の強制）
  6. 8 工程を通すと読み出しが「片付いた」になる
  7. ノート PC の視口で工程列と機械が 1 画面に収まる
  8. reduced-motion では自動が選べず、手動は即時に進む（rAF が回らない）
を確かめ、スクリーンショットを scripts/out/ に残す。明テーマも 1 枚撮る。

ブラウザは $PLAYWRIGHT_BROWSERS_PATH 配下の chromium-*/chrome-linux*/chrome を自分で探す。
`playwright install` は実行しない（CLAUDE.md 5 節）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "out"
URL = (ROOT / "completion-machine.html").as_uri()
URL_LIGHT = (ROOT / "completion-machine-light.html").as_uri()

VIEWPORTS = {
    "laptop125": (1093, 614),   # 1366×768 @125%
    "laptop150": (1280, 720),   # 1920×1080 @150%
    "phone": (390, 844),
}

_ARGS = ["--no-sandbox", "--disable-background-networking", "--disable-component-update",
         "--no-first-run", "--disable-sync", "--disable-default-apps", "--no-default-browser-check"]


def _candidates() -> list[str | None]:
    cands: list[str | None] = []
    for env in ("PLAYWRIGHT_CHROMIUM_PATH", "CHROME_PATH"):
        if os.environ.get(env):
            cands.append(os.environ[env])
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    if Path(base).exists():
        for d in sorted(Path(base).glob("chromium-*"), reverse=True):
            for rel in ("chrome-linux/chrome", "chrome-linux64/chrome", "chrome-mac/Chromium.app/Contents/MacOS/Chromium",
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


READOUT = "document.querySelector('[data-readout]').textContent"
STATES = "[...document.querySelectorAll('.cm-step')].map(b => b.dataset.state + (b.disabled ? '-' : '+')).join(' ')"
EXPECT = "window.CM.model.readout(window.CM.model.stateAfter(%d))"


def press_and_wait(pg, n: int) -> None:  # type: ignore[no-untyped-def]
    """工程 n のボタンを押し、動きが終わるまで待つ"""
    pg.click(f'.cm-step[data-step="{n}"]')
    pg.wait_for_function(f"() => window.CM.live.phaseAt(window.CM.live.clock.now()).n === {n} && window.CM.live.phaseAt(window.CM.live.clock.now()).p >= 1", timeout=15000)
    pg.wait_for_timeout(80)


def main() -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    fails: list[str] = []
    with sync_playwright() as p:
        browser = launch(p)
        for name, (w, h) in VIEWPORTS.items():
            print(f"== {name} {w}x{h}")
            ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, color_scheme="dark", locale="ja-JP")
            pg = ctx.new_page()
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(URL)
            pg.wait_for_function("() => window.CM && window.CM.live")
            pg.wait_for_timeout(200)
            check(pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), "横スクロールなし", fails)
            check(pg.evaluate(STATES) == "next+ locked- locked- locked- locked- locked- locked- locked-", "最初は①だけ押せる", fails)
            r0 = pg.evaluate(READOUT)
            check(r0 == pg.evaluate(EXPECT % 0), f"最初の読み出しがモデルと一致: {r0}", fails)
            pg.screenshot(path=str(OUT / f"{name}-0.png"), full_page=(name == "phone"))
            # ① を押す → 途中では②が押せない → 終わると②が押せる
            pg.click('.cm-step[data-step="1"]')
            pg.wait_for_timeout(300)
            check(pg.evaluate("document.querySelector('.cm-step[data-step=\"2\"]').disabled"), "①の途中では②が押せない", fails)
            check("…" in pg.evaluate(READOUT), "動いている間の読み出しに … が付く", fails)
            pg.wait_for_function("() => window.CM.live.phaseAt(window.CM.live.clock.now()).p >= 1", timeout=15000)
            pg.wait_for_timeout(80)
            r1 = pg.evaluate(READOUT)
            check(r1 == pg.evaluate(EXPECT % 1), f"①の後の読み出しがモデルと一致: {r1}", fails)
            check(pg.evaluate(STATES).startswith("done- next+"), "①が終わると②だけ押せる", fails)
            if name == "laptop125":
                for n in range(2, 9):
                    press_and_wait(pg, n)
                    if n in (3, 6):
                        pg.screenshot(path=str(OUT / f"{name}-step{n}.png"))
                r8 = pg.evaluate(READOUT)
                check(r8 == pg.evaluate(EXPECT % 8) and "片付いた" in r8, f"8 工程を通すと片付いた: {r8}", fails)
                words = pg.evaluate("[...document.querySelectorAll('[data-word]')].map(e => e.querySelector('text').textContent).join('')")
                check(words.strip("　") == "", "片付けた後はテープの語が消える", fails)
                # 最初から
                pg.click(".cm-restart")
                pg.wait_for_timeout(150)
                check(pg.evaluate(STATES).startswith("next+ locked-"), "「最初から」で①に戻る", fails)
            if name.startswith("laptop"):
                fits = pg.evaluate("() => { const p = document.querySelector('.iso-plate').getBoundingClientRect(); const s = document.querySelector('.cm-steps').getBoundingClientRect(); return p.bottom <= window.innerHeight + 1 && s.bottom <= window.innerHeight + 1 && p.right <= window.innerWidth; }")
                check(fits, "工程列と機械が 1 画面に収まる", fails)
            if name == "phone":
                check(pg.evaluate("document.querySelector('.cm-steps').getBoundingClientRect().bottom <= document.querySelector('.iso-plate').getBoundingClientRect().top + 1"), "スマホでは工程列が機械の上に来る", fails)
            # 自動モード: 切り替えると次の工程が自分で始まる
            pg.click('.cm-mode button[data-mode="auto"]')
            pg.wait_for_timeout(1600)
            check(pg.evaluate("window.CM.live.phaseAt(window.CM.live.clock.now()).n") >= 1, "自動にすると次の工程が自分で始まる", fails)
            check(pg.evaluate("[...document.querySelectorAll('.cm-step')].every(b => b.disabled)"), "自動の間はボタンが押せない", fails)
            pg.click('.cm-mode button[data-mode="manual"]')
            check(not errors, "JS エラーなし" + ("" if not errors else f": {errors[:2]}"), fails)
            ctx.close()

        print("== reduced-motion")
        ctx = browser.new_context(viewport={"width": 1280, "height": 720}, reduced_motion="reduce", color_scheme="dark", locale="ja-JP")
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(URL)
        pg.wait_for_function("() => window.CM && window.CM.live")
        check(pg.evaluate("document.querySelector('.cm-mode button[data-mode=\"auto\"]').disabled"), "reduced-motion では自動が選べない", fails)
        pg.evaluate("window.__raf = 0; const o = window.requestAnimationFrame; window.requestAnimationFrame = (f) => { window.__raf++; return o.call(window, f); }; 0")
        pg.click('.cm-step[data-step="1"]')
        pg.wait_for_timeout(300)
        r1 = pg.evaluate(READOUT)
        check(r1 == pg.evaluate(EXPECT % 1), f"reduced-motion では即時に進む: {r1}", fails)
        check(pg.evaluate("window.__raf") <= 2, "reduced-motion では rAF がほぼ回らない", fails)
        check(not errors, "JS エラーなし", fails)
        ctx.close()

        print("== light")
        ctx = browser.new_context(viewport={"width": 1280, "height": 720}, color_scheme="light", locale="ja-JP")
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(URL_LIGHT)
        pg.wait_for_function("() => window.CM && window.CM.live")
        pg.wait_for_timeout(200)
        pg.screenshot(path=str(OUT / "light-0.png"))
        check(pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), "明テーマでも横スクロールなし", fails)
        check(not errors, "明テーマで JS エラーなし", fails)
        ctx.close()

        print("== render")
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, color_scheme="dark", locale="ja-JP")
        pg = ctx.new_page()
        pg.goto(URL + "?render")
        pg.wait_for_function("() => typeof window.seek === 'function'")
        pg.evaluate("window.__raf = 0; const o = window.requestAnimationFrame; window.requestAnimationFrame = (f) => { window.__raf++; return o.call(window, f); }; 0")
        pg.evaluate("window.seek(20)")
        pg.wait_for_timeout(200)
        check(pg.evaluate("window.__raf") == 0, "?render では rAF を起動しない", fails)
        check(pg.evaluate("window.CM.live.phaseAt(20).n") == 5, "seek(20) は工程⑤", fails)
        ctx.close()
        browser.close()

    if fails:
        print(f"=== 不合格: {len(fails)} 件 ===")
        for f in fails:
            print("  -", f)
        return 1
    print("=== 合格 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
