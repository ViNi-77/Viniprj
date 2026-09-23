"""Gitで取得したWindows OCRの欠落・破損を起動前と配布前に検査する。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


REQUIRED_FILES = {
    "tesseract.exe", "tessdata/eng.traineddata", "tessdata/jpn.traineddata",
    "tessdata/LICENSE", "licenses/tesseract-LICENSE.txt", "licenses/leptonica-LICENSE.txt",
}


def verify_bundle(root: Path) -> dict:
    root = root.resolve()
    manifest = json.loads((root / "BUNDLE-MANIFEST.json").read_text(encoding="utf-8-sig"))
    if manifest.get("schema_version") != 1 or manifest.get("platform") != "windows-x64":
        raise ValueError("Unsupported OCR bundle manifest")
    files = manifest.get("files", {})
    if not isinstance(files, dict) or not REQUIRED_FILES.issubset(files):
        raise ValueError("OCR bundle manifest is missing required runtime files")
    for relative, expected in files.items():
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or "\\" in relative or ":" in relative:
            raise ValueError(f"Invalid OCR bundle path: {relative}")
        target = (root / path).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise ValueError(f"OCR bundle file missing: {relative}")
        if target.stat().st_size != expected["size"]:
            raise ValueError(f"OCR bundle size mismatch: {relative}")
        with target.open("rb") as stream:
            actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual_hash != expected["sha256"]:
            raise ValueError(f"OCR bundle checksum mismatch: {relative}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1] / "ocr")
    args = parser.parse_args()
    try:
        manifest = verify_bundle(args.root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"OCR bundle verification failed: {exc}")
        return 1
    print(f"OCR bundle verified: Tesseract {manifest['tesseract_version']}, {len(manifest['files'])} files, Japanese + English")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
