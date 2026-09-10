from app.model import bbox, image_element, new_presentation, new_slide, paragraph, run, text_element
from app.quality_check import check_presentation, summarize


def _pres():
    p = new_presentation("q")
    s = new_slide("s001", 0)
    p["slides"].append(s)
    return p, s


def test_text_overflow_detected():
    p, s = _pres()
    s["elements"].append(text_element("a", [paragraph([run("あ" * 400)])], box=bbox(0, 0, 200, 20)))
    codes = {i["code"] for i in check_presentation(p)}
    assert "TEXT_OVERFLOW" in codes


def test_overlap_detected():
    p, s = _pres()
    s["elements"].append(text_element("a", [paragraph([run("x")])], box=bbox(0, 0, 200, 100)))
    s["elements"].append(text_element("b", [paragraph([run("y")])], box=bbox(50, 50, 200, 100)))
    assert any(i["code"] == "ELEMENT_OVERLAP" for i in check_presentation(p))


def test_image_aspect_and_missing():
    p, s = _pres()
    p["assets"]["img1"] = {"mime": "image/png", "data_base64": "", "width_px": 400, "height_px": 200}
    s["elements"].append(image_element("i1", "img1", bbox(0, 0, 100, 100), fit="stretch"))
    s["elements"].append(image_element("i2", "nope", bbox(0, 200, 100, 100)))
    codes = {i["code"] for i in check_presentation(p)}
    assert "IMAGE_ASPECT_DISTORTED" in codes and "IMAGE_ASSET_MISSING" in codes
    assert summarize(check_presentation(p))["ok"] is False


def test_out_of_canvas_and_index():
    p, s = _pres()
    s["index"] = 3
    s["elements"].append(text_element("a", [paragraph([run("x")])], box=bbox(900, 500, 200, 100)))
    codes = {i["code"] for i in check_presentation(p)}
    assert "OUT_OF_CANVAS" in codes and "SLIDE_INDEX_MISMATCH" in codes
