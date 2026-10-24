"""Claude Code のステータス行に「あなたの水」を出す / 外す。

  python install_statusline.py              入れる（~/.claude/settings.json をバックアップしてから statusLine を足す）
  python install_statusline.py --uninstall  外す（入れたときの状態に戻す）

既に別の statusLine がある場合は上書きせず、案内だけ出して終わる（--force で上書き）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
METER = HERE / "water_meter.py"
def is_ours(cmd: object) -> bool:
    """自分が入れたステータス行か（パスは引用符で囲まれるので、部品ごとに見る）"""
    c = str(cmd or "")
    return "water_meter.py" in c and "--statusline" in c


def settings_path() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "settings.json"


def command() -> str:
    py = sys.executable or ("python" if os.name == "nt" else "python3")
    return f'"{py}" "{METER}" --statusline'


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    sp = settings_path()
    backup = sp.with_name(sp.name + ".bak-ai-water")
    data: dict = {}
    if sp.exists():
        try:
            data = json.loads(sp.read_text(encoding="utf-8") or "{}")
        except ValueError:
            print(f"{sp} が JSON として読めません。手で直してから再実行してください。")
            return 1

    if a.uninstall:
        cur = data.get("statusLine") or {}
        if not is_ours(cur.get("command")):
            print("ステータス行は「あなたの水」ではありません。何もしません。")
            return 0
        restored = False
        if backup.exists():
            try:
                old = json.loads(backup.read_text(encoding="utf-8") or "{}")
            except ValueError:
                old = None
            if isinstance(old, dict) and not is_ours((old.get("statusLine") or {}).get("command")):
                shutil.copy2(backup, sp)
                backup.unlink()
                restored = True
                print(f"{backup.name} から元に戻しました。")
        if not restored:
            data.pop("statusLine", None)
            sp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("statusLine を外しました。")
        return 0

    cur = data.get("statusLine")
    if cur and not is_ours(cur.get("command")) and not a.force:
        print("既に別のステータス行が設定されています。上書きしません。")
        print(f"  現在: {cur}")
        print(f"  入れるなら --force、または次のコマンドを今のステータス行に足してください:\n  {command()}")
        return 0
    sp.parent.mkdir(parents=True, exist_ok=True)
    if sp.exists() and not backup.exists() and not is_ours((cur or {}).get("command")):
        shutil.copy2(sp, backup)
        print(f"バックアップ: {backup}")
    data["statusLine"] = {"type": "command", "command": command(), "padding": 0}
    sp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"入れました: {sp}")
    print("Claude Code を開き直すと、画面下に「💧今日 …」が出ます。外すときは --uninstall。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
