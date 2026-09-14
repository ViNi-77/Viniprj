"""Copilot に渡す一式（ZIP）。

プロンプトだけでは足りないものが 2 つある:

1. **画像** — プロンプトはファイル名で参照させるだけなので、実体を別に渡す必要がある。
2. **Word 文書** — Copilot in PowerPoint の「ファイルから作成」はファイルを取るので、
   構成を Word にしておくと貼り付けより崩れにくい。

Word は python-docx を使わず最小の WordprocessingML を自前で書く（exe の同梱物を増やさないため。
Phase D からの方針を踏襲）。中身は **図解仕様から** 組み立てる。Presentation JSON から直接作ると
「画面に出ているものと渡すものが違う」が起きるため、渡すものは常に仕様を経由させる。
"""
from __future__ import annotations

import base64
import io
import re
import zipfile
from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape as _xml_escape

from . import spec_builder
from .logging_setup import get_logger

log = get_logger("handoff_pack")

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
        f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="{"•" if i == 0 else "–"}"/><w:lvlJc w:val="left"/>'
        f'<w:pPr><w:ind w:left="{720 * (i + 1)}" w:hanging="360"/></w:pPr>'
        '<w:rPr><w:rFonts w:ascii="Meiryo" w:hAnsi="Meiryo" w:eastAsia="Meiryo"/></w:rPr></w:lvl>'
        for i in range(3)
    )
    + '</w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>'
)

# ファイル名に使えない文字だけを落とす。日本語は残す（題名が日本語だと名前が空になるため）。
_SAFE_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def _w_p(text: str, style: str | None = None, level: int = 0) -> str:
    ppr = ""
    if style:
        num = f'<w:numPr><w:ilvl w:val="{min(level, 2)}"/><w:numId w:val="1"/></w:numPr>' if style == "ListBullet" else ""
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/>{num}</w:pPr>'
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{_xml_escape(text)}</w:t></w:r></w:p>'


def _w_table(rows: list[list[str]]) -> str:
    body = "".join(
        "<w:tr>" + "".join(f'<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/></w:tcPr>{_w_p(c)}</w:tc>' for c in row) + "</w:tr>"
        for row in rows if row
    )
    return f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/></w:tblPr>{body}</w:tbl>{_w_p("")}'


def to_docx(spec: dict) -> bytes:
    """図解仕様 → Word 文書（Copilot in PowerPoint の「ファイルから作成」用）。"""
    body: list[str] = [_w_p(spec.get("title") or "資料", "Title")]
    for s in spec.get("slides", []):
        body.append(_w_p(f"{s['no']}. {s.get('title') or 'スライド ' + str(s['no'])}", "Heading1"))
        if s.get("lead"):
            body.append(_w_p(s["lead"], "Note"))
        for it in s.get("items", []) or []:
            text = it.get("heading", "")
            if it.get("body"):
                text += ": " + it["body"]
            body.append(_w_p(text, "ListBullet"))
        for b in s.get("bullets", []) or []:
            body.append(_w_p(b, "ListBullet"))
        if s.get("table"):
            rows = ([s["table"]["header"]] if s["table"].get("header") else []) + list(s["table"].get("rows", []))
            if rows:
                body.append(_w_table(rows))
        for im in s.get("images", []) or []:
            label = im.get("filename") or im.get("asset_id") or "画像"
            body.append(_w_p(f"画像: {label}" + (f"（{im['alt']}）" if im.get("alt") else ""), "Note"))
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
        f"<dc:title>{_xml_escape(spec.get('title') or '')}</dc:title>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>'
    )
    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>Microsoft Office Word</Application></Properties>"
    )
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


def _readme(built: dict, image_count: int) -> str:
    L = [
        "Copilot に渡す一式",
        "=" * 40,
        "",
        f"やること: {built.get('outcome', '')}",
        f"貼り先  : {built.get('target', '')}",
        "",
        "手順",
        f"  1. {built.get('how', '')}",
        "  2. プロンプト.txt の中身をすべてコピーして貼り付ける",
    ]
    if image_count:
        L.append(f"  3. 画像/ の中の {image_count} 個の画像を、同じやり取りに添付する（プロンプトはこのファイル名で参照します）")
        L.append("  4. 出来上がったものを確認する")
    else:
        L.append("  3. 出来上がったものを確認する")
    L += [
        "",
        "同梱ファイル",
        "  プロンプト.txt   : そのまま貼り付けるもの",
        "  図解仕様.yaml    : このアプリが読み取った中身（プロンプトにも含まれています）",
        "  構成.docx        : Copilot in PowerPoint の「ファイルから作成」に使えます",
    ]
    if image_count:
        L.append("  画像/            : 資料に入っていた画像")
    if built.get("dropped_slides"):
        L += ["", f"※ 長さの上限に収めるため、後ろの {built['dropped_slides']} 枚はこのプロンプトに含まれていません。分けて渡してください。"]
    warn = [w for w in built.get("warnings", []) if w.get("message")]
    if warn:
        L += ["", "気を付けること"]
        L += [f"  - {w['message']}" for w in warn]
    L += ["", "このアプリは資料の中身を外部に送信しません。貼り付け先は社内テナントの Copilot を使ってください。"]
    return "\n".join(L) + "\n"


def build_zip(built: dict, spec: dict, presentation: dict | None = None) -> bytes:
    """プロンプト・仕様・Word・画像をまとめた ZIP。"""
    assets = (presentation or {}).get("assets", {}) or {}
    wanted: dict[str, dict] = {}
    for s in spec.get("slides", []):
        for im in s.get("images", []) or []:
            a = assets.get(im.get("asset_id"))
            if a and (a.get("data_base64") or a.get("data")):
                name = im.get("filename") or f"{im.get('asset_id')}.bin"
                wanted[_SAFE_NAME.sub("_", name)] = a

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("はじめにお読みください.txt", _readme(built, len(wanted)))
        z.writestr("プロンプト.txt", built.get("prompt", ""))
        z.writestr("図解仕様.yaml", built.get("spec_yaml") or spec_builder.to_yaml(spec))
        z.writestr("構成.docx", to_docx(spec))
        for name, a in wanted.items():
            data = a.get("data") if isinstance(a.get("data"), (bytes, bytearray)) else base64.b64decode(a.get("data_base64", ""))
            z.writestr(f"画像/{name}", data)
    log.info("受け渡し一式: %s 画像=%s", built.get("direction"), len(wanted))
    return buf.getvalue()


def pack_name(spec: dict, built: dict) -> str:
    base = _SAFE_NAME.sub("_", (spec.get("title") or "copilot").strip())[:40] or "copilot"
    return f"{base}_{built.get('direction', 'prompt')}.zip"


def image_manifest(spec: dict) -> list[dict[str, Any]]:
    """画面に「この画像を添付してください」と出すための一覧。"""
    out = []
    for s in spec.get("slides", []):
        for im in s.get("images", []) or []:
            out.append({"no": s["no"], "filename": im.get("filename") or "", "alt": im.get("alt") or "", "available": bool(im.get("available"))})
    return out
