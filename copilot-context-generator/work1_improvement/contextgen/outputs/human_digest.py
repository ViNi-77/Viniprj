"""v3 柱2: 人間向け読解キット (_HUMAN_DIGEST/*.md).

「AIに読ませるため」ではなく「人間が読み解くため」の出力。
長大な社内マニュアルに対して、目次・鮮度・重複・参照切れを機械的に示し、
最後に「Copilotに聞くときのコピペ用」を添えることで、
LLM を内蔵せずに LLM 活用へつなぐ。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..config import RunConfig
from ..digest import DocumentDigest, analyze, build_questions
from ..textutil import clean_filename, format_size

DIGEST_DIR_NAME = '_HUMAN_DIGEST'
INDEX_FILENAME = '_HUMAN_DIGEST_INDEX.md'

# 「読みにくさ」の目安（1文あたりの文字数）
LONG_SENTENCE_THRESHOLD = 55
STALE_YEARS = 3
COPY_BLOCK_LIMIT = 12000


def _readability_label(avg: float) -> str:
    if avg <= 0:
        return '判定不可'
    if avg < 35:
        return f"読みやすい（1文あたり平均{avg:.0f}字）"
    if avg < LONG_SENTENCE_THRESHOLD:
        return f"標準（1文あたり平均{avg:.0f}字）"
    return f"長文傾向（1文あたり平均{avg:.0f}字）"


def _freshness_lines(digest: DocumentDigest, today: datetime) -> list[str]:
    if not digest.date_mentions:
        return ['- 文書内に日付の記述が見つかりませんでした']

    lines = [f"- 文書内の日付記述: {' / '.join(digest.date_mentions[:5])}"]
    if digest.newest_year:
        age = today.year - digest.newest_year
        if age >= STALE_YEARS:
            lines.append(f"- ⚠ 最も新しい記述が {digest.newest_year} 年（約{age}年前）。内容が古い可能性があります")
        else:
            lines.append(f"- 最も新しい記述: {digest.newest_year} 年")
    return lines


def render_digest(path: Path, relative: str, text: str, size: int,
                  extract_status: str, coverage: float | None,
                  today: datetime | None = None) -> tuple[str, DocumentDigest]:
    """1文書分の読解キット Markdown を組み立てる."""
    today = today or datetime.now()
    digest = analyze(text)

    lines = [
        f"# {path.name} 読み解きキット",
        '',
        f"- 元ファイル: `{relative}`",
        '',
        '## 30秒でわかる',
        '',
        f"- 種別: {path.suffix.lower() or '不明'} / {format_size(size)} / 約{digest.char_count:,}文字",
        f"- 構成: 見出し {len(digest.headings)} 個",
        f"- 読みにくさ: {_readability_label(digest.avg_sentence_length)}",
    ]
    if coverage is not None and coverage < 1.0:
        lines.append(f"- ⚠ 抽出カバレッジ: {coverage:.0%}（一部が読み取れていません）")
    if extract_status not in ('ok', 'partial'):
        lines.append(f"- 抽出ステータス: {extract_status}")
    lines.extend(_freshness_lines(digest, today))

    # ---- 目次 ----
    lines.extend(['', '## 目次（自動抽出）', ''])
    if digest.headings:
        for heading in digest.headings[:80]:
            indent = '  ' * max(0, heading.level - 1)
            lines.append(f"{indent}- {heading.title}")
        if len(digest.headings) > 80:
            lines.append(f"- …ほか {len(digest.headings) - 80} 個の見出し")
    else:
        lines.append('見出しを検出できませんでした（章番号も見出しスタイルも無い文書の可能性）。')

    # ---- 想定質問 ----
    questions = build_questions(digest)
    if questions:
        lines.extend(['', '## この文書が答えられそうな質問', ''])
        for question, source in questions:
            lines.append(f"- {question} → 「{source}」")

    # ---- 気になる点 ----
    findings: list[str] = []
    if digest.broken_references:
        for label in digest.broken_references[:10]:
            findings.append(f"- ⚠ 「{label}」を参照しているが、{label} が本文中に見当たりません")
    if digest.duplicate_paragraphs:
        for line_text, count in digest.duplicate_paragraphs[:5]:
            excerpt = line_text[:40] + ('…' if len(line_text) > 40 else '')
            findings.append(f"- ⚠ 同じ記述が {count} 箇所に重複: 「{excerpt}」")
    if digest.avg_sentence_length >= LONG_SENTENCE_THRESHOLD:
        findings.append('- 1文が長めです。要点を箇条書きにすると読みやすくなります')

    if findings:
        lines.extend(['', '## 気になる点', ''])
        lines.extend(findings)

    # ---- Copilot へのコピペ用 ----
    body = text.strip()
    truncated = len(body) > COPY_BLOCK_LIMIT
    if truncated:
        body = body[:COPY_BLOCK_LIMIT]
    lines.extend([
        '',
        '## Copilotに聞くときのコピペ用',
        '',
        '以下をコピーして Copilot に貼り付けると、この文書について質問できます。',
    ])
    if truncated:
        lines.append(f"（長いため先頭 {COPY_BLOCK_LIMIT:,} 文字のみ。全文は元ファイルを参照）")
    lines.extend(['', '````text', body, '````'])

    return '\n'.join(lines).rstrip() + '\n', digest


def write_document_digest(output_dir: Path, path: Path, relative: str, text: str,
                          size: int, extract_status: str,
                          coverage: float | None) -> tuple[Path, DocumentDigest]:
    digest_dir = output_dir / DIGEST_DIR_NAME
    digest_dir.mkdir(parents=True, exist_ok=True)

    content, digest = render_digest(path, relative, text, size, extract_status, coverage)
    safe_name = clean_filename(Path(relative).with_suffix('').name) or path.stem
    digest_path = digest_dir / f"{safe_name}.md"

    # 同名ファイルが別フォルダにある場合に上書きしない
    counter = 2
    while digest_path.exists():
        digest_path = digest_dir / f"{safe_name}_{counter}.md"
        counter += 1

    digest_path.write_text(content, encoding='utf-8')
    return digest_path, digest


def write_digest_index(output_dir: Path, entries: list[dict], generated_at: str) -> Path:
    """フォルダ全体の読解キット一覧（どれから読むべきかの入口）."""
    lines = [
        '# 読み解きキット一覧',
        '',
        f"- 生成日時: {generated_at}",
        f"- 対象文書: {len(entries)} 件",
        '',
        '長い文書を人間が読み解くための要約です。AI用のナレッジとは別物です。',
        '',
        '## 文書一覧',
        '',
        '| 文書 | 見出し数 | 文字数 | 文書内の最新記述 | 気になる点 |',
        '|---|---|---|---|---|',
    ]

    for entry in sorted(entries, key=lambda e: e['relative']):
        findings = []
        if entry['broken_references']:
            findings.append(f"参照切れ{entry['broken_references']}件")
        if entry['duplicates']:
            findings.append(f"重複{entry['duplicates']}件")
        if entry['stale']:
            findings.append('古い可能性')
        year = entry['newest_year'] or '—'
        lines.append(
            f"| [{entry['relative']}]({DIGEST_DIR_NAME}/{entry['digest_name']}) "
            f"| {entry['headings']} | {entry['chars']:,} | {year} "
            f"| {'／'.join(findings) if findings else '—'} |"
        )

    index_path = output_dir / INDEX_FILENAME
    index_path.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')
    return index_path


def summarize_entry(relative: str, digest_path: Path, digest: DocumentDigest,
                    today: datetime | None = None) -> dict:
    today = today or datetime.now()
    stale = bool(digest.newest_year and (today.year - digest.newest_year) >= STALE_YEARS)
    return {
        'relative': relative,
        'digest_name': digest_path.name,
        'headings': len(digest.headings),
        'chars': digest.char_count,
        'newest_year': digest.newest_year,
        'stale': stale,
        'broken_references': len(digest.broken_references),
        'duplicates': len(digest.duplicate_paragraphs),
    }
