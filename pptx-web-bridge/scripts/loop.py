"""ループエンジニアリング用の一括検査コマンド。

1 回の反復（Issue → 実装 → 検査 → レビュー → 記録）のうち「検査」と「記録」を 1 コマンドで行う。
  python scripts/loop.py                 # 全工程（サンプル生成 → 単体・API → 模擬PPTX検査 → E2E → 要約）
  python scripts/loop.py --quick         # 単体・API のみ（実装中の高速反復）
  python scripts/loop.py --issue 12      # 記録に Issue 番号を残す
結果は docs/ループ実行記録.md に追記し、終了コードで合否を返す（CI と共用）。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "docs" / "ループ実行記録.md"


def run(name: str, cmd: list[str], timeout: int = 900) -> tuple[str, bool, str]:
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
        ok = r.returncode == 0
        out = (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        ok, out = False, "timeout"
    summary = _summarize(name, out)
    print(f"[{'OK ' if ok else 'NG '}] {name} ({time.time() - t0:.1f}s) {summary}")
    if not ok:
        print(out[-3000:])
    return name, ok, summary


def _summarize(name: str, out: str) -> str:
    # pytest の要約行（"=== 3 failed, 40 passed in 1.2s ===" 形式）だけを見る
    summary_lines = [ln for ln in out.splitlines() if re.match(r"^(=+ )?.*\b\d+ (passed|failed|errors?)\b.* in [\d.]+s( =+)?$", ln)]
    target = summary_lines[-1] if summary_lines else ""
    passed = re.search(r"(\d+) passed", target)
    failed = re.search(r"(\d+) failed", target)
    errors = re.search(r"(\d+) errors?\b", target)
    if passed or failed or errors:
        parts = [f"{passed.group(1)} passed" if passed else "0 passed"]
        if failed:
            parts.append(f"{failed.group(1)} failed")
        if errors:
            parts.append(f"{errors.group(1)} error")
        names = re.findall(r"^(?:FAILED|ERROR) ([^\s]+)", out, re.M)
        return ", ".join(parts) + (f" [{'; '.join(names[:5])}]" if names else "")
    m = re.search(r"総合: ([^\n]+)", out)
    if m:
        return m.group(1)
    m = re.search(r"自動検査（pytest）: ([^\n]+)", out)
    if m:
        return m.group(1)
    return (out.splitlines() or [""])[-1][:80]


def git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT), capture_output=True, text=True).stdout.strip()
    except OSError:
        return "?"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="単体・API 試験のみ")
    ap.add_argument("--issue", default="", help="関連 Issue 番号（記録用）")
    ap.add_argument("--no-log", action="store_true", help="docs/ループ実行記録.md へ追記しない")
    args = ap.parse_args()
    py = sys.executable
    results: list[tuple[str, bool, str]] = []
    if not (ROOT / "samples" / "sample_deck.pptx").exists():
        results.append(run("サンプル PPTX 生成", [py, "samples/make_sample_pptx.py"]))
    results.append(run("単体・API 試験 (pytest)", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--override-ini=addopts=", "tests"]))
    if not args.quick:
        results.append(run("模擬 12 枚 PPTX 生成", [py, "mock-pptx/src/generate_mock_pptx.py"]))
        results.append(run("模擬 12 枚 自動検査", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--override-ini=addopts=", "mock-pptx/tests"]))
        results.append(run("模擬 12 枚 検査記録・プレビュー", [py, "mock-pptx/src/validate_mock_pptx.py"]))
        results.append(run("往復 E2E", [py, "scripts/run_e2e.py"]))
    ok_all = all(ok for _n, ok, _s in results)
    line = f"| {datetime.now().isoformat(timespec='minutes')} | {git_head()} | {('#' + args.issue) if args.issue else ''} | {'quick' if args.quick else 'full'} | {'合格' if ok_all else '不合格'} | " + " / ".join(f"{n}: {s}" for n, _ok, s in results) + " |"
    if not args.no_log:
        if not LOG.exists():
            LOG.write_text("# ループ実行記録\n\n`python scripts/loop.py` の実行ごとに 1 行追記される。レビュー時はこの表と `docs/試験結果.md` を根拠にする。\n\n| 日時 | コミット | Issue | 種別 | 結果 | 内訳 |\n|---|---|---|---|---|---|\n", encoding="utf-8")
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    print("\n" + ("=== 合格: コミット可 ===" if ok_all else "=== 不合格: 修正して再実行 ==="))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
