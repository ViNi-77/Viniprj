"""見えない水 — 映像版の書き出し・静止画・決定論検査。

  python scripts/render_film.py --stills 60            # 60 フレームごとに PNG（scripts/out/film/）と一覧表（sheet.png）
  python scripts/render_film.py --mp4 scripts/out/film.mp4 [--fps 60] [--start 0] [--end 2700] [--scenario mid]
  python scripts/render_film.py --check                 # 同じフレームを 2 回描いて一致するか、JS エラーがないか

film.html?record=1 を 1920×1080 で開き、AWF.seek(f) で 1 フレームずつ描いてスクリーンショットを取り、ffmpeg に流す。
ブラウザは $PLAYWRIGHT_BROWSERS_PATH 配下を自分で探す（playwright install はしない）。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui_smoke import launch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "out" / "film"


def open_page(p, scenario: str):  # type: ignore[no-untyped-def]
    browser = launch(p)
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1, locale="ja-JP")
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto((ROOT / "film.html").as_uri() + f"?record=1&scenario={scenario}")
    page.wait_for_function("() => window.AWF && typeof window.AWF.seek === 'function'")
    page.wait_for_timeout(300)  # フォント読み込み
    return browser, page, errors


def shot(page, f: int, fmt: str = "png") -> bytes:  # type: ignore[no-untyped-def]
    """canvas.toDataURL で取る。page.screenshot の PNG は 1 枚 0.7 秒かかるが、こちらは JPEG で 0.05 秒。
    静止画と決定論検査は PNG（無損失）、MP4 は JPEG 品質 0.95（どうせ H.264 に落ちる）。"""
    mime = "image/jpeg" if fmt == "jpeg" else "image/png"
    data = page.evaluate(
        "([f, mime]) => { window.AWF.seek(f); return document.getElementById('stage').toDataURL(mime, 0.95).split(',')[1]; }",
        [f, mime],
    )
    return base64.b64decode(data)


def stills(every: int, scenario: str) -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("f*.png"):
        old.unlink()
    with sync_playwright() as p:
        browser, page, errors = open_page(p, scenario)
        frames = page.evaluate("() => window.AWF.frames")
        n = 0
        for f in range(0, frames, every):
            (OUT / f"f{f:05d}.png").write_bytes(shot(page, f))
            n += 1
        browser.close()
    print(f"stills: {n} 枚 → {OUT}")
    if errors:
        print("JS エラー:", errors)
        return 1
    # 一覧表（6 列）
    sheet = OUT / "sheet.png"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", "1", "-pattern_type", "glob", "-i", str(OUT / "f*.png"),
           "-vf", f"scale=480:-1,tile=6x{(n + 5) // 6}", "-frames:v", "1", str(sheet)]
    subprocess.run(cmd, check=True)
    print(f"sheet: {sheet}")
    return 0


def check(scenario: str) -> int:
    from playwright.sync_api import sync_playwright

    bad = 0
    with sync_playwright() as p:
        browser, page, errors = open_page(p, scenario)
        frames = page.evaluate("() => window.AWF.frames")
        for f in (0, 123, 600, 1234, 1799, 2345, frames - 1):
            a = hashlib.sha256(shot(page, f)).hexdigest()
            shot(page, (f + 400) % frames)  # 別のフレームを挟む
            b = hashlib.sha256(shot(page, f)).hexdigest()
            ok = a == b
            print(("  [OK]   " if ok else "  [FAIL] ") + f"frame {f} は 2 回描いて同じ")
            bad += 0 if ok else 1
        browser.close()
    if errors:
        print("  [FAIL] JS エラー:", errors)
        bad += 1
    else:
        print("  [OK]   JS エラーなし")
    print("=== 合格 ===" if bad == 0 else f"=== 不合格: {bad} 件 ===")
    return 1 if bad else 0


def mp4(path: Path, fps: int, start: int, end: int | None, scenario: str) -> int:
    from playwright.sync_api import sync_playwright

    path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser, page, errors = open_page(p, scenario)
        frames = page.evaluate("() => window.AWF.frames")
        src_fps = page.evaluate("() => window.AWF.fps")
        end = frames if end is None else min(end, frames)
        step = max(1, src_fps // fps)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-vcodec", "mjpeg", "-framerate", str(fps), "-i", "-",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium", "-movflags", "+faststart", str(path)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        assert proc.stdin
        t0 = time.time()
        n = 0
        for f in range(start, end, step):
            proc.stdin.write(shot(page, f, "jpeg"))
            n += 1
            if n % 300 == 0:
                print(f"  {f}/{end} ({time.time() - t0:.0f}s)", flush=True)
        proc.stdin.close()
        proc.wait()
        browser.close()
    print(f"mp4: {path} ({n} フレーム, {fps} fps, {time.time() - t0:.0f}s)")
    if errors:
        print("JS エラー:", errors)
        return 1
    return 0 if proc.returncode == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", type=int, metavar="N", help="N フレームごとに静止画")
    ap.add_argument("--mp4", type=Path, help="出力 MP4")
    ap.add_argument("--check", action="store_true", help="決定論検査")
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--scenario", default="mid", choices=["low", "mid", "high"])
    a = ap.parse_args()
    rc = 0
    if a.check:
        rc |= check(a.scenario)
    if a.stills:
        rc |= stills(a.stills, a.scenario)
    if a.mp4:
        rc |= mp4(a.mp4, a.fps, a.start, a.end, a.scenario)
    if not (a.check or a.stills or a.mp4):
        ap.print_help()
    return rc


if __name__ == "__main__":
    sys.exit(main())
