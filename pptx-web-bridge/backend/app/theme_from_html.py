"""HTML 図解テーマ（HTML + CSS）→ プロンプトに書ける「見た目の指示」。

このアプリは HTML を描き直さない。**Copilot に「この見た目で作って」と言葉で伝える**ための
材料だけを取り出す。だから出てくるのは座標やセレクタではなく、
配色・フォント・角丸・影・含まれる図解の型といった、文章で指示できるものに限る。

設計:
- `<style>` の中身と、要素の `style=` 属性だけを見る。**外部 CSS は取りに行かない**
  （任意サイトのクロールは非目標。取れないときは黙らず `THEME_EXTERNAL_CSS` を出す）。
- CSS 変数（`:root { --brand: #... }`）を先に解決する。AI が書く HTML で一番多い書き方で、
  ここを飛ばすと「色が 1 つも取れない」になる。
- 役割（背景・文字・見出し・アクセント…）はセレクタから当てる。当たらなければ頻度で埋め、
  **どちらで決めたかを `sources` に残す**（推定は外れる前提・CLAUDE.md 9 章）。
- 図解の型は `spec_builder.infer_kind` を使い回す。テーマも結局 HTML 図解なので、
  判定を二重に持たない。
"""
from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from . import spec_builder
from .html_parser import css_color_to_hex, parse_html
from .logging_setup import get_logger
from .model import warning

log = get_logger("theme_from_html")

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
_DECL_RE = re.compile(r"([-a-zA-Z_][-a-zA-Z0-9_]*)\s*:\s*([^;]+)")
_VAR_USE_RE = re.compile(r"var\(\s*(--[-a-zA-Z0-9_]+)\s*(?:,\s*([^)]*))?\)")
_PX_RE = re.compile(r"(-?[0-9]*\.?[0-9]+)\s*px")
_FONT_STRIP = re.compile(r'^[\s"\']+|[\s"\']+$')

# 役割 → その色が書かれていそうなセレクタ。上にあるものを優先する。
_ROLE_SELECTORS: dict[str, tuple[tuple[str, ...], str]] = {
    "background": (("body", "html", ".slide", ".page"), "background"),
    "text": (("body", "html"), "color"),
    "heading": (("h1", "h2", "h3", ".title"), "color"),
    "card": ((".card", ".panel", ".box", ".tile", ".step"), "background"),
    "line": ((".card", ".panel", ".box", "hr", "table", "td", "th"), "border"),
    "muted": ((".muted", ".lead", ".sub", ".caption", ".note"), "color"),
    "accent": ((".badge", ".accent", ".n", ".step", "a", "strong"), "background_or_color"),
}
_ROLE_LABEL = {
    "background": "背景",
    "text": "文字",
    "heading": "見出し",
    "card": "カードの背景",
    "line": "枠線",
    "muted": "補足の文字",
    "accent": "アクセント",
}


def _strip_font(v: str) -> str:
    first = v.split(",")[0]
    return _FONT_STRIP.sub("", first).strip()


