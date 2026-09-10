"""スライドの画像化（見た目優先モード・スクリーンショット比較用）。

Playwright + Chromium が使える場合のみ動作する。使えない環境では is_available() が False を返し、
呼び出し側は編集性優先モードへフォールバックして警告を出す。
"""
from __future__ import annotations

import os
from pathlib import Path

from .config import get_config
from .logging_setup import get_logger
from .web_renderer import _VIEWER_DIR, slide_html

log = get_logger("rasterize")

_RASTER_OVERRIDE_CSS = """
body{background:#fff;margin:0;display:block}
.viewer-body{display:block}
.stage{display:block;padding:0}
.slide-wrap{display:block !important;margin:0 0 8px 0}
.slide{transform:none !important;box-shadow:none}
.notes{display:none}
"""


def _candidate_executables() -> list[str | None]:
    cfg = get_config()
    cands: list[str | None] = [None]  # None = Playwright 既定のブラウザ
    env = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH")
    if env:
        cands.insert(0, env)
    configured = cfg.get("rasterize.chromium_path")
    if configured:
        cands.insert(0, str(configured))
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if base and Path(base).exists():
        for d in sorted(Path(base).glob("chromium-*")):
            for rel in ("chrome-linux/chrome", "chrome-mac/Chromium.app/Contents/MacOS/Chromium", "chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium", "chrome-win/chrome.exe", "chrome-win64/chrome.exe"):
                if (d / rel).exists():
                    cands.append(str(d / rel))
    return cands


def _launch(p):  # type: ignore[no-untyped-def]
    """Chromium を起動する。順序: 設定/環境変数のパス → Playwright 既定 → OS 標準ブラウザ（Edge / Chrome）。

    exe 配布版は Chromium を同梱しないため、Windows 標準の Edge（channel="msedge"）で画像化できる。
    """
    last_err: Exception | None = None
    # 画像化に不要な外部通信（更新確認・同期・初回設定）を抑える
    args = ["--no-sandbox", "--disable-background-networking", "--disable-component-update", "--no-first-run", "--disable-sync", "--disable-default-apps", "--no-default-browser-check"]
    for exe in _candidate_executables():
        try:
            kwargs = {"args": args}
            if exe:
                kwargs["executable_path"] = exe
            return p.chromium.launch(**kwargs)
        except Exception as e:  # noqa: BLE001
            last_err = e
    for channel in [str(c) for c in (get_config().get("rasterize.channels") or ["msedge", "chrome"])]:
        try:
            return p.chromium.launch(channel=channel, args=args)
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(f"Chromium / Edge / Chrome を起動できません: {last_err}")


def is_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            b = _launch(p)
            b.close()
        return True
    except Exception as e:  # noqa: BLE001
        log.info("Playwright は利用できません: %s", e)
        return False


def raster_html(presentation: dict) -> str:
    cfg = get_config()
    template = cfg.template(presentation.get("theme", {}).get("template_id"))
    fonts = cfg.font_fallback()
    css = (_VIEWER_DIR / "viewer.css").read_text(encoding="utf-8")
    slides = "".join(slide_html(s, presentation, True, template) for s in presentation.get("slides", []))
    return f'<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><style>{css}</style><style>:root{{--font:{fonts.get("web_font_stack", "sans-serif")}}}{_RASTER_OVERRIDE_CSS}</style></head><body class="slide-mode"><div class="viewer-body"><main class="stage">{slides}</main></div></body></html>'


def render_slide_images(presentation: dict, scale: float | None = None) -> list[bytes | None]:
    """各スライドの PNG を返す。失敗したスライドは None。Playwright が無ければ例外を投げる。"""
    from playwright.sync_api import sync_playwright

    cfg = get_config()
    scale = float(scale or cfg.get("pptx_export.visual_render_scale", 2))
    html = raster_html(presentation)
    out: list[bytes | None] = []
    with sync_playwright() as p:
        browser = _launch(p)
        try:
            page = browser.new_page(viewport={"width": int(presentation["canvas"]["width_pt"]) + 40, "height": int(presentation["canvas"]["height_pt"]) + 40}, device_scale_factor=scale)
            page.set_content(html, wait_until="load")
            page.wait_for_timeout(100)
            for s in presentation.get("slides", []):
                try:
                    out.append(page.locator(f"#{s['id']}").screenshot(type="png"))
                except Exception as e:  # noqa: BLE001
                    log.warning("スライド画像化に失敗: %s (%s)", s["id"], e)
                    out.append(None)
        finally:
            browser.close()
    return out


