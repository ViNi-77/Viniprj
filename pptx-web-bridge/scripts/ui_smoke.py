"""UI スモークテスト（Playwright）。サーバを起動し、ブラウザでサンプルを取り込んでキャンバス編集の基本操作を確認する。

- Playwright / Chromium（または Edge/Chrome）が無い環境では skip（終了コード 0）。
- 実行: python scripts/ui_smoke.py [--screenshots DIR]
確認項目: キャンバス描画、サムネイル、ドラッグで bbox が変わる、Undo で戻る、インスペクタの数値入力、要素追加・削除、スライド並べ替え、
          PPTX からテンプレート作成（解析 → 枠のドラッグ → 部品の除外 → 保存 → 適用 → 削除）、Copilot に頼む（指示作成 → 回答の貼り付け → 反映）、
          ノート PC の実寸（1366×768@125% / 1920×1080@150%）で切れずに押せること。
ユーザーテンプレートの保存先は一時ディレクトリ（リポジトリの config/ を汚さない）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import tempfile
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


# ノート PC の実寸（CSS px と拡大率）。1366×768 @125% と 1920×1080 @150%
LAPTOPS = [
    ("1366x768@125%", {"width": 1093, "height": 614}, 1.25),
    ("1920x1080@150%", {"width": 1280, "height": 720}, 1.5),
]


def _clickable(page, selector: str) -> tuple[bool, str]:
    """要素が画面内にあり、その中心を押すとその要素（または子）に当たるか（＝スクロール無しで押せる）。"""
    box = page.locator(selector).first.bounding_box()
    if not box:
        return False, f"{selector}: 位置なし"
    vw, vh = page.viewport_size["width"], page.viewport_size["height"]
    inside = box["x"] >= 0 and box["y"] >= 0 and box["x"] + box["width"] <= vw + 1 and box["y"] + box["height"] <= vh + 1
    hit = page.evaluate(
        "([x, y, sel]) => { var el = document.elementFromPoint(x, y); var t = document.querySelector(sel); return !!(el && t && (el === t || t.contains(el))); }",
        [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, selector],
    )
    return inside and hit, f"{selector}: {'画面内' if inside else '画面外'} / {'押せる' if hit else '別の要素に隠れる'} ({box['x']:.0f},{box['y']:.0f} {box['width']:.0f}×{box['height']:.0f})"


def laptop_checks(browser, base: str, brand: Path, record, shots) -> None:
    """ノート PC の画面でも、切れずに押せることを確かめる（Phase H の受入）。"""
    for label, viewport, dsf in LAPTOPS:
        ctx = browser.new_context(viewport=viewport, device_scale_factor=dsf)
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        try:
            page.goto(base + "/")
            page.evaluate("() => { try { localStorage.clear(); } catch (e) {} }")
            page.reload()
            page.wait_for_selector("#dropzone")
            page.set_input_files("#file-input", str(ROOT / "samples" / "sample_deck.pptx"))
            page.wait_for_selector(".canvas-stage .slide", timeout=30000)
            page.wait_for_function("() => document.getElementById('progress').classList.contains('hidden')", timeout=20000)  # 進捗の帯が消えてから
            page.wait_for_timeout(300)
            no_hscroll = page.evaluate("() => document.documentElement.scrollWidth <= document.documentElement.clientWidth && document.body.scrollHeight <= window.innerHeight + 1")
            record(f"[{label}] 画面全体がはみ出さない（横スクロール無し）", no_hscroll)
            problems = []
            for sel in ("#version-badge", ".pane-right .toolbar button[data-action='add-text']", ".inspector-card .tabs", "#canvas-area"):
                ok, why = _clickable(page, sel)
                if not ok:
                    problems.append(why)
            record(f"[{label}] ヘッダー・ツールバー・タブ・キャンバスが画面内", not problems, "; ".join(problems))
            # 左ペインの一番下のボタンはペイン内スクロールで届く
            page.locator("#btn-copilot").scroll_into_view_if_needed()
            ok, why = _clickable(page, "#btn-copilot")
            record(f"[{label}] 「Copilot に頼む」までスクロールして押せる", ok, why)
            # ログを増やしても他のカードを押し出さない
            page.evaluate("() => { for (var i = 0; i < 200; i++) PWB.core.log('ノート PC 試験の行 ' + i, 'INFO'); }")
            page.click(".inspector-card .tab[data-tab='log']")
            page.wait_for_timeout(200)
            ok, why = _clickable(page, ".inspector-card .tabs")
            canvas_h = page.evaluate("() => document.getElementById('canvas-area').clientHeight")
            record(f"[{label}] ログが増えてもタブとキャンバスが残る", ok and canvas_h >= 100, f"canvas={canvas_h}px {why}")
            page.click(".inspector-card .tab[data-tab='inspector']")
            if shots:
                page.screenshot(path=str(shots / f"laptop_{label.replace('%', '')}_main.png"))
            # テンプレート作成モーダル: 部品が多くても保存ボタンが見えて押せる
            page.click("button[data-action='template-from-pptx']")
            page.wait_for_selector("#tpl-modal:not([hidden])")
            page.set_input_files("#tpl-file", str(brand))
            page.wait_for_function("() => PWB.templateEditor.state().proposal && document.querySelectorAll('#tpl-parts .tpl-part').length > 0", timeout=60000)
            page.wait_for_timeout(500)
            n_parts = page.evaluate("() => document.querySelectorAll('#tpl-parts .tpl-part').length")
            ok, why = _clickable(page, "#tpl-save")
            record(f"[{label}] テンプレート作成の「保存」が見えて押せる（部品 {n_parts} 個）", ok, why)
            ok2, why2 = _clickable(page, "#tpl-canvas")
            record(f"[{label}] テンプレートのプレビューが画面内", ok2, why2)
            if shots:
                page.screenshot(path=str(shots / f"laptop_{label.replace('%', '')}_template.png"))
            page.click("button[data-tpl-act='close']")
            page.wait_for_function("() => document.getElementById('tpl-modal').hidden", timeout=10000)
            # Copilot モーダル
            page.click("button[data-action='copilot']")
            page.wait_for_selector("#copilot-modal:not([hidden])")
            page.wait_for_function("() => document.getElementById('copilot-content').value.length > 0", timeout=20000)
            ok, why = _clickable(page, "button[data-copilot-act='copy-all']")
            record(f"[{label}] Copilot モーダルの「全部コピー」が押せる", ok, why)
            if shots:
                page.screenshot(path=str(shots / f"laptop_{label.replace('%', '')}_copilot.png"))
            page.click("button[data-copilot-act='close']")
            page.wait_for_function("() => document.getElementById('copilot-modal').hidden", timeout=10000)
            # 版のモーダル（小さいダイアログ）
            page.click("#version-badge")
            page.wait_for_selector("#version-modal:not([hidden])", timeout=10000)
            ok, why = _clickable(page, "button[data-action='version-close']")
            record(f"[{label}] 小さいダイアログの「閉じる」が押せる", ok, why)
            page.click("button[data-action='version-close']")
            record(f"[{label}] JavaScript エラーなし", not errors, "; ".join(errors)[:200])
        finally:
            ctx.close()


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
    tmp_store = Path(tempfile.mkdtemp(prefix="pwb_ui_"))
    cfg = json.loads((ROOT / "config" / "app_config.json").read_text(encoding="utf-8"))
    cfg["paths"]["user_templates_file"] = str(tmp_store / "user_templates.json")
    cfg["paths"]["user_template_assets_dir"] = str(tmp_store / "assets")
    (tmp_store / "app_config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, PWB_PORT=str(port), PPTX_WEB_BRIDGE_CONFIG=str(tmp_store / "app_config.json"))
    brand = ROOT / "samples" / "brand_template.pptx"
    if not brand.exists():
        sys.path.insert(0, str(ROOT / "samples"))
        from make_brand_template_pptx import build as build_brand  # type: ignore

        build_brand(brand)
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
            page = browser.new_page(viewport={"width": 1600, "height": 950}, accept_downloads=True)
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

            # --- PPTX からテンプレート作成 ---
            page.click("button[data-action='template-from-pptx']")
            page.wait_for_selector("#tpl-modal:not([hidden])")
            page.set_input_files("#tpl-file", str(brand))
            page.wait_for_function("() => PWB.templateEditor.state().proposal && document.querySelectorAll('#tpl-parts .tpl-part').length > 0", timeout=60000)
            page.wait_for_timeout(500)
            n_parts = page.evaluate("() => PWB.templateEditor.state().parts.length")
            n_all = page.evaluate("() => document.querySelectorAll('#tpl-canvas .sel-box.all').length")
            record("テンプレート推定（部品の一覧と番号付き枠）", n_parts >= 8 and n_all >= 3, f"parts={n_parts} boxes(cover)={n_all}")
            if shots:
                page.screenshot(path=str(shots / "ui_04_template_cover.png"))
            page.click("button[data-tpl-tab='content']")
            page.wait_for_timeout(300)
            page.click(".tpl-part[data-part='content:bar']")
            page.wait_for_selector("#tpl-canvas .sel-box.primary")
            bar_before = page.evaluate("() => JSON.parse(JSON.stringify(PWB.templateEditor.state().proposal.content.bar))")
            bb = page.locator("#tpl-canvas .sel-box.primary").bounding_box()
            assert bb
            page.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
            page.mouse.down()
            page.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2 - 40, steps=8)
            page.mouse.up()
            page.wait_for_timeout(700)
            bar_after = page.evaluate("() => PWB.templateEditor.state().proposal.content.bar")
            record("テンプレートの枠をドラッグ（帯の y が変わり描き直される）", bar_after["y"] < bar_before["y"] - 10, f"y {bar_before['y']:.0f} → {bar_after['y']:.0f}")
            page.fill("#tpl-parts input[data-tpl-box='x'][data-part='content:bar']", "150")
            page.press("#tpl-parts input[data-tpl-box='x'][data-part='content:bar']", "Enter")
            page.wait_for_timeout(600)
            bar_x = page.evaluate("() => PWB.templateEditor.state().proposal.content.bar.x")
            record("テンプレート部品の数値入力", abs(bar_x - 150) < 0.01, f"x={bar_x}")
            page.click("button[data-tpl-remove='content:page_number']")
            page.wait_for_function("() => !PWB.templateEditor.state().proposal.content.page_number", timeout=10000)
            page.wait_for_timeout(500)
            has_pn = page.evaluate("() => (PWB.templateEditor.state().previews.content || '').indexOf('data-tpl=\"page_number\"') >= 0")
            record("部品を外す（ページ番号がプレビューから消える）", not has_pn)
            if shots:
                page.screenshot(path=str(shots / "ui_05_template_content.png"))
            page.fill("#tpl-id", "ui_brand")
            page.fill("#tpl-name", "UI 試験テンプレート")
            page.click("#tpl-save")
            page.wait_for_function("() => document.getElementById('tpl-modal').hidden && document.getElementById('template-select').value === 'ui_brand'", timeout=20000)
            page.wait_for_timeout(800)
            tpl_opt = page.evaluate("() => { var s = document.getElementById('template-select'); return s.options[s.selectedIndex].textContent; }")
            del_visible = page.evaluate("() => !document.getElementById('btn-template-delete').hidden && !document.getElementById('use-base-pptx-label').hidden")
            record("テンプレートの保存と選択（★付き、削除・土台の選択肢が出る）", "ui_brand" in page.evaluate("() => document.getElementById('template-select').value") and tpl_opt.startswith("★") and del_visible, tpl_opt)
            page.wait_for_function("() => document.querySelector('.canvas-stage .tpl-bar') !== null", timeout=20000)
            record("保存したテンプレートでキャンバスが描き直される（帯が出る）", True)
            page.on("dialog", lambda d: d.accept())
            page.click("#btn-template-delete")
            page.wait_for_function("() => Array.prototype.every.call(document.getElementById('template-select').options, function (o) { return o.value !== 'ui_brand'; })", timeout=20000)
            record("ユーザーテンプレートの削除", True)

            # --- Copilot に頼む（API 不使用）: プロンプト作成 → 回答の貼り付け → 反映 ---
            page.click("button[data-action='copilot']")
            page.wait_for_selector("#copilot-modal:not([hidden])")
            page.wait_for_function("() => document.getElementById('copilot-content').value.length > 100", timeout=20000)
            instr = page.evaluate("() => document.getElementById('copilot-instruction').value")
            content = page.evaluate("() => document.getElementById('copilot-content').value")
            record("Copilot 向けの指示と内容が作られる", "Markdown" in instr and content.startswith("# ") and "## 2." in content, f"chars={len(instr) + len(content)}")
            page.select_option("#copilot-purpose", "summarize")
            page.wait_for_function("() => document.getElementById('copilot-instruction').value.indexOf('枚のスライド') >= 0", timeout=20000)
            page.fill("#copilot-options input[data-copilot-opt='count']", "5")
            page.dispatch_event("#copilot-options input[data-copilot-opt='count']", "change")
            page.wait_for_function("() => document.getElementById('copilot-instruction').value.indexOf('5 枚') >= 0", timeout=20000)
            record("用途の切替と枚数の反映", True)
            page.click("button[data-copilot-tab='reply']")
            page.fill("#copilot-reply", "# Copilot 回答\n\n## 1. 背景\n型: カード\n- 課題: 二重作業\n- 原因: 形式が違う\n- 対策: 共通形式\nノート: 2 分で\n\n## 2. 効果\n- 半減\n")
            page.click("button[data-copilot-act='apply']")
            page.wait_for_function("() => document.getElementById('copilot-modal').hidden && qcDebug.presentation().slides.length === 3", timeout=20000)
            page.wait_for_timeout(600)
            kinds = page.evaluate("() => qcDebug.presentation().slides.map(function (s) { return s.layout; })")
            note = page.evaluate("() => qcDebug.presentation().slides[1].notes")
            dia = page.evaluate("() => (qcDebug.presentation().slides[1].elements.filter(function (e) { return e.type === 'diagram'; })[0] || {}).diagram || null")
            record("回答を貼り付けて新しい資料にする（カード図解・ノート）", bool(dia) and dia["type"] == "cards" and len(dia["items"]) == 3 and note == "2 分で", f"layouts={kinds} diagram={dia and dia['type']}")
            if shots:
                page.screenshot(path=str(shots / "ui_06_copilot_reply.png"))

            # --- 図解部品（Phase F）: 図解を追加 → 項目を足す ---
            if not page.is_hidden("#copilot-modal"):
                page.click("button[data-copilot-act='close']")
            page.click("button[data-action='add-diagram'][data-diagram='flow']")
            page.wait_for_function("() => qcDebug.slide().elements.some(function (e) { return e.type === 'diagram'; })", timeout=20000)
            page.wait_for_selector(".canvas-stage .el-diagram", timeout=20000)
            page.evaluate("() => { var el = qcDebug.slide().elements.filter(function (e) { return e.type === 'diagram'; })[0]; PWB.core.focusInspector(el.id); }")
            page.wait_for_selector("[data-act='diagram-add']", timeout=20000)
            page.click("[data-act='diagram-add']")
            page.wait_for_timeout(500)
            dia = page.evaluate("() => qcDebug.slide().elements.filter(function (e) { return e.type === 'diagram'; })[0].diagram")
            children = page.evaluate("() => document.querySelectorAll('.canvas-stage .el-diagram .el').length")
            record("図解を追加して項目を編集できる（キャンバスに展開される）", dia["type"] == "flow" and len(dia["items"]) == 4 and children >= 4, f"items={len(dia['items'])} children={children}")

            # --- Copilot エージェント一式の書き出し ---
            page.click("button[data-action='copilot']")
            page.wait_for_selector("#copilot-modal:not([hidden])")
            page.click("button[data-copilot-tab='agent']")
            page.wait_for_function("() => document.getElementById('copilot-agent-instructions').value.length > 100", timeout=20000)
            files = page.evaluate("() => PWB.copilot.state().agent.files.length")
            name = page.evaluate("() => document.getElementById('copilot-agent-name').value")
            with page.expect_download() as dl:
                page.click("button[data-copilot-act='download-agent']")
            path = dl.value.path()
            size = os.path.getsize(path) if path else 0
            record("Copilot エージェント一式の書き出し（指示文・ナレッジ・ZIP）", files >= 3 and bool(name) and size > 1000, f"knowledge={files} name={name} bytes={size}")

            # --- 差分マージ再取込（Phase G）: 同じ HTML を直して投入 → 差分を選ぶ ---
            if not page.is_hidden("#copilot-modal"):
                page.click("button[data-copilot-act='close']")
                page.wait_for_function("() => document.getElementById('copilot-modal').hidden", timeout=10000)
            v1 = tmp_store / "merge_v1.html"
            v2 = tmp_store / "merge_v2.html"
            v1.write_text("<html><body><section><h2>背景</h2><p>課題は二重作業</p></section></body></html>", encoding="utf-8")
            v2.write_text("<html><body><section><h2>背景</h2><p>課題は二重作業と転記</p></section><section><h2>今後</h2><p>全社展開</p></section></body></html>", encoding="utf-8")
            page.set_input_files("#file-input", str(v1))
            page.wait_for_function("() => qcDebug.presentation() && qcDebug.presentation().meta.import_snapshot", timeout=30000)
            page.wait_for_timeout(400)
            moved = page.evaluate("() => { var el = qcDebug.slide(0).elements.filter(function (e) { return e.role !== 'title'; })[0]; return qcDebug.setBbox(el.id, { x: 50, y: 300, w: 200, h: 60 }) && el.id; }")
            page.set_input_files("#file-input", str(v2))
            page.wait_for_selector("#merge-dialog:not([hidden])", timeout=20000)
            page.click("button[data-action='merge-diff']")
            page.wait_for_selector("#merge-result:not([hidden])", timeout=30000)
            page.wait_for_timeout(600)
            kept = page.evaluate("(id) => { var el = qcDebug.slide(0).elements.filter(function (e) { return e.id === id; })[0]; return el ? { x: el.bbox.x, text: (el.paragraphs || []).map(function (p) { return p.runs.map(function (r) { return r.text; }).join(''); }).join('') } : null; }", moved)
            n_after = page.evaluate("() => qcDebug.presentation().slides.length")
            summary = page.inner_text("#merge-report")
            record("差分マージ再取込（位置を残して本文を更新・ページ追加）", bool(kept) and kept["x"] == 50 and "転記" in kept["text"] and n_after == 2, f"slides={n_after} summary={summary.splitlines()[0] if summary else ''}")
            page.click("button[data-action='merge-report-close']")

            # --- 版の表示（更新できているかの確認） ---
            page.wait_for_function("() => document.getElementById('version-badge').textContent.indexOf('確認中') < 0", timeout=20000)
            badge = page.inner_text("#version-badge")
            page.click("#version-badge")
            page.wait_for_selector("#version-modal:not([hidden])", timeout=10000)
            feature_rows = page.evaluate("() => document.querySelectorAll('#version-body .version-table tbody tr').length")
            build = page.evaluate("() => qcDebug.build()")
            page.click("button[data-action='version-close']")
            tagged = page.evaluate("() => Array.prototype.slice.call(document.querySelectorAll('script[src], link[rel=stylesheet]')).every(function (e) { var u = e.src || e.href; return u.indexOf('/static/') < 0 && u.indexOf('/viewer/') < 0 || u.indexOf('?v=') > 0; })")
            record("版の表示と機能一覧（キャッシュ無効化の印つき）", badge.startswith("版 ") and feature_rows >= 7 and bool(build) and tagged, f"badge={badge} features={feature_rows} tagged={tagged}")

            record("JavaScript エラーなし", not errors, "; ".join(errors)[:200])
            laptop_checks(browser, base, brand, record, shots)
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()
        shutil.rmtree(tmp_store, ignore_errors=True)
    ok = all(r[1] for r in results)
    print(f"\n総合: {'合格' if ok else '不合格'}（{sum(1 for r in results if r[1])} / {len(results)}）")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
