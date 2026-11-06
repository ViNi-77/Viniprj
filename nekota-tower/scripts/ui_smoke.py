"""ねこ太と十二月の塔 — 画面検査（Playwright、同期 API）。

まず `scripts/build.py --check` で index.html がソースと一致することを確かめ、
file:// で index.html を開いて次を通す（docs/04_受入試験.md と対応）。

  1. 起動→タイトル（エラーなし、フォント読込、整数倍表示、横スクロールなし）
  2. はじめから→なまえ→きろく→塔（10F）
  3. 歩く／NPC に話す／クエスト❿を受注→入力→すてる→教訓→ほうこく→クリア
  4. クエスト❾：宣言→きょうもやめた（同日2回目は拒否）→お守り
  5. 石碑でセーブ→再読込→つづきから
  6. 未保存の警告（beforeunload）と ちゅうだんデータ
  7. メモリーカード：かきだし→よみこみ→改ざん→あいことば
  8. 時間：12/31→1/1 で けっか はっぴょう、時計の疑いで日次チェック停止
  9. reduced-motion で CRT の動きが止まる
スクリーンショットは scripts/out/ に残す。

ブラウザは $PLAYWRIGHT_BROWSERS_PATH 配下の chromium を自分で探す。`playwright install` は実行しない（CLAUDE.md 5 節）。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "out"
URL = (ROOT / "index.html").as_uri()

VIEWPORTS = {
    "laptop125": (1093, 614, 1.25),   # 1366×768 @125%
    "laptop150": (1280, 720, 1.5),    # 1920×1080 @150%
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
            for rel in ("chrome-linux64/chrome", "chrome-linux/chrome", "chrome-mac/Chromium.app/Contents/MacOS/Chromium",
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


FAILS: list[str] = []


def check(cond: bool, msg: str) -> bool:
    print(("  [OK]   " if cond else "  [FAIL] ") + msg)
    if not cond:
        FAILS.append(msg)
    return bool(cond)


# ---- ゲーム操作の小道具 ----------------------------------------------------

def js(page, expr: str):  # type: ignore[no-untyped-def]
    return page.evaluate(f"() => ({expr})")


def scene(page) -> str | None:  # type: ignore[no-untyped-def]
    return js(page, "window.__NEKOTA.scene()")


def press(page, code: str, n: int = 1, wait: int = 90) -> None:  # type: ignore[no-untyped-def]
    for _ in range(n):
        page.keyboard.press(code)
        page.wait_for_timeout(wait)


def wait_scene(page, sid: str, timeout: float = 4.0) -> bool:  # type: ignore[no-untyped-def]
    end = time.time() + timeout
    while time.time() < end:
        if scene(page) == sid:
            return True
        page.wait_for_timeout(50)
    return False


def dismiss(page, ids=("NOTICE",), limit: int = 12) -> None:  # type: ignore[no-untyped-def]
    for _ in range(limit):
        if scene(page) not in ids:
            return
        press(page, "KeyZ", wait=160)


def type_box(page, text: str) -> None:  # type: ignore[no-untyped-def]
    box = page.locator(".nt-input, .nt-textarea")
    box.wait_for(state="visible", timeout=3000)
    box.fill(text)
    page.keyboard.press("Enter")
    page.wait_for_timeout(220)


def advance_dialog_to_choice(page, limit: int = 20) -> dict | None:  # type: ignore[no-untyped-def]
    for _ in range(limit):
        d = js(page, "window.__NEKOTA.dialog()")
        if d is None or d.get("choice"):
            return d
        press(page, "KeyZ", wait=130)
    return js(page, "window.__NEKOTA.dialog()")


def start_new_game(page, name: str = "みき") -> None:  # type: ignore[no-untyped-def]
    page.goto(URL + "?fast=1")
    wait_scene(page, "TITLE")
    press(page, "KeyZ", wait=250)           # PUSH START
    wait_scene(page, "MENU")
    press(page, "KeyZ", wait=250)           # はじめから（セーブなしなら先頭）
    wait_scene(page, "NAME")
    type_box(page, name)
    wait_scene(page, "CONFIRM")
    press(page, "KeyZ", wait=250)           # はい
    wait_scene(page, "SLOT")
    press(page, "KeyZ", wait=500)           # きろく1
    wait_scene(page, "DIALOG")
    js(page, "window.__NEKOTA.endDialog()")
    page.wait_for_timeout(200)


def face(page, x: int, y: int, direction: str) -> None:  # type: ignore[no-untyped-def]
    """(x,y) に立って direction を向く（固い物に向かって1回押す）"""
    js(page, f"window.__NEKOTA.teleport({x}, {y})")
    page.wait_for_timeout(80)
    press(page, {"left": "ArrowLeft", "right": "ArrowRight", "up": "ArrowUp", "down": "ArrowDown"}[direction], wait=250)


def load_slot1(page) -> None:  # type: ignore[no-untyped-def]
    """タイトル → つづきから → きろく1。ちゅうだんデータの確認が出たら「いいえ」"""
    page.goto(URL + "?fast=1")
    wait_scene(page, "TITLE", 5)
    press(page, "KeyZ", wait=250)
    wait_scene(page, "MENU")
    press(page, "KeyZ", wait=300)
    if wait_scene(page, "CONFIRM", 0.6):
        press(page, "KeyZ", wait=300)       # いいえ
    wait_scene(page, "SLOT")
    press(page, "KeyZ", wait=600)


def close_and_catch_dialog(page) -> list[str]:  # type: ignore[no-untyped-def]
    """beforeunload を走らせて閉じ、出たダイアログの種類を返す（出なければ空）"""
    seen: list[str] = []
    page.on("dialog", lambda dlg: (seen.append(dlg.type), dlg.accept()))
    try:
        with page.expect_event("dialog", timeout=1500):
            page.close(run_before_unload=True)
    except Exception:  # noqa: BLE001  タイムアウト＝ダイアログなし
        pass
    time.sleep(0.3)
    return seen


def band_y(floor: int) -> int:
    return (10 - floor) * 13


# ---- 検査本体 ----------------------------------------------------------------

def run_main_flow(page, name: str) -> None:  # type: ignore[no-untyped-def]
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    # 1. 起動（通常の順序：電源→スキップ）
    page.goto(URL)
    page.wait_for_timeout(300)
    check(scene(page) == "BOOT", "起動直後は BOOT")
    press(page, "KeyZ", wait=300)          # 電源
    check(scene(page) == "BOOT", "電源を入れても BOOT（演出中）")
    press(page, "KeyZ", wait=100)          # スキップ
    check(wait_scene(page, "TITLE", 5), "任意キーで TITLE へ")
    fonts = js(page, "window.__NEKOTA.fonts()")
    check(bool(fonts.get("check")), f"埋め込みフォントが使える {fonts}")
    spr = js(page, "window.__NEKOTA.sprites()")
    check(spr.get("ready") and not spr.get("failed"), f"スプライト読込 失敗0 {spr}")
    geo = js(page, "(() => { const r = document.getElementById('game').getBoundingClientRect(); const d = devicePixelRatio; return { w: r.width * d, h: r.height * d, scrollX: document.documentElement.scrollWidth <= document.documentElement.clientWidth }; })()")
    check(abs(geo["w"] / 320 - round(geo["w"] / 320)) < 0.01, f"canvas がデバイスピクセルで整数倍 ({geo['w']:.1f}px)")
    check(geo["scrollX"], "横スクロールが出ない")
    page.screenshot(path=str(OUT / f"{name}_01_title.png"))

    # 2. はじめから
    start_new_game(page)
    st = js(page, "window.__NEKOTA.state()")
    check(st["name"] == "みき" and st["floor"] == 10, f"なまえ=みき, 10F から開始 ({st['name']}, {st['floor']}F)")
    check(scene(page) == "MAP", "プロローグ後は MAP")
    page.screenshot(path=str(OUT / f"{name}_02_map.png"))

    # 3. 歩く
    js(page, "window.__NEKOTA.teleport(20, 7)")
    page.wait_for_timeout(100)
    press(page, "ArrowRight", 4, wait=260)
    page.wait_for_timeout(300)
    pl = js(page, "window.__NEKOTA.player()")
    check(pl["x"] == 24 and pl["dir"] == "right", f"右4回で x が 20→24 ({pl})")

    # 3b. NPC10 に話す → 受注 → クエスト画面
    face(page, 29, 6, "right")
    press(page, "KeyZ", wait=300)
    check(wait_scene(page, "DIALOG"), "依頼人に話しかけると会話")
    d = advance_dialog_to_choice(page)
    check(bool(d and d.get("choice") == ["うける", "あとで"]), f"うける／あとで の選択肢 {d and d.get('choice')}")
    page.screenshot(path=str(OUT / f"{name}_03_dialog.png"))
    press(page, "KeyZ", wait=300)           # うける
    for _ in range(6):
        if js(page, "window.__NEKOTA.dialog()") is None:
            break
        press(page, "KeyZ", wait=150)
    check(wait_scene(page, "QUEST"), "受注後にクエスト画面")
    q = js(page, "window.__NEKOTA.state().quests.q10")
    check(q["status"] == "accepted" and "plan" in q, "❿ が accepted")

    # 3c. ❿ じゅんび：いつ → 追加
    press(page, "KeyZ", wait=200)
    type_box(page, "土曜の午前")
    press(page, "ArrowDown", 4, wait=120)
    press(page, "KeyZ", wait=200)
    type_box(page, "ワインセラー")
    check(wait_scene(page, "MENU"), "項目の後にタグ選択")
    press(page, "KeyZ", wait=200)          # 大きい
    type_box(page, "見栄で買った")
    q = js(page, "window.__NEKOTA.state().quests.q10")
    check(q["plan"]["when"] == "土曜の午前" and len(q["entries"]) == 1 and q["entries"][0]["tag"] == "big", f"いつ と 項目1件（タグ big）が保存 {q['entries']}")
    page.screenshot(path=str(OUT / f"{name}_04_prep.png"))
    # じっこう：すてる
    press(page, "ArrowRight", wait=200)
    press(page, "KeyZ", wait=200)           # 項目メニュー
    press(page, "KeyZ", wait=200)           # すてる
    check(wait_scene(page, "CONFIRM"), "すてる の確認")
    press(page, "KeyZ", wait=500)           # はい（既定）
    q = js(page, "window.__NEKOTA.state().quests.q10")
    check(bool(q["entries"][0].get("doneKey")), "すてた日付が付く")
    # ほうこく：教訓 → 長老に報告
    press(page, "ArrowRight", wait=200)
    page.screenshot(path=str(OUT / f"{name}_05_report.png"))
    press(page, "KeyZ", wait=200)
    type_box(page, "大きい物は 置き場所が 理由だった")
    press(page, "ArrowDown", wait=120)
    press(page, "KeyZ", wait=200)
    type_box(page, "ワインセラーを 粗大ごみに 出した")
    check(wait_scene(page, "CONFIRM"), "ほうこくの確認")
    press(page, "KeyZ", wait=800)
    check(wait_scene(page, "NOTICE", 3), "クリアの儀式（通知）が始まる")
    page.screenshot(path=str(OUT / f"{name}_06_clear.png"))
    dismiss(page)
    st = js(page, "window.__NEKOTA.state()")
    check(st["clears"] == ["q10"] and st["title"] == "みならい", f"clears=['q10'], 称号=みならい ({st['clears']}, {st['title']})")
    check(bool(st["flowers"].get("10")), "10F に花が咲いた")
    check(scene(page) == "MAP", "儀式の後は MAP に戻る")

    # 4. ❾ やめる
    face(page, 11, band_y(9) + 6, "right")
    press(page, "KeyZ", wait=300)
    d = advance_dialog_to_choice(page)
    check(bool(d and d.get("choice") and d["choice"][0] == "うける"), "❾ の依頼人と会話")
    press(page, "KeyZ", wait=300)
    for _ in range(6):
        if js(page, "window.__NEKOTA.dialog()") is None:
            break
        press(page, "KeyZ", wait=150)
    check(wait_scene(page, "QUEST"), "❾ のクエスト画面")
    press(page, "ArrowDown", 4, wait=120)
    press(page, "KeyZ", wait=200)
    type_box(page, "寝る前のSNS")
    type_box(page, "朝が つらいから")
    press(page, "ArrowRight", wait=200)     # じっこう
    press(page, "KeyZ", wait=200)           # 候補のメニュー
    press(page, "KeyZ", wait=400)           # 宣言する
    q9 = js(page, "window.__NEKOTA.state().quests.q9")
    check(bool(q9.get("declared")) and q9["declared"]["text"] == "寝る前のSNS", f"宣言できる {q9.get('declared')}")
    page.screenshot(path=str(OUT / f"{name}_07_q9.png"))
    press(page, "KeyZ", wait=300)           # きょうも やめた
    check(wait_scene(page, "NOTICE"), "チェックで通知")
    dismiss(page)
    q9 = js(page, "window.__NEKOTA.state().quests.q9")
    today = js(page, "window.__NEKOTA.todayKey()")
    check(q9["checks"] == [today], f"きょう({today})のチェックが1件")
    press(page, "KeyZ", wait=300)           # 同日2回目
    check(wait_scene(page, "NOTICE"), "同日2回目は拒否の通知")
    dismiss(page)
    q9 = js(page, "window.__NEKOTA.state().quests.q9")
    check(len(q9["checks"]) == 1 and q9["charms"] == 2, f"チェックは1件のまま、お守り2 ({len(q9['checks'])}, {q9['charms']})")
    press(page, "KeyX", wait=300)           # とじる
    check(wait_scene(page, "MAP"), "X でクエスト画面を閉じる")

    # 5. 石碑でセーブ
    face(page, 9, band_y(9) + 4 if False else 4, "left")   # 10F の石碑 (8,4)
    js(page, "window.__NEKOTA.teleport(9, 4)")
    page.wait_for_timeout(80)
    press(page, "ArrowLeft", wait=250)
    press(page, "KeyZ", wait=300)
    check(wait_scene(page, "SLOT"), "石碑で きろく 画面")
    press(page, "KeyZ", wait=300)           # きろく1（上書き確認）
    check(wait_scene(page, "CONFIRM"), "上書き確認")
    press(page, "ArrowDown", wait=120)
    press(page, "KeyZ", wait=400)
    dismiss(page)
    saved = js(page, "(() => { const r = JSON.parse(localStorage.getItem('nekota-tower:v1:slot:1')); return { v: r.v, name: r.state.name, clears: r.state.clears, dirty: window.__NEKOTA.dirty() }; })()")
    check(saved["v"] == 1 and saved["clears"] == ["q10"] and saved["dirty"] is False, f"きろく1 に v1 で保存、未保存フラグ解除 {saved}")
    page.screenshot(path=str(OUT / f"{name}_08_saved.png"))

    # 5b. 再読込 → つづきから
    page.reload()
    wait_scene(page, "BOOT")
    js(page, "window.__NEKOTA.skipBoot()")
    check(wait_scene(page, "TITLE", 5), "再読込後 TITLE")
    press(page, "KeyZ", wait=250)
    wait_scene(page, "MENU")
    press(page, "KeyZ", wait=300)           # つづきから（セーブありなら初期カーソル）
    check(wait_scene(page, "SLOT"), "つづきから で きろく 画面")
    press(page, "KeyZ", wait=600)
    check(wait_scene(page, "MAP"), "きろく1 を開いて MAP")
    st = js(page, "window.__NEKOTA.state()")
    check(st["name"] == "みき" and st["clears"] == ["q10"] and st["quests"]["q9"]["declared"]["text"] == "寝る前のSNS", "読み込んだ状態が一致")

    # 6. ちゅうだんデータ（visibilitychange）と beforeunload
    press(page, "ArrowDown", wait=300)      # 変更して dirty に
    check(js(page, "window.__NEKOTA.dirty()") is True, "移動で未保存になる")
    js(page, "(() => { Object.defineProperty(document, 'hidden', { value: true, configurable: true }); document.dispatchEvent(new Event('visibilitychange')); Object.defineProperty(document, 'hidden', { value: false, configurable: true }); return 1; })()")
    check(js(page, "localStorage.getItem('nekota-tower:v1:suspend') !== null"), "隠れたときに ちゅうだんデータ を書く")
    seen = close_and_catch_dialog(page)
    check("beforeunload" in seen, f"未保存で閉じると beforeunload の確認が出る {seen}")
    check(not errors, f"ページエラーなし {errors[:3]}")


def run_resume_and_card(ctx, name: str) -> None:  # type: ignore[no-untyped-def]
    """同じコンテキスト（同じ localStorage）で、ちゅうだんデータの復帰とメモリーカードを検査"""
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL + "?fast=1")
    wait_scene(page, "TITLE", 5)
    press(page, "KeyZ", wait=250)
    wait_scene(page, "MENU")
    press(page, "KeyZ", wait=300)           # つづきから
    check(wait_scene(page, "CONFIRM"), "ちゅうだんデータがあると復帰を提案")
    press(page, "ArrowDown", wait=120)      # はい
    press(page, "KeyZ", wait=600)
    check(wait_scene(page, "MAP") and js(page, "window.__NEKOTA.dirty()") is True, "ちゅうだんデータを開くと未保存扱いで MAP")
    # 負のケース：セーブ済みなら閉じても確認なし
    js(page, "window.__NEKOTA.teleport(9, 4)")
    page.wait_for_timeout(80)
    press(page, "ArrowLeft", wait=250)
    press(page, "KeyZ", wait=300)
    wait_scene(page, "SLOT")
    press(page, "KeyZ", wait=300)
    wait_scene(page, "CONFIRM")
    press(page, "ArrowDown", wait=120)
    press(page, "KeyZ", wait=400)
    dismiss(page)
    check(js(page, "window.__NEKOTA.dirty()") is False, "セーブで未保存解除")
    seen = close_and_catch_dialog(page)
    check("beforeunload" not in seen, "セーブ済みなら閉じても確認が出ない")

    # メモリーカード
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL + "?fast=1")
    wait_scene(page, "TITLE", 5)
    press(page, "KeyZ", wait=250)
    wait_scene(page, "MENU")
    press(page, "ArrowDown", wait=120)      # つづきから → メモリーカード
    press(page, "KeyZ", wait=300)
    check(wait_scene(page, "CARDMENU"), "タイトルから メモリーカード")
    page.screenshot(path=str(OUT / f"{name}_09_card.png"))
    press(page, "KeyZ", wait=300)           # かきだす
    check(wait_scene(page, "MENU"), "かきだす きろく の選択")
    with page.expect_download() as dl:
        press(page, "KeyZ", wait=200)       # きろく1
        type_box(page, "")                  # あいことばなし
    download = dl.value
    path = download.path()
    data = Path(path).read_bytes()
    text = data.decode("utf-8-sig")
    check(data.startswith(b"\xef\xbb\xbf") and text.splitlines()[0] == "slot,line,data", f"カードは BOM 付き CSV（{download.suggested_filename}）")
    check(download.suggested_filename.startswith("nekota-tower_card_") and download.suggested_filename.endswith("_slot1.csv"), "ファイル名の形式")
    page.wait_for_timeout(300)
    status = js(page, "window.__NEKOTA.cardStatus()")
    check("かきだしました" in (status or ""), f"かきだし完了の表示 {status}")
    # 改ざん → あいことばが ちがう
    lines = text.splitlines()
    kana = list(lines[1].split(",", 2)[2])
    kana[5] = "あ" if kana[5] != "あ" else "い"
    tampered = "﻿" + "\n".join([lines[0], ",".join(lines[1].split(",", 2)[:2] + ["".join(kana)])] + lines[2:]) + "\n"
    page.set_input_files("#filepick", {"name": "bad.csv", "mimeType": "text/csv", "buffer": tampered.encode("utf-8")})
    page.wait_for_timeout(800)
    status = js(page, "window.__NEKOTA.cardStatus()")
    check(status == "あいことばが ちがうようです", f"改ざんしたカードは拒否 ({status})")
    # 正しいカード → きろく2 へ
    page.set_input_files("#filepick", {"name": "good.csv", "mimeType": "text/csv", "buffer": data})
    page.wait_for_timeout(800)
    check(wait_scene(page, "MENU"), "読み込んだカードの保存先を聞く")
    press(page, "ArrowDown", wait=120)
    press(page, "KeyZ", wait=500)
    status = js(page, "window.__NEKOTA.cardStatus()")
    slot2 = js(page, "(() => { const r = localStorage.getItem('nekota-tower:v1:slot:2'); return r ? JSON.parse(r).state.name : null; })()")
    check("よみこみました" in (status or "") and slot2 == "みき", f"きろく2 に復元 ({status}, {slot2})")
    # あいことば付き
    press(page, "KeyZ", wait=300)           # かきだす
    wait_scene(page, "MENU")
    with page.expect_download() as dl2:
        press(page, "KeyZ", wait=200)
        type_box(page, "ねこ")
        type_box(page, "ねこ")
    data2 = Path(dl2.value.path()).read_bytes()
    page.wait_for_timeout(300)
    page.set_input_files("#filepick", {"name": "pw.csv", "mimeType": "text/csv", "buffer": data2})
    page.wait_for_timeout(900)
    box = js(page, "window.__NEKOTA.inputbox()")
    check(bool(box) and "あいことば" in box["title"], f"あいことば付きカードは あいことば を聞く {box}")
    type_box(page, "まちがい")
    page.wait_for_timeout(900)
    status = js(page, "window.__NEKOTA.cardStatus()")
    check(status == "あいことばが ちがうようです", f"誤った あいことば は同じ文言で拒否 ({status})")
    page.set_input_files("#filepick", {"name": "pw.csv", "mimeType": "text/csv", "buffer": data2})
    page.wait_for_timeout(900)
    type_box(page, "ねこ")
    check(wait_scene(page, "MENU"), "正しい あいことば で復号して保存先を聞く")
    press(page, "KeyX", wait=200)
    page.screenshot(path=str(OUT / f"{name}_10_card_done.png"))
    check(not errors, f"ページエラーなし（カード）{errors[:3]}")


def run_time(browser, name: str) -> None:  # type: ignore[no-untyped-def]
    """時計を 12/31 23:59:50 JST に固定し、年明けで けっか はっぴょう になる。TZ は LA でも同じ日付キー"""
    for tz in ("America/Los_Angeles", "Asia/Tokyo"):
        ctx = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1, locale="ja-JP", timezone_id=tz)
        page = ctx.new_page()
        page.clock.install(time=dt.datetime(2026, 12, 31, 14, 59, 50, tzinfo=dt.timezone.utc))
        start_new_game(page)
        key = js(page, "window.__NEKOTA.todayKey()")
        check(key == "2026-12-31" and js(page, "window.__NEKOTA.phase()") == "final", f"[{tz}] JST の日付キーは 2026-12-31、局面 final ({key})")
        page.clock.run_for(20_000)
        check(js(page, "window.__NEKOTA.todayKey()") == "2027-01-01", f"[{tz}] 20秒後に 2027-01-01")
        # 保存 → 再読込 → つづきから → けっか はっぴょう
        js(page, "window.__NEKOTA.teleport(9, 4)")
        page.wait_for_timeout(80)
        press(page, "ArrowLeft", wait=250)
        press(page, "KeyZ", wait=300)
        wait_scene(page, "SLOT")
        press(page, "KeyZ", wait=300)
        wait_scene(page, "CONFIRM")
        press(page, "ArrowDown", wait=120)
        press(page, "KeyZ", wait=400)
        dismiss(page)
        load_slot1(page)
        check(wait_scene(page, "ENDING"), f"[{tz}] 年が明けたら けっか はっぴょう")
        if tz == "Asia/Tokyo":
            page.screenshot(path=str(OUT / f"{name}_11_result.png"))
        ctx.close()
    # 時計の疑い：未来の savedAt を持つ記録
    ctx = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1, locale="ja-JP")
    page = ctx.new_page()
    start_new_game(page)
    js(page, "(() => { const k = 'nekota-tower:v1:slot:1'; const r = JSON.parse(localStorage.getItem(k)); r.savedAt = new Date(Date.now() + 3 * 86400000).toISOString(); localStorage.setItem(k, JSON.stringify(r)); return 1; })()")
    load_slot1(page)
    js(page, "window.__NEKOTA.endDialog()")   # プロローグ前の保存なので プロローグが再生される
    dismiss(page)
    check(wait_scene(page, "MAP") and js(page, "window.__NEKOTA.state().flags.clockSuspect") is True, "未来の保存時刻で 時計の疑い フラグ")
    res = js(page, "(() => { const Q = window.__NEKOTA.quests(); Q.accept('q9'); Q.declare('q9', 'x', 'y'); return Q.checkToday('q9'); })()")
    check(res.get("ok") is False and "とけい" in res.get("why", ""), f"疑いがあると日次チェックを止める {res}")
    ctx.close()


def run_reduced_motion(browser, name: str) -> None:  # type: ignore[no-untyped-def]
    ctx = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1, locale="ja-JP", reduced_motion="reduce")
    page = ctx.new_page()
    page.goto(URL + "?fast=1")
    wait_scene(page, "TITLE", 5)
    anim = js(page, "getComputedStyle(document.getElementById('crt'), '::after').animationName")
    check(anim == "none", f"reduced-motion で CRT の帯が止まる ({anim})")
    check(js(page, "window.__NEKOTA.NT.Settings.get('reduceMotion')") is True, "設定の うごき が ひかえめ になる")
    page.screenshot(path=str(OUT / f"{name}_12_reduced.png"))
    ctx.close()


def main() -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    print("== build --check")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build.py"), "--check"], capture_output=True, text=True)
    print(r.stdout.strip())
    check(r.returncode == 0, "index.html がソースと一致（build.py --check）")
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    check(not any(s in html for s in ('src="http', "href=\"http", "fetch(", "import(")), "外部参照を含まない")

    with sync_playwright() as p:
        browser = launch(p)
        for name, (w, h, dpr) in VIEWPORTS.items():
            print(f"== {name} {w}x{h} @{dpr}")
            ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr, locale="ja-JP", accept_downloads=True)
            page = ctx.new_page()
            run_main_flow(page, name)
            if name == "laptop150":
                print("== resume / card")
                run_resume_and_card(ctx, name)
            ctx.close()
        print("== time")
        run_time(browser, "time")
        print("== reduced-motion")
        run_reduced_motion(browser, "rm")
        browser.close()

    if FAILS:
        print(f"=== 不合格: {len(FAILS)} 件 ===")
        for f in FAILS:
            print("  - " + f)
        return 1
    print("=== 合格 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