def _luma(hexv: str) -> float:
    r, g, b = (int(hexv[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _chroma(hexv: str) -> float:
    vals = [int(hexv[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    return max(vals) - min(vals)


class _Css:
    """`<style>` と `style=` から集めた宣言。セレクタ順を保つ。"""

    def __init__(self) -> None:
        self.rules: list[tuple[str, dict[str, str]]] = []
        self.vars: dict[str, str] = {}

    def add_block(self, css: str) -> None:
        css = _COMMENT_RE.sub(" ", css)
        for m in _RULE_RE.finditer(css):
            selectors = [s.strip() for s in m.group(1).split(",") if s.strip()]
            decls = {d.group(1).strip().lower(): d.group(2).strip() for d in _DECL_RE.finditer(m.group(2))}
            for name, value in decls.items():
                if name.startswith("--"):
                    self.vars.setdefault(name, value)
            for sel in selectors:
                self.rules.append((sel, decls))

    def add_inline(self, style: str) -> None:
        decls = {d.group(1).strip().lower(): d.group(2).strip() for d in _DECL_RE.finditer(style)}
        if decls:
            self.rules.append(("@inline", decls))

    def resolve(self, value: str, depth: int = 0) -> str:
        """`var(--brand, #fff)` を実際の値にする。循環参照は深さで止める。"""
        if depth > 6 or "var(" not in value:
            return value
        def sub(m: re.Match) -> str:
            got = self.vars.get(m.group(1))
            return (got if got is not None else (m.group(2) or "")).strip()
        return self.resolve(_VAR_USE_RE.sub(sub, value), depth + 1)

    def lookup(self, selectors: tuple[str, ...], prop: str) -> tuple[str | None, str | None]:
        """セレクタ群のどれかに書かれた prop の値。返り値は (値, 効いたセレクタ)。"""
        for want in selectors:
            for sel, decls in self.rules:
                if not _sel_matches(sel, want):
                    continue
                for name in _prop_names(prop):
                    if name in decls:
                        return self.resolve(decls[name]), sel
        return None, None

    def all_values(self, names: tuple[str, ...]) -> list[str]:
        out = []
        for _sel, decls in self.rules:
            for n in names:
                if n in decls:
                    out.append(self.resolve(decls[n]))
        return out


def _sel_matches(sel: str, want: str) -> bool:
    """『body』が『body』『html, body』『body.dark』に当たる程度の素朴な一致。"""
    sel = sel.strip()
    if sel == want:
        return True
    parts = re.split(r"[\s>+~]+", sel)
    last = parts[-1] if parts else sel
    if last == want:
        return True
    if want.startswith("."):
        return bool(re.search(r"(^|[\s>+~.:#])" + re.escape(want[1:]) + r"($|[\s>+~.:#\[])", sel.replace(".", ".")))
    return bool(re.match(re.escape(want) + r"[.:#\[]", last))


def _prop_names(prop: str) -> tuple[str, ...]:
    if prop == "background":
        return ("background-color", "background")
    if prop == "border":
        return ("border-color", "border", "border-bottom", "border-top")
    if prop == "background_or_color":
        return ("background-color", "background", "color")
    return (prop,)


def _colors_from(values: list[str]) -> list[str]:
    out = []
    for v in values:
        for token in re.findall(r"(#[0-9A-Fa-f]{3,8}|rgba?\([^)]*\))", v):
            hexv = css_color_to_hex(token)
            if hexv:
                out.append(hexv)
    return out


def extract_theme(data: bytes, filename: str = "theme.html") -> dict:
    """HTML 図解テーマ → {name, colors, fonts, decoration, kinds, palette, sources, warnings}。"""
    text = data.decode("utf-8", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    css = _Css()
    warnings: list[dict] = []

    for tag in soup.find_all("style"):
        css.add_block(tag.get_text() or "")
    for tag in soup.find_all(style=True):
        css.add_inline(str(tag.get("style") or ""))

    externals = [str(l.get("href")) for l in soup.find_all("link") if "stylesheet" in " ".join(l.get("rel") or []).lower() and l.get("href")]
    if externals:
        warnings.append(warning(
            "theme_from_html", "THEME_EXTERNAL_CSS",
            f"外部の CSS は読み込みません（{len(externals)} 件）: {', '.join(externals[:3])}。"
            "色やフォントが取れていない場合は、その CSS を HTML の <style> に貼ってから読み込ませてください。",
            fallback="HTML 内に書かれた分だけで組み立てます",
        ))

    colors: dict[str, str] = {}
    sources: dict[str, str] = {}
    for role, (selectors, prop) in _ROLE_SELECTORS.items():
        value, sel = css.lookup(selectors, prop)
        found = _colors_from([value]) if value else []
        if found:
            colors[role] = found[0]
            sources[role] = f"{sel} の {prop}"

    palette = _colors_from(css.all_values(("color", "background", "background-color", "border", "border-color", "fill")))
    seen: list[str] = []
    for c in palette:
        if c not in seen:
            seen.append(c)
    palette = seen

    # セレクタで取れなかった役割を、色そのものの性質で埋める（決めた根拠は残す）
    if palette:
        if "background" not in colors:
            light = max(palette, key=_luma)
            colors["background"], sources["background"] = light, "一番明るい色（セレクタからは取れず）"
        if "text" not in colors:
            dark = min(palette, key=_luma)
            colors["text"], sources["text"] = dark, "一番暗い色（セレクタからは取れず）"
        if "accent" not in colors:
            vivid = max(palette, key=_chroma)
            if _chroma(vivid) > 0.15:
                colors["accent"], sources["accent"] = vivid, "一番鮮やかな色（セレクタからは取れず）"
    if not colors:
        warnings.append(warning("theme_from_html", "THEME_NO_COLORS", "このテーマからは色を 1 つも読み取れませんでした。", fallback="配色の指示なしでプロンプトを作ります"))

    fonts: dict[str, str] = {}
    body_font, _ = css.lookup(("body", "html"), "font-family")
    head_font, _ = css.lookup(("h1", "h2", "h3", ".title"), "font-family")
    if body_font:
        fonts["body"] = _strip_font(body_font)
    if head_font:
        fonts["heading"] = _strip_font(head_font)
    if not fonts:
        warnings.append(warning("theme_from_html", "THEME_NO_FONTS", "フォントの指定が見つかりませんでした。", fallback="フォントの指示なしでプロンプトを作ります"))

    decoration: dict[str, Any] = {}
    radius, _ = css.lookup((".card", ".panel", ".box", ".tile", ".step"), "border-radius")
    if radius:
        m = _PX_RE.search(radius)
        decoration["radius_px"] = float(m.group(1)) if m else radius.strip()
    pad, _ = css.lookup((".card", ".panel", ".box", ".tile", ".step"), "padding")
    if pad:
        m = _PX_RE.search(pad)
        if m:
            decoration["padding_px"] = float(m.group(1))
    shadows = css.all_values(("box-shadow",))
    decoration["shadow"] = bool([s for s in shadows if s and s.strip().lower() not in ("none", "0")])
    borders = css.all_values(("border", "border-width"))
    decoration["border"] = bool([b for b in borders if b and "0" != b.strip()])

    # 型は spec_builder に任せる（判定を二重に持たない）
    kinds: list[str] = []
    try:
        pres = parse_html(data, filename)
        spec = spec_builder.build_spec(pres)
        for s in spec.get("slides", []):
            if s["kind"] not in kinds and s["kind"] not in ("title_only",):
                kinds.append(s["kind"])
        warnings.extend(w for w in pres.get("warnings", []) if w.get("code") != "GRID_COLUMNS_LIMITED")
    except Exception as exc:  # 構造が読めなくても配色だけは返す
        warnings.append(warning("theme_from_html", "THEME_STRUCTURE_UNREADABLE", f"テーマの構造を読めませんでした: {exc}", fallback="配色とフォントだけ使います"))

    name = (soup.title.get_text().strip() if soup.title else "") or filename
    theme = {
        "name": name,
        "filename": filename,
        "colors": colors,
        "fonts": fonts,
        "decoration": decoration,
        "kinds": kinds,
        "palette": palette[:12],
        "sources": sources,
        "warnings": warnings,
    }
    log.info("HTML テーマ抽出: %s 色=%s フォント=%s 型=%s 警告=%s", filename, len(colors), len(fonts), ",".join(kinds) or "-", len(warnings))
    return theme


def to_prompt_lines(theme: dict) -> list[str]:
    """プロンプトに埋める「見た目の指示」。言葉で伝わる形だけを出す。"""
    L: list[str] = []
    colors = theme.get("colors") or {}
    if colors:
        L.append("配色（16 進数）:")
        for role, hexv in colors.items():
            L.append(f"  - {_ROLE_LABEL.get(role, role)}: {hexv}")
    fonts = theme.get("fonts") or {}
    if fonts:
        L.append("フォント:")
        if fonts.get("heading"):
            L.append(f"  - 見出し: {fonts['heading']}")
        if fonts.get("body"):
            L.append(f"  - 本文: {fonts['body']}")
    dec = theme.get("decoration") or {}
    bits = []
    if dec.get("radius_px"):
        bits.append(f"角丸 {dec['radius_px']}px")
    if dec.get("shadow"):
        bits.append("影あり")
    if dec.get("border"):
        bits.append("枠線あり")
    if bits:
        L.append("装飾: " + " / ".join(bits))
    kinds = theme.get("kinds") or []
    if kinds:
        L.append("このテーマに含まれる図解の型: " + " / ".join(spec_builder.KINDS.get(k, k) for k in kinds))
    return L
