"""PPTX のテーマとスタイル継承の解決（Issue #4 / #5）。

- テーマ色: マスターの theme パート（a:clrScheme）と clrMap を読み、scheme 色（accent1 等）を #RRGGBB に解決する。
  lumMod/lumOff は python-pptx の brightness（-1.0〜1.0）で近似する。
- テーマフォント: a:fontScheme（major/minor の latin/ea）で '+mj-ea' などの参照名を実フォント名に解決する。
- 文字スタイルの継承: run → 段落 → 図形の lstStyle → レイアウトのプレースホルダ → マスターのプレースホルダ → マスターの txStyles
  の順で sz / 箇条書き / 太字 / 色 / フォントを探す（PowerPoint と同じ優先順）。

変換中の「現在のテーマ」は contextvar に置き、同時に複数の変換が走っても混ざらないようにする。
"""
from __future__ import annotations

import contextvars
import copy
from typing import Any

from lxml import etree
from pptx.enum.dml import MSO_COLOR_TYPE, MSO_THEME_COLOR
from pptx.oxml import parse_xml
from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.opc.constants import RELATIONSHIP_TYPE as RT

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}

# MSO_THEME_COLOR → clrMap / clrScheme のキー
_THEME_KEYS = {
    MSO_THEME_COLOR.TEXT_1: "tx1",
    MSO_THEME_COLOR.TEXT_2: "tx2",
    MSO_THEME_COLOR.BACKGROUND_1: "bg1",
    MSO_THEME_COLOR.BACKGROUND_2: "bg2",
    MSO_THEME_COLOR.DARK_1: "dk1",
    MSO_THEME_COLOR.DARK_2: "dk2",
    MSO_THEME_COLOR.LIGHT_1: "lt1",
    MSO_THEME_COLOR.LIGHT_2: "lt2",
    MSO_THEME_COLOR.ACCENT_1: "accent1",
    MSO_THEME_COLOR.ACCENT_2: "accent2",
    MSO_THEME_COLOR.ACCENT_3: "accent3",
    MSO_THEME_COLOR.ACCENT_4: "accent4",
    MSO_THEME_COLOR.ACCENT_5: "accent5",
    MSO_THEME_COLOR.ACCENT_6: "accent6",
    MSO_THEME_COLOR.HYPERLINK: "hlink",
    MSO_THEME_COLOR.FOLLOWED_HYPERLINK: "folHlink",
}
_TITLE_TYPES = {PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE, PP_PLACEHOLDER.VERTICAL_TITLE}
_current_theme: contextvars.ContextVar["ThemeInfo | None"] = contextvars.ContextVar("pptx_theme", default=None)


def _hex(v: str | None) -> str | None:
    if not v or len(v) != 6:
        return None
    return "#" + v.upper()


class ThemeInfo:
    """1 つのスライドマスターに紐づくテーマ情報。"""

    def __init__(self, master: Any):
        self.colors: dict[str, str] = {}
        self.clr_map: dict[str, str] = {}
        self.fonts: dict[str, str] = {}
        self.unresolved: set[str] = set()
        try:
            theme_part = master.part.part_related_by(RT.THEME)
            root = parse_xml(theme_part.blob)  # python-pptx と同じパーサ（外部実体を展開しない）
        except Exception:  # noqa: BLE001 - テーマが無い PPTX でも解析は続ける
            root = None
        if root is not None:
            scheme = root.find(".//a:clrScheme", NS)
            if scheme is not None:
                for entry in scheme:
                    if not isinstance(entry.tag, str):
                        continue  # コメントノードを飛ばす
                    key = etree.QName(entry).localname
                    child = entry[0] if len(entry) else None
                    if child is None:
                        continue
                    if etree.QName(child).localname == "srgbClr":
                        val = _hex(child.get("val"))
                    else:  # sysClr
                        val = _hex(child.get("lastClr"))
                    if val:
                        self.colors[key] = val
            fs = root.find(".//a:fontScheme", NS)
            if fs is not None:
                for kind, tag in (("major", "a:majorFont"), ("minor", "a:minorFont")):
                    node = fs.find(tag, NS)
                    if node is None:
                        continue
                    for script in ("latin", "ea", "cs"):
                        el = node.find(f"a:{script}", NS)
                        if el is not None and el.get("typeface"):
                            self.fonts[f"{kind}_{script}"] = el.get("typeface")
        clr_map = master._element.find("p:clrMap", NS)
        if clr_map is not None:
            self.clr_map = dict(clr_map.attrib)

    def with_override(self, override: dict[str, str] | None) -> "ThemeInfo":
        """スライド / レイアウトの clrMapOvr を適用した派生テーマ（色・フォントは共有、対応表だけ差し替え）。"""
        if not override:
            return self
        view = copy.copy(self)  # colors / fonts / unresolved は共有（unresolved の警告集約は基底で行う）
        view.clr_map = {**self.clr_map, **override}
        return view

    def scheme_hex(self, key: str) -> str | None:
        """'tx1' や 'accent1' などのキーを #RRGGBB に解決する。"""
        mapped = self.clr_map.get(key, key)
        return self.colors.get(mapped) or self.colors.get(key)

    def resolve_theme_color(self, theme_color: Any, brightness: float = 0.0) -> str | None:
        key = _THEME_KEYS.get(theme_color)
        if key is None:
            self.unresolved.add(str(theme_color))
            return None
        base = self.scheme_hex(key)
        if base is None:
            self.unresolved.add(key)
            return None
        return apply_brightness(base, brightness)

    def resolve_font(self, name: str | None) -> str | None:
        """'+mj-ea' → majorFont/ea（無ければ latin）。通常名はそのまま。"""
        if not name or not name.startswith("+"):
            return name
        kind = "major" if name[1:3] == "mj" else "minor"
        script = name[4:6] if len(name) >= 6 else "lt"
        script_key = {"lt": "latin", "ea": "ea", "cs": "cs"}.get(script, "latin")
        return self.fonts.get(f"{kind}_{script_key}") or self.fonts.get(f"{kind}_latin") or None


