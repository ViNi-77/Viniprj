"""E2E 試験: サンプル PPTX / HTML で往復変換を実行し、結果を docs/試験結果.md に書く。

  python scripts/run_e2e.py            … 実行して docs/試験結果.md と output/e2e/ を更新
  python scripts/run_e2e.py --no-raster … 画像化（Playwright）を使う工程を省く
"""
from __future__ import annotations

import io
import json
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pptx import Presentation  # noqa: E402

from app import pipeline  # noqa: E402
from app.pptx_parser import parse_pptx  # noqa: E402
from app.quality_check import check_presentation, summarize  # noqa: E402
from app.rasterize import is_available  # noqa: E402
from app.validate import validate  # noqa: E402
from app.web_renderer import write_bundle  # noqa: E402

OUT = ROOT / "output" / "e2e"
REPORT = ROOT / "docs" / "試験結果.md"


def _reread(data: bytes) -> tuple[int, list[str]]:
    prs = Presentation(io.BytesIO(data))
    p = parse_pptx(data, "reread.pptx")
    return len(prs.slides), [s["title"] for s in p["slides"]]


def main() -> int:
    use_raster = "--no-raster" not in sys.argv and is_available()
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, str, str]] = []
    ok_all = True

    def record(name: str, ok: bool, detail: str) -> None:
        nonlocal ok_all
        ok_all = ok_all and ok
        rows.append((name, "合格" if ok else "不合格", detail))

    t0 = time.time()
    # --- PPTX → JSON → Web ---
    deck = ROOT / "samples" / "sample_deck.pptx"
    if not deck.exists():
        sys.path.insert(0, str(ROOT / "samples"))
        from make_sample_pptx import build  # type: ignore

        build(deck)
    res = pipeline.import_pptx(deck.read_bytes(), deck.name)
    pres = res["presentation"]
    record("PPTX→JSON 解析", not res["schema_errors"] and len(pres["slides"]) == 6, f"slides={len(pres['slides'])} assets={len(pres['assets'])} warnings={len(res['warnings'])}")
    (OUT / "deck.json").write_text(json.dumps(pres, ensure_ascii=False, indent=2), encoding="utf-8")
    web_dir = write_bundle(pres, OUT / "deck_web")
    index_html = (web_dir / "index.html").read_text(encoding="utf-8")
    record("JSON→Web 一式生成", all(f'id="{s["id"]}"' in index_html for s in pres["slides"]) and (web_dir / "assets").exists(), f"{web_dir}")
    q = check_presentation(pres)
    record("PPTX 由来の品質検査", summarize(q)["ok"], f"issues={len(q)}")
    # JSON 保存→再読込
    again = json.loads((OUT / "deck.json").read_text(encoding="utf-8"))
    record("JSON 保存・再読込", validate(again) == [] and again == pres, "同一内容で復元")
    # PPTX 往復
    data, warns = pipeline.export_pptx(pres, "editable")[0:2]
    (OUT / "deck_roundtrip.pptx").write_bytes(data)
    n, titles = _reread(data)
    record("JSON→PPTX（編集性優先）→再読込", n == 6 and titles == [s["title"] for s in pres["slides"]], f"slides={n} titles一致")

    # --- HTML → JSON → PPTX ---
    base = ROOT / "samples" / "sample_html"
    files = {str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*") if p.is_file()}
    for name in ("long.html", "slides.html", "cards.html"):
        res = pipeline.import_html(files[name], name, extra_files=files)
        pres_h = res["presentation"]
        record(f"HTML→JSON（{name}）", not res["schema_errors"] and len(pres_h["slides"]) >= 3, f"slides={len(pres_h['slides'])} warnings={[w['code'] for w in res['warnings']]}")
        (OUT / f"{name}.json").write_text(json.dumps(pres_h, ensure_ascii=False, indent=2), encoding="utf-8")
        for mode in ("editable", "hybrid") + (("visual",) if use_raster else ()):
            data, _p, warns = pipeline.export_pptx(pres_h, mode)
            (OUT / f"{name}.{mode}.pptx").write_bytes(data)
            n, _t = _reread(data)
            bad = [w["code"] for w in warns if w["code"] in ("ELEMENT_WRITE_FAILED", "VISUAL_MODE_UNAVAILABLE")]
            record(f"JSON→PPTX（{name}, {mode}）", n == len(pres_h["slides"]) and not bad, f"slides={n} warnings={[w['code'] for w in warns]}")
        write_bundle(pres_h, OUT / f"{name}_web")
        q = check_presentation(pres_h)
        record(f"HTML 由来の品質検査（{name}）", summarize(q)["ok"], f"issues={[i['code'] for i in q]}")

    # --- 模擬 12 枚 PPTX（mock-pptx）と コーポレートテンプレート ---
    mock = ROOT / "mock-pptx" / "output" / "mock_bidirectional_conversion_12slides.pptx"
    if not mock.exists():
        import subprocess

        subprocess.run([sys.executable, str(ROOT / "mock-pptx" / "src" / "generate_mock_pptx.py")], check=True)
    res = pipeline.import_pptx(mock.read_bytes(), mock.name)
    pres_m = res["presentation"]
    record("模擬12枚 PPTX→JSON", len(pres_m["slides"]) == 12 and not res["warnings"], f"slides={len(pres_m['slides'])} warnings={[w['code'] for w in res['warnings']]}")
    write_bundle(pres_m, OUT / "mock_web")
    q = check_presentation(pres_m)
    record("模擬12枚 品質検査", summarize(q)["ok"] and not q, f"issues={[i['code'] for i in q]}")
    data, _p, warns = pipeline.export_pptx(pres_m, "editable")
    (OUT / "mock_roundtrip.pptx").write_bytes(data)
    n, titles = _reread(data)
    record("模擬12枚 JSON→PPTX→再読込", n == 12 and titles == [s["title"] for s in pres_m["slides"]], f"slides={n} warnings={[w['code'] for w in warns]}")
    from app.report import build_report

    rep = build_report(pres_m)["summary"]
    record("要素判別レポート（文字はテキストシェイプ）", rep["text_as_shapes"] == rep["text_with_bbox"] and rep["editable_ratio"] == 1.0, f"{rep}")
    pres_t = pipeline.import_pptx(mock.read_bytes(), mock.name, "corporate_standard")["presentation"]
    from app.template_kit import make_closing_slide

    pres_t["slides"].append(make_closing_slide("s_end", len(pres_t["slides"]), ""))
    pres_t, _e, _f = pipeline.prepare(pres_t)
    data, _p, warns = pipeline.export_pptx(pres_t, "editable")
    (OUT / "mock_corporate_template.pptx").write_bytes(data)
    write_bundle(pres_t, OUT / "mock_corporate_web")
    prs_t = Presentation(io.BytesIO(data))
    names0 = {sh.name for sh in prs_t.slides[0].shapes}
    record("コーポレートテンプレート適用（表紙背景・ロゴ・帯・最終ページ）", "cover_background" in names0 and "logo" in names0 and len(prs_t.slides) == 13 and not warns, f"slides={len(prs_t.slides)} cover={sorted(names0)[:4]}")

    # --- 例外系 ---
    try:
        pipeline.import_pptx(b"broken", "broken.pptx")
        record("壊れた PPTX の拒否", False, "例外が出なかった")
    except Exception as e:  # noqa: BLE001
        record("壊れた PPTX の拒否", True, type(e).__name__)
    broken_json = {"slides": [{"elements": [{"type": "text", "paragraphs": [{"runs": [{"text": "修復"}]}]}]}]}
    from app.validate import validate_and_repair

    fixed, errors, fixes = validate_and_repair(broken_json)
    record("壊れた JSON の自動修復", not errors and fixes, f"repairs={[f['code'] for f in fixes]}")
    html_ext = b"<html><body><section><h2>t</h2><img src='https://example.invalid/x.png'></section></body></html>"
    res = pipeline.import_html(html_ext, "ext.html")
    record("外部画像の非取得と警告", any(w["code"] == "REMOTE_IMAGE_SKIPPED" for w in res["warnings"]), "REMOTE_IMAGE_SKIPPED")

    elapsed = time.time() - t0
    lines = [
        "# 試験結果（E2E）",
        "",
        f"- 実行日時: {datetime.now().isoformat(timespec='seconds')}",
        f"- 実行環境: Python {sys.version.split()[0]} / 画像化（Playwright）: {'利用可' if use_raster else '利用不可・省略'}",
        f"- 所要時間: {elapsed:.1f} 秒",
        f"- 総合: {'合格' if ok_all else '不合格あり'}（{sum(1 for r in rows if r[1] == '合格')} / {len(rows)}）",
        f"- 成果物: `{OUT.relative_to(ROOT)}/`（リポジトリには含めない）",
        "",
        "| 試験項目 | 結果 | 詳細 |",
        "|---|---|---|",
    ]
    lines += [f"| {n} | {r} | {d.replace('|', '／')} |" for n, r, d in rows]
    lines += ["", "再実行: `python scripts/run_e2e.py`（単体試験は `python -m pytest`）", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
