"""スキャン + コンテキスト生成の一括実行（restored 版 backup_worker 相当）."""
from __future__ import annotations

import threading

from .config import RunConfig
from .events import Emitter
from .pipeline import PipelineStats, build_ai_context
from .scanner import scan


def run_all(config: RunConfig, emitter: Emitter, stop_event: threading.Event) -> PipelineStats | None:
    """検索元を走査してコンテキスト一式を生成する。

    戻り値: PipelineStats（検索元が存在しない/停止時は None の場合あり）。
    'finish' イベントを必ず emit する。
    """
    stop_event.clear()
    stats = None
    try:
        scan_result = scan(config, emitter, stop_event)

        if not config.search_root.exists():
            emitter.emit('finish', None)
            return None

        if not stop_event.is_set():
            emitter.log(f"コンテキスト生成対象数: {len(scan_result.files)}")
            stats = build_ai_context(
                config,
                emitter,
                stop_event,
                source_files=scan_result.files,
                skipped_temp=scan_result.skipped_temp,
                cloud_only_skipped=scan_result.cloud_only_skipped,
                cloud_only_downloaded=scan_result.cloud_only_downloaded,
            )

        if config.teams_webhook_url and stats is not None:
            from .notify import notify_run_result
            notify_run_result(config, stats, emitter)

        emitter.emit('finish', None)
        return stats
    except Exception as e:
        emitter.log(f"致命的エラー: {e}")
        emitter.emit('finish', None)
        return stats
