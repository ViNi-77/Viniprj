"""テンプレート推定が壊れる軸ごとの回帰試験（`samples/make_template_matrix.py` が作る資料を使う）。

1 つの実ファイルに合わせ込むと他のテンプレートで壊れるため、壊れ方の軸を資料にして固定する。
資料は実行時に生成する（リポジトリには置かない）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.template_from_pptx import analyze

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def matrix(tmp_path_factory) -> dict[str, bytes]:
    sys.path.insert(0, str(ROOT / "samples"))
    from make_template_matrix import build  # type: ignore

    out = tmp_path_factory.mktemp("templates")
    return {p.stem: p.read_bytes() for p in build(out)}


def _analyze(matrix: dict[str, bytes], name: str) -> dict:
    return analyze(matrix[name], f"{name}.pptx", template_id=f"mx_{name}")


def test_wide_logo_on_a_bar_with_a_swatch_column(matrix):
    """利用者が投入したものに近い形: 幅広ロゴを拾い、下部の帯を色見本判定で消さない。"""
    r = _analyze(matrix, "chrome_on_slide_wide_logo")
    cover = r["proposal"]["cover"]
    assert "logo" in cover and abs(cover["logo"]["w"] - 300) < 3
    assert "bar" in cover and abs(cover["bar"]["y"] - 490) < 3
    assert r["proposal"].get("palette_candidates"), "色見本の色がテーマ候補に入っていない"


def test_chrome_on_layout_is_found(matrix):
    """装飾をレイアウトに置いたテンプレートでも、ロゴと帯を拾う。"""
    cover = _analyze(matrix, "chrome_on_layout")["proposal"]["cover"]
    assert "logo" in cover and "bar" in cover


def test_chrome_on_master_is_found(matrix):
    """装飾をマスターに置いたテンプレートでも、レイアウト → マスターと辿って拾う。"""
    cover = _analyze(matrix, "chrome_on_master")["proposal"]["cover"]
    assert "logo" in cover and "bar" in cover


def test_freeform_logo_is_reported_not_dropped(matrix):
    """色を取れないベクターロゴは色が出せないが、黙って消さず装飾として残して警告を出す。"""
    r = _analyze(matrix, "logo_freeform")
    assert any("色を取れない図形" in w for w in r["warnings"])
    decor = r["proposal"]["cover"].get("decor") or []
    assert any(d.get("unresolved_fill") for d in decor)


def test_logo_in_group_is_found(matrix):
    cover = _analyze(matrix, "logo_in_group")["proposal"]["cover"]
    assert "logo" in cover


def test_three_slide_deck_maps_all_roles(matrix):
    r = _analyze(matrix, "three_slides")
    assert [s["role"] for s in r["slides"]] == ["cover", "content", "closing"]
    assert {"cover", "content", "closing"} <= set(r["proposal"])


def test_swatch_page_is_not_chosen_as_content(matrix):
    """色見本ページが混ざったデッキでは、題名・本文のある実スライドを中身に選ぶ。"""
    r = _analyze(matrix, "swatch_page_plus_content")
    roles = [s["role"] for s in r["slides"]]
    assert roles[1] == "skip", f"色見本ページが中身に選ばれている: {roles}"
    content = r["proposal"]["content"]
    assert "title" in content and "body" in content


def test_4_3_deck_keeps_the_bar_at_the_bottom(matrix):
    r = _analyze(matrix, "aspect_4_3")
    cover = r["proposal"]["cover"]
    assert "bar" in cover and "logo" in cover
    # 960×540 基準へ正規化されるので、4:3（720×540）の y=500 は 500 付近のまま
    assert cover["bar"]["y"] > 400


def test_every_case_parses_without_an_exception(matrix):
    """どの軸でも例外で止まらない（止まると利用者には「読めません」しか出ない）。"""
    for name in matrix:
        r = _analyze(matrix, name)
        assert r["proposal"].get("cover"), f"{name}: 表紙の部品が 1 つも取れていない"
