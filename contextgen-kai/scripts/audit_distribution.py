"""完成ZIPの配布構成・OCR・文書画像・権利表示を検査する。"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from contextgen_kai import __version__
from contextgen_kai.api import MANUAL_ASSETS


def audit(path):
    checks = []
    def check(condition, message):
        if not condition:
            raise AssertionError(message)
        checks.append(message)
    screenshots = {}
    with zipfile.ZipFile(path) as archive:
        names = {n.replace("\\", "/"): n for n in archive.namelist() if not n.endswith(("/", "\\"))}
        check(all(n.startswith("ContextgenKai/") and ".." not in PurePosixPath(n).parts for n in names), "single safe ContextgenKai folder")
        contents = {n[len("ContextgenKai/"):]: original for n, original in names.items()}
        check({n.split("/")[0] for n in contents} == {"ContextgenKai.exe", "_internal", "contextgen改_操作マニュアル.html", "最初にお読みください.txt"}, "four user-facing entries")
        check(not any(PurePosixPath(n).suffix.lower() in {".py", ".pyc", ".pyo", ".pyi", ".spec", ".pdb"} for n in contents), "no external Python source, bytecode or debug files")
        check(not any(PurePosixPath(n).name.startswith("._") or ".DS_Store" in n or "__MACOSX" in n for n in contents), "no development OS archive artifacts")
        check(not any(p in PurePosixPath(n).parts for n in contents if not n.startswith("_internal/THIRD_PARTY_LICENSES/") for p in {".git", "tests", "docs", "artifacts", "__pycache__"}), "no owner documents, Git files or tests")
        check(not any(PurePosixPath(n).name in {"BUILD-MANIFEST.json", "BUNDLE-MANIFEST.json", "requirements.txt", "start_windows.bat"} for n in contents), "no development manifests or source launchers")
        def read(name):
            return archive.read(contents[name])
        for name in ("contextgen改_操作マニュアル.html", "最初にお読みください.txt", "_internal/contextgen_kai/static/index.html", "_internal/contextgen_kai/static/app.js"):
            content = read(name).decode("utf-8-sig")
            check(not re.search(r"/Users/|/private/|macOS|Mac OS|Codex", content), "no development traces in " + name)
        check(__version__ in read("contextgen改_操作マニュアル.html").decode(), "manual version matches application")
        for asset in sorted(MANUAL_ASSETS):
            name = "_internal/manual/images/" + asset
            check(name in contents and len(read(name)) > 0, "manual asset " + asset)
            if asset.endswith(".png"):
                with Image.open(io.BytesIO(read(name))) as image:
                    check(image.format == "PNG" and not image.info, "valid PNG without embedded metadata " + asset)
                    screenshots[asset] = dict(width=image.width, height=image.height)
        manifest = json.loads((ROOT / "ocr/BUNDLE-MANIFEST.json").read_text())
        for name in ("tesseract.exe", "tessdata/jpn.traineddata", "tessdata/eng.traineddata"):
            check(hashlib.sha256(read("_internal/ocr/" + name)).hexdigest() == manifest["files"][name]["sha256"], "bundled OCR matches tracked checksum " + name)
        licenses = "_internal/THIRD_PARTY_LICENSES/"
        for name in ("Tcl-LICENSE.txt", "Tk-LICENSE.txt", "tesseract-LICENSE.txt", "tessdata-LICENSE.txt", "python/Python-LICENSE.txt"):
            check(bool(read(licenses + name)), "runtime notice " + name)
        dependencies = json.loads(read(licenses + "python/DEPENDENCIES.json"))
        for component in dependencies:
            key = re.sub(r"[-_.]+", "-", component["name"]).lower()
            check(bool(component["license_files"]), "declared notices " + key)
            for notice in component["license_files"]:
                check(bool(read(licenses + "python/" + key + "/" + notice)), "notice present " + key + "/" + notice)
    return dict(version=__version__, archive=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), checks=checks, screenshots=screenshots, passed=True,
                note="ZIP structure/content audit. Does not imply target-PC or Copilot acceptance, nor prevent reverse engineering.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS: {len(result['checks'])} distribution checks")
