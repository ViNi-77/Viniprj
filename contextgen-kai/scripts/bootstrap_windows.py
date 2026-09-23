"""Git取得後の初回セットアップと安全な更新。標準ライブラリだけで動作する。"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_BRANCHES = {"main", "codex/contextgen-kai"}
ALLOWED_ORIGINS = {
    "https://github.com/ViNi-77/Viniprj.git", "https://github.com/ViNi-77/Viniprj",
    "git@github.com:ViNi-77/Viniprj.git", "ssh://git@github.com/ViNi-77/Viniprj.git",
}


def load_installation(root: Path):
    spec = importlib.util.spec_from_file_location("contextgen_installation", root / "contextgen_kai/installation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(command, *, root: Path, capture=False):
    result = subprocess.run([str(part) for part in command], cwd=root, check=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None,
                            encoding="utf-8", errors="replace")
    return result.stdout.strip() if capture else None


def dependency_fingerprint(root: Path) -> str:
    digest = hashlib.sha256(b"contextgen-kai-bootstrap-v1\0")
    for name in ("requirements.lock", "pyproject.toml"):
        digest.update(name.encode("ascii") + b"\0" + (root / name).read_bytes())
    return digest.hexdigest()


def venv_python(root: Path) -> Path:
    return root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def environment_current(root: Path) -> bool:
    marker = root / ".venv/.contextgen-dependencies.sha256"
    return (venv_python(root).is_file() and marker.is_file()
            and marker.read_text(encoding="ascii").strip() == dependency_fingerprint(root))


def prepare(root: Path) -> Path:
    """同期済みなら共有ロックで検査だけ。環境を変更する呼出側は排他ロックを保持する。"""
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Git版にはPython 3.12（64bit）が必要です。Pythonを導入せず使う場合はWindows配布ZIPをご利用ください。")
    if os.name == "nt":
        if sys.maxsize <= 2**32:
            raise RuntimeError("Python 3.12の64bit版を使用してください。")
        run([sys.executable, root / "packaging/verify_ocr_bundle.py", "--root", root / "ocr"], root=root)
    python = venv_python(root)
    if not python.is_file():
        print("初回セットアップ: このフォルダ専用のPython環境を作成しています。", flush=True)
        run([sys.executable, "-m", "venv", root / ".venv"], root=root)
    run([python, "-c", "import sys; assert sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32, 'Python 3.12 (64bit) required'"], root=root)
    stamp = root / ".venv/.contextgen-dependencies.sha256"
    fingerprint = dependency_fingerprint(root)
    if not stamp.is_file() or stamp.read_text(encoding="ascii").strip() != fingerprint:
        print("依存ファイルを同期しています。初回・依存変更時はインターネット接続が必要です。", flush=True)
        run([python, "-m", "pip", "install", "--disable-pip-version-check", "-r", root / "requirements.lock"], root=root)
        run([python, "-m", "pip", "install", "--disable-pip-version-check", "--no-deps", "--no-build-isolation", "-e", root], root=root)
        run([python, "-c", "import fastapi, uvicorn, pypdf, pypdfium2, PIL, openpyxl, contextgen_kai"], root=root)
        temporary = stamp.with_suffix(".tmp")
        temporary.write_text(fingerprint + "\n", encoding="ascii")
        temporary.replace(stamp)
        print("初回セットアップ／依存更新が完了しました。", flush=True)
    else:
        print("依存ファイルは同期済みです。追加ダウンロードなしで起動できます。", flush=True)
    return python


def update(root: Path):
    """現在の安全な追跡ブランチをfast-forwardのみで更新し、変更を消さない。"""
    def git(*arguments):
        return run(["git", *arguments], root=root, capture=True)

    repository = Path(git("rev-parse", "--show-toplevel")).resolve()
    if repository != root.parent.resolve() or root.name != "contextgen-kai":
        raise RuntimeError("Viniprj/contextgen-kai のGit取得フォルダから実行してください。")
    origin = git("config", "--get", "remote.origin.url")
    if origin not in ALLOWED_ORIGINS:
        raise RuntimeError("origin が ViNi-77/Viniprj ではないため自動更新を停止しました。Gitの接続先を確認してください。")
    branch = git("branch", "--show-current")
    if branch not in ALLOWED_BRANCHES:
        raise RuntimeError("自動更新の対象は main / codex/contextgen-kai です。現在のブランチは変更していません。")
    if git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("追跡対象のファイルにローカル変更があります。変更を残したまま更新を停止しました。先にGitの差分を確認してください。")
    before = git("rev-parse", "HEAD")
    print(f"Gitから {branch} を更新します（既存データ・ローカル変更を削除する操作は行いません）。", flush=True)
    run(["git", "pull", "--ff-only", "origin", branch], root=root)
    after = git("rev-parse", "HEAD")
    print("すでに最新版です。" if before == after else f"更新しました: {before[:8]} → {after[:8]}", flush=True)
    print("「起動.bat」を開くと、必要な依存更新を確認してアプリを起動します。", flush=True)


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    setup_only = arguments == ["--setup-only"]
    update_only = arguments == ["--update-only"]
    try:
        installation = load_installation(ROOT)
        if update_only:
            with installation.installation_lock(ROOT, shared=False):
                update(ROOT)
                return 0
        while True:
            with installation.installation_lock(ROOT, shared=True):
                if environment_current(ROOT):
                    python = prepare(ROOT)
                    if setup_only:
                        return 0
                    # 起動前の検査から子プロセス終了まで共有を保持し、途中の更新を防ぐ。
                    # 同期済みのUI起動は、バックグラウンド予約の共有ロックと共存できる。
                    return subprocess.call([str(python), "-m", "contextgen_kai", *arguments], cwd=ROOT)
            # ロックの昇格は行わずいったん解放。排他取得後にprepareが再判定する。
            with installation.installation_lock(ROOT, shared=False):
                prepare(ROOT)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"\n起動・更新を中止しました: {error}", file=sys.stderr, flush=True)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
