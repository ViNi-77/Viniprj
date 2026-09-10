"""exe（onedir）をビルドし、配布用 ZIP を作る。Windows で実行すると Windows 用、他の OS で実行するとその OS 用ができる。

  python packaging/build_exe.py            # dist/pptx-web-bridge/ と dist/pptx-web-bridge-<os>.zip
  python packaging/build_exe.py --no-zip
GitHub Actions（.github/workflows/build-windows.yml）はこのスクリプトを Windows ランナーで実行する。
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "pptx-web-bridge"

# Windows の cp1252 / cp932 コンソールでも日本語メッセージで落ちないようにする
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def main() -> int:
    spec = ROOT / "packaging" / "pptx-web-bridge.spec"
    if not (ROOT / "samples" / "sample_deck.pptx").exists():
        subprocess.run([sys.executable, str(ROOT / "samples" / "make_sample_pptx.py")], check=True)
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"), str(spec)]
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=str(ROOT))

    # 利用者が触るもの（設定・テンプレート素材・サンプル・README）を exe の隣に置く
    for rel in ("config", "samples"):
        src, dst = ROOT / rel, DIST / rel
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for rel in ("README.md",):
        shutil.copy2(ROOT / rel, DIST / rel)
    for d in ("projects", "output", "logs"):
        (DIST / d).mkdir(exist_ok=True)
    # ビルド情報（どのコミットから作ったか）を同梱する
    import datetime
    import os

    sha = os.environ.get("GITHUB_SHA", "")
    if not sha:
        try:
            sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True).stdout.strip()
        except OSError:
            sha = "unknown"
    (DIST / "BUILD_INFO.txt").write_text(f"commit: {sha}\nbuilt_at_utc: {datetime.datetime.utcnow().isoformat(timespec='seconds')}Z\nplatform: {platform.platform()}\npython: {platform.python_version()}\n", encoding="utf-8")
    (DIST / "はじめにお読みください.txt").write_text(
        "PPTX <-> Web図解 変換アプリ\n\n"
        "1. pptx-web-bridge.exe をダブルクリックしてください（初回は Windows の SmartScreen が出たら「詳細情報」→「実行」）。\n"
        "2. 黒い窓が開き、数秒後にブラウザで http://127.0.0.1:8765/ が開きます。\n"
        "3. 画面左の枠に PPTX / HTML(ZIP) / JSON をドロップして変換します。samples フォルダに試用ファイルがあります。\n"
        "4. 終了するときは黒い窓を閉じてください。\n\n"
        "設定: config/app_config.json（ポート等）、テンプレート: config/templates.json と config/template_assets/\n"
        "保存: projects/  出力: output/  ログ: logs/app.log\n"
        "見た目優先モードは Windows 標準の Microsoft Edge を使って画像化します（Edge が無い場合は編集性優先へ自動で代替）。\n\n"
        "うまく起動しないとき:\n"
        "- ZIP は C:\\pptx-web-bridge のような短いパスに展開してください（深い階層だと Windows のパス長上限に達することがあります）。\n"
        "- 起動直後にエラーが出た場合は logs/startup_error.log の内容を担当者に共有してください。\n"
        "- 最新版の入手: https://github.com/ViNi-77/Viniprj （dist/windows ブランチに最新の ZIP があります）\n",
        encoding="utf-8",
    )
    print(f"ビルド完了: {DIST}", flush=True)

    if "--no-zip" not in sys.argv:
        tag = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(platform.system(), platform.system().lower())
        zip_base = ROOT / "dist" / f"pptx-web-bridge-{tag}"
        if zip_base.with_suffix(".zip").exists():
            zip_base.with_suffix(".zip").unlink()
        shutil.make_archive(str(zip_base), "zip", root_dir=str(ROOT / "dist"), base_dir="pptx-web-bridge")
        print(f"ZIP: {zip_base.with_suffix('.zip')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
