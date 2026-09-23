"""cloneだけで揃うOCRと、別OSで誤ってWindows EXEを選ばないことを検証。"""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from contextgen_kai import extractors


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_ocr_bundle", ROOT / "packaging/verify_ocr_bundle.py")
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def test_tracked_ocr_matches_manifest_and_detects_corruption(tmp_path):
    manifest = verifier.verify_bundle(ROOT / "ocr")
    assert manifest["tesseract_version"] == "5.5.1"
    assert all(item["size"] < 100_000_000 for item in manifest["files"].values())
    bundle = tmp_path / "ocr"
    shutil.copytree(ROOT / "ocr", bundle)
    target = bundle / "tessdata/eng.traineddata"
    with target.open("r+b") as stream:
        first = stream.read(1)
        stream.seek(0)
        stream.write(bytes([first[0] ^ 1]))
    with pytest.raises(ValueError, match="checksum mismatch"):
        verifier.verify_bundle(bundle)
    target.unlink()
    with pytest.raises(ValueError, match="file missing"):
        verifier.verify_bundle(bundle)


def test_bundle_manifest_rejects_paths_outside_bundle(tmp_path):
    manifest = json.loads((ROOT / "ocr/BUNDLE-MANIFEST.json").read_text())
    manifest["files"] = {"../outside.txt": {"size": 0, "sha256": "unused"}, **manifest["files"]}
    (tmp_path / "BUNDLE-MANIFEST.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Invalid OCR bundle path"):
        verifier.verify_bundle(tmp_path)


@pytest.mark.parametrize("platform,expected", [("win32", "bundled"), ("darwin", "native"), ("linux", "native")])
def test_platform_selects_compatible_ocr(monkeypatch, tmp_path, platform, expected):
    app = tmp_path / "project" / "contextgen_kai"
    app.mkdir(parents=True)
    bundle = app.parent / "ocr"
    bundle.mkdir()
    executable = bundle / "tesseract.exe"
    executable.write_bytes(b"windows test binary")
    monkeypatch.delenv("CONTEXTGEN_TESSERACT", raising=False)
    monkeypatch.setattr(extractors.sys, "platform", platform)
    monkeypatch.setattr(extractors.sys, "executable", str(tmp_path / "python"))
    monkeypatch.delattr(extractors.sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(extractors, "__file__", str(app / "extractors.py"))
    monkeypatch.setattr(extractors.shutil, "which", lambda name: "/native/tesseract")
    assert extractors.tesseract_path() == (str(executable) if expected == "bundled" else "/native/tesseract")
