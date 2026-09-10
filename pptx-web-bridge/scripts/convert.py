"""コマンドライン変換ツール（UI を使わずに E2E を回す）。

例:
  python scripts/convert.py pptx2web samples/sample_deck.pptx output/deck_web
  python scripts/convert.py html2pptx samples/sample_html/long.html output/long.pptx --mode editable
  python scripts/convert.py pptx2json samples/sample_deck.pptx output/deck.json
  python scripts/convert.py json2pptx output/deck.json output/deck2.pptx
  python scripts/convert.py check output/deck.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import pipeline, storage  # noqa: E402
from app.quality_check import check_presentation, summarize  # noqa: E402
from app.web_renderer import write_bundle  # noqa: E402


def _files_next_to(path: Path) -> dict[str, bytes]:
    base = path.parent
    return {str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*") if p.is_file()}


def _print_warnings(warnings: list[dict]) -> None:
    for w in warnings:
        print(f"  [{w.get('code')}] {w.get('message')}" + (f" → {w['fallback']}" if w.get("fallback") else ""))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["pptx2web", "pptx2json", "html2json", "html2pptx", "json2pptx", "json2web", "check"])
    ap.add_argument("src")
    ap.add_argument("dst", nargs="?")
    ap.add_argument("--mode", default=None, help="PPTX 出力モード: editable / visual / hybrid")
    ap.add_argument("--template", default=None, help="テンプレート ID")
    args = ap.parse_args(argv)
    src = Path(args.src)
    data = src.read_bytes()

    ext = src.suffix.lower()
    if args.command in ("pptx2web", "pptx2json") or (args.command == "check" and ext == ".pptx"):
        res = pipeline.import_pptx(data, src.name, args.template)
    elif args.command in ("html2json", "html2pptx") or (args.command == "check" and ext in (".html", ".htm", ".zip")):
        res = pipeline.import_html(data, src.name, args.template, _files_next_to(src) if ext != ".zip" else None)
    else:
        raw = json.loads(data.decode("utf-8"))
        from app.validate import validate_and_repair

        pres, errors, fixes = validate_and_repair(raw)
        res = {"presentation": pres, "warnings": fixes, "schema_errors": errors, "quality": {"issues": check_presentation(pres), "summary": summarize(check_presentation(pres))}}
    pres = res["presentation"]
    print(f"取込: slides={len(pres['slides'])} assets={len(pres.get('assets', {}))} warnings={len(res['warnings'])} schema_errors={len(res['schema_errors'])}")
    _print_warnings(res["warnings"])

    if args.command == "check":
        q = res["quality"]
        print(f"品質検査: {q['summary']}")
        for i in q["issues"]:
            print(f"  [{i['severity']}] [{i['code']}] {i['message']} ({i.get('slide_id')}/{i.get('element_id')})")
        return 0 if q["summary"]["ok"] else 1

    dst = Path(args.dst) if args.dst else None
    if dst is None:
        ap.error("dst を指定してください")
    if args.command in ("pptx2json", "html2json"):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(pres, ensure_ascii=False, indent=2), encoding="utf-8")
    elif args.command in ("pptx2web", "json2web"):
        pres, _e, _f = pipeline.prepare(pres)
        write_bundle(pres, dst)
    else:
        out, pres2, warns = pipeline.export_pptx(pres, args.mode)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(out)
        print(f"PPTX 生成: warnings={len(warns)}")
        _print_warnings(warns)
    print(f"出力: {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
