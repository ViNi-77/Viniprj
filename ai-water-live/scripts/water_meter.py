"""あなたの水 — Claude Code の利用記録から、蒸発させた淡水を数える。

~/.claude/projects/**/*.jsonl の各行から message.usage・message.model・message.id・timestamp だけを読む
（会話の本文・ツールの入出力は読まない。どこにも送らない）。
差分読みの状態は ~/.cache/ai-water/state.json（Windows は %LOCALAPPDATA%\\ai-water）に置く。

  python water_meter.py --summary            日別の表（直近 7 日）
  python water_meter.py --json               今日・7 日・直近セッションの JSON（today.json にも書く）
  python water_meter.py --statusline         Claude Code のステータス行（stdin に session_id / transcript_path の JSON）

数値はすべて ../src/data/params.json（画面と共有）から読む。標準ライブラリのみ。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARAMS_PATH = HERE.parent / "src" / "data" / "params.json"
STATE_VERSION = 3
KEEP_DAYS = 35
TOKEN_KEYS = ("input", "cw5m", "cw1h", "cr", "out")
COUNTERS = TOKEN_KEYS + ("msgs",)  # msgs = 応答の数（重複除外後）


# ---------------------------------------------------------------- 設定と置き場
def load_params(path: Path = PARAMS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def claude_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def cache_dir() -> Path:
    if os.environ.get("AI_WATER_CACHE"):
        return Path(os.environ["AI_WATER_CACHE"])
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "ai-water"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "ai-water"


# ---------------------------------------------------------------- 1 行の解釈
def class_for(model_id: str | None, params: dict) -> str:
    m = (model_id or "").lower()
    for r in params["modelIdToClass"]:
        if r["match"] in m:
            return r["class"]
    return params["defaultModelClass"]


def usage_counters(u: dict) -> dict[str, int]:
    """usage → 5 種の数。cache_creation の内訳（5 分 / 1 時間）があれば分ける"""
    cc = u.get("cache_creation") if isinstance(u.get("cache_creation"), dict) else None
    total_cw = int(u.get("cache_creation_input_tokens") or 0)
    if cc:
        cw1h = int(cc.get("ephemeral_1h_input_tokens") or 0)
        cw5m = int(cc.get("ephemeral_5m_input_tokens") or 0)
        rest = max(0, total_cw - cw1h - cw5m)
        cw5m += rest
    else:
        cw1h, cw5m = 0, total_cw
    return {
        "input": int(u.get("input_tokens") or 0),
        "cw5m": cw5m,
        "cw1h": cw1h,
        "cr": int(u.get("cache_read_input_tokens") or 0),
        "out": int(u.get("output_tokens") or 0),
        "msgs": 1,
    }


def local_day(ts: str | None) -> str:
    if not ts:
        return dt.date.today().isoformat()
    try:
        t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        return t.astimezone().date().isoformat()
    except ValueError:
        return dt.date.today().isoformat()


# ---------------------------------------------------------------- 差分読み
def empty_state() -> dict:
    return {"version": STATE_VERSION, "files": {}}


def load_state(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            s = json.load(f)
        if s.get("version") == STATE_VERSION:
            return s
    except (OSError, ValueError):
        pass
    return empty_state()


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".state-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, separators=(",", ":"))
    os.replace(tmp, path)


def scan_file(path: Path, entry: dict, params: dict) -> dict:
    """entry = {offset, size, seen:[ids], days:{day:{cls:{counter:n}}}, last} を続きから更新する"""
    try:
        size = path.stat().st_size
    except OSError:
        return entry
    if size < entry.get("offset", 0):  # 切り詰められた → 最初から
        entry = {"offset": 0, "seen": [], "days": {}}
    if size == entry.get("offset", 0):
        return entry
    seen = set(entry.get("seen", []))
    days = entry.setdefault("days", {})
    with open(path, "rb") as f:
        f.seek(entry.get("offset", 0))
        data = f.read()
    end = data.rfind(b"\n")
    if end < 0:
        return entry  # 書きかけの 1 行だけ
    for raw in data[: end + 1].splitlines():
        if b'"usage"' not in raw:
            continue  # 本文だけの行は解釈しない
        try:
            o = json.loads(raw)
        except ValueError:
            continue
        m = o.get("message")
        if not isinstance(m, dict) or not isinstance(m.get("usage"), dict):
            continue
        mid = m.get("id") or o.get("uuid")
        if mid in seen:
            continue  # 同じ応答が複数行に分かれて記録される
        if mid:
            seen.add(mid)
        day = local_day(o.get("timestamp"))
        cls = class_for(m.get("model"), params)
        bucket = days.setdefault(day, {}).setdefault(cls, {k: 0 for k in COUNTERS})
        for k, v in usage_counters(m["usage"]).items():
            bucket[k] = bucket.get(k, 0) + v
        entry["last"] = o.get("timestamp") or entry.get("last")
    entry["offset"] = entry.get("offset", 0) + end + 1
    entry["seen"] = list(seen)[-5000:]
    return entry


def update(state: dict, root: Path, params: dict) -> dict:
    files = state.setdefault("files", {})
    for p in root.glob("*/*.jsonl"):
        key = str(p)
        files[key] = scan_file(p, files.get(key, {"offset": 0, "seen": [], "days": {}}), params)
    # 古い日を捨てる
    cutoff = (dt.date.today() - dt.timedelta(days=KEEP_DAYS)).isoformat()
    for e in files.values():
        for d in [d for d in e.get("days", {}) if d < cutoff]:
            del e["days"][d]
    return state


# ---------------------------------------------------------------- 水に換算
def weighted(c: dict, w: dict) -> float:
    return c["input"] * w["input"] + c["cw5m"] * w["cw5m_w"] + c["cw1h"] * w["cw1h_w"] + c["cr"] * w["cacheRead"] + c["out"] * w["output"]


def weights(params: dict) -> dict:
    w = dict(params["tokenWeights"])
    w["cw5m_w"], w["cw1h_w"] = w["cacheWrite5m"], w["cacheWrite1h"]
    return w


def water(buckets: list[dict[str, dict]], params: dict) -> dict:
    """buckets: [{cls: counters}] → 加重トークン・kWh・L（低/中/高）・キャッシュなしの L"""
    w = weights(params)
    nocache = {"input": 1.0, "cw5m_w": 1.0, "cw1h_w": 1.0, "cacheRead": 1.0, "output": w["output"]}
    raw = {k: 0 for k in COUNTERS}
    wt = 0.0
    kwh = {lvl: 0.0 for lvl in ("low", "mid", "high")}
    kwh_nocache = 0.0
    by_class: dict[str, float] = {}
    mid_wh = params["presets"]["mid"]["whPerKTok"]
    for b in buckets:
        for cls, c in b.items():
            for k in COUNTERS:
                raw[k] += c.get(k, 0)
            x = weighted(c, w)
            wt += x
            by_class[cls] = by_class.get(cls, 0) + x
            cls_wh = params["modelClasses"].get(cls, params["modelClasses"][params["defaultModelClass"]])["whPerKTok"]
            for lvl, p in params["presets"].items():
                # 級の Wh に、前提の幅（低 0.3 / 中 1 / 高 3 倍）を掛ける
                kwh[lvl] += x / 1000 * cls_wh * (p["whPerKTok"] / mid_wh) / 1000
            kwh_nocache += weighted(c, nocache) / 1000 * cls_wh / 1000
    msgs = raw.pop("msgs", 0)
    out = {"tokens": raw, "tokensTotal": sum(raw.values()), "messages": msgs, "weightedTokens": wt, "byClass": by_class, "kWh": kwh}
    out["liters"] = {lvl: kwh[lvl] * (p["wue"] + p["offsite"]) for lvl, p in params["presets"].items()}
    mid = params["presets"]["mid"]
    out["litersOnsite"] = kwh["mid"] * mid["wue"]
    out["litersNoCache"] = kwh_nocache * (mid["wue"] + mid["offsite"])
    out["bottles"] = out["liters"]["mid"] / params["bottleLiters"]
    return out


def summarize(state: dict, params: dict, session_file: str | None = None, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    t = today.isoformat()
    week = {(today - dt.timedelta(days=i)).isoformat() for i in range(7)}
    files = state.get("files", {})
    today_b, week_b, sess_b = [], [], []
    per_day: dict[str, list] = {}
    latest_key, latest_ts = None, ""
    for key, e in files.items():
        for d, b in e.get("days", {}).items():
            if d == t:
                today_b.append(b)
            if d in week:
                week_b.append(b)
                per_day.setdefault(d, []).append(b)
        if (e.get("last") or "") > latest_ts:
            latest_ts, latest_key = e.get("last") or "", key
    sk = session_file if session_file and session_file in files else latest_key
    if sk:
        sess_b = list(files[sk].get("days", {}).values())
    return {
        "asOf": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "today": water(today_b, params),
        "week": water(week_b, params),
        "session": water(sess_b, params),
        "sessionId": Path(sk).stem if sk else None,
        "days": {d: water(per_day[d], params) for d in sorted(per_day)},
        "preset": "mid",
        "sourceIds": ["PR1", "MR1", "L1"],
    }


def refresh(params: dict | None = None, session_file: str | None = None) -> dict:
    params = params or load_params()
    sp = cache_dir() / "state.json"
    state = update(load_state(sp), claude_dir() / "projects", params)
    save_state(sp, state)
    s = summarize(state, params, session_file)
    try:
        tmp = cache_dir() / ".today.json.tmp"
        tmp.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, cache_dir() / "today.json")
    except OSError:
        pass
    return s


# ---------------------------------------------------------------- 表示
def fmt_l(x: float) -> str:
    if x < 1:
        return f"{x * 1000:.0f} mL"
    if x < 10:
        return f"{x:.2f} L"
    if x < 1000:
        return f"{x:.1f} L"
    if x < 10000:
        return f"{x:,.0f} L"
    return f"{x / 10000:.1f} 万 L"


def width(s: str) -> int:
    import re
    s = re.sub(r"\x1b\[[0-9;]*m", "", s)
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def bar(frac: float, cells: int = 8) -> str:
    blocks = " ▏▎▍▌▋▊▉█"
    frac = max(0.0, min(1.0, frac))
    full = int(frac * cells)
    rem = int((frac * cells - full) * 8)
    s = "█" * full + (blocks[rem] if full < cells else "")
    return s.ljust(cells)


def statusline(s: dict, color: bool = True) -> str:
    today, sess = s["today"], s["session"]
    L = today["liters"]["mid"]
    bottles = int(L // 0.5)
    frac = (L % 0.5) / 0.5
    saved = max(0.0, today["litersNoCache"] - L)
    blue, dim, reset = ("\x1b[38;5;74m", "\x1b[2m", "\x1b[0m") if color else ("", "", "")
    parts = [f"💧今日 {fmt_l(L)} ▕{blue}{bar(frac)}{reset}▏{bottles}本",
             f"会話 {fmt_l(sess['liters']['mid'])}"]
    if saved >= 0.05:
        parts.append(f"{dim}節水 {fmt_l(saved)}{reset}")
    return " · ".join(parts)


def summary_table(s: dict) -> str:
    rows = ["日付        加重トークン   電力      水（低 / 中 / 高）              ボトル   キャッシュ無しなら"]
    for d, w in s["days"].items():
        rows.append(f"{d}  {w['weightedTokens'] / 1e6:9.2f}M  {w['kWh']['mid']:7.2f} kWh  "
                    f"{fmt_l(w['liters']['low']):>8} / {fmt_l(w['liters']['mid']):>8} / {fmt_l(w['liters']['high']):>8}  "
                    f"{w['bottles']:6.0f}本  {fmt_l(w['litersNoCache']):>8}")
    t = s["today"]
    rows.append("")
    rows.append(f"今日: {fmt_l(t['liters']['mid'])}（幅 {fmt_l(t['liters']['low'])} – {fmt_l(t['liters']['high'])}）= 500 mL ペットボトル {t['bottles']:.0f} 本。"
                f"キャッシュが無ければ {fmt_l(t['litersNoCache'])}。")
    rows.append("前提: 価格比の重み（PR1）× モデル級の Wh（MR1）×（施設内 WUE + 発電側の水）（L1）。すべて推計。")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--statusline", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--no-color", action="store_true")
    a = ap.parse_args(argv)
    if a.statusline:
        session_file = None
        try:
            if not sys.stdin.isatty():
                info = json.loads(sys.stdin.read() or "{}")
                session_file = info.get("transcript_path")
        except ValueError:
            pass
        try:
            s = refresh(session_file=session_file)
            sys.stdout.write(statusline(s, color=not a.no_color))
        except Exception as e:  # noqa: BLE001 - ステータス行は落とさない
            sys.stdout.write(f"💧 計測できません（{type(e).__name__}）")
        return 0
    s = refresh()
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
    else:
        print(summary_table(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
