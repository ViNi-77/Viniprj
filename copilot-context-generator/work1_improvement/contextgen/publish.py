"""v3 柱0: 原子的公開とサニティチェック.

v2 までは生成物を出力先へ直接書いていたため、以下の事故が起きていた
（いずれも再現確認済み）。

- 実行中に停止すると、既存ナレッジが**部分内容で上書き**される
- 参照元が一時的に空（Box未同期・パス誤り）だと、既存ナレッジが**消える**

v3 では、いったん出力先配下のステージング領域に全生成物を作り、
**完全に成功し、かつ内容が極端に減っていないときだけ**本番の固定名
ファイルへ差し替える。中断・異常・大幅減の場合は既存を温存する。

夜間バッチでは「壊れた新版」より「無事な旧版」の方が常に良い、
という原則に基づく。
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import M365_CONTEXT_ARCHIVE_DIR_NAME, M365_CONTEXT_BASENAME, RunConfig
from .outputs.m365 import m365_fixed_file_pattern

STAGING_PREFIX = '.staging_'

# INDEX ヘッダに書かれている収録チャンク数
_CHUNK_COUNT_RE = re.compile(r'^SourceChunkCount:\s*(\d+)\s*$', re.MULTILINE)


@dataclass
class PublishDecision:
    publish: bool
    reason: str = ''
    previous_chunks: int | None = None
    new_chunks: int = 0


def staging_dir_for(config: RunConfig, generated_stamp: str) -> Path:
    """出力先と同一ファイルシステム上にステージングを作る（os.replace を原子的にするため）."""
    return config.context_output_dir / f"{STAGING_PREFIX}{generated_stamp}"


def published_chunk_count(output_dir: Path) -> int | None:
    """既に公開されているナレッジの収録チャンク数（全グループ合計）.

    公開物が無ければ None（初回実行）。
    """
    if not output_dir.is_dir():
        return None
    total = None
    for index_path in sorted(output_dir.glob(f"{M365_CONTEXT_BASENAME}*_INDEX.txt")):
        try:
            match = _CHUNK_COUNT_RE.search(index_path.read_text(encoding='utf-8'))
        except Exception:
            continue
        if match:
            total = (total or 0) + int(match.group(1))
    return total


def decide(config: RunConfig, new_chunks: int, output_dir: Path,
           stopped: bool, had_source: bool) -> PublishDecision:
    """公開してよいかを判定する."""
    previous = published_chunk_count(output_dir)

    if config.force_publish:
        return PublishDecision(True, '強制公開が指定されています', previous, new_chunks)

    if stopped:
        return PublishDecision(
            False, '実行が中断されたため、既存ナレッジを温存しました', previous, new_chunks
        )

    if not had_source:
        return PublishDecision(
            False,
            '参照元に対象ファイルが1件もありませんでした'
            '（Box未同期・パス誤りの可能性）。既存ナレッジを温存しました',
            previous, new_chunks,
        )

    if previous is None:
        return PublishDecision(True, '初回公開', previous, new_chunks)

    if previous > 0 and new_chunks == 0:
        return PublishDecision(
            False, f'収録チャンクが0件になりました（前回 {previous} 件）。既存ナレッジを温存しました',
            previous, new_chunks,
        )

    if previous > 0:
        ratio = new_chunks / previous
        if ratio < config.publish_min_ratio:
            return PublishDecision(
                False,
                f'収録チャンクが前回の {ratio:.0%}（{previous} → {new_chunks} 件）まで減少しました。'
                f'意図した変更であれば --force-publish で公開できます',
                previous, new_chunks,
            )

    return PublishDecision(True, '', previous, new_chunks)


def _move_into(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.replace(str(src), str(dst))


def publish_staging(staging_dir: Path, output_dir: Path, emitter) -> list[Path]:
    """ステージングの内容を出力先へ反映する。

    - 直下のファイルは os.replace で差し替え（同一FS上なので原子的）
    - 今回生成されなかった古い固定名ファイルは削除（分割構成の変更に追随）
    - Archive は追記（過去世代を消さない）
    """
    published: list[Path] = []
    if not staging_dir.is_dir():
        return published

    staged_files = [p for p in staging_dir.iterdir() if p.is_file()]
    staged_names = {p.name for p in staged_files}

    # 今回生成されなかった固定名ファイルを掃除する
    pattern = m365_fixed_file_pattern()
    for old in output_dir.glob(f"{M365_CONTEXT_BASENAME}_*.txt"):
        if not old.is_file() or old.name in staged_names:
            continue
        if not pattern.match(old.name):
            continue
        try:
            old.unlink()
            emitter.log(f"旧構成の固定名ファイルを削除: {old.name}")
        except Exception as e:
            emitter.log(f"固定名ファイル削除エラー: {old.name} / {e}")

    for src in staged_files:
        dst = output_dir / src.name
        _move_into(src, dst)
        published.append(dst)

    # Archive とその他のサブフォルダは追記的に移す
    for sub in [p for p in staging_dir.iterdir() if p.is_dir()]:
        target_dir = output_dir / sub.name
        target_dir.mkdir(parents=True, exist_ok=True)
        for item in sub.rglob('*'):
            if item.is_file():
                _move_into(item, target_dir / item.relative_to(sub))

    discard_staging(staging_dir)
    return published


def discard_staging(staging_dir: Path) -> None:
    shutil.rmtree(staging_dir, ignore_errors=True)


def cleanup_orphan_staging(output_dir: Path) -> None:
    """異常終了で残った過去のステージングを掃除する."""
    if not output_dir.is_dir():
        return
    for path in output_dir.glob(f"{STAGING_PREFIX}*"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


def archive_dir_of(output_dir: Path) -> Path:
    return output_dir / M365_CONTEXT_ARCHIVE_DIR_NAME


HOLD_NOTICE_FILENAME = '_AI_CONTEXT_HOLD.md'


def write_hold_notice(output_dir: Path, decision: PublishDecision,
                      generated_at: str) -> Path | None:
    """公開を見送ったことを出力フォルダ上で分かるようにする。

    ナレッジ本体には触れず、この通知ファイルだけを置く。
    次回の公開成功時に自動削除される。
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            '# ⚠ 前回の実行では公開を見送りました',
            '',
            f"- 判定日時: {generated_at}",
            f"- 理由: {decision.reason}",
            f"- 今回の収録チャンク数: {decision.new_chunks}",
        ]
        if decision.previous_chunks is not None:
            lines.append(f"- 公開中のナレッジの収録チャンク数: {decision.previous_chunks}")
        lines.extend([
            '',
            '## いま起きていること',
            '',
            '- **公開中のナレッジファイルは、前回成功時のまま維持されています**',
            '  （壊れた新版で上書きされていません）',
            '- Copilot エージェント側での差し替え作業は不要です',
            '',
            '## 確認すること',
            '',
            '1. 参照元フォルダが正しく同期・アクセスできる状態か（Box の同期状態）',
            '2. 参照元のパス指定が正しいか',
            '3. 実行が途中で停止されていないか',
            '',
            'ファイルを大幅に削除したなど、減少が意図したものであれば、',
            '`--force-publish` を付けて実行すると公開できます。',
            '',
            'このファイルは、次回の公開が成功すると自動的に削除されます。',
        ])
        path = output_dir / HOLD_NOTICE_FILENAME
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return path
    except Exception:
        return None


def clear_hold_notice(output_dir: Path) -> None:
    try:
        (output_dir / HOLD_NOTICE_FILENAME).unlink(missing_ok=True)
    except Exception:
        pass
