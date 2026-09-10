"""v3 柱2: 人間向け読解キットの解析（LLM不要）.

長大な社内マニュアルを「人間が読み解く」ための材料を、機械的に取り出す。
LLM を使わないため API キー不要・データ持ち出しゼロという本ツールの
前提を維持できる。

取り出すもの:
- 目次（Word の見出しスタイル / 抽出器が付けた構造マーカー / 手打ちの章番号）
- 文書内に書かれた日付表現（「2019年4月版」等）→ 鮮度の判断材料
- 同一文書内で繰り返されている段落（コピペで膨らんだ箇所）
- 参照切れ（「別紙2参照」と書いてあるのに別紙2が無い）
- 読みにくさの目安（1文の長さ・見出し密度）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 抽出器が本文に埋め込む構造マーカー（# Page / # Sheet: / # Slide / ## Notes …）
_MARKER_RE = re.compile(r'^(#{1,4})\s+(.*\S)\s*$')

# 手打ちの章番号（Word の見出しスタイルを使わない文書が社内では多い）
# 判定順に意味がある: 階層の深いものから先に試さないと
# 「1.1 適用設備」が「1.」にマッチして番号が壊れる
_NUMBERED_PATTERNS = [
    (re.compile(r'^第\s*([0-9０-９一二三四五六七八九十]+)\s*[章編]\s*(.*)$'), 1),
    (re.compile(r'^第\s*([0-9０-９一二三四五六七八九十]+)\s*節\s*(.*)$'), 2),
    (re.compile(r'^([0-9]+[.．][0-9]+[.．][0-9]+)[.．]?\s*(\S.*)$'), 3),
    (re.compile(r'^([0-9]+[.．][0-9]+)[.．]?\s*(\S.*)$'), 2),
    (re.compile(r'^([0-9]+)[.．]\s*(\S.*)$'), 1),
    (re.compile(r'^[（(]\s*([0-9]+)\s*[）)]\s*(\S.*)$'), 3),
]

# 文書内の日付・版数の記述
_DATE_PATTERNS = [
    re.compile(r'(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?'),
    re.compile(r'(?:令和|平成)\s*[0-9０-９元]{1,2}\s*年\s*\d{1,2}\s*月'),
    re.compile(r'(?:19|20)\d{2}[/-]\d{1,2}(?:[/-]\d{1,2})?'),
    re.compile(r'(?:Rev|Ver|ver|版数)[.．]?\s*[0-9]+(?:\.[0-9]+)?'),
    re.compile(r'第\s*[0-9]+\s*版'),
]
_YEAR_RE = re.compile(r'(19|20)\d{2}')
_WAREKI_RE = re.compile(r'(令和|平成)\s*([0-9０-９元]{1,2})\s*年')

# 「別紙2参照」のような参照表現
_REFERENCE_RE = re.compile(r'(別紙|別表|附属書|付録|様式|参考資料|図|表)\s*([0-9０-９A-Za-z]{1,3})')
_REFERENCE_HINT = ('参照', '参考', 'による', 'のとおり', '別途', '添付')

MIN_DUPLICATE_LENGTH = 30
MAX_HEADING_LENGTH = 60


@dataclass
class Heading:
    level: int
    title: str
    line: int


@dataclass
class DocumentDigest:
    headings: list[Heading] = field(default_factory=list)
    date_mentions: list[str] = field(default_factory=list)
    newest_year: int | None = None
    duplicate_paragraphs: list[tuple[str, int]] = field(default_factory=list)
    broken_references: list[str] = field(default_factory=list)
    avg_sentence_length: float = 0.0
    char_count: int = 0
    line_count: int = 0

    @property
    def has_findings(self) -> bool:
        return bool(self.duplicate_paragraphs or self.broken_references)


def _normalize_digits(value: str) -> str:
    return value.translate(str.maketrans('０１２３４５６７８９', '0123456789'))


def extract_headings(text: str) -> list[Heading]:
    """構造マーカーと手打ちの章番号から目次を組み立てる."""
    headings: list[Heading] = []
    for index, raw in enumerate(text.splitlines()):
        line = raw.strip()
        if not line or len(line) > MAX_HEADING_LENGTH:
            continue

        marker = _MARKER_RE.match(line)
        if marker:
            headings.append(Heading(len(marker.group(1)), marker.group(2), index))
            continue

        # 見出しらしさ: 句点で終わらない・短い
        if line.endswith('。'):
            continue
        for pattern, level in _NUMBERED_PATTERNS:
            matched = pattern.match(line)
            if matched:
                number, title = matched.group(1), matched.group(2).strip()
                if not title:
                    break
                headings.append(Heading(level, f"{_normalize_digits(number)} {title}", index))
                break
    return headings


def extract_date_mentions(text: str) -> tuple[list[str], int | None]:
    """本文中の日付・版数の記述と、そこから読み取れる最も新しい年を返す."""
    mentions: list[str] = []
    years: list[int] = []

    for pattern in _DATE_PATTERNS:
        for matched in pattern.finditer(text):
            value = matched.group(0).strip()
            if value not in mentions:
                mentions.append(value)

    for value in mentions:
        year_match = _YEAR_RE.search(value)
        if year_match:
            years.append(int(year_match.group(0)))
            continue
        wareki = _WAREKI_RE.search(value)
        if wareki:
            era, num = wareki.group(1), _normalize_digits(wareki.group(2))
            num = 1 if num == '元' else int(num)
            years.append((2018 + num) if era == '令和' else (1988 + num))

    return mentions[:20], (max(years) if years else None)


def find_duplicate_paragraphs(text: str) -> list[tuple[str, int]]:
    """同一文書内で繰り返されている段落（コピペで膨らんだ箇所）."""
    counts: dict[str, int] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if len(line) < MIN_DUPLICATE_LENGTH or line.startswith('#'):
            continue
        counts[line] = counts.get(line, 0) + 1

    duplicates = [(line, count) for line, count in counts.items() if count > 1]
    duplicates.sort(key=lambda item: item[1], reverse=True)
    return duplicates[:20]


def find_broken_references(text: str) -> list[str]:
    """「別紙2参照」と書いてあるのに、別紙2が見当たらないものを拾う."""
    referenced: set[str] = set()
    defined: set[str] = set()

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        # 行頭にある場合はその資料の見出し（定義側）とみなす。
        # ただし「別紙2参照のこと」のような参照文は定義ではない
        head = _REFERENCE_RE.match(line)
        if head:
            head_tail = line[head.end():head.end() + 12]
            if not any(hint in head_tail for hint in _REFERENCE_HINT):
                defined.add(f"{head.group(1)}{_normalize_digits(head.group(2))}")

        for matched in _REFERENCE_RE.finditer(line):
            label = f"{matched.group(1)}{_normalize_digits(matched.group(2))}"
            tail = line[matched.end():matched.end() + 12]
            if any(hint in tail for hint in _REFERENCE_HINT):
                referenced.add(label)

    return sorted(referenced - defined)


def average_sentence_length(text: str) -> float:
    body = '\n'.join(line for line in text.splitlines() if not line.startswith('#'))
    sentences = [s.strip() for s in re.split(r'[。\n]', body) if s.strip()]
    if not sentences:
        return 0.0
    return sum(len(s) for s in sentences) / len(sentences)


def analyze(text: str) -> DocumentDigest:
    """1文書分の読解材料をまとめて取り出す."""
    mentions, newest_year = extract_date_mentions(text)
    return DocumentDigest(
        headings=extract_headings(text),
        date_mentions=mentions,
        newest_year=newest_year,
        duplicate_paragraphs=find_duplicate_paragraphs(text),
        broken_references=find_broken_references(text),
        avg_sentence_length=average_sentence_length(text),
        char_count=len(text),
        line_count=len(text.splitlines()),
    )


def build_questions(digest: DocumentDigest, limit: int = 12) -> list[tuple[str, str]]:
    """見出しから「この文書が答えられそうな質問」を組み立てる.

    戻り値: [(質問, 対応する見出し), ...]
    """
    questions: list[tuple[str, str]] = []
    seen: set[str] = set()

    for heading in digest.headings:
        title = heading.title.strip()
        # 抽出器が付ける機械的なマーカーは質問にしても意味がない
        if re.match(r'^(Page|Slide|Sheet:|ZIP|Notes|XML Text|埋め込みオブジェクト)', title):
            continue
        core = re.sub(r'^[0-9.]+\s*', '', title).strip()
        if not core or core in seen or len(core) < 3:
            continue
        seen.add(core)

        if re.search(r'(手順|方法|フロー|作業|進め方)$', core):
            question = f"{core}は？（具体的な手順）"
        elif re.search(r'(基準|条件|範囲|要件|仕様)$', core):
            question = f"{core}はどう決まっている？"
        elif re.search(r'(注意|禁止|リスク|安全)', core):
            question = f"{core}として気をつけることは？"
        else:
            question = f"{core}について教えて"

        questions.append((question, title))
        if len(questions) >= limit:
            break
    return questions
