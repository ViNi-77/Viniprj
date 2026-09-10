import json

from app.model import new_presentation
from app.validate import repair, validate, validate_and_repair


def test_new_presentation_is_valid():
    assert validate(new_presentation("t")) == []


def test_repair_fixes_missing_fields():
    broken = {"slides": [{"elements": [{"type": "text", "paragraphs": [{"runs": [{"text": "a"}]}]}, {"type": "bogus"}, "junk"]}, 5], "extra": 1}
    fixed, fixes = repair(json.loads(json.dumps(broken)))
    assert validate(fixed) == []
    assert len(fixed["slides"]) == 1
    assert len(fixed["slides"][0]["elements"]) == 1
    codes = {f["code"] for f in fixes}
    assert "UNKNOWN_KEY_REMOVED" in codes and "ELEMENT_DROPPED" in codes and "SLIDE_DROPPED" in codes


def test_repair_normalizes_colors():
    p = new_presentation("t")
    p["theme"]["colors"]["primary"] = "#abc"
    p["theme"]["colors"]["accent"] = "rgb(1, 2, 3)"
    p["theme"]["colors"]["text"] = "nonsense"
    fixed, _ = repair(p)
    assert fixed["theme"]["colors"]["primary"] == "#AABBCC"
    assert fixed["theme"]["colors"]["accent"] == "#010203"
    assert fixed["theme"]["colors"]["text"].startswith("#")


def test_validate_and_repair_root_not_object():
    fixed, errors, fixes = validate_and_repair("not a dict")
    assert errors == []
    assert fixes[0]["code"] == "ROOT_NOT_OBJECT"
