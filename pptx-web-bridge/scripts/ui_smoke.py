"""UI スモークテスト（Playwright）。サーバを起動し、ブラウザでサンプルを取り込んでキャンバス編集の基本操作を確認する。

- Playwright / Chromium（または Edge/Chrome）が無い環境では skip（終了コード 0）。
- 実行: python scripts/ui_smoke.py [--screenshots DIR]
確認項目: キャンバス描画、サムネイル、ドラッグで bbox が変わる、Undo で戻る、インスペクタの数値入力、要素追加・削除、スライド並べ替え。
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshots", default="")
    args = ap.parse_args()
    from app import rasterize

    if not rasterize.is_available():
        print("[SKIP] Playwright / ブラウザが無いため UI スモークを省略")
        return 0
    from playwright.sync_api import sync_playwright

    port = _free_port()
    env = dict(os.environ, PWB_PORT=str(port))
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"], cwd=str(ROOT / "backend"), env=env)
    results: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        print(f"[{'OK ' if ok else 'NG '}] {name} {detail}")

    try:
        base = f"http://127.0.0.1:{port}"
        if not _wait(base + "/api/health"):
            print("サーバが起動しませんでした")
            return 1
        shots = Path(args.screenshots) if args.screenshots else None
        if shots:
            shots.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            try:
                browser = rasterize._launch(p)  # 同梱 Chromium → Edge / Chrome の順（--no-sandbox 等の引数も共通）
            except Exception as e:  # noqa: BLE001
                print(f"[SKIP] ブラウザを起動できません: {e}")
                return 0
            page = browser.new_page(viewport={"width": 1600, "height": 950})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(base + "/")
            page.evaluate("() => { try { localStorage.clear(); } catch (e) {} }")
            page.reload()
            page.wait_for_selector("#dropzone")
            page.set_input_files("#file-input", str(ROOT / "samples" / "sample_deck.pptx"))
            page.wait_for_selector(".canvas-stage .slide", timeout=30000)
            page.wait_for_function("() => window.qcDebug && qcDebug.rendered() > 0")
            page.wait_for_timeout(600)
            n_slides = page.evaluate("() => qcDebug.presentation().slides.length")
            record("PPTX 取込 → キャンバス描画", n_slides == 6, f"slides={n_slides}")
            page.wait_for_function("() => document.querySelectorAll('.slide-item .thumb .slide').length >= 6", timeout=30000)
            record("サムネイル描画", True)
            if shots:
                page.screenshot(path=str(shots / "ui_01_imported.png"))

            # スライド 2 を選び、最初の文字要素をドラッグ
            page.click(".slide-item[data-slide='1'] .thumb")
            page.wait_for_function("() => qcDebug.state().selectedSlide === 1")
            page.wait_for_timeout(500)
            el_id, before = page.evaluate("() => { var s = qcDebug.slide(); var el = s.elements.filter(function(e){return e.type==='text';})[0]; return [el.id, el.bbox]; }")
            box = page.locator(f".canvas-stage .el[id='{el_id}']").bounding_box()
            assert box
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 10)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] / 2 + 60, box["y"] + 10 + 30, steps=8)
            page.mouse.up()
            page.wait_for_timeout(500)
            after = page.evaluate(f"() => qcDebug.slide().elements.filter(function(e){{return e.id==='{el_id}';}})[0].bbox")
            moved = after["x"] > before["x"] + 20 and after["y"] > before["y"] + 10
            record("ドラッグで移動（bbox が変わる）", moved, f"{before['x']:.0f},{before['y']:.0f} → {after['x']:.0f},{after['y']:.0f}")
            user_bbox = page.evaluate(f"() => !!qcDebug.slide().elements.filter(function(e){{return e.id==='{el_id}';}})[0].user_bbox")
            record("user_bbox が付く", user_bbox)
            if shots:
                page.screenshot(path=str(shots / "ui_02_dragged.png"))

            # リサイズ（右下ハンドル）
            page.wait_for_selector(".sel-handle.h-se")
            hb = page.locator(".sel-handle.h-se").bounding_box()
            assert hb
            page.mouse.move(hb["x"] + 5, hb["y"] + 5)
            page.mouse.down()
            page.mouse.move(hb["x"] + 5 + 80, hb["y"] + 5 + 40, steps=8)
            page.mouse.up()
            page.wait_for_timeout(500)
            resized = page.evaluate(f"() => qcDebug.slide().elements.filter(function(e){{return e.id==='{el_id}';}})[0].bbox")
            record("ハンドルでリサイズ", resized["w"] > after["w"] + 30, f"w {after['w']:.0f} → {resized['w']:.0f}")

            # Undo ×2 で元に戻る
            page.keyboard.press("Escape")
            page.click("#canvas-area")
            page.keyboard.press("Control+z")
            page.keyboard.press("Control+z")
            page.wait_for_timeout(500)
            undone = page.evaluate(f"() => qcDebug.slide().elements.filter(function(e){{return e.id==='{el_id}';}})[0].bbox")
            record("Undo で元に戻る", abs(undone["x"] - before["x"]) < 0.01 and abs(undone["w"] - before["w"]) < 0.01, f"x={undone['x']:.0f} w={undone['w']:.0f}")

            # インスペクタで数値入力
            page.evaluate(f"() => qcDebug.select('{el_id}')")
            page.wait_for_selector("#inspector input[data-prop='bbox.x']")
            page.fill("#inspector input[data-prop='bbox.x']", "100")
            page.press("#inspector input[data-prop='bbox.x']", "Enter")
            page.wait_for_timeout(500)
            xv = page.evaluate(f"() => qcDebug.slide().elements.filter(function(e){{return e.id==='{el_id}';}})[0].bbox.x")
            record("インスペクタの数値入力", abs(xv - 100) < 0.01, f"x={xv}")
            page.fill("#inspector input[data-prop='font_pt']", "30")
            page.press("#inspector input[data-prop='font_pt']", "Enter")
            page.wait_for_timeout(500)
            fs = page.evaluate(f"() => qcDebug.slide().elements.filter(function(e){{return e.id==='{el_id}';}})[0].paragraphs[0].runs[0].size_pt")
            record("フォント pt の明示指定", fs == 30, f"size_pt={fs}")

            # 要素追加・削除
            n0 = page.evaluate("() => qcDebug.slide().elements.length")
            page.click("button[data-action='add-text']")
            page.wait_for_timeout(500)
            n1 = page.evaluate("() => qcDebug.slide().elements.length")
            record("文字要素の追加", n1 == n0 + 1, f"{n0} → {n1}")
            added_selected = page.evaluate("() => qcDebug.selection().length === 1 && qcDebug.selection()[0] === qcDebug.slide().elements[qcDebug.slide().elements.length - 1].id")
            record("追加した要素が選択される", added_selected)
            page.focus("#canvas-area")
            page.keyboard.press("Delete")
            page.wait_for_timeout(500)
            n2 = page.evaluate("() => qcDebug.slide().elements.length")
            record("Delete で削除", n2 == n0, f"{n1} → {n2}")

            # スライドの並べ替え（↓ボタン）
            first_id = page.evaluate("() => qcDebug.presentation().slides[1].id")
            page.click(".slide-item[data-slide='1'] button[data-slide-act='down']")
            page.wait_for_timeout(400)
            moved_id = page.evaluate("() => qcDebug.presentation().slides[2].id")
            record("スライドの並べ替え", moved_id == first_id)
            if shots:
                page.screenshot(path=str(shots / "ui_03_inspector.png"))

            record("JavaScript エラーなし", not errors, "; ".join(errors)[:200])
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()
    ok = all(r[1] for r in results)
    print(f"\n総合: {'合格' if ok else '不合格'}（{sum(1 for r in results if r[1])} / {len(results)}）")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
