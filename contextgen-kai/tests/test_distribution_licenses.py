"""配布の権利表示から開発依存とコードを除き、実行時の権利表示を落とさない。"""
from email.message import Message
import importlib.util
from pathlib import Path

import pytest

from packaging.utils import canonicalize_name


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("collect_python_licenses", ROOT / "packaging/collect_python_licenses.py")
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class Distribution:
    def __init__(self, root, name, *, requires=(), notices=("LICENSE",), files=None):
        self.root = root / name
        self.version = "1.0"
        self.requires = requires
        self.metadata = Message()
        self.metadata["Name"] = name
        for notice in notices:
            self.metadata["License-File"] = notice
        contents = files if files is not None else {f"{name}-1.0.dist-info/licenses/{notice}": f"Original rights: {name} {notice}\n" for notice in notices}
        self.files = [Path(relative) for relative in contents]
        for relative, content in contents.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def locate_file(self, entry):
        return self.root / entry


def test_runtime_graph_includes_transitive_extras_and_platform_but_not_dev(tmp_path):
    packages = {
        "contextgen-kai": Distribution(tmp_path, "contextgen-kai", requires=(
            "service[ocr]>=1", "dev-only; extra == 'dev'", "windows-extra; sys_platform == 'win32'",
            "mac-extra; sys_platform == 'darwin'")),
        "service": Distribution(tmp_path, "service", requires=("shared>=1", "ocr-data; extra == 'ocr'", "test-only; extra == 'test'")),
        "shared": Distribution(tmp_path, "shared", requires=("service>=1",)),
        "ocr-data": Distribution(tmp_path, "ocr-data"),
        "windows-extra": Distribution(tmp_path, "windows-extra"),
        "mac-extra": Distribution(tmp_path, "mac-extra"),
    }
    def lookup(name):
        return packages[canonicalize_name(name)]
    windows = collector.runtime_distributions(lookup=lookup, environment={"sys_platform": "win32"})
    assert set(windows) == {"service", "shared", "ocr-data", "windows-extra"}
    mac = collector.runtime_distributions(lookup=lookup, environment={"sys_platform": "darwin"})
    assert set(mac) == {"service", "shared", "ocr-data", "mac-extra"}


def test_formal_notices_preserved_and_license_named_code_directories_excluded(tmp_path):
    dist = Distribution(tmp_path, "package", notices=("LICENSE", "NOTICE", "data/BUILD_LICENSES/pdfium.txt"), files={
        "package-1.0.dist-info/licenses/LICENSE": "package license",
        "package-1.0.dist-info/licenses/NOTICE": "package notice",
        "package-1.0.dist-info/licenses/data/BUILD_LICENSES/pdfium.txt": "third party native notice",
        "package/licenses/__init__.py": "print('source')",
        "package/licenses/__pycache__/__init__.cpython-312.pyc": "bytecode",
        "package-1.0.dist-info/licenses/helper.py": "code under metadata licenses too",
        "package/LICENSE.py": "code with a misleading file name",
        "package/LICENSE.txt": "legacy vendored license",
        "package/licenses/README.md": "non-notice developer guide",
    })
    notices = {str(relative): source.read_text() for relative, source in collector.notice_files(dist)}
    assert len(notices) == 4
    assert "third party native notice" in notices.values()
    assert "legacy vendored license" in notices.values()
    assert not any(Path(name).suffix in {".py", ".pyc"} for name in notices)


def test_missing_declared_notice_fails_build(tmp_path):
    dist = Distribution(tmp_path, "package", notices=("LICENSE", "NOTICE"), files={
        "package-1.0.dist-info/licenses/LICENSE": "license",
    })
    with pytest.raises(RuntimeError, match="Declared license files missing.*NOTICE"):
        collector.notice_files(dist)


def test_vendor_license_cannot_replace_distribution_own_declared_license(tmp_path):
    dist = Distribution(tmp_path, "package", notices=("LICENSE",), files={
        "package/_vendor/other-1.0.dist-info/licenses/LICENSE": "vendor license only",
    })
    with pytest.raises(RuntimeError, match="Declared license files missing.*LICENSE"):
        collector.notice_files(dist)


def test_collect_keeps_python_and_bootloader_without_build_tool_dependencies(tmp_path):
    packages = {
        "contextgen-kai": Distribution(tmp_path, "contextgen-kai", requires=("runtime>=1", "pytest; extra == 'dev'")),
        "runtime": Distribution(tmp_path, "runtime"),
        "pyinstaller": Distribution(tmp_path, "pyinstaller", requires=("build-tool>=1",), notices=("COPYING.txt",)),
    }
    for name in collector.BUNDLED_OPTIONAL_DISTRIBUTIONS:
        packages[name] = Distribution(tmp_path, name)
    prefix = tmp_path / "python"
    prefix.mkdir()
    original = "Python runtime and standard library original rights\n"
    (prefix / "LICENSE.txt").write_text(original)
    out = tmp_path / "output"
    infos = collector.collect(out, lookup=lambda name: packages[canonicalize_name(name)], python_prefix=prefix)
    assert {item["name"] for item in infos} == {"runtime", "pyinstaller", "lxml", "packaging", "setuptools"}
    assert (out / "Python-LICENSE.txt").read_text() == original
    assert (out / "pyinstaller/pyinstaller-1.0.dist-info/licenses/COPYING.txt").is_file()
    assert not any(p.suffix in {".py", ".pyc"} for p in out.rglob("*"))
    # 古いビルドの混入を黙って残さない。再実行はクリーンな配布先を必要とする。
    with pytest.raises(RuntimeError, match="must be empty"):
        collector.collect(out, lookup=lambda name: packages[canonicalize_name(name)], python_prefix=prefix)


def test_installed_runtime_notices_have_no_python_source():
    distributions = collector.runtime_distributions()
    assert "fastapi" in distributions and "starlette" in distributions
    assert not {"pytest", "playwright", "pip", "pipx", "pyinstaller"}.intersection(distributions)
    for name in collector.BUNDLED_OPTIONAL_DISTRIBUTIONS:
        distributions[name] = collector.metadata.distribution(name)
    for dist in distributions.values():
        notices = collector.notice_files(dist)
        assert notices
        assert all(relative.suffix.lower() not in collector.CODE_SUFFIXES for relative, _ in notices)
