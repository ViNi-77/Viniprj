"""配布するPython実行時依存・bootloaderの正式な権利表示だけを収集する。"""
from __future__ import annotations

import argparse
from collections import deque
import importlib.metadata as metadata
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


NOTICE_NAME = re.compile(r"^(?:licen[sc]e|copying|notice|copyright)(?:$|[._-])", re.IGNORECASE)
CODE_SUFFIXES = {".py", ".pyc", ".pyo", ".pyi", ".pyx", ".so", ".pyd", ".dll", ".exe", ".pdb"}
# 0.2.0のWindows EXE/PYZを直接監査して確認した、Requires-Distには出ない実収録物。
# openpyxl等の任意importとPyInstallerの解析で入る。変更時は配布物の実収録と照合する。
BUNDLED_OPTIONAL_DISTRIBUTIONS = ("lxml", "packaging", "setuptools")


def runtime_distributions(project="contextgen-kai", *, lookup=metadata.distribution, environment=None):
    """Requires-Distをたどり、対象OSの通常依存と明示されたextrasだけを採用する。"""
    environment = dict(default_environment() if environment is None else environment)
    root = canonicalize_name(project)
    queue = deque([(root, frozenset())])
    contexts = {}
    selected = {}
    while queue:
        name, extras = queue.popleft()
        wanted = {"", *extras}
        previous = contexts.get(name, set())
        if wanted.issubset(previous):
            continue
        contexts[name] = previous | wanted
        dist = lookup(name)
        selected[name] = dist
        for raw in dist.requires or ():
            requirement = Requirement(raw)
            if requirement.marker and not any(
                requirement.marker.evaluate({**environment, "extra": extra}) for extra in contexts[name]
            ):
                continue
            child = lookup(requirement.name)
            if requirement.specifier and not requirement.specifier.contains(child.version, prereleases=True):
                raise RuntimeError(f"Installed runtime dependency does not satisfy {requirement}: {child.version}")
            queue.append((canonicalize_name(requirement.name), frozenset(requirement.extras)))
    selected.pop(root, None)  # アプリに新たな権利帰属・ライセンスを付与しない。
    return selected


def notice_files(dist):
    """ライセンス用ディレクトリにあるコードを除外し、宣言済みの文書は欠落を検知する。"""
    declared = set(dist.metadata.get_all("License-File") or ())
    matched = set()
    candidates = []
    for entry in dist.files or ():
        relative = PurePosixPath(str(entry).replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            continue
        if "__pycache__" in relative.parts or relative.suffix.lower() in CODE_SUFFIXES:
            continue
        parts = relative.parts
        metadata_index = next((i for i, part in enumerate(parts) if part.endswith(".dist-info")), None)
        metadata_relative = PurePosixPath(*parts[metadata_index + 1:]) if metadata_index is not None else None
        license_relative = (
            PurePosixPath(*metadata_relative.parts[1:])
            if metadata_relative is not None and metadata_relative.parts and metadata_relative.parts[0] == "licenses"
            else None
        )
        declaration_paths = {str(relative)}
        if metadata_index == 0:
            # vendored依存のLICENSEが、この配布物自身のLicense-File宣言を満たさないようにする。
            declaration_paths.update((str(metadata_relative), str(license_relative)))
        declarations = declared.intersection(declaration_paths)
        # PEP 639のdist-info/licenses配下、License-File宣言、旧形式の文書ファイル名を採用。
        # packaging/licenses/__init__.pyのような通常モジュールはディレクトリ名で選ばない。
        if not (license_relative is not None or declarations or NOTICE_NAME.match(relative.name)):
            continue
        source = Path(dist.locate_file(entry))
        if source.is_file():
            candidates.append((relative, source))
            matched.update(declarations)
    missing = declared - matched
    if missing:
        raise RuntimeError(f"Declared license files missing for {dist.metadata['Name']}: {', '.join(sorted(missing))}")
    if not candidates:
        raise RuntimeError(f"No license/notice document found for runtime component: {dist.metadata['Name']}")
    return sorted(candidates, key=lambda item: str(item[0]))


def collect(out: Path, *, lookup=metadata.distribution, environment=None, python_prefix=None):
    # 旧ビルドの.py/.pycや不要パッケージを残したまま成功扱いにしない。
    if out.exists() and any(out.iterdir()):
        raise RuntimeError("License output must be empty; rebuild the distribution into a clean output directory")
    out.mkdir(parents=True, exist_ok=True)
    distributions = runtime_distributions(lookup=lookup, environment=environment)
    for name in BUNDLED_OPTIONAL_DISTRIBUTIONS:
        distributions[name] = lookup(name)
    # PyInstallerのビルド依存一式は不要だが、配布EXEに含まれるbootloaderの権利表示は保持する。
    distributions["pyinstaller"] = lookup("pyinstaller")
    packages = []
    for key, dist in sorted(distributions.items()):
        target = out / key
        target.mkdir(exist_ok=True)
        copied = []
        for relative, source in notice_files(dist):
            destination = target.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(relative.as_posix())
        info = {
            "name": dist.metadata["Name"], "version": dist.version,
            "license_expression": dist.metadata.get("License-Expression"),
            "license": dist.metadata.get("License"), "license_files": copied,
        }
        (target / "metadata.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        packages.append(info)
    (out / "DEPENDENCIES.json").write_text(json.dumps(packages, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # CPython標準ライブラリ等の権利表示は既存の配布処理どおり原文で保持する。
    prefix = Path(python_prefix or sys.base_prefix)
    for notice in (prefix / "LICENSE.txt", prefix / "LICENSE"):
        if notice.is_file():
            shutil.copy2(notice, out / "Python-LICENSE.txt")
            break
    else:
        if sys.platform == "win32":
            raise RuntimeError("Python runtime license could not be located")
    (out / "Python-VERSION.txt").write_text(sys.version, encoding="utf-8")
    return packages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    packages = collect(arguments.output)
    print(f"Collected notices for {len(packages)} runtime components (including PyInstaller bootloader).")


if __name__ == "__main__":
    main()
