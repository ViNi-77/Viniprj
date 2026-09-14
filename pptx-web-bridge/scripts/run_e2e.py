"""通し検査: 投入 → 図解仕様 → プロンプト → 受け渡し一式。

このアプリは図解を描かないので、往復（PPTX → HTML → PPTX）を突き合わせる検査は無い。
代わりに見るのは **渡すものが揃っているか**:

- 両方向（PowerPoint 化 / HTML 図解化）でプロンプトが組み立つ
- 文言が一字も変わらずプロンプトに載っている
- 型ごとの作り方が必ず書かれている
- 画像はファイル名で参照され、一式に実体が入っている
- 読めなかったものは必ず警告として出てくる

結果は docs/試験結果.md に書き出す。
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import handoff_pack, pipeline, prompt_builder, spec_builder  # noqa: E402
from app.logging_setup import get_logger  # noqa: E402

log = get_logger("e2e")
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"[{'OK ' if ok else 'NG '}] {name} {detail}")


def _themes() -> dict[str, bytes]:
    sys.path.insert(0, str(ROOT / "samples"))
    from make_html_themes import build  # type: ignore

    return {p.name: p.read_bytes() for p in build()}


def main() -> int:
    themes = _themes()
    sample = ROOT / "samples" / "sample_deck.pptx"
    if not sample.exists():
        sys.path.insert(0, str(ROOT / "samples"))
        from make_sample_pptx import build as build_sample  # type: ignore

        build_sample(sample)

    # ---- 1. PowerPoint を投入して HTML 図解化のプロンプトを作る ----
    deck = sample.read_bytes()
    got = pipeline.analyze(deck, "sample_deck.pptx")
    check("PowerPoint を読み取れる", got["kind"] == "pptx" and got["spec"]["slide_count"] >= 5,
          f"{got['spec']['slide_count']} 枚")
    check("実ファイルのテーマ色を読む（アプリ既定ではない）",
          bool(got["theme"]["colors"]) and got["theme"]["colors"]["heading"] != "#1F3A5F",
          got["theme"]["colors"].get("heading", "-"))
    kinds = [s["kind"] for s in got["spec"]["slides"]]
    check("すべての頁に型と理由が付く",
          all(s["kind"] and s["kind_reason"] for s in got["spec"]["slides"]), ",".join(kinds))

    to_html = prompt_builder.build(got["spec"], got["theme"], "to_html")
    check("HTML 図解化のプロンプトが組み立つ", to_html["chars"] > 500, f"{to_html['chars']} 字")
    check("型ごとの作り方が書かれている",
          all(spec_builder.KINDS[k].split("（")[0] + ":" in to_html["prompt"] for k in set(kinds)))
    check("画像はファイル名で参照し、本文に埋め込まない",
          to_html["has_images"] and "img001.png" in to_html["prompt"] and "base64" not in to_html["prompt"])

    words = []
    for s in got["spec"]["slides"]:
        words.extend(b for b in (s.get("bullets") or [])[:2])
        words.append(s["title"])
    missing = [w for w in words if w and w not in to_html["prompt"]]
    check("文言が一字も変わらず載る", not missing, f"欠け {len(missing)} 件" + (f": {missing[:2]}" if missing else ""))

    pack = handoff_pack.build_zip(to_html, got["spec"], got["presentation"])
    z = zipfile.ZipFile(io.BytesIO(pack))
    need = {"プロンプト.txt", "図解仕様.yaml", "構成.docx", "はじめにお読みください.txt"}
    check("受け渡し一式が揃う", need <= set(z.namelist()) and any(n.startswith("画像/") for n in z.namelist()),
          f"{len(z.namelist())} ファイル")
    check("Word 構成が本物の .docx として開ける",
          "word/document.xml" in zipfile.ZipFile(io.BytesIO(handoff_pack.to_docx(got["spec"]))).namelist())

    # ---- 2. HTML 図解 + テーマを投入して PowerPoint 化のプロンプトを作る ----
    src = pipeline.analyze(themes["theme_cards.html"], "theme_cards.html")
    check("HTML 図解を読み取れる", src["kind"] == "html" and src["spec"]["slides"][0]["kind"] == "cards",
          src["spec"]["slides"][0]["kind"])
    theme = pipeline.analyze_theme(themes["theme_vars.html"], "theme_vars.html")
    to_pptx = prompt_builder.build(src["spec"], theme, "to_pptx")
    check("読み込んだテーマの色がプロンプトに入る", "#6C3CE0" in to_pptx["prompt"])
    check("見た目を語るのはテーマの所だけ", "#" not in to_pptx["spec_yaml"])
    check("PowerPoint 化の指示になっている",
          "PowerPoint のスライドを作ってください" in to_pptx["prompt"] and to_pptx["target"] == "Copilot in PowerPoint")

    nothing = prompt_builder.build(src["spec"], None, "to_pptx")
    check("テーマが無ければ色を勝手に決めない", "#" not in nothing["prompt"])

    # ---- 3. 黙って失敗しない ----
    ext = pipeline.analyze_theme(themes["theme_external.html"], "theme_external.html")
    check("外部 CSS は読まないと明言する", any(w["code"] == "THEME_EXTERNAL_CSS" for w in ext["warnings"]))
    cut = prompt_builder.build(got["spec"], got["theme"], "to_html", {"max_chars": 400})
    check("長すぎて切ったら必ず言う",
          cut["dropped_slides"] > 0 and any(w["code"] == "PROMPT_TRUNCATED" for w in cut["warnings"]),
          f"{cut['dropped_slides']} 枚を外した")
    empty = pipeline.analyze(b'<html lang="ja"><head><title>x</title></head><body><section><h1>t</h1></section></body></html>', "e.html")
    check("中身の無い頁を黙って流さない", any(w["code"] == "SLIDE_HAS_NO_CONTENT" for w in empty["warnings"]))
    try:
        pipeline.analyze(b"plain text", "x.txt")
        check("読めないファイルは理由を返す", False, "例外が出なかった")
    except ValueError as e:
        check("読めないファイルは理由を返す", "PowerPoint" in str(e))

    ok = sum(1 for _n, o, _d in RESULTS if o)
    total = len(RESULTS)
    print(f"\n総合: {'合格' if ok == total else '不合格'}（{ok} / {total}）")

    out = ROOT / "docs" / "試験結果.md"
    lines = ["# 試験結果（通し検査）", "", "`python scripts/run_e2e.py` が自動で書き出す。手で編集しない。", "",
             f"総合: **{'合格' if ok == total else '不合格'}**（{ok} / {total}）", "", "| 項目 | 結果 | 内訳 |", "|---|---|---|"]
    lines += [f"| {n} | {'合格' if o else '不合格'} | {d} |" for n, o, d in RESULTS]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
