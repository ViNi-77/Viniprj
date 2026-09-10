"""改善④: CLI / ヘッドレスモード.

使用例:
    python -m contextgen --source <参照元> --output <出力先>
    python -m contextgen --source D:\\docs --output D:\\ctx --full-rescan --capacity tokens

終了コード:
    0 正常終了
    2 引数・フォルダ指定の誤り
    3 実行時エラー / 停止
    4 公開見送り（既存ナレッジを温存した）
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from pathlib import Path

from . import __version__
from .config import RunConfig
from .events import ConsoleEmitter
from .textutil import is_same_or_child
from .worker import run_all


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='contextgen',
        description='フォルダを走査して M365 Copilot エージェント用コンテキストを生成する',
    )
    parser.add_argument('--source', help='参照元フォルダ（--digest-file 指定時は不要）')
    parser.add_argument('--output', required=True, help='コンテキスト出力先フォルダ')
    parser.add_argument('--base-dir', default=None, help='管理フォルダ（ログ・設定・キャッシュ。既定: 出力先の隣の「管理」）')

    parser.add_argument('--full-rescan', action='store_true', help='キャッシュを無視して全ファイルを再抽出')
    parser.add_argument('--no-cache', action='store_true', help='差分キャッシュを使わない')
    parser.add_argument('--no-report', action='store_true', help='抽出レポートを出力しない')
    parser.add_argument('--dry-run', action='store_true',
                        help='見積のみ（対象数・推定トークン・20ファイルに収まるか予測）。ファイルは書き込まない')
    parser.add_argument('--digest', action='store_true',
                        help='人間向け読解キット（目次・鮮度・重複・参照切れ）を _HUMAN_DIGEST に出力する')
    parser.add_argument('--digest-file', default=None,
                        help='1ファイルだけ読解キットにする（--source の代わりに指定）。'
                             '長いマニュアルを分解して読むための入口')
    parser.add_argument('--force-publish', action='store_true',
                        help='収録量が大幅に減っていても公開する'
                             '（既定では、中断・参照元が空・大幅減の場合は既存ナレッジを温存する）')
    parser.add_argument('--teams-webhook', default=None,
                        help='実行結果を投稿する Teams Incoming Webhook URL'
                             '（環境変数 CONTEXTGEN_TEAMS_WEBHOOK でも指定可）')
    parser.add_argument('--cloud-only', choices=['download', 'skip', 'warn'], default='download',
                        help='Box Drive等のオンラインオンリーファイルの扱い'
                             '（download=従来どおり取得 / skip=抽出しない / warn=取得するが件数を報告）')
    parser.add_argument('--sensitive', choices=['off', 'warn', 'mask', 'block'], default='warn',
                        help='機密情報スキャン（warn=検知のみ / mask=伏字化 / block=該当チャンク除外）')
    parser.add_argument('--dedupe', choices=['off', 'warn', 'exclude'], default='warn',
                        help='重複・類似文書の検出（warn=レポートのみ / exclude=最新版以外を収録除外）')
    parser.add_argument('--dedupe-threshold', type=float, default=0.90,
                        help='類似と判定する閾値（既定 0.90）')
    parser.add_argument('--ocr', choices=['off', 'auto'], default='off',
                        help='テキスト層のないPDFへのOCR実行（要 extras: pip install -e ".[ocr-windows]" 等）')
    parser.add_argument('--ocr-max-pages', type=int, default=30,
                        help='1つのPDFにOCRする最大ページ数（既定 30）')

    parser.add_argument('--chunk-mode', choices=['semantic', 'legacy'], default='semantic',
                        help='チャンク分割方式（既定: semantic）')
    parser.add_argument('--summary-mode', choices=['headings', 'legacy'], default='headings',
                        help='要約方式（既定: headings）')
    parser.add_argument('--capacity', choices=['chars', 'tokens'], default='chars',
                        help='M365ファイル容量の基準（既定: chars=30,000文字）')
    parser.add_argument('--packing', choices=['sequential', 'bestfit'], default='sequential',
                        help='M365ファイルへの詰め込み方式')
    parser.add_argument('--sort', choices=['path', 'mtime_desc'], default='path',
                        help='収録順（mtime_desc: 更新の新しい順に収録し上限あふれに強くする）')
    parser.add_argument('--priority-folder', action='append', default=[],
                        help='優先的に収録するサブフォルダ（相対パス、複数指定可）')
    parser.add_argument('--split-by-subfolder', action='store_true',
                        help='トップレベルのサブフォルダごとに別の20ファイルパッケージを生成')

    parser.add_argument('--legacy', action='store_true',
                        help='従来版(exe)と同一の出力を生成（改善機能をすべて無効化）')
    parser.add_argument('--verbose', action='store_true', help='処理中ファイルも表示')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    return parser


def config_from_args(args) -> RunConfig:
    config = RunConfig(
        search_root=Path(args.source).expanduser(),
        context_output_dir=Path(args.output).expanduser(),
        base_dir=Path(args.base_dir).expanduser() if args.base_dir else None,
        use_cache=not args.no_cache,
        full_rescan=args.full_rescan,
        write_report=not args.no_report,
        dry_run=args.dry_run,
        force_publish=args.force_publish,
        human_digest=args.digest or bool(args.digest_file),
        teams_webhook_url=(args.teams_webhook
                           if args.teams_webhook is not None
                           else os.environ.get('CONTEXTGEN_TEAMS_WEBHOOK', '')),
        cloud_only_mode=args.cloud_only,
        sensitive_scan=args.sensitive,
        dedupe_mode=args.dedupe,
        dedupe_threshold=args.dedupe_threshold,
        ocr_mode=args.ocr,
        ocr_max_pages=args.ocr_max_pages,
        chunk_mode=args.chunk_mode,
        summary_mode=args.summary_mode,
        m365_capacity_mode=args.capacity,
        m365_packing=args.packing,
        sort_mode=args.sort,
        priority_folders=list(args.priority_folder),
        split_by_subfolder=args.split_by_subfolder,
    )
    if args.legacy:
        config = config.legacy()
    return config


def run_single_file_digest(args) -> int:
    """v3 柱2: 1ファイルだけ読解キットにする。

    長いマニュアルを「まず1つ分解してみる」ための最短経路。
    参照元フォルダの指定もキャッシュも要らない。
    """
    import threading as _threading

    from .extractors import ExtractorContext, extract as extract_file
    from .outputs.human_digest import DIGEST_DIR_NAME, write_document_digest
    from .textutil import normalize_text

    target = Path(args.digest_file).expanduser()
    if not target.is_file():
        print(f"エラー: ファイルが見つかりません: {target}", file=sys.stderr)
        return 2

    output_dir = Path(args.output).expanduser()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"エラー: 出力先を作成できません: {e}", file=sys.stderr)
        return 2

    config = RunConfig(search_root=target.parent, context_output_dir=output_dir,
                       base_dir=Path(args.base_dir).expanduser() if args.base_dir else None,
                       human_digest=True)
    ctx = ExtractorContext(config=config, stop_event=_threading.Event())

    print(f"読み解き中: {target.name}")
    result = extract_file(target, ctx)
    text = normalize_text(result.text)

    if not text:
        print(f"本文を抽出できませんでした（{result.status}: {result.reason}）", file=sys.stderr)
        return 3

    digest_path, digest = write_document_digest(
        output_dir, target, target.name, text,
        target.stat().st_size, result.status, result.coverage,
    )

    print(f"読み解きキットを作成しました: {digest_path}")
    print(f"  見出し {len(digest.headings)} 個 / 約{digest.char_count:,}文字")
    if digest.newest_year:
        print(f"  文書内の最新記述: {digest.newest_year} 年")
    if digest.broken_references:
        print(f"  ⚠ 参照切れ: {', '.join(digest.broken_references[:5])}")
    if digest.duplicate_paragraphs:
        print(f"  ⚠ 重複記述: {len(digest.duplicate_paragraphs)} 箇所")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    # 1ファイルだけ読み解くモード（参照元フォルダは不要）
    if args.digest_file:
        return run_single_file_digest(args)

    if not args.source:
        print('エラー: --source を指定してください（1ファイルだけなら --digest-file）',
              file=sys.stderr)
        return 2

    config = config_from_args(args)

    if not config.search_root.is_dir():
        print(f"エラー: 参照元フォルダが存在しません: {config.search_root}", file=sys.stderr)
        return 2

    try:
        config.context_output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"エラー: コンテキスト出力先を作成できません: {e}", file=sys.stderr)
        return 2

    for blocked in (config.context_output_dir, config.base_dir):
        if is_same_or_child(config.search_root, blocked):
            print(f"エラー: コンテキスト出力先・管理フォルダは参照元に指定できません: {blocked}",
                  file=sys.stderr)
            return 2

    stop_event = threading.Event()

    def handle_sigint(signum, frame):
        print('\n停止要求を受け付けました。現在の処理が終わり次第終了します...', file=sys.stderr)
        stop_event.set()

    signal.signal(signal.SIGINT, handle_sigint)

    emitter = ConsoleEmitter(log_path=config.log_path, verbose=args.verbose)
    stats = run_all(config, emitter, stop_event)

    if stats is None or stop_event.is_set():
        return 3
    if not stats.published:
        # 異常ではないが人の確認が要る状態。タスクスケジューラ上で区別できるようにする
        print(f"公開を見送りました: {stats.publish_hold_reason}", file=sys.stderr)
        return 4
    return 0


if __name__ == '__main__':  # pragma: no cover
    sys.exit(main())
