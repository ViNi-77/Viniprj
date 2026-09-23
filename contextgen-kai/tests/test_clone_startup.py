"""Git更新の実リポジトリ操作とインストール失敗時の再試行・実行中排他を検証する。"""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from contextgen_kai.installation import InstallationBusy, installation_lock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bootstrap_windows", ROOT / "scripts/bootstrap_windows.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def test_shared_app_locks_allow_background_and_block_update(tmp_path):
    script = (
        "from pathlib import Path; from contextgen_kai.installation import installation_lock; "
        "import sys; "
        "lock=installation_lock(Path(sys.argv[1]), shared=sys.argv[2]=='shared'); "
        "lock.__enter__(); lock.__exit__(None,None,None)"
    )
    with installation_lock(tmp_path, shared=True):
        shared = subprocess.run([sys.executable, "-c", script, str(tmp_path), "shared"], capture_output=True)
        assert shared.returncode == 0, shared.stderr
        exclusive = subprocess.run([sys.executable, "-c", script, str(tmp_path), "exclusive"], capture_output=True)
        assert exclusive.returncode != 0
    # 正常終了/異常終了後はOSが解放し、古いlockファイルが残っても更新できる。
    subprocess.run([sys.executable, "-c", script, str(tmp_path), "exclusive"], check=True)


def test_exclusive_update_blocks_app(tmp_path):
    with installation_lock(tmp_path, shared=False):
        with pytest.raises(InstallationBusy):
            with installation_lock(tmp_path, shared=True):
                pass


