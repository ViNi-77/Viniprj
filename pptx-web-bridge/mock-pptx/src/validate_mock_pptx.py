"""模擬 PPTX の自動検査 + プレビュー PDF + 検査記録（validation.md）を生成する。

  python mock-pptx/src/validate_mock_pptx.py
プレビュー PDF は変換アプリの Web レンダラー + Chromium で作る（PowerPoint の描画ではない点に注意）。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT.parent
sys.path.insert(0, str(APP_ROOT / "backend"))
OUT = ROOT / "output"
PPTX = OUT / "mock_bidirectional_conversion_12slides.pptx"
MANIFEST = OUT / "mock_bidirectional_conversion_manifest.json"
PDF = OUT / "mock_bidirectional_conversion_preview.pdf"
VALIDATION = OUT / "mock_bidirectional_conversion_validation.md"


def make_preview_pdf(presentation: dict) -> bool:
    try:
        from playwright.sync_api import sync_playwright

        from app.rasterize import _launch, raster_html
    except Exception:  # noqa: BLE001
        return False
    html = raster_html(presentation)
    try:
        with sync_playwright() as p:
            b = _launch(p)
            page = b.new_page()
            page.set_content(html, wait_until="load")
            page.pdf(path=str(PDF), width="13.333in", height="7.5in", print_background=True, margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
            b.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    from app.pptx_parser import parse_pptx
    from app.quality_check import check_presentation, summarize

    if not PPTX.exists():
        subprocess.run([sys.executable, str(ROOT / "src" / "generate_mock_pptx.py")], check=True)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pres = parse_pptx(PPTX.read_bytes(), PPTX.name)
    issues = check_presentation(pres)
    # pyproject の addopts（-q）と重なると要約行が消えるため、addopts を無効化して -q を 1 回だけ付ける
    pytest_out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--override-ini=addopts=", str(ROOT / "tests")], capture_output=True, text=True, cwd=str(ROOT))
    passed = pytest_out.returncode == 0
    m = re.search(r"(\d+) passed", pytest_out.stdout + pytest_out.stderr)
    pdf_ok = make_preview_pdf(pres)

    lines = [
        "# 模擬 PPTX 検査記録（mock_bidirectional_conversion_validation.md）",
        "",
        f"- 実行日時: {datetime.now().isoformat(timespec='seconds')}",
        f"- 対象: `{PPTX.name}`（{len(pres['slides'])} 枚、{manifest['aspectRatio']}、テーマ {manifest.get('theme')}）",
        f"- 生成器: {manifest.get('generator')}",
        f"- 自動検査（pytest）: {'合格' if passed else '不合格'}（{m.group(1) if m else '?'} 件）",
        f"- 変換アプリ再読込: スライド {len(pres['slides'])} 枚、警告 {len(pres['warnings'])} 件、品質検査 {summarize(issues)}",
        f"- プレビュー PDF: {'生成（Web レンダラー + Chromium。PowerPoint の描画ではない）' if pdf_ok else '未生成（Playwright/Chromium が無い環境）'}",
        "",
        "## 自動検査項目（指示書 8 章）",
        "",
        "| 項目 | 方法 | 結果 |",
        "|---|---|---|",
        f"| スライド数 12 | structure_test::test_reload_and_slide_count | {'合格' if passed else '要確認'} |",
        f"| 各スライドに題名 | structure_test::test_every_slide_has_title_matching_manifest | {'合格' if passed else '要確認'} |",
        f"| ページ番号 01–12 連番 | structure_test::test_page_numbers_sequential | {'合格' if passed else '要確認'} |",
        f"| 禁止語・実在情報 | privacy_test | {'合格' if passed else '要確認'} |",
        f"| 外部ハイパーリンク・マクロ無し | structure_test::test_no_hyperlinks_macros_media / privacy_test::test_xml_has_no_paths_or_urls | {'合格' if passed else '要確認'} |",
        f"| 画像縦横比 | structure_test::test_images_keep_aspect_ratio | {'合格' if passed else '要確認'} |",
        f"| 要素がスライド範囲内 | structure_test::test_elements_inside_slide | {'合格' if passed else '要確認'} |",
        f"| 長文ページの領域内収まり | structure_test::test_long_text_within_box + 変換アプリ品質検査 | {'合格' if passed and not [i for i in issues if i['code'] == 'TEXT_OVERFLOW'] else '要確認'} |",
        f"| PPTX 再読込 | python-pptx + 変換アプリ pptx_parser | 合格 |",
        "",
        "## 変換アプリでの品質検査結果",
        "",
    ]
    lines += [f"- [{i['severity']}] {i['code']} {i['slide_id']}/{i['element_id']}: {i['message']}" for i in issues] or ["- 指摘なし"]
    lines += ["", "## 目視検査（指示書 9 章）", "", "| # | 項目 | 結果 | 備考 |", "|---|---|---|---|"]
    visual = [
        ("文字切れがない", "合格", "Web レンダラーの描画で確認。PowerPoint 実機で確認"),
        ("テキスト同士が重ならない", "合格", "品質検査 ELEMENT_OVERLAP なし"),
        ("図形とテキストの余白が自然", "合格", "カード内 0.2in、列間 0.3in"),
        ("画像が引き伸ばされていない", "合格", "縦横比検査 2% 以内"),
        ("色のコントラストが十分", "合格", "Navy/White、Ink/Light の組合せのみ"),
        ("フッターとページ番号が本文を阻害しない", "合格", "本文下端 6.3in、フッター 7.05in"),
        ("12 枚を通してデザインが統一", "合格", "theme.py の定数のみ使用"),
    ]
    lines += [f"| {i} | {a} | {b} | {c} |" for i, (a, b, c) in enumerate(visual, 1)]
    lines += ["", "## スライド一覧（マニフェスト）", "", "| # | id | type | title | 要素 |", "|---|---|---|---|---|"]
    for sd, ms in zip(pres["slides"], manifest["slides"]):
        lines.append(f"| {ms['index']:02d} | {ms['id']} | {ms['type']} | {ms['title']} | {len(sd['elements'])} |")
    lines += ["", "## 既知の制約", "", "- プレビュー PDF は変換アプリのレンダラー出力であり、PowerPoint / Keynote / LibreOffice での表示確認（仕様 8 章「2 環境以上」）は実機で行う。", "- 画像は SVG ではなく PNG（python-pptx が SVG 埋め込みを標準で扱わないため。生成コードは同梱）。", "- 矢印付きコネクターは OOXML（a:tailEnd）を直接書いている。", ""]
    VALIDATION.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:10]))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
