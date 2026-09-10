"""folder-context MCP サーバ.

Claude Desktop / Claude Code などの MCP クライアントから、指定フォルダの
Office文書・PDF・ZIP を「その場で」検索・抽出できるようにする。
事前の静的パッケージ生成が不要になり、20ファイル上限からも解放される。

起動:
    FOLDER_CONTEXT_ROOT=/path/to/docs folder-context-mcp
    または folder-context-mcp --root /path/to/docs

Claude Code への登録例:
    claude mcp add folder-context -- folder-context-mcp --root ~/Documents/資料
"""
from __future__ import annotations

import hashlib
import os
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from contextgen.cache import ExtractCache
from contextgen.config import EXCLUDE_DIRS, RunConfig, TARGET_EXTENSIONS
from contextgen.events import now_text
from contextgen.extractors import ExtractorContext, ExtractResult, extract
from contextgen.scanner import is_temp_file
from contextgen.textutil import format_size, heading_summary, normalize_text

mcp = FastMCP('folder-context')

_root: Path | None = None
_stop = threading.Event()


def get_root() -> Path:
    global _root
    if _root is None:
        env = os.environ.get('FOLDER_CONTEXT_ROOT', '')
        if not env:
            raise RuntimeError('FOLDER_CONTEXT_ROOT が設定されていません（--root でも指定可）')
        _root = Path(env).expanduser().resolve()
    if not _root.is_dir():
        raise RuntimeError(f"ルートフォルダが存在しません: {_root}")
    return _root


def cache_db_path(root: Path) -> Path:
    digest = hashlib.sha256(str(root).encode('utf-8')).hexdigest()[:16]
    return Path.home() / '.folder-context-mcp' / f"cache_{digest}.db"


def make_ctx(root: Path) -> ExtractorContext:
    config = RunConfig(search_root=root, context_output_dir=root / '_unused_output')
    return ExtractorContext(config=config, stop_event=_stop)


def resolve_safe(root: Path, relative_path: str) -> Path:
    path = (root / relative_path).resolve()
    if not str(path).startswith(str(root)):
        raise ValueError(f"ルートフォルダ外のパスは指定できません: {relative_path}")
    return path


def iter_target_files(root: Path):
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        if path.name.startswith('_AI_CONTEXT_'):
            continue
        if is_temp_file(path.name):
            continue
        if path.suffix.lower() not in TARGET_EXTENSIONS:
            continue
        yield path


def cached_extract(root: Path, path: Path) -> ExtractResult:
    st = path.stat()
    with ExtractCache(cache_db_path(root), now_text) as cache:
        cache.begin_run()
        result = cache.get(path, st.st_size, st.st_mtime)
        if result is None:
            result = extract(path, make_ctx(root))
            cache.put(path, st.st_size, st.st_mtime, result)
        return result


@mcp.tool()
def search_files(query: str = '', extensions: str = '', max_results: int = 100) -> str:
    """フォルダ内の対象ファイル（Word/Excel/PowerPoint/PDF/txt/zip）をファイル名で検索する。

    Args:
        query: ファイル名・パスに含まれる語（空なら全件）。空白区切りで AND 検索。
        extensions: 絞り込む拡張子（例: ".pdf,.xlsx"）。空なら全対象形式。
        max_results: 最大件数。
    """
    root = get_root()
    terms = [t.lower() for t in query.split() if t.strip()]
    exts = {e.strip().lower() for e in extensions.split(',') if e.strip()}

    lines = []
    for path in iter_target_files(root):
        rel = str(path.relative_to(root))
        if terms and not all(t in rel.lower() for t in terms):
            continue
        if exts and path.suffix.lower() not in exts:
            continue
        st = path.stat()
        mtime = datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M')
        lines.append(f"{rel}\t{format_size(st.st_size)}\t更新 {mtime}")
        if len(lines) >= max_results:
            lines.append(f"...（{max_results} 件で打ち切り。query で絞り込んでください）")
            break

    if not lines:
        return '該当するファイルがありません。'
    return '\n'.join(lines)


