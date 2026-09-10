from app.text_metrics import estimate_paragraphs_height, text_width_pt, wrapped_lines
from app.units import emu_to_pt, pt_to_emu, pt_to_px, px_to_pt


def test_emu_pt_roundtrip():
    assert pt_to_emu(72) == 914400
    assert abs(emu_to_pt(pt_to_emu(123.4)) - 123.4) < 0.01


def test_px_pt():
    assert abs(pt_to_px(72) - 96) < 1e-9
    assert abs(px_to_pt(96) - 72) < 1e-9


def test_cjk_wider_than_latin():
    assert text_width_pt("あいう", 16) > text_width_pt("abc", 16)


def test_wrapped_lines_grows_with_text():
    assert wrapped_lines("あ" * 10, 16, 400) == 1
    assert wrapped_lines("あ" * 60, 16, 400) == 3


def test_estimate_height_positive():
    h = estimate_paragraphs_height([{"runs": [{"text": "テスト"}], "level": 0}], 400, 16)
    assert h > 16