def apply_brightness(hex_color: str, brightness: float) -> str:
    """lumMod/lumOff の近似: 正なら白へ、負なら黒へ寄せる。"""
    if not brightness:
        return hex_color
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    if brightness > 0:
        r, g, b = (int(round(c + (255 - c) * brightness)) for c in (r, g, b))
    else:
        r, g, b = (int(round(c * (1 + brightness))) for c in (r, g, b))
    return f"#{max(0, min(255, r)):02X}{max(0, min(255, g)):02X}{max(0, min(255, b)):02X}"


def set_current_theme(theme: ThemeInfo | None) -> contextvars.Token:
    return _current_theme.set(theme)


def reset_current_theme(token: contextvars.Token) -> None:
    _current_theme.reset(token)


def current_theme() -> ThemeInfo | None:
    return _current_theme.get()


def color_to_hex(color_obj: Any) -> str | None:
    """python-pptx の ColorFormat を #RRGGBB へ。RGB 直指定とテーマ色の両方に対応。"""
    try:
        ctype = color_obj.type
    except (AttributeError, TypeError, ValueError):
        return None
    if ctype is None:
        return None
    try:
        if ctype == MSO_COLOR_TYPE.RGB:
            return "#" + str(color_obj.rgb).upper()
        if ctype == MSO_COLOR_TYPE.SCHEME:
            theme = current_theme()
            if theme is None:
                return None
            try:
                brightness = float(color_obj.brightness or 0.0)
            except (AttributeError, TypeError, ValueError):
                brightness = 0.0
            return theme.resolve_theme_color(color_obj.theme_color, brightness)
    except (AttributeError, TypeError, ValueError):
        return None
    return None


# ---------------------------------------------------------------- 文字スタイルの継承
def _xml_color(fill_parent: etree._Element | None, theme: ThemeInfo | None) -> str | None:
    """a:defRPr / a:rPr 直下の solidFill を #RRGGBB に。"""
    if fill_parent is None:
        return None
    sf = fill_parent.find("a:solidFill", NS)
    if sf is None:
        return None
    srgb = sf.find("a:srgbClr", NS)
    if srgb is not None:
        return _hex(srgb.get("val"))
    sch = sf.find("a:schemeClr", NS)
    if sch is not None and theme is not None:
        base = theme.scheme_hex(sch.get("val", ""))
        if base is None:
            return None
        lum_mod = sch.find("a:lumMod", NS)
        lum_off = sch.find("a:lumOff", NS)
        brightness = 0.0
        if lum_off is not None:
            brightness = int(lum_off.get("val", 0)) / 100000.0
        elif lum_mod is not None:
            brightness = int(lum_mod.get("val", 100000)) / 100000.0 - 1.0
        return apply_brightness(base, brightness)
    return None


def _level_props(ppr: etree._Element | None, theme: ThemeInfo | None) -> dict[str, Any]:
    """lvlNpPr（または段落の pPr）から継承対象の属性を取り出す。"""
    out: dict[str, Any] = {"sz": None, "bullet": None, "bold": None, "color": None, "font": None}
    if ppr is None:
        return out
    if ppr.find("a:buNone", NS) is not None:
        out["bullet"] = "none"
    elif ppr.find("a:buAutoNum", NS) is not None:
        out["bullet"] = "number"
    elif ppr.find("a:buChar", NS) is not None or ppr.find("a:buBlip", NS) is not None:
        out["bullet"] = "bullet"
    d = ppr.find("a:defRPr", NS)
    if d is not None:
        if d.get("sz"):
            out["sz"] = int(d.get("sz")) / 100.0
        if d.get("b") is not None:
            out["bold"] = d.get("b") in ("1", "true")
        out["color"] = _xml_color(d, theme)
        ea = d.find("a:ea", NS)
        latin = d.find("a:latin", NS)
        face = (ea.get("typeface") if ea is not None else None) or (latin.get("typeface") if latin is not None else None)
        if face:
            out["font"] = theme.resolve_font(face) if theme else face
    return out


def _lst_level(txbody: etree._Element | None, level: int, theme: ThemeInfo | None) -> dict[str, Any]:
    if txbody is None:
        return _level_props(None, theme)
    lst = txbody.find("a:lstStyle", NS)
    if lst is None:
        return _level_props(None, theme)
    return _level_props(lst.find(f"a:lvl{level + 1}pPr", NS), theme)


