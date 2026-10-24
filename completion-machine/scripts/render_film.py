"""補完機 — 動画版の書き出し・静止画・決定論検査。

  python scripts/render_film.py --check                 # 同じ時刻を 2 回描いて画素が一致するか、JS エラーがないか
  python scripts/render_film.py --stills 3              # 3 秒ごとに PNG（scripts/out/film/）と一覧表（sheet.png）
  python scripts/render_film.py --mp4 scripts/out/film.mp4 [--fps 30] [--light]

completion-machine.html?render を開くと時計が止まり、window.seek(t) で時刻 t の画が描ける。
1 フレームずつ #cm-app のスクリーンショットを取り、ffmpeg に流して H.264（yuv420p, faststart）にする。
ブラウザは $PLAYWRIGHT_BROWSERS_PATH 配下を自分で探す（playwright install はしない）。
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui_smoke import launch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "out" / "film"
WIDTH, HEIGHT = 1500, 1320


def open_page(p, light: bool):  # type: ignore[no-untyped-def]
    browser = launch(p)
    ctx = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1, locale="ja-JP", color_scheme="light" if light else "dark")
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    name = "completion-machine-light.html" if light else "completion-machine.html"
    page.goto((ROOT / name).as_uri() + "?render")
    page.wait_for_function("() => typeof window.seek === 'function'")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(300)
    # 画面全体を動画の枠にする: 本文の余白を詰め、#cm-app の矩形で切り抜く
    page.add_style_tag(content="body{margin:0}.iso-page{margin:24px auto}")
    return browser, page, errors


def shot(page, t: float, fmt: str = "png") -> bytes:  # type: ignore[no-untyped-def]
    page.evaluate("t => window.seek(t)", t)
    return page.locator("#cm-app").screenshot(type=fmt, quality=92 if fmt == "jpeg" else None)


def duration(page) -> float:  # type: ignore[no-untyped-def]
    return float(page.evaluate("window.CM.duration"))


def nearly_same(a: bytes, b: bytes) -> tuple[bool, str]:
    """同じ時刻の 2 枚が一致するか。ぼかし（iso-halo）のラスタ化が ±2 階調ほど揺れるので、
    各チャンネル 4 階調以内の差は同じとみなし、それを超える画素が 0.1% 未満なら合格。DOM は同一であることを別に確かめる。"""
    import io

    from PIL import Image, ImageChops  # type: ignore

    A, B = Image.open(io.BytesIO(a)).convert("RGB"), Image.open(io.BytesIO(b)).convert("RGB")
    if A.size != B.size:
        return False, f"大きさが違う {A.size} vs {B.size}"
    diff = ImageChops.difference(A, B).convert("L").point(lambda v: 255 if v > 4 else 0)
    bad = sum(1 for v in diff.getdata() if v)
    ratio = bad / (A.size[0] * A.size[1])
    return ratio < 0.001, f"4 階調超の画素 {bad} ({ratio * 100:.3f}%)"


def check(light: bool) -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, page, errors = open_page(p, light)
        total = duration(page)
        times = [0.5, 11.0, 20.0, 31.5, 38.0, total - 1]
        first = [shot(page, t) for t in times]
        doms = [page.evaluate("document.getElementById('cm-app').outerHTML") for _ in [0]]
        second = list(reversed([shot(page, t) for t in reversed(times)]))
        page.evaluate("t => window.seek(t)", times[0])
        # 最初の時刻に戻したとき DOM が完全に同じか
        shot(page, times[0])
        dom_same = page.evaluate("document.getElementById('cm-app').outerHTML") == doms[0] if False else True
        page.evaluate("t => window.seek(t)", times[-1])
        d0 = page.evaluate("t => { window.seek(t); return document.getElementById('cm-app').outerHTML; }", times[1])
        page.evaluate("t => window.seek(t)", times[3])
        d1 = page.evaluate("t => { window.seek(t); return document.getElementById('cm-app').outerHTML; }", times[1])
        dom_same = d0 == d1
        results = [nearly_same(a, b) for a, b in zip(first, second)]
        same = all(ok for ok, _ in results)
        distinct = len({hashlib.sha1(x).hexdigest() for x in first}) == len(first)
        browser.close()
    for t, (ok, note) in zip(times, results):
        print(f"  [{'OK' if ok else 'FAIL'}]   t={t}: {note}")
    print("  [OK]   同じ時刻は同じ画（±4 階調）" if same else "  [FAIL] 同じ時刻なのに画が違う")
    print("  [OK]   同じ時刻は同じ DOM" if dom_same else "  [FAIL] 同じ時刻なのに DOM が違う")
    print("  [OK]   時刻が違えば画が違う" if distinct else "  [FAIL] 時刻が違うのに画が同じ")
    same = same and dom_same
    print("  [OK]   JS エラーなし" if not errors else f"  [FAIL] JS エラー: {errors[:2]}")
    ok = same and distinct and not errors
    print("=== 合格 ===" if ok else "=== 不合格 ===")
    return 0 if ok else 1


def stills(every: float, light: bool) -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("t*.png"):
        old.unlink()
    with sync_playwright() as p:
        browser, page, errors = open_page(p, light)
        total = duration(page)
        t = 0.0
        files = []
        while t <= total:
            f = OUT / f"t{int(round(t * 10)):04d}.png"
            f.write_bytes(shot(page, t))
            files.append(f)
            t += every
        browser.close()
    try:
        from PIL import Image  # type: ignore

        cols = 4
        imgs = [Image.open(f) for f in files]
        w, h = imgs[0].size
        scale = 360 / w
        tw, th = int(w * scale), int(h * scale)
        rows = (len(imgs) + cols - 1) // cols
        sheet = Image.new("RGB", (tw * cols, th * rows), "black")
        for i, im in enumerate(imgs):
            sheet.paste(im.resize((tw, th)), ((i % cols) * tw, (i // cols) * th))
        sheet.save(OUT / "sheet.png")
        print("sheet", OUT / "sheet.png")
    except ImportError:
        print("PIL がないので一覧表は作らない")
    print(f"{len(files)} 枚", "JS エラーなし" if not errors else f"JS エラー: {errors[:2]}")
    return 0 if not errors else 1


def mp4(path: Path, fps: int, light: bool) -> int:
    from playwright.sync_api import sync_playwright

    path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser, page, errors = open_page(p, light)
        total = duration(page)
        frames = int(total * fps)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-vcodec", "mjpeg", "-framerate", str(fps), "-i", "-",
               "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        assert proc.stdin is not None
        for i in range(frames):
            proc.stdin.write(shot(page, i / fps, "jpeg"))
            if i % (fps * 5) == 0:
                print(f"  {i}/{frames}")
        proc.stdin.close()
        proc.wait()
        browser.close()
    ok = proc.returncode == 0 and not errors
    print(path, f"{frames} frames @ {fps} fps = {total:.1f} s", "OK" if ok else f"NG rc={proc.returncode} {errors[:2]}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="決定論検査")
    ap.add_argument("--stills", type=float, metavar="SEC", help="SEC 秒ごとに静止画")
    ap.add_argument("--mp4", type=Path, help="出力 MP4")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--light", action="store_true", help="明テーマで撮る")
    a = ap.parse_args()
    if a.check:
        return check(a.light)
    if a.stills:
        return stills(a.stills, a.light)
    if a.mp4:
        return mp4(a.mp4, a.fps, a.light)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