# ---------------------------------------------------------------- Computed Style（Issue #6）
_STYLE_PROPS = ["color", "background-color", "font-size", "font-weight", "font-family", "text-align", "border-top-color", "border-top-width", "float"]


def collect_computed_styles(html_text: str, files: dict[str, bytes] | None = None, base_path: str = "") -> tuple[dict[str, dict[str, str]], str | None]:
    """HTML を外部通信なし・JavaScript 無効で描画し、data-pwb-id を付けた各要素の Computed Style を返す。

    - 同梱 CSS（<link rel=stylesheet href=...>）は files から読み込んで <style media=...> に置き換える。
    - 画像や外部 URL への通信はすべて遮断し（route.abort + offline）、取込 HTML のスクリプトは実行しない。
    - Playwright が無い／失敗した場合は ({}, 理由) を返し、呼び出し側は静的解析のみで続行する。
    返り値: ({"3": {"color": "rgb(11, 61, 145)", "font-size": "24px", ...}, ...}, None) または ({}, "理由")
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {}, "Playwright が導入されていません"
    import posixpath
    import re

    cfg = get_config()
    files = files or {}
    base_dir = posixpath.dirname(base_path.replace("\\", "/"))

    def _inline_css(m: "re.Match[str]") -> str:
        tag = m.group(0)
        href_m = re.search(r"href=[\"']([^\"']+)[\"']", tag, re.I)
        rel_m = re.search(r"rel=[\"']([^\"']+)[\"']", tag, re.I)
        if not href_m or not rel_m or "stylesheet" not in rel_m.group(1).lower().split() or "alternate" in rel_m.group(1).lower():
            return tag
        media_m = re.search(r"media=[\"']([^\"']+)[\"']", tag, re.I)
        media = f' media="{media_m.group(1)}"' if media_m else ""
        href = href_m.group(1)
        cand = (posixpath.normpath(posixpath.join(base_dir, href)) if base_dir else posixpath.normpath(href)).lstrip("./")
        for key, blob in files.items():
            nk = key.replace("\\", "/").lstrip("./")
            if nk == cand or posixpath.basename(nk) == posixpath.basename(cand):  # basename 一致は resolve_image と同じ方針
                return f"<style{media}>" + blob.decode("utf-8", "replace") + "</style>"
        return ""  # 見つからない CSS は無視（外部へは取りに行かない）

    html_inlined = re.sub(r"<link\b[^>]*>", _inline_css, html_text, flags=re.I)
    js = """
    () => {
      const out = {};
      const props = %s;
      document.querySelectorAll('[data-pwb-id]').forEach(el => {
        const cs = getComputedStyle(el);
        const rec = {};
        props.forEach(p => { rec[p] = cs.getPropertyValue(p); });
        const r = el.getBoundingClientRect();
        rec.width = String(Math.round(r.width));
        rec.display = cs.getPropertyValue('display');
        out[el.getAttribute('data-pwb-id')] = rec;
      });
      return out;
    }
    """ % (str(_STYLE_PROPS).replace("'", '"'))
    try:
        with sync_playwright() as p:
            browser = _launch(p)
            try:
                # JavaScript 無効（取込 HTML のスクリプトを実行しない）+ offline（Fetch 外の接続も遮断）
                context = browser.new_context(java_script_enabled=False, offline=True, viewport={"width": int(cfg.get("html_import.viewport_width", 1280)), "height": int(cfg.get("html_import.viewport_height", 900))})
                page = context.new_page()
                page.route("**/*", lambda route: route.abort())  # すべてのサブリソース通信を遮断
                page.set_content(html_inlined, wait_until="domcontentloaded", timeout=int(cfg.get("html_import.render_timeout_ms", 10000)))
                return page.evaluate(js), None
            finally:
                browser.close()
    except Exception as e:  # noqa: BLE001
        reason = str(e).splitlines()[0][:160]
        log.info("Computed Style の取得に失敗（静的解析のみで続行）: %s", reason)
        return {}, reason
