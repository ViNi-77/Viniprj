"""ローカル資料の非破壊抽出。上限・欠落・OCRの失敗を必ず結果に残す。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import io
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any
import zipfile

from defusedxml import ElementTree as ET

OFFICE_EXTENSIONS = {".docx", ".docm", ".xlsx", ".xlsm", ".pptx", ".pptm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".tsv", ".json", ".jsonl", ".log"}
LEGACY_EXTENSIONS = {".doc", ".xls", ".ppt", ".rtf", ".odt", ".ods", ".odp"}
SUPPORTED_EXTENSIONS = OFFICE_EXTENSIONS | IMAGE_EXTENSIONS | TEXT_EXTENSIONS | LEGACY_EXTENSIONS | {".pdf", ".zip"}
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 5000
MAX_COMPRESSION_RATIO = 2000
MAX_TEXT_CHARS = 10_000_000
MAX_UNITS = 20_000
MAX_DEPTH = 3
MAX_IMAGE_PIXELS = 40_000_000
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


@dataclass
class Extraction:
    text: str = ""
    status: str = "empty"
    warnings: list[str] = field(default_factory=list)
    units: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class _Limit(Exception):
    pass


@dataclass
class _Budget:
    deadline: float
    max_pages: int
    ocr: bool
    timeout: float
    expanded_bytes: int = 0
    entry_count: int = 0
    chars: int = 0
    units: int = 0

    def check(self):
        if time.monotonic() >= self.deadline:
            raise _Limit("処理時間の上限に達しました。未読部分があります。")

    def add(self, result: Extraction, locator: str, text: str, status: str = "ok"):
        self.check()
        text = text.strip()
        if self.units >= MAX_UNITS:
            raise _Limit(f"抽出単位の上限 {MAX_UNITS:,} 件に達しました。未読部分があります。")
        available = MAX_TEXT_CHARS - self.chars
        if len(text) > available:
            if available > 0:
                result.units.append({"locator": locator, "text": text[:available], "status": "partial"})
                self.chars += available
            raise _Limit(f"抽出文字数の上限 {MAX_TEXT_CHARS:,} 字に達しました。未読部分があります。")
        self.chars += len(text)
        self.units += 1
        result.units.append({"locator": locator, "text": text, "status": status})


def _warn(result: Extraction, text: str):
    if text not in result.warnings:
        result.warnings.append(text)


def _finalize(result: Extraction) -> Extraction:
    result.text = "\n\n".join(f"[{u['locator']}]\n{u['text']}" for u in result.units if u["text"])
    result.metadata["unit_count"] = len(result.units)
    result.metadata["text_characters"] = sum(len(u["text"]) for u in result.units)
    if result.text:
        result.status = "partial" if result.warnings or any(u["status"] not in {"ok", "ocr"} for u in result.units) else "ok"
    elif result.status not in {"protected", "needs_conversion", "needs_ocr", "error"}:
        result.status = "error" if result.warnings else "empty"
    return result


def extract_document(path: Path, *, ocr: bool = True, max_pages: int = 500, timeout: float = 60) -> Extraction:
    """本文・出典単位・警告を返す。原本への書込み、マクロ実行、外部通信は行わない。

    timeout は資料全体の協調的期限であり、OCR子プロセスには残り時間を強制適用。
    Office/PDFライブラリ内部の単一呼出しは中断できないため、バイト数上限も併用する。
    """
    if max_pages < 1 or timeout <= 0:
        raise ValueError("max_pages と timeout は正数で指定してください。")
    budget = _Budget(time.monotonic() + timeout, max_pages, ocr, timeout)
    return _extract(Path(path), budget, 0)


def _extract(path: Path, budget: _Budget, depth: int) -> Extraction:
    result = Extraction(metadata={"filename": path.name, "format": path.suffix.lower(), "ocr_requested": budget.ocr})
    try:
        budget.check()
        if depth > MAX_DEPTH:
            raise _Limit(f"入れ子の上限 {MAX_DEPTH} 階層に達しました。内部資料を個別に登録してください。")
        size = path.stat().st_size
        result.metadata["source_bytes"] = size
        if size > MAX_FILE_BYTES:
            raise _Limit(f"ファイル容量の上限 {MAX_FILE_BYTES // 1024 // 1024} MB を超えています。資料を分割してください。")
        suffix = path.suffix.lower()
        if suffix in LEGACY_EXTENSIONS or suffix not in SUPPORTED_EXTENSIONS:
            result.status = "needs_conversion"
            _warn(result, "この形式は直接読み取れません。Officeの新形式（DOCX・XLSX・PPTX）またはPDF・TXTへ変換してください。")
        elif suffix in TEXT_EXTENSIONS:
            _plain(path, result, budget)
        elif suffix == ".pdf":
            _pdf(path, result, budget)
        elif suffix in IMAGE_EXTENSIONS:
            _image_file(path, result, budget, "画像")
        elif suffix == ".zip":
            _archive(path, result, budget, depth)
        else:
            with path.open("rb") as src:
                signature = src.read(8)
            if signature == OLE_MAGIC:
                result.status = "protected"
                _warn(result, "暗号化されたOffice文書、または拡張子と内容が異なる旧形式です。保護解除または新形式での保存が必要です。")
            else:
                _office(path, result, budget, depth)
    except _Limit as exc:
        _warn(result, str(exc))
    except PermissionError:
        result.status = "error"
        _warn(result, "資料を読み取る権限がありません。アクセス権と他アプリでの使用状況を確認してください。")
    except FileNotFoundError:
        result.status = "error"
        _warn(result, "資料が見つかりません。クラウド上の資料はローカルへ取得してから再実行してください。")
    except Exception as exc:
        result.status = "error"
        # 本文・パス・外部ライブラリの生エラーをログやUIに漏らさない。
        _warn(result, f"読み取りに失敗しました（{type(exc).__name__}）。破損・保護・クラウド未取得を確認してください。")
    return _finalize(result)


def _plain(path: Path, result: Extraction, budget: _Budget):
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        encodings = ["utf-32"]
    elif raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings = ["utf-16"]
    else:
        encodings = ["utf-8-sig", "cp932"]
    text = None
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
            result.metadata["encoding"] = encoding
            break
        except UnicodeDecodeError:
            pass
    if text is None:
        from charset_normalizer import from_bytes
        match = from_bytes(raw).best()
        if match is None:
            raise ValueError("文字コードを判定できません")
        text = str(match)
        result.metadata["encoding"] = match.encoding
        _warn(result, f"文字コードを {match.encoding} と推定しました。文字化けがないか確認してください。")
    if "\x00" in text:
        raise ValueError("バイナリデータを含むテキスト")
    budget.add(result, "本文", text)


def tesseract_path() -> str | None:
    """利用者指定、EXEと同梱のOCR、開発環境PATHの順で探す。"""
    configured = os.environ.get("CONTEXTGEN_TESSERACT")
    if configured:
        return str(Path(configured)) if Path(configured).is_file() else None
    names = ("tesseract.exe", "tesseract")
    bases = [Path(sys.executable).parent / "ocr", Path(__file__).resolve().parents[1] / "ocr"]
    if getattr(sys, "_MEIPASS", None):
        bases.append(Path(sys._MEIPASS) / "ocr")
    for base in bases:
        for name in names:
            if (base / name).is_file():
                return str(base / name)
    return shutil.which("tesseract")


def _ocr_image(image, result: Extraction, budget: _Budget, locator: str):
    budget.check()
    if not budget.ocr:
        _warn(result, f"{locator}: OCRが無効のため画像内の文字は未読です。")
        result.status = "needs_ocr"
        budget.add(result, locator, "", "needs_ocr")
        return
    executable = tesseract_path()
    if not executable:
        _warn(result, f"{locator}: Tesseractが見つからないため画像内の文字は未読です。OCR同梱版をご利用ください。")
        result.status = "needs_ocr"
        budget.add(result, locator, "", "needs_ocr")
        return
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise _Limit(f"{locator}: 画像が {MAX_IMAGE_PIXELS:,} 画素の上限を超えています。縮小して再登録してください。")
    with tempfile.TemporaryDirectory(prefix="contextgen-kai-ocr-") as tmp:
        img_path = Path(tmp) / "input.png"
        # DPI不明の画像には架空の値を与えず、Tesseractの推定を使う。
        options = {}
        dpi = image.info.get("dpi")
        if isinstance(dpi, (tuple, list)) and len(dpi) == 2 and all(70 <= d <= 2400 for d in dpi):
            options["dpi"] = dpi
        image.convert("RGB").save(img_path, **options)
        command = [executable, str(img_path), "stdout", "-l", os.environ.get("CONTEXTGEN_OCR_LANG", "jpn+eng")]
        tessdata = Path(executable).parent / "tessdata"
        if tessdata.is_dir():
            command.extend(["--tessdata-dir", str(tessdata)])
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        remaining = min(30, max(0.01, budget.deadline - time.monotonic()))
        try:
            completed = subprocess.run(command, capture_output=True, timeout=remaining, creationflags=flags, check=False)
        except subprocess.TimeoutExpired:
            _warn(result, f"{locator}: OCRが制限時間を超えました。この部分は未読です。")
            budget.add(result, locator, "", "needs_ocr")
            result.status = "needs_ocr"
            return
        if completed.returncode:
            _warn(result, f"{locator}: OCRに失敗しました。日本語・英語の言語データと画像を確認してください。")
            budget.add(result, locator, "", "needs_ocr")
            result.status = "needs_ocr"
            return
        text = completed.stdout.decode("utf-8", errors="replace").strip()
        result.metadata["ocr_engine"] = "Tesseract"
        result.metadata["ocr_units"] = result.metadata.get("ocr_units", 0) + 1
        if not text:
            _warn(result, f"{locator}: OCRで文字を検出できませんでした。原本を確認してください。")
        budget.add(result, locator, text, "ocr" if text else "empty")


def _image_file(path: Path, result: Extraction, budget: _Budget, locator: str):
    from PIL import Image, ImageOps
    with Image.open(path) as image:
        frames = getattr(image, "n_frames", 1)
        if frames > budget.max_pages:
            _warn(result, f"画像は {frames} ページ中 {budget.max_pages} ページまで処理します。残りは未読です。")
        for i in range(min(frames, budget.max_pages)):
            budget.check()
            image.seek(i)
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise _Limit(f"{locator}: 画像サイズの上限を超えています。縮小して再登録してください。")
            _ocr_image(ImageOps.exif_transpose(image), result, budget, f"{locator} {i + 1}" if frames > 1 else locator)


def _pdf(path: Path, result: Extraction, budget: _Budget):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            unlocked = reader.decrypt("")
        except Exception:
            unlocked = False
        if not unlocked:
            result.status = "protected"
            _warn(result, "パスワード保護されたPDFです。保護を解除してから登録してください。")
            return
    total = len(reader.pages)
    result.metadata["page_count"] = total
    if total > budget.max_pages:
        _warn(result, f"PDFは {total} ページ中 {budget.max_pages} ページまで処理します。残りは未読です。")
    rendered = None
    try:
        for number, page in enumerate(reader.pages[:budget.max_pages], 1):
            budget.check()
            locator = f"ページ {number}"
            try:
                text = page.extract_text() or ""
                if text.strip():
                    budget.add(result, locator, text)
                    # テキストがあるページの写真/図は図意を推論しない。画像内文字は表示で区別。
                    resources = page.get("/Resources", {})
                    if hasattr(resources, "get_object"):
                        resources = resources.get_object()
                    if "/XObject" in resources:
                        _warn(result, f"{locator}: 本文の文字を抽出しました。図・画像内の文字や意味は原本でも確認してください。")
                elif not budget.ocr or not tesseract_path():
                    _ocr_image(None, result, budget, locator)
                else:
                    if rendered is None:
                        import pypdfium2
                        rendered = pypdfium2.PdfDocument(str(path))
                    pdf_page = rendered[number - 1]
                    try:
                        width, height = pdf_page.get_size()
                        scale = min(200 / 72, (MAX_IMAGE_PIXELS / max(1, width * height)) ** 0.5)
                        if scale < 200 / 72:
                            _warn(result, f"{locator}: OCR画像を画素数の上限に合わせて縮小しました。小さい文字は原本で確認してください。")
                        bitmap = pdf_page.render(scale=scale)
                        try:
                            pil_image = bitmap.to_pil()
                            pil_image.info["dpi"] = (scale * 72, scale * 72)
                            _ocr_image(pil_image, result, budget, locator)
                            pil_image.close()
                        finally:
                            bitmap.close()
                    finally:
                        pdf_page.close()
            except _Limit:
                raise
            except Exception as exc:
                _warn(result, f"{locator}: 読み取りに失敗しました（{type(exc).__name__}）。このページは未読です。")
                budget.add(result, locator, "", "error")
    finally:
        if rendered is not None:
            rendered.close()


def _safe_info(info: zipfile.ZipInfo, budget: _Budget):
    name = info.filename.replace("\\", "/")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", name) or "\x00" in name:
        raise ValueError("安全でない格納パス")
    if stat.S_ISLNK(info.external_attr >> 16):
        raise ValueError("シンボリックリンク")
    if info.flag_bits & 1:
        raise ValueError("パスワード保護")
    if info.file_size > MAX_MEMBER_BYTES:
        raise ValueError(f"単一項目が {MAX_MEMBER_BYTES // 1024 // 1024} MB を超過")
    if info.file_size / max(1, info.compress_size) > MAX_COMPRESSION_RATIO:
        raise ValueError("展開率の上限超過")
    budget.check()


def _read_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, budget: _Budget) -> bytes:
    _safe_info(info, budget)
    if budget.entry_count >= MAX_ARCHIVE_ENTRIES:
        raise _Limit(f"展開項目数が上限 {MAX_ARCHIVE_ENTRIES:,} 件に達しました。残りは未読です。")
    if budget.expanded_bytes + info.file_size > MAX_ARCHIVE_BYTES:
        raise _Limit("ZIP・Officeの累計展開容量が上限 512 MB に達しました。残りは未読です。")
    budget.entry_count += 1
    budget.expanded_bytes += info.file_size
    with zf.open(info) as src:
        data = src.read(MAX_MEMBER_BYTES + 1)
    if len(data) > MAX_MEMBER_BYTES:
        raise _Limit("ZIP項目が展開容量の上限を超えました。")
    return data


def _xml(zf: zipfile.ZipFile, name: str, budget: _Budget):
    return ET.fromstring(_read_member(zf, zf.getinfo(name), budget))


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _paragraph_text(element) -> str:
    parts = []
    for node in element.iter():
        tag = _local(node.tag)
        if tag == "t":
            parts.append(node.text or "")
        elif tag == "tab":
            parts.append("\t")
        elif tag in {"br", "cr"}:
            parts.append("\n")
    return "".join(parts)


def _office(path: Path, result: Extraction, budget: _Budget, depth: int):
    with zipfile.ZipFile(path) as zf:
        if len(zf.infolist()) > MAX_ARCHIVE_ENTRIES:
            raise _Limit(f"Office内部の項目数が上限 {MAX_ARCHIVE_ENTRIES:,} 件を超えています。資料を分割してください。")
        # openpyxlも同じZIP上限を満たした文書だけ受け取る。
        for info in zf.infolist():
            _safe_info(info, budget)
        if sum(i.file_size for i in zf.infolist()) > MAX_ARCHIVE_BYTES:
            raise _Limit("Officeの展開容量が上限 512 MB を超えています。")
        if path.suffix.lower() in {".docx", ".docm"}:
            _word(zf, result, budget)
        elif path.suffix.lower() in {".xlsx", ".xlsm"}:
            _excel(path, result, budget)
        else:
            _powerpoint(zf, result, budget)
        if any("vbaproject" in n.lower() for n in zf.namelist()):
            result.metadata["macros_present"] = True
            _warn(result, "マクロを含む資料です。マクロは実行せず本文のみ読み取っています。")
        _office_assets(zf, result, budget, depth)


def _word(zf: zipfile.ZipFile, result: Extraction, budget: _Budget):
    names = ["word/document.xml"]
    names += sorted(n for n in zf.namelist() if re.fullmatch(r"word/(header\d+|footer\d+|footnotes|endnotes)\.xml", n))
    for name in names:
        root = _xml(zf, name, budget)
        title = "本文" if name == "word/document.xml" else PurePosixPath(name).stem
        body = next((n for n in root if _local(n.tag) == "body"), root)
        paragraph = table = 0
        for node in body:
            budget.check()
            tag = _local(node.tag)
            if tag == "p":
                paragraph += 1
                text = _paragraph_text(node)
                if text:
                    budget.add(result, f"{title} 段落 {paragraph}", text)
            elif tag == "tbl":
                table += 1
                rows = []
                for row in node:
                    if _local(row.tag) == "tr":
                        rows.append("\t".join(_paragraph_text(cell) for cell in row if _local(cell.tag) == "tc"))
                budget.add(result, f"{title} 表 {table}", "\n".join(rows))
            elif tag in {"footnote", "endnote", "sdt", "customXml"}:
                paragraph += 1
                text = "\n".join(_paragraph_text(p) for p in node.iter() if _local(p.tag) == "p")
                if text:
                    budget.add(result, f"{title} 補足 {paragraph}", text)
    result.metadata["word_pagination"] = "Wordのレイアウト計算は行わず、段落・表番号で出典を示します。"


def _excel(path: Path, result: Extraction, budget: _Budget):
    import openpyxl
    from openpyxl.utils import get_column_letter
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=False, keep_links=False)
    try:
        result.metadata["sheet_count"] = len(workbook.sheetnames)
        if len(workbook.sheetnames) > budget.max_pages:
            _warn(result, f"シート上限 {budget.max_pages} 件を超えたシートは未読です。")
        formula = False
        for sheet in workbook.worksheets[:budget.max_pages]:
            budget.check()
            max_row = sheet.max_row or 100_000
            max_col = sheet.max_column or 256
            if max_row > 100_000 or max_col > 256:
                _warn(result, f"シート「{sheet.title}」: 100,000 行・256 列を超える範囲は未読です。")
            for number, cells in enumerate(sheet.iter_rows(max_row=min(max_row, 100_000), max_col=min(max_col, 256)), 1):
                budget.check()
                pieces = []
                for index, cell in enumerate(cells, 1):
                    if cell.value is not None:
                        formula = formula or cell.data_type == "f"
                        pieces.append(f"{get_column_letter(index)}{number}: {cell.value}")
                if pieces:
                    budget.add(result, f"シート「{sheet.title}」 行 {number}", "\t".join(pieces))
        if formula:
            _warn(result, "数式セルは計算式を抽出しています。計算は実行しません。表示結果はExcel原本で確認してください。")
    finally:
        workbook.close()


def _natural_key(name: str):
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def _powerpoint(zf: zipfile.ZipFile, result: Extraction, budget: _Budget):
    slides = sorted((n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=_natural_key)
    # presentation.xmlの実際の表示順を優先し、ファイル名順に依存しない。
    if "ppt/presentation.xml" in zf.namelist() and "ppt/_rels/presentation.xml.rels" in zf.namelist():
        relationships = _xml(zf, "ppt/_rels/presentation.xml.rels", budget)
        targets = {n.get("Id"): "ppt/" + n.get("Target", "").lstrip("/") for n in relationships}
        actual = []
        for node in _xml(zf, "ppt/presentation.xml", budget).iter():
            if _local(node.tag) == "sldId":
                rid = next((v for k, v in node.attrib.items() if k.endswith("}id")), None)
                target = targets.get(rid, "")
                if target.startswith("ppt/ppt/"):
                    target = target[4:]
                if target in slides:
                    actual.append(target)
        if actual:
            slides = actual
    result.metadata["slide_count"] = len(slides)
    if len(slides) > budget.max_pages:
        _warn(result, f"スライドは {len(slides)} 枚中 {budget.max_pages} 枚まで読み取り、残りは未読です。")
    for number, name in enumerate(slides[:budget.max_pages], 1):
        root = _xml(zf, name, budget)
        tables = [node for node in root.iter() if _local(node.tag) == "tbl"]
        table_paragraphs = {id(p) for table in tables for p in table.iter() if _local(p.tag) == "p"}
        paragraphs = [_paragraph_text(p) for p in root.iter() if _local(p.tag) == "p" and id(p) not in table_paragraphs]
        budget.add(result, f"スライド {number}", "\n".join(p for p in paragraphs if p))
        for table_number, table in enumerate(tables, 1):
            rows = ["\t".join(_paragraph_text(cell) for cell in row if _local(cell.tag) == "tc")
                    for row in table if _local(row.tag) == "tr"]
            budget.add(result, f"スライド {number} 表 {table_number}", "\n".join(rows))
        rel_name = str(PurePosixPath(name).parent / "_rels" / (PurePosixPath(name).name + ".rels"))
        if rel_name in zf.namelist():
            for relation in _xml(zf, rel_name, budget):
                if relation.get("Type", "").endswith("/notesSlide") and relation.get("TargetMode") != "External":
                    import posixpath
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(name), relation.get("Target", "")))
                    if target.startswith("/"):
                        target = target.lstrip("/")
                    if target in zf.namelist():
                        note = _xml(zf, target, budget)
                        # スライド番号プレースホルダを除いたノート本文を抽出。
                        texts = []
                        for shape in note.iter():
                            if _local(shape.tag) == "sp":
                                if any(_local(n.tag) == "ph" and n.get("type") in {"sldNum", "dt", "ftr", "hdr"} for n in shape.iter()):
                                    continue
                                texts.extend(_paragraph_text(p) for p in shape.iter() if _local(p.tag) == "p")
                        if any(texts):
                            budget.add(result, f"スライド {number} ノート", "\n".join(texts))


def _merge_child(result: Extraction, child: Extraction, locator: str):
    for unit in child.units:
        result.units.append({**unit, "locator": f"{locator} / {unit['locator']}"})
    for warning in child.warnings:
        _warn(result, f"{locator}: {warning}")
    if child.status not in {"ok", "empty"} and not child.warnings:
        _warn(result, f"{locator}: 読み取り状態 {child.status}")


def _guess_office_suffix(data: bytes) -> str | None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as embedded:
            names = set(embedded.namelist())
            if "word/document.xml" in names:
                return ".docx"
            if "xl/workbook.xml" in names:
                return ".xlsx"
            if "ppt/presentation.xml" in names:
                return ".pptx"
    except zipfile.BadZipFile:
        pass
    return None


def _office_assets(zf: zipfile.ZipFile, result: Extraction, budget: _Budget, depth: int):
    images = embedded = 0
    with tempfile.TemporaryDirectory(prefix="contextgen-kai-office-") as tmp:
        for index, info in enumerate(zf.infolist()):
            name = info.filename.replace("\\", "/")
            if info.is_dir() or ("/media/" not in name and "/embeddings/" not in name):
                continue
            budget.check()
            locator = f"埋め込み {name}"
            try:
                data = _read_member(zf, info, budget)
                suffix = PurePosixPath(name).suffix.lower()
                if "/media/" in name:
                    images += 1
                    if suffix not in IMAGE_EXTENSIONS:
                        _warn(result, f"{locator}: この画像形式のOCRは未対応です。原本を確認してください。")
                        continue
                else:
                    embedded += 1
                    if suffix == ".bin":
                        suffix = _guess_office_suffix(data) or suffix
                    if suffix not in SUPPORTED_EXTENSIONS:
                        _warn(result, f"{locator}: 旧OLE形式などのため抽出できません。元の資料をOffice新形式で保存して別途登録してください。")
                        continue
                # 元ZIP内のパスは使わず、管理下の一時ファイル名だけを利用。
                local = Path(tmp) / f"asset-{index}{suffix}"
                local.write_bytes(data)
                child = _extract(local, budget, depth + 1)
                _merge_child(result, child, locator)
            except _Limit:
                raise
            except Exception as exc:
                _warn(result, f"{locator}: 読み取れませんでした（{type(exc).__name__}）。")
    result.metadata["embedded_images"] = images
    result.metadata["embedded_documents"] = embedded


def _archive(path: Path, result: Extraction, budget: _Budget, depth: int):
    with zipfile.ZipFile(path) as zf, tempfile.TemporaryDirectory(prefix="contextgen-kai-zip-") as tmp:
        result.metadata["archive_entries"] = len(zf.infolist())
        if len(zf.infolist()) > MAX_ARCHIVE_ENTRIES:
            _warn(result, f"ZIPの項目数上限 {MAX_ARCHIVE_ENTRIES:,} 件を超えた部分は未読です。")
        for index, info in enumerate(zf.infolist()[:MAX_ARCHIVE_ENTRIES]):
            budget.check()
            if info.is_dir():
                continue
            locator = f"ZIP内 {info.filename}"
            try:
                _safe_info(info, budget)
                suffix = PurePosixPath(info.filename.replace("\\", "/")).suffix.lower()
                if suffix not in SUPPORTED_EXTENSIONS:
                    _warn(result, f"{locator}: 非対応形式のため未読です。")
                    continue
                if suffix == ".zip" and depth >= MAX_DEPTH:
                    _warn(result, f"{locator}: 入れ子の上限 {MAX_DEPTH} 階層を超えたため未読です。")
                    continue
                data = _read_member(zf, info, budget)
                local = Path(tmp) / f"entry-{index}{suffix}"
                local.write_bytes(data)
                child = _extract(local, budget, depth + 1)
                _merge_child(result, child, locator)
            except _Limit:
                raise
            except ValueError as exc:
                _warn(result, f"{locator}: {exc}のため読み取りを省略しました。")
            except Exception as exc:
                _warn(result, f"{locator}: 読み取りに失敗しました（{type(exc).__name__}）。")
