"""トークンの水 — 映像（film.html）の書き出し・静止画・決定論検査。第 1 案の render_film.py を移植。

  python scripts/render_film.py --check                 同じフレームを 2 回描いて画素が一致するか、JS エラーがないか
  python scripts/render_film.py --stills 60             60 フレームごとの PNG と一覧表（scripts/out/film/sheet.png）
  python scripts/render_film.py --mp4 scripts/out/film.mp4 [--fps 60]

dist/ を http.server で配り（module は file:// で動かない）、film.html?record=1 を 1920×1080 で開いて
AWF.seek(f) で 1 フレームずつ描き、canvas.toDataURL で取り出して ffmpeg に流す。先に npm run build が要る。
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
from ui_smoke import launch, serve  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "out" / "film"


def open_page(p, url: str):  # type: ignore[no-untyped-def]
    browser = launch(p)
    page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1, locale="ja-JP")
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url + "film.html?record=1")
    page.wait_for_function("() => window.AWF && typeof window.AWF.seek === 'function'")
    page.wait_for_timeout(300)
    return browser, page, errors


def shot(page, f: int, fmt: str = "png") -> bytes:  # type: ignore[no-untyped-def]
    mime = "image/jpeg" if fmt == "jpeg" else "image/png"
    data = page.evaluate("([f, mime]) => { window.AWF.seek(f); return document.getElementById('stage').toDataURL(mime, 0.95).split(',')[1]; }", [f, mime])
    return base64.b64decode(data)


def main() -> int:
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--stills", type=int, metavar="N")
    ap.add_argument("--mp4", type=Path)
    ap.add_argument("--fps", type=int, default=60)
    a = ap.parse_args()
    if not (ROOT / "dist" / "film.html").exists():
        print("dist/film.html がありません。先に npm run build。")
        return 1
    srv, url = serve(ROOT / "dist")
    rc = 0
    try:
        with sync_playwright() as p:
            browser, page, errors = open_page(p, url)
            frames = page.evaluate("() => window.AWF.frames")
            if a.check:
                bad = 0
                for f in (0, 200, 600, 1000, 1400, 1800, 2200, 2500, frames - 1):
                    h1 = hashlib.sha256(shot(page, f)).hexdigest()
                    shot(page, (f + 500) % frames)
                    h2 = hashlib.sha256(shot(page, f)).hexdigest()
                    print(("  [OK]   " if h1 == h2 else "  [FAIL] ") + f"frame {f} は 2 回描いて同じ")
                    bad += h1 != h2
                print(("  [OK]   JS エラーなし" if not errors else f"  [FAIL] JS エラー {errors[:2]}"))
                bad += bool(errors)
                print("=== 合格 ===" if not bad else f"=== 不合格: {bad} 件 ===")
                rc |= 1 if bad else 0
            if a.stills:
                OUT.mkdir(parents=True, exist_ok=True)
                for old in OUT.glob("f*.png"):
                    old.unlink()
                k = 0
                for f in range(0, frames, a.stills):
                    (OUT / f"f{f:05d}.png").write_bytes(shot(page, f))
                    k += 1
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "1", "-pattern_type", "glob", "-i", str(OUT / "f*.png"),
                                "-vf", f"scale=480:-1,tile=6x{(k + 5) // 6}", "-frames:v", "1", str(OUT / "sheet.png")], check=True)
                print(f"stills: {k} 枚 → {OUT}/sheet.png")
            if a.mp4:
                a.mp4.parent.mkdir(parents=True, exist_ok=True)
                step = max(1, 60 // a.fps)
                proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-vcodec", "mjpeg", "-framerate", str(a.fps), "-i", "-",
                                         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium", "-movflags", "+faststart", str(a.mp4)], stdin=subprocess.PIPE)
                assert proc.stdin
                t0 = time.time()
                for f in range(0, frames, step):
                    proc.stdin.write(shot(page, f, "jpeg"))
                    if f % 600 == 0:
                        print(f"  {f}/{frames} ({time.time() - t0:.0f}s)", flush=True)
                proc.stdin.close()
                proc.wait()
                print(f"mp4: {a.mp4} ({time.time() - t0:.0f}s)")
                rc |= proc.returncode
            browser.close()
    finally:
        srv.shutdown()
    return rc


if __name__ == "__main__":
    sys.exit(main())
