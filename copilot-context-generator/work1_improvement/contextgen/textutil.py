"""テキスト整形・要約・チャンク分割.

legacy 系関数は復元版と同一挙動（パリティテストで担保）。
semantic 系は改善③: 構造マーカー優先の分割 + オーバーラップ。
"""
from __future__ import annotations

import re

from .config import MAX_SUMMARY_CHARS, MAX_TEXT_CHARS_PER_CONTEXT_RECORD

# 抽出器が本文に埋め込む構造マーカー（# Page / # Sheet: / # Slide / ## Notes 等）
HEADING_RE = re.compile(r'^#{1,4} ')


def format_size(size):
    if size >= 1073741824:
        return f"{size / 1073741824:.2f} GB"
    if size >= 1048576:
        return f"{size / 1048576:.2f} MB"
    if size >= 1024:
        return f"{size / 1024:.2f} KB"
    return f"{size} B"


def clean_filename(name):
    return re.sub(r'[\\/:*?"<>|]', '_', name)


def is_same_or_child(path, parent):
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def normalize_text(text):
    text = text.replace('\r', '\n')
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def simple_summary(text):
    """レガシー要約: 先頭20行 / 1200文字."""
    text = normalize_text(text)
    if not text:
        return '本文抽出不可。ファイル名・パス・拡張子を参照。'
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    head = '\n'.join(lines[:20])
    if len(head) > MAX_SUMMARY_CHARS:
        head = head[:MAX_SUMMARY_CHARS] + '...'
    return head


def heading_summary(text, max_chars=MAX_SUMMARY_CHARS):
    """改善③要約: 見出し一覧 + 先頭段落。見出しがなければレガシーへフォールバック."""
    text = normalize_text(text)
    if not text:
        return '本文抽出不可。ファイル名・パス・拡張子を参照。'
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    headings = [line for line in lines if HEADING_RE.match(line)]

    lead: list[str] = []
    for line in lines:
        if HEADING_RE.match(line):
            continue
        lead.append(line)
        if len(lead) >= 8 or len('\n'.join(lead)) > 400:
            break

    parts = []
    if headings:
        items = [h.lstrip('#').strip() for h in headings[:30]]
        parts.append('見出し: ' + ' / '.join(items))
    if lead:
        parts.append('\n'.join(lead))
    head = '\n'.join(parts) if parts else '\n'.join(lines[:20])
    if len(head) > max_chars:
        head = head[:max_chars] + '...'
    return head


def split_text_for_context(text, max_chars=MAX_TEXT_CHARS_PER_CONTEXT_RECORD):
    """レガシー分割: 行単位・文字数ベース（復元版と同一）."""
    text = normalize_text(text)
    if not text:
        return ['']

    chunks = []
    current = []
    current_len = 0

    for line in text.splitlines():
        line_len = len(line) + 1

        if line_len > max_chars:
            if current:
                chunks.append('\n'.join(current))
                current = []
                current_len = 0
            for start in range(0, len(line), max_chars):
                chunks.append(line[start:start + max_chars])
            continue

        if current and current_len + line_len > max_chars:
            chunks.append('\n'.join(current))
            current = []
            current_len = 0

        current.append(line)
        current_len += line_len

    if current:
        chunks.append('\n'.join(current))

    return chunks or ['']


def _line_tail(text, n):
    """末尾 n 文字を行境界に丸めて返す（オーバーラップ用）."""
    if n <= 0 or not text:
        return ''
    tail = text[-n:]
    pos = tail.find('\n')
    if pos != -1:
        tail = tail[pos + 1:]
    return tail.strip('\n')


def split_text_semantic(text, max_chars=MAX_TEXT_CHARS_PER_CONTEXT_RECORD, overlap_ratio=0.12):
    """改善③分割: 構造マーカー（# Page / # Sheet: / # Slide / ##...）を境界として
    優先し、チャンク間に overlap_ratio ぶんの重なりを持たせる。

    マーカーがない本文は空行（段落）単位で詰める。1セクションが max_chars を
    超える場合のみレガシー分割にフォールバックする。
    """
    text = normalize_text(text)
    if not text:
        return ['']

    overlap = max(0, int(max_chars * overlap_ratio))
    lines = text.splitlines()

    # 見出し行を境界にセクション化
    sections: list[str] = []
    current: list[str] = []
    for line in lines:
        if HEADING_RE.match(line) and current:
            sections.append('\n'.join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append('\n'.join(current))

    # セクションが大きすぎる場合は段落→行の順で分割して max_chars 以下のブロック列に
    blocks: list[str] = []
    for sec in sections:
        if len(sec) <= max_chars:
            blocks.append(sec)
            continue
        for para_group in _split_by_paragraphs(sec, max_chars):
            if len(para_group) <= max_chars:
                blocks.append(para_group)
            else:
                blocks.extend(split_text_for_context(para_group, max_chars))

    # ブロックを詰めてチャンク化。チャンク境界に前チャンク末尾を重ねる。
    chunks: list[str] = []
    cur = ''
    for block in blocks:
        joined_len = len(cur) + (1 if cur else 0) + len(block)
        if cur and joined_len > max_chars:
            chunks.append(cur)
            cur = _line_tail(cur, overlap)
        cur = block if not cur else cur + '\n' + block
        while len(cur) > max_chars:
            chunks.append(cur[:max_chars])
            cur = cur[max_chars:]
    if cur:
        chunks.append(cur)

    return chunks or ['']


def _split_by_paragraphs(text, max_chars):
    """空行区切りの段落を max_chars 以下のグループに詰める."""
    paragraphs = text.split('\n\n')
    groups: list[str] = []
    cur = ''
    for para in paragraphs:
        joined_len = len(cur) + (2 if cur else 0) + len(para)
        if cur and joined_len > max_chars:
            groups.append(cur)
            cur = para
        else:
            cur = para if not cur else cur + '\n\n' + para
    if cur:
        groups.append(cur)
    return groups


def markdown_code_block(text):
    text = text or '本文抽出不可。ファイル名・パス・拡張子を参照。'
    max_backticks = 3
    for match in re.finditer('`+', text):
        max_backticks = max(max_backticks, len(match.group(0)) + 1)
    fence = '`' * max_backticks
    return [f"{fence}text", text, fence]
