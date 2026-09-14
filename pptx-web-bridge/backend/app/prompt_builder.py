"""図解仕様（+ テーマ）→ Copilot に貼るプロンプト。

**このアプリの主役。** 図解を描くのは Copilot で、アプリがやるのは
「何をどう作ってほしいか」を漏れなく言葉にすることだけ。

2 つの向きがある:

| 向き | 入力 | 貼り先 | 出来上がるもの |
|---|---|---|---|
| `to_pptx` | HTML 図解（+ テーマ） | Copilot in PowerPoint | 会社様式の PowerPoint |
| `to_html` | PowerPoint | ふつうの Copilot チャット | HTML の図解ページ |

設計:
- 文言を変えさせない。要約・言い換えは利用者が別途頼むもので、この変換の仕事ではない。
- 型（フロー・カード・比較…）ごとの作り方を必ず書く。「いい感じに」では毎回違うものが出る。
- 長すぎるプロンプトは貼れないので上限で切り、**切ったことを必ず返す**（黙って落とさない）。
- 画像は本文に埋め込まず、ファイル名で参照させる（一式 ZIP に同梱して添付してもらう）。
"""
from __future__ import annotations

from typing import Any

from . import spec_builder, theme_from_html
from .config import get_config
from .logging_setup import get_logger
from .model import warning

log = get_logger("prompt_builder")

DEFAULT_MAX_CHARS = 12000

# 型ごとの「どう作るか」。ここがプロンプトの効き目を決める中心。
_KIND_RECIPE_PPTX: dict[str, str] = {
    "flow": "左から右へ同じ大きさの箱を並べ、箱と箱の間を矢印でつなぐ",
    "cards": "同じ大きさの角丸の箱を横に並べる（3 つなら 3 列、4 つ以上は 2 段に折り返す）",
    "compare": "スライドを左右 2 列に分け、左を before / 右を after として対比させる",
    "kpi": "数字だけを大きく（他の文字の 3 倍以上）、単位と説明はその下に小さく置く",
    "timeline": "横 1 本の線に沿って左から右へ時系列に並べ、各時点に見出しを付ける",
    "table": "そのまま表にする。見出し行は色を敷いて太字にする",
    "bullets": "箇条書きのまま。1 行 1 項目で、階層があれば字下げする",
    "image_text": "左に画像の枠、右に説明。画像は後で差し替えるので枠と名前だけ置く",
    "image": "画像を中央に大きく置く",
    "title_only": "表紙として、題名を中央に大きく置く",
}
_KIND_RECIPE_HTML: dict[str, str] = {
    "flow": "横並びの flex に箱を置き、間に矢印（→）を入れる",
    "cards": "grid か flex で同じ幅のカードを並べる。角丸と余白を付ける",
    "compare": "2 列の grid にし、左右で背景色を変えて対比させる",
    "kpi": "数字を大きな font-size で、単位と説明を小さく添える",
    "timeline": "横一列（狭い画面では縦）に並べ、線でつなぐ",
    "table": "<table> でそのまま。狭い画面では横スクロールさせる",
    "bullets": "<ul><li> のまま",
    "image_text": "画像と説明を横並びにし、狭い画面では縦に積む",
    "image": "<img> を幅いっぱいに置く",
    "title_only": "見出しだけの表紙セクションにする",
}

DIRECTIONS: dict[str, dict[str, str]] = {
    "to_pptx": {
        "id": "to_pptx",
        "name": "PowerPoint にする（HTML 図解 → PowerPoint）",
        "target": "Copilot in PowerPoint",
        "outcome": "HTML の図解が、会社様式の PowerPoint スライドになります。",
        "how": "PowerPoint を開き、Copilot の入力欄にこのプロンプトを貼ります。画像がある場合は一式 ZIP の画像を先に貼り付けてください。",
    },
    "to_html": {
        "id": "to_html",
        "name": "HTML 図解にする（PowerPoint → Web 図解）",
        "target": "ふつうの Copilot チャット",
        "outcome": "PowerPoint の中身が、1 ファイルの HTML 図解ページになります。",
        "how": "Copilot のチャットにこのプロンプトを貼ります。返ってきた HTML を .html で保存すればブラウザで開けます。",
    },
}


def directions() -> list[dict]:
    return [dict(v) for v in DIRECTIONS.values()]


def _kind_lines(spec: dict, recipes: dict[str, str]) -> list[str]:
    """この資料に実際に出てくる型だけを書く（使わない型の説明で薄めない）。"""
    used: list[str] = []
    for s in spec.get("slides", []):
        if s["kind"] not in used:
            used.append(s["kind"])
    return [f"  - {spec_builder.KINDS[k].split('（')[0]}: {recipes.get(k, 'そのまま素直に置く')}" for k in used]