def _merge(*layers: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"sz": None, "bullet": None, "bold": None, "color": None, "font": None}
    for layer in layers:
        for k, v in layer.items():
            if out[k] is None and v is not None:
                out[k] = v
    return out


class TextStyleResolver:
    """スライド 1 枚分の継承解決。同じレイアウト・マスターを持つスライドで使い回せる。"""

    def __init__(self, slide: Any, theme: ThemeInfo | None):
        self.slide = slide
        self.layout = slide.slide_layout
        self.master = self.layout.slide_master
        self.theme = theme
        tx = self.master._element.find("p:txStyles", NS)
        self.master_styles: dict[str, etree._Element | None] = {
            "title": tx.find("p:titleStyle", NS) if tx is not None else None,
            "body": tx.find("p:bodyStyle", NS) if tx is not None else None,
            "other": tx.find("p:otherStyle", NS) if tx is not None else None,
        }
        # 最終層: presentation.xml の defaultTextStyle（素のテキストボックスは本来これで解決される）
        self.default_text_style: etree._Element | None = None
        try:
            prs_el = slide.part.package.presentation_part.presentation._element
            self.default_text_style = prs_el.find("p:defaultTextStyle", NS)
        except Exception:  # noqa: BLE001
            self.default_text_style = None

    @staticmethod
    def clr_map_override(slide: Any) -> dict[str, str]:
        """スライド / レイアウトの clrMapOvr（色対応の上書き）。スライド側が優先（Issue #14）。"""
        result: dict[str, str] = {}
        for el in (slide.slide_layout._element, slide._element):
            ovr = el.find("p:clrMapOvr", NS)
            mapping = ovr.find("a:overrideClrMapping", NS) if ovr is not None else None
            if mapping is not None:
                result.update({k: v for k, v in mapping.attrib.items() if isinstance(k, str)})
        return result

    def _placeholder_chain(self, shape: Any) -> list[etree._Element | None]:
        """レイアウト → マスター のプレースホルダ txBody を返す（見つからなければ空）。"""
        try:
            if not shape.is_placeholder:
                return []
            pf = shape.placeholder_format
        except (AttributeError, ValueError):
            return []
        chain: list[etree._Element | None] = []
        lay_ph = None
        for ph in self.layout.placeholders:
            if ph.placeholder_format.idx == pf.idx:
                lay_ph = ph
                break
        if lay_ph is None:
            for ph in self.layout.placeholders:
                if ph.placeholder_format.type == pf.type:
                    lay_ph = ph
                    break
        if lay_ph is not None and lay_ph.has_text_frame:
            chain.append(lay_ph.text_frame._txBody)
        master_type = PP_PLACEHOLDER.TITLE if pf.type in _TITLE_TYPES else PP_PLACEHOLDER.BODY
        for ph in self.master.placeholders:
            if ph.placeholder_format.type == master_type and ph.has_text_frame:
                chain.append(ph.text_frame._txBody)
                break
        return chain

    def resolve(self, shape: Any, level: int, paragraph_ppr: etree._Element | None = None) -> dict[str, Any]:
        """level（0 始まり）の段落に効く既定スタイルを返す。{'sz','bullet','bold','color','font'}"""
        layers: list[dict[str, Any]] = [_level_props(paragraph_ppr, self.theme)]
        txbody = shape.text_frame._txBody if getattr(shape, "has_text_frame", False) else None
        layers.append(_lst_level(txbody, level, self.theme))
        for ph_body in self._placeholder_chain(shape):
            layers.append(_lst_level(ph_body, level, self.theme))
        try:
            is_ph = shape.is_placeholder
            ph_type = shape.placeholder_format.type if is_ph else None
        except (AttributeError, ValueError):
            is_ph, ph_type = False, None
        style_key = "other" if not is_ph else ("title" if ph_type in _TITLE_TYPES else "body")
        style = self.master_styles.get(style_key)
        if style is not None:
            layers.append(_level_props(style.find(f"a:lvl{level + 1}pPr", NS), self.theme))
            if level > 0:  # 上位レベルが無ければ lvl1 を使う（仕様上は既定 18pt だが、実務上は lvl1 の方が近い。意思決定ログ参照）
                layers.append(_level_props(style.find("a:lvl1pPr", NS), self.theme))
        if self.default_text_style is not None:
            layers.append(_level_props(self.default_text_style.find(f"a:lvl{level + 1}pPr", NS), self.theme))
        return _merge(*layers)

    @staticmethod
    def font_scale(shape: Any) -> float:
        """bodyPr の normAutofit fontScale（例: 85000 → 0.85）。無ければ 1.0。"""
        try:
            bodypr = shape.text_frame._txBody.find("a:bodyPr", NS)
            auto = bodypr.find("a:normAutofit", NS) if bodypr is not None else None
            if auto is not None and auto.get("fontScale"):
                return int(auto.get("fontScale")) / 100000.0
        except (AttributeError, TypeError, ValueError):
            pass
        return 1.0
