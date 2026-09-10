"""crossai-packager CLI.

使用例:
    # 生成済み JSONL から Claude Projects 用パッケージを作る
    crossai-packager --jsonl 生成コンテキスト/_AI_CONTEXT_DATA.jsonl \
        --output ./claude_pkg --profile claude-projects

    # フォルダから一括生成（contextgen で抽出 → パッケージ）
    crossai-packager --source ~/Documents/家の書類 --output ./claude_pkg \
        --profile claude-projects
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import threading
from pathlib import Path

from .packager import PackResult, Profile, load_records, pack


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='crossai-packager',
        description='AIサービス別のナレッジアップロード用パッケージを生成する',
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument('--jsonl', help='contextgen が生成した _AI_CONTEXT_DATA.jsonl')
    src.add_argument('--source', help='参照元フォルダ（contextgen で抽出から実行）')
    parser.add_argument('--output', required=True, help='パッケージ出力先フォルダ')
    parser.add_argument('--profile', required=True, choices=Profile.available(),
                        help='出力プロファイル')
    parser.add_argument('--scope-label', default='', help='INDEX に記載する生成元の説明')
    return parser


def generate_jsonl_from_source(source: Path, workdir: Path) -> Path:
    from contextgen.config import RunConfig
    from contextgen.events import ConsoleEmitter
    from contextgen.worker import run_all

    config = RunConfig(
        search_root=source,
        context_output_dir=workdir / 'generated',
        base_dir=workdir / 'base',
    )
    emitter = ConsoleEmitter(log_path=None)
    run_all(config, emitter, threading.Event())
    return config.context_jsonl_path


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    profile = Profile.load(args.profile)
    output_dir = Path(args.output).expanduser()

    if args.jsonl:
        jsonl_path = Path(args.jsonl).expanduser()
        if not jsonl_path.is_file():
            print(f"エラー: JSONL が見つかりません: {jsonl_path}", file=sys.stderr)
            return 2
        scope = args.scope_label or str(jsonl_path)
        records = load_records(jsonl_path)
        result = pack(records, profile, output_dir, source_scope=scope)
    else:
        source = Path(args.source).expanduser()
        if not source.is_dir():
            print(f"エラー: 参照元フォルダが存在しません: {source}", file=sys.stderr)
            return 2
        with tempfile.TemporaryDirectory(prefix='crossai_') as tmp:
            jsonl_path = generate_jsonl_from_source(source, Path(tmp))
            records = load_records(jsonl_path)
        scope = args.scope_label or str(source)
        result = pack(records, profile, output_dir, source_scope=scope)

    _print_result(profile, result, output_dir)
    return 0


def _print_result(profile: Profile, result: PackResult, output_dir: Path) -> None:
    print(f"プロファイル: {profile.display_name}")
    print(f"出力先: {output_dir}")
    upload_count = len(result.body_paths) + (1 if result.index_path else 0)
    print(f"アップロード対象: {upload_count} ファイル（本文 {len(result.body_paths)} + INDEX）")
    print(f"収録チャンク: {result.total_chunks - result.overflow_chunks} / {result.total_chunks}")
    if result.overflow_chunks:
        print(f"警告: {result.overflow_chunks} チャンクが上限あふれで未収録です")
    if result.index_path:
        print(f"INDEX: {result.index_path.name}")


if __name__ == '__main__':  # pragma: no cover
    sys.exit(main())
