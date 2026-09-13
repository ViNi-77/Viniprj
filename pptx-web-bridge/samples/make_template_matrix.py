"""テンプレート推定が壊れる軸を網羅した試験用 PPTX を生成する。

1 つの実ファイルに合わせ込むと他のテンプレートで壊れるため、壊れ方の軸ごとに最小の資料を作る。

| 軸 | 値 |
|---|---|

| 装飾の置き場所 | スライド / レイアウト / マスター |
| ロゴ形式 | PNG / フリーフォーム図形（グラデーション） / グループ |
| ロゴ幅 | 狭い（20%） / ロックアップ（31%。旧しきい値 25% では拾えなかった） |
| 枚数 | 1 枚 / 3 枚 |
| 中身 | 色見本の列 / グラデーション図形 |
| 比率 | 16:9 / 4:3 |

実案件の素材は含まない（PIL で描いた図形のみ）。`python samples/make_template_matrix.py` で `samples/templates/` に出る。
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.util import Pt

_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

OUT_DIR = Path(__file__).resolve().parent / "templates"
NAVY = RGBColor(0x00, 0x30, 0x87)
CHIPS = (0x001A72, 0x3355A0, 0x6688C0, 0x99AADD, 0xCCDDEE, 0x00B0F0, 0xFF0044, 0x333333, 0x000000, 0x808080, 0xC0C0C0)


def _rgb(v: int) -> RGBColor:
    return RGBColor(v >> 16, (v >> 8) & 0xFF, v & 0xFF)


def _logo_png(w: int = 600, h: int = 120) -> bytes:
    """ロゴ + タグラインのロックアップに見せた画像。"""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((4, 20, 84, 100), fill=(255, 255, 255, 255))
    d.rectangle((100, 46, 430, 74), fill=(255, 255, 255, 255))
    d.rectangle((100, 84, 330, 96), fill=(200, 214, 236, 255))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()




def _new(width_pt: float = 960, height_pt: float = 540) -> Presentation:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Pt(width_pt), Pt(height_pt)
    return prs


def _blank(prs: Presentation):
    return prs.slides.add_slide(prs.slide_layouts[6])


def _fill(shape, color: RGBColor) -> None:
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def _bar(container, x: float, y: float, w: float, h: float, color: RGBColor = NAVY):
    s = container.shapes.add_shape(MSO_SHAPE.RECTANGLE, Pt(x), Pt(y), Pt(w), Pt(h))
    _fill(s, color)
    return s


def _swatch_column(slide, cw: float) -> None:
    """左端に並ぶ色見本（会社テンプレートの配色ページ）。"""
    for i, c in enumerate(CHIPS):
        _fill(slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Pt(20), Pt(30 + i * 38), Pt(50), Pt(30)), _rgb(c))


def _title_body(prs: Presentation):
    """題名 + 本文プレースホルダを持つ中身スライド。"""
    slide = prs.slides.add_slide(prs.slide_layouts[1])  # Title and Content
    slide.shapes.title.text = "中身の題名"
    slide.placeholders[1].text_frame.text = "本文の 1 行目"
    return slide


# ---------------------------------------------------------------- 各ケース
def chrome_on_slide_wide_logo(path: Path) -> None:
    """利用者が投入したものに近い形: 1 枚・下部の帯・帯に乗る幅広ロゴ・左端の色見本。"""
    prs = _new()
    slide = _blank(prs)
    _bar(slide, 0, 490, 960, 50)
    _swatch_column(slide, 960)
    slide.shapes.add_picture(io.BytesIO(_logo_png()), Pt(30), Pt(500), width=Pt(300), height=Pt(30))
    prs.save(path)


def _adopt(layout, slide, shape) -> None:
    """スライドに作った図形をレイアウトへ移す。

    python-pptx はレイアウトへ図形を足す API を持たないため XML を移し替える。
    画像はレイアウト側にも関係（r:embed）を張り直さないと壊れる。
    """
    el = shape._element
    for blip in el.findall(f".//{{{_A_NS}}}blip"):
        rid = blip.get(f"{{{_R_NS}}}embed")
        if rid:
            blip.set(f"{{{_R_NS}}}embed", layout.part.relate_to(slide.part.related_part(rid), RT.IMAGE))
    layout._element.spTree.append(el)


def _drop_slide(prs: Presentation, slide) -> None:
    for sldId in list(prs.slides._sldIdLst):
        if sldId.rId == prs.part.relate_to(slide.part, RT.SLIDE):
            prs.part.drop_rel(sldId.rId)
            prs.slides._sldIdLst.remove(sldId)
            return


def chrome_on_layout(path: Path) -> None:
    """装飾をレイアウトに置いた正しい形のテンプレート（Phase B のレイアウト方式が効く）。"""
    prs = _new()
    layout = prs.slide_layouts[1]
    scratch = _blank(prs)
    _adopt(layout, scratch, _bar(scratch, 0, 490, 960, 50))
    _adopt(layout, scratch, scratch.shapes.add_picture(io.BytesIO(_logo_png()), Pt(30), Pt(500), width=Pt(220), height=Pt(22)))
    _drop_slide(prs, scratch)
    _title_body(prs)
    prs.save(path)


def chrome_on_master(path: Path) -> None:
    """装飾をスライドマスターに置いたテンプレート。レイアウト → マスターまで辿らないとロゴが消える。"""
    prs = _new()
    master = prs.slide_masters[0]
    scratch = _blank(prs)
    _adopt(master, scratch, _bar(scratch, 0, 490, 960, 50))
    _adopt(master, scratch, scratch.shapes.add_picture(io.BytesIO(_logo_png()), Pt(30), Pt(500), width=Pt(220), height=Pt(22)))
    _drop_slide(prs, scratch)
    _title_body(prs)
    prs.save(path)


def logo_freeform(path: Path) -> None:
    """ロゴがベクター図形（塗りがグラデーション）。色は取れないが黙って消してはいけない。"""
    prs = _new()
    slide = _blank(prs)
    _bar(slide, 0, 490, 960, 50)
    logo = slide.shapes.add_shape(MSO_SHAPE.OVAL, Pt(30), Pt(498), Pt(34), Pt(34))
    logo.fill.gradient()
    logo.line.fill.background()
    prs.save(path)


def logo_in_group(path: Path) -> None:
    """ロゴが図形 + 文字のグループ。グループは展開して中の画像を拾えなければならない。"""
    prs = _new()
    slide = _blank(prs)
    _bar(slide, 0, 490, 960, 50)
    slide.shapes.add_picture(io.BytesIO(_logo_png()), Pt(30), Pt(500), width=Pt(180), height=Pt(18))
    tag = slide.shapes.add_textbox(Pt(220), Pt(500), Pt(200), Pt(20))
    tag.text_frame.text = "We Touch the Future"
    prs.save(path)


def three_slides(path: Path) -> None:
    """表紙・中身・最終ページの 3 枚（役割の自動判定が効く形）。"""
    prs = _new()
    cover = _blank(prs)
    _fill(cover.shapes.add_shape(MSO_SHAPE.RECTANGLE, Pt(0), Pt(0), Pt(960), Pt(540)), NAVY)
    cover.shapes.add_picture(io.BytesIO(_logo_png()), Pt(40), Pt(40), width=Pt(200), height=Pt(20))
    _title_body(prs)
    closing = _blank(prs)
    closing.shapes.add_picture(io.BytesIO(_logo_png()), Pt(360), Pt(250), width=Pt(240), height=Pt(24))
    prs.save(path)


def swatch_page_plus_content(path: Path) -> None:
    """色見本ページと中身が混ざったデッキ。色見本を中身に選んではいけない。"""
    prs = _new()
    cover = _blank(prs)
    _fill(cover.shapes.add_shape(MSO_SHAPE.RECTANGLE, Pt(0), Pt(0), Pt(960), Pt(540)), NAVY)
    swatch = _blank(prs)
    _swatch_column(swatch, 960)
    _title_body(prs)
    closing = _blank(prs)
    closing.shapes.add_picture(io.BytesIO(_logo_png()), Pt(360), Pt(250), width=Pt(240), height=Pt(24))
    prs.save(path)


def aspect_4_3(path: Path) -> None:
    """4:3 のテンプレート（比率が違っても部品が端に残る）。"""
    prs = _new(720, 540)
    slide = _blank(prs)
    _bar(slide, 0, 500, 720, 40)
    slide.shapes.add_picture(io.BytesIO(_logo_png()), Pt(24), Pt(508), width=Pt(160), height=Pt(16))
    prs.save(path)


CASES = {
    "chrome_on_slide_wide_logo.pptx": chrome_on_slide_wide_logo,
    "chrome_on_layout.pptx": chrome_on_layout,
    "chrome_on_master.pptx": chrome_on_master,
    "logo_freeform.pptx": logo_freeform,
    "logo_in_group.pptx": logo_in_group,
    "three_slides.pptx": three_slides,
    "swatch_page_plus_content.pptx": swatch_page_plus_content,
    "aspect_4_3.pptx": aspect_4_3,
}


def build(out_dir: Path = OUT_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for name, fn in CASES.items():
        path = out_dir / name
        fn(path)
        made.append(path)
    return made


if __name__ == "__main__":
    for p in build():
        print(p)
