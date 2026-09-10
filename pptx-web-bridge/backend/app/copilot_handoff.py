"""Copilot 連携（API を使わない受け渡し）。

渡す側: Presentation JSON → Copilot に貼る／添付する形（Markdown・簡易 JSON・Word 文書・プロンプト）。
戻す側: Copilot の回答（Markdown または簡易 JSON）→ Presentation JSON（新しい資料、またはノートだけ反映）。

設計:
- 文章と構成だけを渡し、座標・ブランド部品はこのアプリとブランドキットが受け持つ（AI は中身、プログラムは決定的な生成）。
- Markdown の読み戻しは、簡単な Markdown → HTML 変換の後に既存の html_parser を通す（実装を二重にしない）。
- Word 文書は python-docx を使わず最小の WordprocessingML を書く（exe の同梱物を増やさない）。
  見出し 1 = 資料題名、見出し 2 = スライド、箇条書き、表、ノートの段落。Copilot in PowerPoint の「ファイルから作成」に使える。
"""
from __future__ import annotations

import html
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape as _xml_escape

from .config import get_config
from .model import slide_title
from .web_renderer import asset_filename

_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_BULLET_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_NOTE_RE = re.compile(r"^\s*(?:>\s*)?(?:ノート|Notes?|発表者ノート|スピーカーノート)\s*[:：]\s*(.*)$", re.I)
_KIND_RE = re.compile(r"^\s*(?:型|レイアウト|Layout|Type)\s*[:：]\s*(.*)$", re.I)
_SLIDE_NO_RE = re.compile(r"^\s*(?:スライド\s*)?\d+\s*[.．:：)]\s*")
_LAYOUT_WORDS = {"フロー": "title_body", "手順": "title_body", "カード": "three_column", "3分割": "three_column", "比較": "two_column", "Before": "two_column", "数値": "title_body", "画像": "image", "表": "table"}


# ---------------------------------------------------------------- 渡す側
def _para_text(p: dict) -> str:
    return "".join(r.get("text", "") for r in p.get("runs", []))


def _brand_line(presentation: dict) -> str:
    """テンプレートの色・フォントを 1 行にする（ブランドキットが無い環境でも色味が伝わるように）。"""
    theme = presentation.get("theme", {})
    colors = theme.get("colors", {})
    fonts = theme.get("fonts", {})
    parts = []
    if colors.get("primary"):
        parts.append(f"主色 {colors['primary']}")
    if colors.get("accent"):
        parts.append(f"強調色 {colors['accent']}")
    if fonts.get("heading"):
        parts.append(f"見出しフォント {fonts['heading']}")
    return ("- 配色・フォントの参考: " + "、".join(parts)) if parts else ""


def slide_to_markdown(slide: dict, presentation: dict, index: int, image_note: bool = True) -> str:
    """1 スライド → Markdown（## 番号. 題名、箇条書き、表、画像、ノート）。"""
    lines: list[str] = []
    title = slide_title(slide) or f"スライド {index + 1}"
    lines.append(f"## {index + 1}. {title}")
    layout = slide.get("layout")
    if layout in ("title", "closing"):
        lines.append(f"型: {'表紙' if layout == 'title' else '最終ページ'}")
    for el in sorted(slide.get("elements", []), key=lambda e: ((e.get('bbox') or {}).get('y', 0), (e.get('bbox') or {}).get('x', 0))):
        t = el.get("type")
        if t in ("text", "shape"):
            if el.get("role") == "title":
                continue  # 題名は見出しに出した
            for p in el.get("paragraphs", []):
                text = _para_text(p).strip()
                if not text:
                    continue
                level = int(p.get("level", 0) or 0)
                if p.get("bullet") or el.get("role") in ("body", "card") or level > 0:
                    lines.append("  " * level + f"- {text}")
                elif el.get("role") == "subtitle":
                    lines.append(f"*{text}*")
                else:
                    lines.append(text)
        elif t == "table":
            rows = el.get("rows") or []
            if not rows:
                continue
            header = int(el.get("header_rows", 1) or 0)
            for ri, row in enumerate(rows):
                cells = [str(c.get("text", "")).replace("|", "／").replace("\n", " ") for c in row]
                lines.append("| " + " | ".join(cells) + " |")
                if ri == 0:
                    lines.append("|" + "|".join([" --- "] * len(cells)) + "|")
            if header == 0 and rows:
                pass
        elif t == "image" and image_note:
            asset = presentation.get("assets", {}).get(el.get("asset_id") or "", {})
            name = asset_filename(el.get("asset_id"), asset) if el.get("asset_id") else "(画像なし)"
            alt = (el.get("alt") or "").strip()
            lines.append(f"画像: {name}" + (f"（{alt}）" if alt and alt != name else ""))
    if slide.get("notes"):
        lines.append(f"ノート: {str(slide['notes']).strip()}")
    return "\n".join(lines)