@mcp.tool()
def read_document(relative_path: str, offset_chars: int = 0, max_chars: int = 20000) -> str:
    """ファイルの本文テキストを抽出して返す（Word/Excel/PowerPoint/PDF/txt/zip 対応）。

    Args:
        relative_path: search_files が返した相対パス。
        offset_chars: この文字位置から返す（長い文書の続きを読む用）。
        max_chars: 返す最大文字数。
    """
    root = get_root()
    path = resolve_safe(root, relative_path)
    if not path.is_file():
        return f"ファイルが見つかりません: {relative_path}"

    result = cached_extract(root, path)
    text = normalize_text(result.text)
    if not text:
        return f"本文を抽出できません（status={result.status}: {result.reason}）"

    total = len(text)
    piece = text[offset_chars:offset_chars + max_chars]
    suffix = ''
    if offset_chars + max_chars < total:
        suffix = (f"\n\n...（{total} 文字中 {offset_chars + max_chars} 文字まで表示。"
                  f"続きは offset_chars={offset_chars + max_chars} で取得）")
    return piece + suffix


@mcp.tool()
def get_summary(relative_path: str) -> str:
    """ファイルの要約（見出し一覧 + 先頭段落）と抽出ステータスを返す。"""
    root = get_root()
    path = resolve_safe(root, relative_path)
    if not path.is_file():
        return f"ファイルが見つかりません: {relative_path}"

    result = cached_extract(root, path)
    st = path.stat()
    header = (f"FileName: {path.name}\nSize: {format_size(st.st_size)}\n"
              f"Status: {result.status}" + (f" ({result.reason})" if result.reason else ''))
    if not result.text:
        return header
    return header + '\n\n' + heading_summary(normalize_text(result.text))


@mcp.tool()
def search_content(query: str, max_results: int = 20) -> str:
    """全対象ファイルの本文からキーワードを含む箇所を探す（初回はフォルダ全体を抽出するため時間がかかる）。

    Args:
        query: 検索語（空白区切りで AND）。
        max_results: 返すヒット箇所の最大数。
    """
    root = get_root()
    terms = [t.lower() for t in query.split() if t.strip()]
    if not terms:
        return '検索語を指定してください。'

    hits = []
    for path in iter_target_files(root):
        result = cached_extract(root, path)
        text = normalize_text(result.text)
        if not text:
            continue
        lower = text.lower()
        if not all(t in lower for t in terms):
            continue
        rel = str(path.relative_to(root))
        pos = lower.find(terms[0])
        start = max(0, pos - 80)
        excerpt = text[start:pos + 160].replace('\n', ' / ')
        hits.append(f"### {rel}\n...{excerpt}...")
        if len(hits) >= max_results:
            break

    if not hits:
        return f"「{query}」を含むファイルはありません。"
    return '\n\n'.join(hits)


@mcp.tool()
def list_recent_changes(days: int = 7, max_results: int = 100) -> str:
    """直近 days 日以内に更新されたファイルの一覧を返す。"""
    root = get_root()
    threshold = datetime.now() - timedelta(days=days)

    entries = []
    for path in iter_target_files(root):
        st = path.stat()
        mtime = datetime.fromtimestamp(st.st_mtime)
        if mtime >= threshold:
            entries.append((mtime, path))

    entries.sort(reverse=True)
    if not entries:
        return f"直近 {days} 日に更新されたファイルはありません。"

    lines = []
    for mtime, path in entries[:max_results]:
        rel = str(path.relative_to(root))
        lines.append(f"{mtime.strftime('%Y-%m-%d %H:%M')}\t{rel}")
    return '\n'.join(lines)


def main():
    global _root
    args = sys.argv[1:]
    if '--root' in args:
        idx = args.index('--root')
        if idx + 1 >= len(args):
            print('エラー: --root にはフォルダパスを指定してください', file=sys.stderr)
            sys.exit(2)
        _root = Path(args[idx + 1]).expanduser().resolve()
    try:
        get_root()
    except RuntimeError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(2)
    mcp.run()


if __name__ == '__main__':  # pragma: no cover
    main()
