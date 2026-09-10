"""参照元フォルダの走査.

restored 版 backup_worker のスキャン部を移植。
改善②: skip_temp_files で Office ロックファイル (~$) や OS メタファイルを除外。
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .config import EXCLUDE_DIRS, RunConfig, TARGET_EXTENSIONS
from .events import Emitter
from .textutil import format_size

TEMP_FILE_PREFIXES = ('~$', '.~')
TEMP_FILE_NAMES = ('.DS_Store', 'Thumbs.db', 'desktop.ini')

# v2.1 F4: クラウドストレージのプレースホルダ（オンラインオンリー）属性
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x40000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000
CLOUD_ONLY_ATTRIBUTES = (
    FILE_ATTRIBUTE_OFFLINE
    | FILE_ATTRIBUTE_RECALL_ON_OPEN
    | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
)


def is_cloud_only(stat_result) -> bool:
    """Box Drive / OneDrive 等の「クラウドのみ」プレースホルダか。

    Windows の st_file_attributes で判定する（非Windowsでは常に False）。
    """
    attributes = getattr(stat_result, 'st_file_attributes', 0)
    return bool(attributes & CLOUD_ONLY_ATTRIBUTES)


@dataclass
class ScanResult:
    files: list[Path] = field(default_factory=list)
    counters: dict = field(default_factory=dict)
    skipped_temp: list[str] = field(default_factory=list)
    cloud_only_skipped: list[str] = field(default_factory=list)     # skipモードで除外
    cloud_only_downloaded: list[str] = field(default_factory=list)  # warnモードで検知
    stopped: bool = False


def new_counters() -> dict:
    return {
        'scan_checked': 0,
        'target': 0,
        'error': 0,
        'referenced_bytes': 0,
        'ext': {ext: 0 for ext in TARGET_EXTENSIONS},
    }


def is_temp_file(name: str) -> bool:
    if name in TEMP_FILE_NAMES:
        return True
    return any(name.startswith(prefix) for prefix in TEMP_FILE_PREFIXES)


def matched_file(path: Path) -> bool:
    return path.suffix.lower() in TARGET_EXTENSIONS


def push_progress(emitter: Emitter, counters: dict) -> None:
    percent = counters['scan_checked'] % 100
    emitter.emit('progress', {
        'percent': percent,
        'scan_checked': counters['scan_checked'],
        'target': counters['target'],
        'error': counters['error'],
        'referenced_bytes': counters['referenced_bytes'],
        'ext': counters['ext'].copy(),
    })


def scan(config: RunConfig, emitter: Emitter, stop_event: threading.Event) -> ScanResult:
    result = ScanResult(counters=new_counters())
    counters = result.counters

    emitter.log('====================================')
    emitter.log('参照元直接読み取りコンテキスト生成開始')
    emitter.log('収集データへのコピーは行いません')
    emitter.log(f"検索元: {config.search_root}")
    emitter.log(f"AIコンテキスト保存先: {config.context_output_dir}")

    if not config.search_root.exists():
        emitter.log(f"検索元フォルダが存在しません: {config.search_root}")
        result.stopped = True
        return result

    stack = [config.search_root]

    while stack:
        if stop_event.is_set():
            emitter.log('停止要求を受けました')
            result.stopped = True
            break

        current_dir = stack.pop()
        emitter.emit('current_dir', str(current_dir))

        try:
            with os.scandir(current_dir) as entries:
                for entry in entries:
                    if stop_event.is_set():
                        emitter.log('停止要求を受けました')
                        result.stopped = True
                        break

                    counters['scan_checked'] += 1

                    try:
                        if entry.is_dir(follow_symlinks=False):
                            dir_name = Path(entry.path).name
                            if dir_name in EXCLUDE_DIRS:
                                emitter.log(f"除外フォルダスキップ: {entry.path}")
                                continue
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            path = Path(entry.path)

                            if config.skip_temp_files and is_temp_file(path.name):
                                result.skipped_temp.append(str(path))
                                continue

                            if matched_file(path):
                                if config.cloud_only_mode != 'download':
                                    try:
                                        if is_cloud_only(entry.stat(follow_symlinks=False)):
                                            if config.cloud_only_mode == 'skip':
                                                result.cloud_only_skipped.append(str(path))
                                                emitter.log(f"クラウドのみスキップ: {path}")
                                                continue
                                            result.cloud_only_downloaded.append(str(path))
                                    except Exception:
                                        pass

                                counters['target'] += 1
                                try:
                                    counters['referenced_bytes'] += path.stat().st_size
                                except Exception:
                                    pass
                                ext = path.suffix.lower()
                                if ext in counters['ext']:
                                    counters['ext'][ext] += 1
                                result.files.append(path)
                                emitter.emit('current', str(path))
                                emitter.log(f"参照元ファイル発見: {path}")
                                push_progress(emitter, counters)

                        if counters['scan_checked'] % 20 == 0:
                            emitter.emit(
                                'current',
                                f"検索中... 確認:{counters['scan_checked']} / 参照元ファイル:{counters['target']}",
                            )
                            push_progress(emitter, counters)
                    except Exception as e:
                        counters['error'] += 1
                        emitter.log(f"ファイル処理エラー: {entry.path}")
                        emitter.log(str(e))
                        push_progress(emitter, counters)
                        continue
        except Exception as e:
            counters['error'] += 1
            emitter.log(f"フォルダ読込エラー: {current_dir}")
            emitter.log(str(e))
            push_progress(emitter, counters)

    push_progress(emitter, counters)

    emitter.log('====================================')
    emitter.log(f"確認件数: {counters['scan_checked']}")
    emitter.log(f"参照元ファイル数: {counters['target']}")
    emitter.log(f"エラー数: {counters['error']}")
    emitter.log(f"参照元ファイル容量: {format_size(counters['referenced_bytes'])}")
    if result.skipped_temp:
        emitter.log(f"一時ファイルスキップ: {len(result.skipped_temp)} 件")
    if result.cloud_only_skipped:
        emitter.log(f"クラウドのみ（未ダウンロード）スキップ: {len(result.cloud_only_skipped)} 件")
    if result.cloud_only_downloaded:
        emitter.log(f"クラウドのみ検知（ダウンロードが発生します）: {len(result.cloud_only_downloaded)} 件")
    emitter.log('参照元検索処理終了')
    emitter.log('====================================')

    return result