def to_markdown(presentation: dict, image_note: bool | None = None) -> str:
    """資料全体 → Markdown。先頭に資料題名（# ）と作成情報。"""
    cfg = get_config()
    if image_note is None:
        image_note = bool(cfg.get("copilot.image_note", True))
    title = presentation.get("meta", {}).get("title") or "資料"
    out = [f"# {title}", ""]
    for i, s in enumerate(presentation.get("slides", [])):
        out.append(slide_to_markdown(s, presentation, i, image_note))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def to_outline_json(presentation: dict) -> dict:
    """資料全体 → 簡易 JSON（Copilot に読ませる・返させる用。座標や資産は含めない）。"""
    slides = []
    for i, s in enumerate(presentation.get("slides", [])):
        bullets: list[dict] = []
        tables: list[list[list[str]]] = []
        images: list[dict] = []
        for el in s.get("elements", []):
            t = el.get("type")
            if t in ("text", "shape"):
                if el.get("role") == "title":
                    continue
                for p in el.get("paragraphs", []):
                    text = _para_text(p).strip()
                    if text:
                        bullets.append({"text": text, "level": int(p.get("level", 0) or 0), "role": el.get("role") or "body"})
            elif t == "table":
                tables.append([[str(c.get("text", "")) for c in row] for row in el.get("rows") or []])
            elif t == "image":
                asset = presentation.get("assets", {}).get(el.get("asset_id") or "", {})
                images.append({"file": asset_filename(el["asset_id"], asset) if el.get("asset_id") else None, "alt": el.get("alt") or ""})
        slides.append({"n": i + 1, "title": slide_title(s) or "", "layout": s.get("layout") or "title_body", "bullets": bullets, "tables": tables, "images": images, "notes": s.get("notes") or ""})
    theme = presentation.get("theme", {})
    return {"title": presentation.get("meta", {}).get("title") or "資料", "brand": {"colors": dict(theme.get("colors", {})), "fonts": dict(theme.get("fonts", {}))}, "slides": slides}


# ---------------------------------------------------------------- Word 文書（最小の WordprocessingML）
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
    '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
    "</Types>"
)
_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
    '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
    "</Relationships>"
)
_DOC_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
    "</Relationships>"
)
_STYLES = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="{_W}">'
    '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Meiryo" w:hAnsi="Meiryo" w:eastAsia="Meiryo"/><w:sz w:val="22"/></w:rPr></w:rPrDefault>'
    '<w:pPrDefault><w:pPr><w:spacing w:after="120"/></w:pPr></w:pPrDefault></w:docDefaults>'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="240"/></w:pPr><w:rPr><w:b/><w:sz w:val="48"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="360" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="ListBullet"><w:name w:val="List Bullet"/><w:basedOn w:val="Normal"/><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Note"><w:name w:val="Note"/><w:basedOn w:val="Normal"/><w:rPr><w:i/><w:color w:val="666666"/></w:rPr></w:style>'
    '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders>'
    '<w:top w:val="single" w:sz="4" w:color="999999"/><w:left w:val="single" w:sz="4" w:color="999999"/><w:bottom w:val="single" w:sz="4" w:color="999999"/><w:right w:val="single" w:sz="4" w:color="999999"/>'
    '<w:insideH w:val="single" w:sz="4" w:color="999999"/><w:insideV w:val="single" w:sz="4" w:color="999999"/></w:tblBorders></w:tblPr></w:style>'
    "</w:styles>"
)
_NUMBERING = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering xmlns:w="{_W}">'
    '<w:abstractNum w:abstractNumId="0">'
    + "".join(
        f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="{"•" if i == 0 else "–"}"/><w:lvlJc w:val="left"/><w:pPr><w:ind w:left="{720 * (i + 1)}" w:hanging="360"/></w:pPr><w:rPr><w:rFonts w:ascii="Meiryo" w:hAnsi="Meiryo" w:eastAsia="Meiryo"/></w:rPr></w:lvl>'
        for i in range(3)
    )
    + '</w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>'
)