def test_dependency_failure_does_not_mark_success_and_unchanged_start_stays_offline(tmp_path, monkeypatch):
    (tmp_path / "requirements.lock").write_text("pinned==1\n")
    (tmp_path / "pyproject.toml").write_text("name = 'example'\n")
    python = bootstrap.venv_python(tmp_path)
    python.parent.mkdir(parents=True)
    python.touch()
    marker = tmp_path / ".venv/.contextgen-dependencies.sha256"
    commands = []
    fail_install = True

    def run(command, **kwargs):
        commands.append([str(item) for item in command])
        if "pip" in command and fail_install:
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(bootstrap, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        bootstrap.prepare(tmp_path)
    assert not marker.exists()
    fail_install = False
    assert bootstrap.prepare(tmp_path) == python
    first_fingerprint = marker.read_text()
    commands.clear()
    bootstrap.prepare(tmp_path)
    assert not any("pip" in command for command in commands)
    (tmp_path / "pyproject.toml").write_text("name = 'updated'\n")
    bootstrap.prepare(tmp_path)
    assert any("pip" in command for command in commands)
    assert marker.read_text() != first_fingerprint
    old_marker = marker.read_text()
    (tmp_path / "requirements.lock").write_text("pinned==2\n")
    fail_install = True
    with pytest.raises(subprocess.CalledProcessError):
        bootstrap.prepare(tmp_path)
    assert marker.read_text() == old_marker


def test_synced_start_can_open_ui_during_background_job_but_dependency_update_cannot(tmp_path, monkeypatch):
    (tmp_path / "requirements.lock").write_text("pinned==1\n")
    (tmp_path / "pyproject.toml").write_text("name = 'example'\n")
    python = bootstrap.venv_python(tmp_path)
    python.parent.mkdir(parents=True)
    python.touch()
    marker = tmp_path / ".venv/.contextgen-dependencies.sha256"
    marker.write_text(bootstrap.dependency_fingerprint(tmp_path) + "\n", encoding="ascii")
    module = bootstrap.load_installation(ROOT)
    monkeypatch.setattr(bootstrap, "ROOT", tmp_path)
    monkeypatch.setattr(bootstrap, "load_installation", lambda root: module)
    commands = []
    monkeypatch.setattr(bootstrap, "run", lambda command, **kwargs: commands.append(command))
    launches = []

    def launch(command, **kwargs):
        launches.append(command)
        # 起動前から子プロセス待機中も共有ロックが途切れず、更新を防止する。
        with pytest.raises(InstallationBusy):
            with installation_lock(tmp_path, shared=False):
                pass
        return 0

    monkeypatch.setattr(bootstrap.subprocess, "call", launch)
    with installation_lock(tmp_path, shared=True):
        assert bootstrap.main(["--no-browser"]) == 0
        assert launches == [[str(python), "-m", "contextgen_kai", "--no-browser"]]
        assert not any("pip" in command for command in commands)
        assert bootstrap.main(["--setup-only"]) == 0
        (tmp_path / "requirements.lock").write_text("pinned==2\n")
        assert bootstrap.main(["--no-browser"]) == 1
        assert len(launches) == 1
        assert not any("pip" in command for command in commands)


@pytest.fixture
def git_checkout(tmp_path, monkeypatch):
    # 実Gitとローカルbareリポジトリでff-onlyの動作を確認。ネット接続は行わない。
    git = shutil.which("git")
    assert git is not None
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_CONFIG_COUNT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Contextgen Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Contextgen Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.invalid")
    remote = tmp_path / "remote.git"
    subprocess.run([git, "init", "--bare", str(remote)], check=True, capture_output=True)
    checkout = tmp_path / "Viniprj"
    subprocess.run([git, "clone", str(remote), str(checkout)], check=True, capture_output=True)

    def command(*args, cwd=checkout):
        return subprocess.check_output([git, *args], cwd=cwd, text=True, encoding="utf-8", stderr=subprocess.STDOUT).strip()

    command("checkout", "-b", "codex/contextgen-kai")
    root = checkout / "contextgen-kai"
    root.mkdir()
    (root / "version.txt").write_text("1\n")
    (checkout / ".gitignore").write_text("contextgen-kai/.runtime/\n")
    command("add", ".")
    command("commit", "-m", "Initial fixture")
    command("push", "-u", "origin", "codex/contextgen-kai")
    peer = tmp_path / "peer"
    command("clone", "--branch", "codex/contextgen-kai", str(remote), str(peer), cwd=tmp_path)
    command("remote", "set-url", "origin", "https://github.com/ViNi-77/Viniprj.git")
    # 論理originは検証対象の公式URLに保ち、転送先だけローカルbareへ向ける。
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{remote.as_posix()}.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://github.com/ViNi-77/Viniprj.git")
    return root, peer, command


def test_update_fast_forwards_without_touching_user_data(git_checkout):
    root, peer, git = git_checkout
    (root / "personal.txt").write_text("keep this\n")
    (peer / "contextgen-kai/version.txt").write_text("2\n")
    git("commit", "-am", "Remote update", cwd=peer)
    git("push", cwd=peer)
    bootstrap.update(root)
    assert (root / "version.txt").read_text() == "2\n"
    assert (root / "personal.txt").read_text() == "keep this\n"
    assert git("branch", "--show-current") == "codex/contextgen-kai"


def test_update_preserves_dirty_unexpected_branch_and_origin(git_checkout):
    root, peer, git = git_checkout
    initial = git("rev-parse", "HEAD")
    (root / "version.txt").write_text("my local changes\n")
    with pytest.raises(RuntimeError, match="ローカル変更"):
        bootstrap.update(root)
    assert git("rev-parse", "HEAD") == initial
    assert (root / "version.txt").read_text() == "my local changes\n"
    git("checkout", "-b", "user-work")
    with pytest.raises(RuntimeError, match="ブランチ"):
        bootstrap.update(root)
    assert git("branch", "--show-current") == "user-work"
    git("checkout", "codex/contextgen-kai")
    git("remote", "set-url", "origin", "https://example.invalid/other.git")
    with pytest.raises(RuntimeError, match="origin"):
        bootstrap.update(root)
    assert git("rev-parse", "HEAD") == initial


def test_diverged_history_is_not_merged_or_reset(git_checkout):
    root, peer, git = git_checkout
    (root / "local.txt").write_text("keep local commit")
    git("add", ".")
    git("commit", "-m", "Local work")
    local = git("rev-parse", "HEAD")
    (peer / "contextgen-kai/version.txt").write_text("remote changes")
    git("commit", "-am", "Other remote work", cwd=peer)
    git("push", cwd=peer)
    with pytest.raises(subprocess.CalledProcessError):
        bootstrap.update(root)
    assert git("rev-parse", "HEAD") == local
    assert (root / "local.txt").read_text() == "keep local commit"