def _theme_block(theme: dict | None) -> list[str]:
    """見た目の指示。**ここが見た目を語る唯一の場所**（仕様の YAML には入れない）。

    テーマは実ファイルから読んだものだけを使う。読めなければ何も言わない
    （アプリ既定の色を書くと、その資料が実際には使っていない色を指示してしまう）。
    """
    if not theme:
        return []
    lines = theme_from_html.to_prompt_lines(theme)
    if not lines:
        return []
    return ["", f"見た目は次に合わせてください（{theme.get('name') or 'テーマ'}）:", *lines]


def _truncate(spec: dict, max_chars: int) -> tuple[dict, int]:
    """仕様が長すぎるとき、後ろのページから落とす。落とした枚数を返す。"""
    if len(spec_builder.to_yaml(spec)) <= max_chars:
        return spec, 0
    slides = list(spec.get("slides", []))
    dropped = 0
    while slides and len(spec_builder.to_yaml({**spec, "slides": slides})) > max_chars:
        slides.pop()
        dropped += 1
    return {**spec, "slides": slides}, dropped


def build(spec: dict, theme: dict | None = None, direction: str = "to_pptx", options: dict | None = None) -> dict:
    """図解仕様 → プロンプト。

    返り値: {direction, direction_name, target, outcome, how, instruction, spec_yaml,
             prompt, chars, dropped_slides, warnings}
    """
    opts = options or {}
    if direction not in DIRECTIONS:
        direction = "to_pptx"
    d = DIRECTIONS[direction]
    max_chars = int(opts.get("max_chars") or get_config().get("copilot.max_prompt_chars", DEFAULT_MAX_CHARS))
    warnings: list[dict] = []

    used_spec, dropped = _truncate(spec, max_chars)
    if dropped:
        warnings.append(warning(
            "prompt_builder", "PROMPT_TRUNCATED",
            f"プロンプトが長すぎるため、後ろの {dropped} 枚を外しました（全 {spec.get('slide_count', 0)} 枚中）。"
            "残りは分けて渡してください。",
            fallback=f"先頭 {len(used_spec.get('slides', []))} 枚だけを渡します",
        ))

    title = used_spec.get("title") or "（題名なし）"
    n = len(used_spec.get("slides", []))
    has_images = any(s.get("images") for s in used_spec.get("slides", []))

    if direction == "to_pptx":
        head = [
            f"以下は「{title}」という資料の図解仕様です（全 {n} 枚）。",
            "この仕様のとおりに PowerPoint のスライドを作ってください。",
            "",
            "守ってほしいこと:",
            f"- 「ページ」1 つを 1 枚のスライドにする（全 {n} 枚。増やさない・減らさない）",
            "- 文言は一字も変えない（要約・言い換え・追記をしない）",
            "- 各ページの「型」に合わせて図解にする:",
            *_kind_lines(used_spec, _KIND_RECIPE_PPTX),
            "- 「ノート」の行は発表者ノートに入れる（スライド上に出さない）",
        ]
        if has_images:
            head.append("- 「画像」の行は、そのファイル名の画像を置く枠を作る（画像は別途貼り付けます）")
        head.append("- レイアウトは PowerPoint の標準機能（プレースホルダ・図形・SmartArt）で作る")
    else:
        head = [
            f"以下は「{title}」という PowerPoint 資料の中身です（全 {n} 枚）。",
            "これを 1 ファイルの HTML 図解ページにしてください。",
            "",
            "出力の決まり:",
            "- HTML ファイル 1 つだけを出力する（前置きや説明文は書かない）",
            "- CSS は <style> の中に書く。外部ファイル・CDN・JavaScript は使わない",
            "- 「ページ」1 つを 1 つの <section> にする",
            "- 各ページの「型」に合わせた見た目にする:",
            *_kind_lines(used_spec, _KIND_RECIPE_HTML),
            "- 文言は一字も変えない（要約・言い換え・追記をしない）",
            "- 画面の幅が狭いときは縦に積む（横スクロールを出さない）",
        ]
        if has_images:
            head.append('- 「画像」の行は <img src="そのファイル名" alt="説明"> で参照する（画像ファイルは別途添付します）')
        head.append("- 「ノート」は画面に出さず、HTML コメントとして残す")

    head.extend(_theme_block(theme))
    instruction = "\n".join(head) + "\n"
    spec_yaml = spec_builder.to_yaml(used_spec)
    prompt = instruction + "\n--- ここから仕様 ---\n" + spec_yaml

    if theme:
        warnings.extend(theme.get("warnings", []))

    out = {
        "direction": d["id"],
        "direction_name": d["name"],
        "target": d["target"],
        "outcome": d["outcome"],
        "how": d["how"],
        "instruction": instruction,
        "spec_yaml": spec_yaml,
        "prompt": prompt,
        "chars": len(prompt),
        "dropped_slides": dropped,
        "has_images": has_images,
        "warnings": warnings,
    }
    log.info("プロンプト生成: %s %s 枚 %s 字 落とした枚数=%s", direction, n, out["chars"], dropped)
    return out
