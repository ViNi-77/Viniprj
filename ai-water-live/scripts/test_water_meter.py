"""water_meter の単体テスト（標準ライブラリの unittest）。作り物の jsonl を使う。"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import water_meter as wm  # noqa: E402

P = wm.load_params()
TODAY = dt.date.today()
NOW_UTC = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def line(mid: str, model: str, usage: dict, ts: dt.datetime = NOW_UTC, extra: dict | None = None) -> str:
    o = {"type": "assistant", "timestamp": ts.isoformat().replace("+00:00", "Z"), "message": {"id": mid, "model": model, "usage": usage, "content": [{"type": "text", "text": "秘密の本文"}]}}
    if extra:
        o.update(extra)
    return json.dumps(o, ensure_ascii=False)


class WaterMeterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.projects = root / "claude" / "projects" / "-proj"
        self.projects.mkdir(parents=True)
        os.environ["CLAUDE_CONFIG_DIR"] = str(root / "claude")
        os.environ["AI_WATER_CACHE"] = str(root / "cache")
        self.f = self.projects / "sess-a.jsonl"
        lines = [
            line("m1", "claude-opus-5-5", {"input_tokens": 1000, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 100000, "output_tokens": 2000}),
            line("m1", "claude-opus-5-5", {"input_tokens": 1000, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 100000, "output_tokens": 2000}),  # 重複
            line("m2", "claude-sonnet-5-5", {"input_tokens": 0, "cache_creation_input_tokens": 8000, "cache_creation": {"ephemeral_5m_input_tokens": 4000, "ephemeral_1h_input_tokens": 4000}, "cache_read_input_tokens": 0, "output_tokens": 1000}),
            line("m3", "claude-haiku-5-5", {"input_tokens": 500, "output_tokens": 500}, ts=NOW_UTC - dt.timedelta(days=3)),
            "{壊れた行",
            json.dumps({"type": "user", "message": {"role": "user", "content": "本文だけの行"}}, ensure_ascii=False),
        ]
        self.f.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        os.environ.pop("AI_WATER_CACHE", None)

    def test_class_mapping(self) -> None:
        self.assertEqual(wm.class_for("claude-opus-5-5", P), "frontier")
        self.assertEqual(wm.class_for("claude-fable-5-1", P), "frontier")
        self.assertEqual(wm.class_for("claude-sonnet-5-5", P), "standard")
        self.assertEqual(wm.class_for("claude-haiku-5-5", P), "light")
        self.assertEqual(wm.class_for("something-else", P), "standard")

    def test_weights_and_dedup(self) -> None:
        s = wm.refresh()
        t = s["today"]
        # m1 は 1 回だけ数える。m3 は 3 日前なので今日に入らない
        self.assertEqual(t["tokens"], {"input": 1000, "cw5m": 4000, "cw1h": 4000, "cr": 100000, "out": 3000})
        self.assertEqual(t["messages"], 2)  # m1（重複は 1 回）と m2
        w_opus = 1000 * 1.0 + 100000 * 0.1 + 2000 * 5.0          # 21,000
        w_sonnet = 4000 * 1.25 + 4000 * 2.0 + 1000 * 5.0         # 18,000
        self.assertAlmostEqual(t["weightedTokens"], w_opus + w_sonnet)
        kwh_mid = (w_opus / 1000 * 3.0 + w_sonnet / 1000 * 1.0) / 1000
        self.assertAlmostEqual(t["kWh"]["mid"], kwh_mid)
        self.assertAlmostEqual(t["liters"]["mid"], kwh_mid * (0.375 + 4.5))
        self.assertAlmostEqual(t["kWh"]["low"], kwh_mid * 0.3)
        self.assertAlmostEqual(t["kWh"]["high"], kwh_mid * 3.0)
        # 7 日には m3 も入る
        self.assertEqual(s["week"]["tokens"]["out"], 3500)
        # キャッシュが無ければもっと多い
        self.assertGreater(t["litersNoCache"], t["liters"]["mid"])

    def test_incremental_and_partial_line(self) -> None:
        wm.refresh()
        with open(self.f, "a", encoding="utf-8") as fh:
            fh.write(line("m4", "claude-sonnet-5-5", {"input_tokens": 1000, "output_tokens": 0}) + "\n")
            fh.write('{"message": {"id": "m5", "usage": {"input_tokens": 9')  # 書きかけ
        s = wm.refresh()
        self.assertEqual(s["today"]["tokens"]["input"], 2000)
        with open(self.f, "a", encoding="utf-8") as fh:
            fh.write('99}}, "timestamp": "' + NOW_UTC.isoformat().replace("+00:00", "Z") + '"}\n')
        s = wm.refresh()
        self.assertEqual(s["today"]["tokens"]["input"], 2999)

    def test_does_not_store_text(self) -> None:
        wm.refresh()
        state = (Path(os.environ["AI_WATER_CACHE"]) / "state.json").read_text(encoding="utf-8")
        today = (Path(os.environ["AI_WATER_CACHE"]) / "today.json").read_text(encoding="utf-8")
        self.assertNotIn("秘密の本文", state)
        self.assertNotIn("秘密の本文", today)
        self.assertNotIn("本文だけの行", state)

    def test_statusline_one_line_and_width(self) -> None:
        s = wm.refresh()
        out = wm.statusline(s)
        self.assertNotIn("\n", out)
        self.assertLessEqual(wm.width(out), 64)
        self.assertIn("💧今日", out)


class InstallerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["CLAUDE_CONFIG_DIR"] = self.tmp.name
        import install_statusline as ins
        self.ins = ins
        self.sp = Path(self.tmp.name) / "settings.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()
        os.environ.pop("CLAUDE_CONFIG_DIR", None)

    def test_install_keeps_other_keys_and_is_idempotent(self) -> None:
        self.sp.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
        self.ins.main([])
        d = json.loads(self.sp.read_text(encoding="utf-8"))
        self.assertEqual(d["theme"], "dark")
        self.assertTrue(self.ins.is_ours(d["statusLine"]["command"]))
        self.ins.main([])  # 2 回目も自分のものとして扱う
        self.assertTrue(self.ins.is_ours(json.loads(self.sp.read_text(encoding="utf-8"))["statusLine"]["command"]))
        self.ins.main(["--uninstall"])
        self.assertEqual(json.loads(self.sp.read_text(encoding="utf-8")), {"theme": "dark"})

    def test_fresh_install_twice_then_uninstall(self) -> None:
        # 設定ファイルが無い状態から 2 回入れても、外すと statusLine が消える
        self.ins.main([])
        self.ins.main([])
        self.assertFalse((Path(self.tmp.name) / "settings.json.bak-ai-water").exists())
        self.ins.main(["--uninstall"])
        self.assertNotIn("statusLine", json.loads(self.sp.read_text(encoding="utf-8")))

    def test_does_not_overwrite_other_statusline(self) -> None:
        other = {"statusLine": {"type": "command", "command": "my-line.sh"}}
        self.sp.write_text(json.dumps(other), encoding="utf-8")
        self.ins.main([])
        self.assertEqual(json.loads(self.sp.read_text(encoding="utf-8")), other)


if __name__ == "__main__":
    unittest.main()