def _w_p(text: str, style: str | None = None, level: int = 0) -> str:
    ppr = ""
    if style:
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/>' + (f'<w:numPr><w:ilvl w:val="{min(level, 2)}"/><w:numId w:val="1"/></w:numPr>' if style == "ListBullet" else "") + "</w:pPr>"
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{_xml_escape(text)}</w:t></w:r></w:p>'


def _w_table(rows: list[list[str]]) -> str:
    cells = "".join("<w:tr>" + "".join(f'<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/></w:tcPr>{_w_p(c)}</w:tc>' for c in row) + "</w:tr>" for row in rows if row)
    return f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/></w:tblPr>{cells}</w:tbl>{_w_p("")}'


def to_docx(presentation: dict) -> bytes:
    """資料全体 → Word 文書（見出し 1 = 資料題名、見出し 2 = スライド、箇条書き、表、ノート）。"""
    outline = to_outline_json(presentation)
    body: list[str] = [_w_p(outline["title"], "Title")]
    for s in outline["slides"]:
        body.append(_w_p(f"{s['n']}. {s['title'] or 'スライド ' + str(s['n'])}", "Heading1"))
        for b in s["bullets"]:
            if b.get("role") == "subtitle":
                body.append(_w_p(b["text"], "Note"))
            else:
                body.append(_w_p(b["text"], "ListBullet", int(b.get("level", 0))))
        for tbl in s["tables"]:
            body.append(_w_table(tbl))
        for img in s["images"]:
            body.append(_w_p(f"画像: {img.get('file') or '(画像なし)'}" + (f"（{img['alt']}）" if img.get("alt") else ""), "Note"))
        if s.get("notes"):
            body.append(_w_p(f"ノート: {s['notes']}", "Note"))
    document = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{_W}"><w:body>'
        + "".join(body)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr></w:body></w:document>'
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{_xml_escape(outline['title'])}</dc:title><dc:creator>{_xml_escape(presentation.get('meta', {}).get('author') or '')}</dc:creator>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>'
    )
    app = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Microsoft Office Word</Application></Properties>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", _STYLES)
        z.writestr("word/numbering.xml", _NUMBERING)
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
    return buf.getvalue()


# ---------------------------------------------------------------- プロンプトと受け渡し一式
def purposes() -> list[dict]:
    return [dict(p) for p in get_config().copilot_prompts().get("purposes", [])]


def purpose(purpose_id: str | None) -> dict:
    items = purposes()
    for p in items:
        if p.get("id") == purpose_id:
            return p
    return items[0]


