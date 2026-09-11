"""Copilot エージェント一式の書き出し（API を使わない）。

このアプリと Copilot の「書式の約束」を、Copilot 側に登録できる形にまとめて ZIP で出す:

- `declarativeAgent.json` … 宣言型エージェントの定義（Copilot Studio / Teams Toolkit に読ませる）
- `instructions.md` … エージェントへの指示文（読み込めない環境では、この本文をそのまま貼れば同じ働きをする）
- `knowledge/` … ナレッジとして添付するテキスト（M365 Copilot の上限に合わせ 1 ファイル 30,000 字・20 ファイルまで）
- `kit.json` … 上の元になった記録（将来 crossai-packager など別の詰め替えに渡せる形）
- `READ_ME.txt` … 登録手順

知識の中身はコードと設定から組み立てる（文書ファイルに依存しない = exe 単体でも同じものが出る）。
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

from . import copilot_handoff
from .config import get_config

MANIFEST_SCHEMA = "https://developer.microsoft.com/json-schemas/copilot/declarative-agent/v1.0/schema.json"
KNOWLEDGE_PREFIX = "M365AgentContext"
MAX_CHARS = 30000  # M365 Copilot のナレッジ 1 ファイルの目安
MAX_FILES = 19  # INDEX と合わせて 20 ファイル


# ---------------------------------------------------------------- 知識のもと
def _markdown_contract() -> str:
    """このアプリが読み書きする Markdown の約束（copilot_handoff の実装と対応）。"""
    words = "、".join(f"{w}" for w in copilot_handoff._LAYOUT_WORDS)
    return (
        "# 資料 Markdown の書式（このアプリが読み書きする形）\n"
        "\n"
        "資料 1 つを 1 つの Markdown で表す。行の意味は次のとおり。\n"
        "\n"
        "- `# 題名` … 資料全体の題名（先頭に 1 つだけ）\n"
        "- `## 3. スライド題名` … スライドの区切り。番号はスライドの並び順で、題名と一緒に必ず書く\n"
        "- `型: カード` … そのスライドの型。使える語: " + words + "、表紙、最終ページ\n"
        "- `- 箇条書き` … 本文。字下げ 2 文字で 1 段深くなる（最大 3 段）\n"
        "- `*副題*` … 表紙の副題\n"
        "- `| a | b |` … 表（2 行目は `|---|---|`）\n"
        "- `画像: file.png（説明）` … 画像の位置。画像そのものはアプリが持っているので、行だけ残す\n"
        "- `ノート: …` … 発表者ノート（スライド 1 枚に 1 行）\n"
        "\n"
        "## 守ってほしいこと\n"
        "- 出力は Markdown だけにする（前置き・後書き・「以下が結果です」などは書かない）\n"
        "- スライドの番号と題名は、指示がない限り変えない\n"
        "- 数字・固有名詞・URL は変えない\n"
        "- 1 行は 30 字以内、1 枚は 5 項目以内を目安にする\n"
        "- 画像・表・ノートの行は消さずに残す\n"
        "\n"
        "## 例\n"
        "```\n"
        "# 新サービスのご提案\n"
        "## 1. 新サービスのご提案\n"
        "型: 表紙\n"
        "*2026 年 4 月版*\n"
        "## 2. 現状の課題\n"
        "型: カード\n"
        "- 手作業が多い: 月 40 時間を転記に使っている\n"
        "- 様式がばらつく: 部署ごとに書式が違う\n"
        "ノート: 最初に現場の声を紹介する。\n"
        "```\n"
    )


def _schema_summary() -> str:
    """アプリ内部の Presentation JSON（簡易 JSON で受け渡しする形）の説明。"""
    return (
        "# アプリ用 JSON の形（上級・content_format=json のとき）\n"
        "\n"
        "```json\n"
        "{\n"
        '  "title": "資料題名",\n'
        '  "brand": {"colors": {"primary": "#001A72"}, "fonts": {"heading": "Meiryo"}},\n'
        '  "slides": [\n'
        '    {"n": 1, "title": "スライド題名", "layout": "title",\n'
        '     "bullets": [{"text": "本文", "level": 0, "role": "body"}],\n'
        '     "tables": [[["見出し"], ["値"]]],\n'
        '     "images": [{"file": "img001.png", "alt": "説明"}],\n'
        '     "notes": "発表者ノート"}\n'
        "  ]\n"
        "}\n"
        "```\n"
        "\n"
        "- `layout` に使える値: title（表紙）, section（章扉）, title_body（題名＋本文）, two_column（2 分割）,\n"
        "  three_column（3 分割・カード）, image（画像中心）, table（表）, closing（最終ページ）, blank\n"
        "- 座標・色・フォントはアプリとブランドキットが決めるので、JSON には書かない（`brand` は参考値）\n"
        "- 返すときは ```json で囲む。キーは上の 9 つだけにする\n"
        "\n"
        "## 役割分担\n"
        "- AI（Copilot）… 文章・構成・言い換え・翻訳・ノート\n"
        "- アプリ … 座標、文字サイズ、テンプレート部品（ロゴ・帯・ページ番号）、PowerPoint / HTML の生成\n"
    )


def _purposes_text(purposes: list[dict]) -> str:
    lines = ["# 用途別の依頼と、返してほしい形", ""]
    for p in purposes:
        lines.append(f"## {p.get('name') or p.get('id')}（id: {p.get('id')}）")
        if p.get("description"):
            lines.append(p["description"])
        lines.append(f"- 返す形式: {'アプリ用 JSON' if p.get('content_format') == 'json' else '資料 Markdown'}")
        if p.get("attach_hint"):
            lines.append(f"- 補足: {p['attach_hint']}")
        lines.append("- 依頼文（利用者はこの文面で頼んでくる）:")
        for ln in str(p.get("prompt", "")).splitlines():
            lines.append("  > " + ln if ln.strip() else "  >")
        lines.append("")
    return "\n".join(lines)


def _template_text(template: dict) -> str:
    colors = template.get("colors") or {}
    fonts = template.get("fonts") or {}
    lines = [f"# 資料の見た目（テンプレート「{template.get('name') or template.get('id')}」）", ""]
    if colors:
        lines.append("## 配色")
        lines += [f"- {k}: {v}" for k, v in colors.items()]
        lines.append("")
    if fonts:
        lines.append("## フォント")
        lines += [f"- {k}: {v}" for k, v in fonts.items()]
        lines.append("")
    parts = []
    for section in ("cover", "content", "closing"):
        spec = template.get(section)
        if isinstance(spec, dict):
            parts += [f"- {section}.{k}" for k in spec]
    if parts:
        lines.append("## テンプレートの部品（アプリが自動で置くもの。AI は触らない）")
        lines += parts
        lines.append("")
    lines.append("色を指定するときは上の 16 進数をそのまま使い、色名（「濃い青」など）では書かない。")
    return "\n".join(lines)


def _diagram_text() -> str:
    """図解の型（Phase F で diagrams.MARKDOWN_SPEC が入ったら使う）。今は空。"""
    try:
        from .diagrams import MARKDOWN_SPEC  # type: ignore
    except Exception:  # noqa: BLE001  # Phase F 未実装
        return ""
    return str(MARKDOWN_SPEC)


def collect_sources(template_id: str | None = None) -> list[dict]:
    """ナレッジの元になる記録（file_name / summary / text）を集める。"""
    cfg = get_config()
    purposes = copilot_handoff.purposes()
    template = cfg.template(template_id)
    records = [
        {"file_name": "markdown_contract.md", "summary": "資料 Markdown の書式（行の意味と守ってほしいこと）", "text": _markdown_contract()},
        {"file_name": "json_format.md", "summary": "アプリ用 JSON の形と役割分担", "text": _schema_summary()},
        {"file_name": "purposes.md", "summary": "用途別の依頼と返してほしい形", "text": _purposes_text(purposes)},
        {"file_name": "template.md", "summary": f"テンプレート「{template.get('name') or template.get('id')}」の配色・フォント・部品", "text": _template_text(template)},
    ]
    diagram = _diagram_text()
    if diagram.strip():
        records.append({"file_name": "diagrams.md", "summary": "図解の型と Markdown 記法", "text": diagram})
    return records


# ---------------------------------------------------------------- 指示文と定義
def build_instructions(purposes: list[dict] | None = None, template: dict | None = None) -> str:
    purposes = purposes if purposes is not None else copilot_handoff.purposes()
    template = template if template is not None else get_config().template(None)
    colors = template.get("colors") or {}
    lines = [
        "# 役割",
        "",
        "あなたは「PowerPoint・Web 図解 双方向変換アプリ」の相棒です。利用者はアプリから資料の構成を Markdown（または JSON）で貼ってきます。",
        "あなたの仕事は文章と構成を整えることで、座標・文字サイズ・ロゴや帯などの体裁はアプリが決めます。体裁の指示は書かないでください。",
        "",
        "# 返し方（必ず守る）",
        "",
        "1. 出力は資料 Markdown だけにする。前置き・後書き・説明文は書かない。",
        "2. `# 題名` / `## 番号. 題名` / `型:` / `- 箇条書き` / `ノート:` / `画像:` / 表 の書式を崩さない（詳細はナレッジ `markdown_contract.md`）。",
        "3. スライドの番号と題名は、頼まれていない限り変えない。数字・固有名詞・URL も変えない。",
        "4. 「アプリ用 JSON で作らせる」と頼まれたときだけ、```json で囲んだ JSON を返す（形は `json_format.md`）。",
        "5. 1 行 30 字以内、1 枚 5 項目以内を目安に、短く言い切る。",
        "",
        "# 型の選び方",
        "",
        "- 手順・流れ → `型: フロー`",
        "- 要点を並べる → `型: カード`",
        "- 良し悪しや前後の対比 → `型: 比較`",
        "- 数値を見せる → `型: 数値`",
        "- 写真・図が主役 → `型: 画像`、一覧表 → `型: 表`",
        "- 表紙 → `型: 表紙`、最後の挨拶 → `型: 最終ページ`",
        "",
        "# 配色",
        "",
        ("- この資料の色: " + "、".join(f"{k} {v}" for k, v in colors.items()) if colors else "- 色はアプリのテンプレートが決めます。"),
        "- 色に触れるときは 16 進数で書く。色名では書かない。",
        "",
        "# よく来る依頼",
        "",
    ]
    for p in purposes:
        lines.append(f"- **{p.get('name') or p.get('id')}**（{p.get('id')}）: {p.get('description') or ''}".rstrip())
    lines += [
        "",
        "# 注意",
        "",
        "- 貼られた内容は利用者の資料そのものです。社外へ出さないでください。",
        "- 内容が足りないときは作り話で埋めず、`ノート:` に「要確認」と書いてください。",
        "",
    ]
    return "\n".join(lines)


_STARTER_VALUES = {"{title}": "この資料", "{slides}": "数", "{count}": "8", "{language}": "英語", "{brand}": ""}


def _plain(text: str) -> str:
    """会話の開始例に置くため、プロンプトの差込語を一般的な言い回しに直す。"""
    for k, v in _STARTER_VALUES.items():
        text = text.replace(k, v)
    return " ".join(text.split())


def build_manifest(name: str | None = None, description: str | None = None, purposes: list[dict] | None = None) -> dict:
    cfg = get_config()
    agent = cfg.copilot_prompts().get("agent") or {}
    purposes = purposes if purposes is not None else copilot_handoff.purposes()
    starters_max = int(agent.get("starters_max", 6) or 6)
    starters = []
    for item in purposes[:starters_max]:
        label = str(item.get("name") or item.get("id"))
        starters.append({"title": label[:50], "text": _plain(f"これから資料の Markdown を貼ります。「{label}」でお願いします。")[:200]})
    return {
        "$schema": MANIFEST_SCHEMA,
        "version": "v1.0",
        "name": (name or agent.get("name") or "資料づくりの相棒")[:100],
        "description": (description or agent.get("description") or "PowerPoint・Web 図解 双方向変換アプリと同じ書式で、資料の構成を整えるエージェント。")[:1000],
        "instructions": "$[file('instructions.md')]",
        "conversation_starters": starters,
    }


# ---------------------------------------------------------------- ナレッジの詰め替え
def _split_text(text: str, max_chars: int) -> list[str]:
    """段落の境界で max_chars 以内に切り分ける（境界が無ければ字数で切る）。"""
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    rest = text
    while len(rest) > max_chars:
        window = rest[:max_chars]
        cut = window.rfind("\n\n")
        if cut < max_chars // 2:
            cut = window.rfind("\n")
        if cut < max_chars // 2:
            cut = max_chars
        chunks.append(rest[:cut].rstrip("\n"))
        rest = rest[cut:].lstrip("\n")
    if rest:
        chunks.append(rest)
    return chunks


def pack_knowledge(records: list[dict], max_chars: int = MAX_CHARS, max_files: int = MAX_FILES) -> list[tuple[str, str]]:
    """記録を M365 Copilot のナレッジ向けテキストにする。先頭は INDEX。"""
    bodies: list[tuple[str, str, str]] = []  # (file_name, summary, text)
    overflow = 0
    for rec in records:
        for i, chunk in enumerate(_split_text(str(rec.get("text", "")), max_chars)):
            if len(bodies) >= max_files:
                overflow += 1
                continue
            suffix = f"（{i + 1}）" if i else ""
            bodies.append((f"{KNOWLEDGE_PREFIX}_{len(bodies) + 1:03d}.txt", f"{rec.get('summary', '')}{suffix}", chunk))
    index = [
        "PowerPoint・Web 図解 双方向変換アプリ / エージェント用ナレッジ 目次",
        f"作成: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"本文ファイル: {len(bodies)} 件",
        "",
    ]
    index += [f"{name}\t{summary}" for name, summary, _ in bodies]
    if overflow:
        index.append("")
        index.append(f"※ 上限（{max_files} ファイル）を超えたため {overflow} 件を省きました。")
    return [(f"{KNOWLEDGE_PREFIX}_INDEX.txt", "\n".join(index) + "\n")] + [(name, text) for name, _s, text in bodies]


def build_kit_zip(template_id: str | None = None, agent_name: str | None = None, description: str | None = None) -> bytes:
    cfg = get_config()
    purposes = copilot_handoff.purposes()
    template = cfg.template(template_id)
    records = collect_sources(template_id)
    instructions = build_instructions(purposes, template)
    manifest = build_manifest(agent_name, description, purposes)
    knowledge = pack_knowledge(records)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("declarativeAgent.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        z.writestr("instructions.md", instructions)
        for name, text in knowledge:
            z.writestr(f"knowledge/{name}", text)
        z.writestr("kit.json", json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "template_id": template.get("id"), "records": records}, ensure_ascii=False, indent=2))
        z.writestr("READ_ME.txt", _readme(manifest["name"], len(knowledge)))
    return buf.getvalue()


def _readme(agent_name: str, knowledge_files: int) -> str:
    return (
        "Copilot エージェント一式\n"
        "\n"
        f"エージェント名: {agent_name}\n"
        f"ナレッジ: knowledge/ 内の {knowledge_files} ファイル（目次 1 + 本文）\n"
        "\n"
        "登録のしかた（どちらか）\n"
        "A. Copilot Studio（エージェントビルダー）\n"
        "   1. 新しいエージェントを作り、「指示」に instructions.md の本文をそのまま貼る\n"
        "   2. 「ナレッジ」に knowledge/ のテキストをすべて添付する（M365 Copilot は 20 ファイルまで）\n"
        "   3. 会話の開始例に declarativeAgent.json の conversation_starters を入れる\n"
        "B. Teams Toolkit / 宣言型エージェント\n"
        "   declarativeAgent.json と instructions.md をそのまま使う（読み込めない版では A の手順で貼る）\n"
        "\n"
        "使い方\n"
        "  アプリの「Copilot に頼む」で作った文面をこのエージェントに貼ると、\n"
        "  同じ書式で返ってくるので、そのまま「回答を貼り付けて反映」で資料に戻せます。\n"
        "\n"
        "注意\n"
        "  資料の文章をそのまま渡します。社外秘の資料は社内テナントの M365 Copilot でのみ使ってください。\n"
    )
