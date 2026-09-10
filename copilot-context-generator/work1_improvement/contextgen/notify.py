"""v2.1 F3: Teams Incoming Webhook 通知.

実行結果のサマリを Teams チャネルへ投稿する。標準ライブラリのみ使用。
通知の失敗は本処理を止めない（ログに残すのみ）。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import RunConfig
from .events import Emitter

TIMEOUT_SECONDS = 5


def build_summary_text(config: RunConfig, stats) -> str:
    """PipelineStats から Teams 投稿本文（Markdown）を組み立てる."""
    title = 'コンテキスト生成 完了'
    if getattr(stats, 'dry_run', False):
        title = 'コンテキスト生成 ドライラン結果'
    if getattr(stats, 'stopped', False):
        title = 'コンテキスト生成 停止'

    if not getattr(stats, 'published', True):
        title = 'コンテキスト生成 公開見送り（既存ナレッジは維持）'

    lines = [
        f"**{title}**",
        '',
        f"- 参照元: {config.search_root}",
        f"- 対象ファイル: {stats.total_files} / チャンク: {stats.jsonl_records}",
    ]

    if not getattr(stats, 'published', True):
        lines.append(f"- ⚠️ 公開を見送りました: {stats.publish_hold_reason}")
        lines.append('- 公開中のナレッジは前回成功時のまま維持されています')

    if config.use_cache:
        lines.append(f"- キャッシュ: ヒット {stats.cache_hits} / 再抽出 {stats.cache_misses}")

    errors = stats.status_counts.get('error', 0)
    needs_ocr = stats.status_counts.get('needs_ocr', 0)
    if errors:
        lines.append(f"- ⚠️ 抽出エラー: {errors} 件（レポート参照）")
    if needs_ocr:
        lines.append(f"- OCR候補: {needs_ocr} 件")

    if stats.overflow_count:
        lines.append(f"- ⚠️ 20ファイル上限あふれ: {stats.overflow_count} チャンク")

    if getattr(stats, 'sensitive_files', 0):
        lines.append(f"- 🔒 機密情報検知: {stats.sensitive_files} ファイル（レポート参照）")

    if stats.upload_needed:
        names = ', '.join(stats.upload_needed[:8])
        more = f" ほか{len(stats.upload_needed) - 8}件" if len(stats.upload_needed) > 8 else ''
        lines.append(f"- 📤 要再アップロード: {len(stats.upload_needed)} 件（{names}{more}）")
    elif not getattr(stats, 'dry_run', False) and getattr(stats, 'published', True):
        # 公開を見送った場合は「最新」ではないため、この行を出してはいけない
        lines.append('- 📤 再アップロード不要（ナレッジは最新）')

    if stats.upload_removed:
        lines.append(f"- 🗑 ナレッジから削除: {', '.join(stats.upload_removed[:8])}")

    return '\n'.join(lines)


def send_teams_notification(webhook_url: str, text: str, emitter: Emitter) -> bool:
    """Incoming Webhook へ投稿する。成功で True。失敗してもログのみで例外は出さない."""
    if not webhook_url:
        return False
    payload = json.dumps({'text': text}).encode('utf-8')
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, 'status', 200)
        if 200 <= status < 300:
            emitter.log('Teams通知を送信しました')
            return True
        emitter.log(f"Teams通知エラー: HTTP {status}")
        return False
    except (urllib.error.URLError, OSError, ValueError) as e:
        emitter.log(f"Teams通知エラー: {e}")
        return False


def notify_run_result(config: RunConfig, stats, emitter: Emitter) -> bool:
    if not config.teams_webhook_url or stats is None:
        return False
    text = build_summary_text(config, stats)
    return send_teams_notification(config.teams_webhook_url, text, emitter)