def build_prompt(presentation: dict, purpose_id: str | None, options: dict | None = None) -> dict:
    """用途プリセットのプロンプトに資料の内容を付けて返す。

    返り値: {"purpose", "prompt"（内容込み）, "instruction"（指示部分だけ）, "content", "content_format", "chars", "truncated"}
    """
    cfg = get_config()
    p = purpose(purpose_id)
    opts = {**(p.get("options") or {}), **(options or {})}
    fmt = p.get("content_format", "markdown")
    content = to_markdown(presentation) if fmt == "markdown" else json.dumps(to_outline_json(presentation), ensure_ascii=False, indent=1)
    if fmt == "json":
        content = "```json\n" + content + "\n```"
    values = {
        "title": presentation.get("meta", {}).get("title") or "資料",
        "slides": str(len(presentation.get("slides", []))),
        "count": str(opts.get("count", 8)),
        "language": str(opts.get("language", "英語")),
        "brand": _brand_line(presentation),
    }
    instruction = str(p.get("prompt", ""))
    for k, v in values.items():
        instruction = instruction.replace("{" + k + "}", v)
    instruction = "\n".join(ln for ln in instruction.splitlines() if ln.strip() or ln == "")  # 空の {brand} 行を消す
    instruction = re.sub(r"\n{3,}", "\n\n", instruction)
    max_chars = int(cfg.get("copilot.max_chars", 60000))
    truncated = False
    if len(content) > max_chars:
        content = content[:max_chars] + "\n\n（以下省略: 資料が長いため、Word 文書を添付してください）"
        truncated = True
    return {"purpose": p.get("id"), "purpose_name": p.get("name"), "attach_hint": p.get("attach_hint") or "", "instruction": instruction, "content": content, "content_format": fmt, "prompt": instruction.rstrip("\n") + "\n" + content, "chars": len(instruction) + len(content), "truncated": truncated, "chat_url": cfg.copilot_prompts().get("chat_url")}


def bundle_zip(presentation: dict, purpose_id: str | None, options: dict | None = None) -> bytes:
    """Copilot へ渡す一式（prompt.txt / outline.md / outline.json / outline.docx / images/）。"""
    import base64

    built = build_prompt(presentation, purpose_id, options)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("prompt.txt", built["instruction"].rstrip("\n") + "\n\n（この下に outline.md の内容を貼るか、outline.docx を添付してください）\n")
        z.writestr("outline.md", to_markdown(presentation))
        z.writestr("outline.json", json.dumps(to_outline_json(presentation), ensure_ascii=False, indent=2))
        z.writestr("outline.docx", to_docx(presentation))
        for asset_id, asset in presentation.get("assets", {}).items():
            if asset.get("data_base64"):
                z.writestr(f"images/{asset_filename(asset_id, asset)}", base64.b64decode(asset["data_base64"]))
        z.writestr("READ_ME.txt", "Copilot への渡し方\n1. Copilot チャット: prompt.txt の文面を貼り、続けて outline.md を貼る（または outline.docx を添付）\n2. Copilot in PowerPoint: 「ファイルから作成」で outline.docx を選ぶ。ブランドキットを適用すると自社様式になる\n3. Copilot の回答（Markdown）は、アプリの「Copilot に頼む」→「回答を貼り付けて反映」で資料に戻せる\n")
    return buf.getvalue()


# ---------------------------------------------------------------- 戻す側: Markdown → HTML → Presentation JSON
def _strip_fences(text: str) -> str:
    lines = text.splitlines()
    out = [ln for ln in lines if not _FENCE_RE.match(ln)]
    return "\n".join(out)


def _inline_html(text: str) -> str:
    """太字・斜体・リンク・画像のインライン記法を HTML に。"""
    text = html.escape(text, quote=False)
    text = _IMAGE_RE.sub(lambda m: f'<img src="{m.group(2)}" alt="{m.group(1)}">', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def _render_list(items: list[dict]) -> str:
    return "<ul>" + "".join(f"<li>{it['html']}" + (_render_list(it["children"]) if it.get("children") else "") + "</li>" for it in items) + "</ul>"


def markdown_to_html(md: str) -> tuple[str, list[dict]]:
    """Copilot の回答（Markdown）→ 見出し単位の section を持つ HTML。ノートと型は別に返す。

    返り値: (html, [{"index": n, "notes": str, "kind": str}])  index は section の順番（0 始まり、表紙を除く）。
    箇条書きは入れ子を <li> の中に置く（html_parser がレベルとして読む）。
    """
    md = _strip_fences(md.replace("\r\n", "\n").replace("\r", "\n"))
    lines = md.split("\n")
    doc_title = ""
    sections: list[dict] = []  # {"title", "level", "html": [..], "notes", "kind"}
    cur: dict | None = None
    para: list[str] = []
    table: list[list[str]] = []
    list_root: list[dict] = []
    list_stack: list[tuple[int, list[dict]]] = []  # (インデント, その深さの項目一覧)

    def flush_list() -> None:
        nonlocal list_root, list_stack
        if list_root and cur is not None:
            cur["html"].append(_render_list(list_root))
        list_root, list_stack = [], []

    def flush_para() -> None:
        nonlocal para
        if para and cur is not None:
            cur["html"].append("<p>" + _inline_html(" ".join(x.strip() for x in para)) + "</p>")
        para = []

    def flush_table() -> None:
        nonlocal table
        if table and cur is not None:
            rows = [r for r in table if any(c.strip() for c in r)]
            if rows:
                th = "".join(f"<th>{_inline_html(c)}</th>" for c in rows[0])
                trs = "".join("<tr>" + "".join(f"<td>{_inline_html(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
                cur["html"].append(f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>")
        table = []

    def flush_all() -> None:
        flush_para()
        flush_table()
        flush_list()

    def ensure_section(title: str, level: int) -> None:
        nonlocal cur
        flush_all()
        cur = {"title": title, "level": level, "html": [], "notes": "", "kind": ""}
        sections.append(cur)

    for raw in lines:
        line = raw.rstrip()
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            if level == 1 and not doc_title and not sections:
                doc_title = title
                continue
            ensure_section(_SLIDE_NO_RE.sub("", title) if level <= 2 else title, level)
            continue
        if cur is None:
            if not line.strip():
                continue
            ensure_section(doc_title or "スライド 1", 2)
        assert cur is not None
        nm = _NOTE_RE.match(line)
        if nm:
            flush_all()
            cur["notes"] = (cur["notes"] + "\n" + nm.group(1).strip()).strip()
            continue
        km = _KIND_RE.match(line)
        if km:
            flush_para()
            cur["kind"] = km.group(1).strip()
            continue
        if "|" in line and line.strip().startswith("|"):
            flush_para()
            flush_list()
            if _TABLE_SEP_RE.match(line):
                continue
            table.append([c.strip() for c in line.strip().strip("|").split("|")])
            continue
        flush_table()
        bm = _BULLET_RE.match(line)
        if bm:
            flush_para()
            indent = len(bm.group(1).replace("\t", "    "))
            item = {"html": _inline_html(bm.group(3).strip()), "children": []}
            while list_stack and indent < list_stack[-1][0]:
                list_stack.pop()
            if not list_stack:
                list_root = []
                list_stack = [(indent, list_root)]
            elif indent > list_stack[-1][0] and list_stack[-1][1]:
                parent = list_stack[-1][1][-1]
                list_stack.append((indent, parent["children"]))
            list_stack[-1][1].append(item)
            continue
        if not line.strip():
            flush_para()
            flush_list()
            continue
        if line.strip().startswith(">"):
            line = line.strip().lstrip(">").strip()
        img = _IMAGE_RE.fullmatch(line.strip())
        if img:
            flush_all()
            cur["html"].append(f'<figure><img src="{html.escape(img.group(2))}" alt="{html.escape(img.group(1))}"></figure>')
            continue
        flush_list()
        para.append(line)
    flush_all()

    parts = ["<!DOCTYPE html><html><head><meta charset='utf-8'><title>" + html.escape(doc_title or (sections[0]["title"] if sections else "資料")) + "</title></head><body>"]
    cover_from_section = bool(sections) and ("表紙" in sections[0]["kind"] or (doc_title and sections[0]["title"] == doc_title))
    meta: list[dict] = []
    if cover_from_section:
        # 表紙: 見出しを h1、本文（副題）を lead 段落にする（html_parser が表紙スライドを作る）
        first = sections.pop(0)
        subtitle = re.sub(r"<[^>]+>", "", " ".join(x for x in first["html"] if x.startswith("<p>")).replace("</p>", " / ")).strip(" /")
        parts.append(f"<h1>{_inline_html(first['title'])}</h1>")
        if subtitle:
            parts.append(f'<p class="lead">{html.escape(subtitle)}</p>')
    elif doc_title:
        parts.append(f"<h1>{_inline_html(doc_title)}</h1>")
    for i, sec in enumerate(sections):
        tag = "h2" if sec["level"] <= 2 else "h3"
        body_html = "".join(sec["html"])
        cls = ""
        if sec["kind"]:
            for word, lay in _LAYOUT_WORDS.items():
                if word.lower() in sec["kind"].lower():
                    cls = f' class="kind-{lay}"'
                    break
        parts.append(f"<section{cls}><{tag}>{_inline_html(sec['title'])}</{tag}>{body_html}</section>")
        meta.append({"index": i, "notes": sec["notes"], "kind": sec["kind"]})
    parts.append("</body></html>")
    return "".join(parts), meta


def _layout_from_kind(kind: str) -> str | None:
    for word, lay in _LAYOUT_WORDS.items():
        if word.lower() in kind.lower():
            return lay
    return None


def import_markdown(md: str, template_id: str | None = None, filename: str = "copilot.md") -> dict:
    """Copilot の回答（Markdown）→ Presentation JSON（レイアウト前）。ノート・型を各スライドへ付ける。"""
    from .html_parser import parse_html

    html_text, meta = markdown_to_html(md)
    pres = parse_html(html_text.encode("utf-8"), filename, {}, template_id, computed_style=False)
    pres["meta"]["source"] = {"type": "html", "filename": filename, "via": "copilot"}
    # html_parser は section ごとに 1 スライドを作る（表紙の h1 を除く）。順に対応付ける
    body_slides = [s for s in pres.get("slides", []) if s.get("layout") != "title" or s.get("index", 0) > 0]
    if len(body_slides) == len(meta):
        for s, m in zip(body_slides, meta):
            if m["notes"]:
                s["notes"] = m["notes"]
            lay = _layout_from_kind(m["kind"]) if m["kind"] else None
            if lay and not any(e.get("layout_hint") for e in s.get("elements", [])):
                s["layout"] = lay
                if lay in ("two_column", "three_column"):
                    cols = 2 if lay == "two_column" else 3
                    texts = [e for e in s["elements"] if e.get("type") == "text" and e.get("role") != "title"]
                    _split_bullets_into_columns(s, texts, cols)
    return pres


def _split_bullets_into_columns(slide: dict, texts: list[dict], cols: int) -> None:
    """「型: カード / 比較」のスライド: 箇条書きを列に分けて layout_hint を付ける（見出し行とその下位項目を 1 枚のカードにする）。"""
    if len(texts) != 1 or not texts[0].get("paragraphs"):
        return
    src = texts[0]
    paras = [p for p in src["paragraphs"] if _para_text(p).strip()]
    cards: list[list[dict]] = []
    for p in paras:
        if int(p.get("level", 0) or 0) == 0 or not cards:
            cards.append([p])
        else:
            cards[-1].append(p)
    if len(cards) < 2:
        return
    cols = min(cols, len(cards))
    per = -(-len(cards) // cols)  # 切り上げ
    groups = [sum(cards[i * per : (i + 1) * per], []) for i in range(cols)]
    slide["elements"].remove(src)
    for c, g in enumerate(groups):
        if not g:
            continue
        paragraphs = [dict(p, bullet=None if int(p.get("level", 0) or 0) == 0 else p.get("bullet")) for p in g]
        slide["elements"].append(dict(src, id=f"{src['id']}_c{c + 1}", paragraphs=paragraphs, role="card", layout_hint={"columns": cols, "column": c}))


def import_outline_json(data: dict, template_id: str | None = None) -> dict:
    """簡易 JSON（to_outline_json と同じ形）→ Presentation JSON（レイアウト前）。"""
    from .model import new_presentation, new_slide, paragraph, run, table_element, text_element, cell

    pres = new_presentation(str(data.get("title") or "資料"), "manual", "copilot.json", template_id)
    pres["meta"]["source"] = {"type": "json", "filename": "copilot.json", "via": "copilot"}
    for i, s in enumerate(data.get("slides") or []):
        sid = f"s{i + 1:03d}"
        layout = str(s.get("layout") or "title_body")
        if layout not in ("title", "section", "title_body", "two_column", "three_column", "image", "table", "blank", "closing"):
            layout = _layout_from_kind(layout) or "title_body"
        slide = new_slide(sid, i, layout=layout, title=str(s.get("title") or "") or None)
        if s.get("title"):
            slide["elements"].append(text_element(f"{sid}_t", [paragraph([run(str(s["title"]), bold=True)])], role="title"))
        bullets = s.get("bullets") or []
        paras = []
        for b in bullets:
            if isinstance(b, str):
                paras.append(paragraph([run(b)], bullet="bullet"))
            elif isinstance(b, dict) and b.get("text"):
                lvl = int(b.get("level", 0) or 0)
                paras.append(paragraph([run(str(b["text"]))], level=lvl, bullet=None if b.get("role") == "subtitle" else "bullet"))
        if paras:
            slide["elements"].append(text_element(f"{sid}_b", paras, role="subtitle" if layout == "title" else "body"))
        for ti, tbl in enumerate(s.get("tables") or []):
            rows = [[cell(str(c), bold=(ri == 0)) for c in row] for ri, row in enumerate(tbl) if isinstance(row, list)]
            if rows:
                slide["elements"].append(table_element(f"{sid}_tbl{ti + 1}", rows))
        if s.get("notes"):
            slide["notes"] = str(s["notes"])
        pres["slides"].append(slide)
    return pres


def parse_copilot_reply(text: str) -> tuple[str, Any]:
    """貼り付けられた回答を JSON か Markdown か判定する。返り値: ("json", dict) / ("markdown", str)"""
    stripped = _strip_fences(text).strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
            if isinstance(data, dict) and "slides" in data:
                return "json", data
        except json.JSONDecodeError:
            pass
    return "markdown", text


def apply_notes(presentation: dict, reply: str) -> tuple[dict, int]:
    """「発表者ノートを作る」の回答を、番号（## n.）または順番で既存スライドのノートへ入れる。返り値: (資料, 反映件数)"""
    kind, data = parse_copilot_reply(reply)
    notes: list[tuple[int | None, str]] = []
    if kind == "json":
        for s in data.get("slides") or []:
            n = s.get("n")
            notes.append((int(n) - 1 if isinstance(n, int) else None, str(s.get("notes") or "")))
    else:
        _html, meta = markdown_to_html(data)
        # 見出しの番号を拾う
        numbers: list[int | None] = []
        for ln in _strip_fences(data).splitlines():
            m = _HEADING_RE.match(ln.rstrip())
            if m and len(m.group(1)) >= 2:
                nm = re.match(r"^\s*(?:スライド\s*)?(\d+)\s*[.．:：)]", m.group(2))
                numbers.append(int(nm.group(1)) - 1 if nm else None)
        for i, m in enumerate(meta):
            notes.append((numbers[i] if i < len(numbers) else None, m["notes"]))
    slides = presentation.get("slides", [])
    count = 0
    for pos, (n, note) in enumerate(notes):
        if not note:
            continue
        idx = n if n is not None and 0 <= n < len(slides) else (pos if pos < len(slides) else None)
        if idx is None:
            continue
        slides[idx]["notes"] = note
        count += 1
    return presentation, count
