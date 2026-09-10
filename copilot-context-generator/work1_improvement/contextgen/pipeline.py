"""コンテキスト生成パイプライン.

restored 版 build_ai_context の移植 + 改善①②③⑤の統合。
config.legacy() 相当の設定では出力ファイルは原本と同一
（タイムスタンプを除く。tests/test_parity.py で担保）。
"""
from __future__ import annotations

import contextlib
import dataclasses
import json
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from pathlib import Path

from .cache import DiffReport, ExtractCache
from .dedupe import estimate_jaccard, find_similar_groups, make_signature
from .config import (
    M365_CONTEXT_BASENAME,
    M365_CONTEXT_MAX_BODY_FILES,
    RunConfig,
    TARGET_EXTENSIONS,
)
from .events import Emitter, NullEmitter, filename_timestamp, now_text
from .extractors import ExtractorContext, ExtractResult, extract
from .outputs.m365 import M365Packer, build_m365_section, write_m365_package
from .outputs.markdown import MarkdownWriter
from .outputs.report import CoverageReport, FileOutcome, write_coverage_report
from .outputs.health import write_health_report
from .outputs.human_digest import (
    summarize_entry,
    write_digest_index,
    write_document_digest,
)
from .outputs.upload_note import write_upload_note
from .publish import (
    HOLD_NOTICE_FILENAME,
    cleanup_orphan_staging,
    clear_hold_notice,
    decide as decide_publish,
    discard_staging,
    publish_staging,
    staging_dir_for,
    write_hold_notice,
)
from .scanner import is_temp_file
from .sensitive import SensitiveScanner
from .textutil import (
    clean_filename,
    format_size,
    heading_summary,
    markdown_code_block,
    normalize_text,
    simple_summary,
    split_text_for_context,
    split_text_semantic,
)


@dataclass
class PipelineStats:
    total_files: int = 0
    jsonl_records: int = 0
    md_part_paths: list = field(default_factory=list)
    m365_fixed_paths: dict = field(default_factory=dict)   # group -> [paths]
    overflow_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    stopped: bool = False
    # v2.1
    dry_run: bool = False
    estimated_total_tokens: int = 0
    m365_parts_needed: dict = field(default_factory=dict)  # group -> パート数
    status_counts: dict = field(default_factory=dict)      # 抽出ステータス -> 件数
    upload_needed: list = field(default_factory=list)      # 要再アップロードのファイル名
    upload_removed: list = field(default_factory=list)     # ナレッジから削除すべきファイル名
    sensitive_files: int = 0                                # 機密検知のあったファイル数
    sensitive_blocked_chunks: int = 0                       # blockモードで除外したチャンク数
    dedupe_groups: int = 0                                  # 類似文書グループ数
    dedupe_excluded_files: int = 0                          # 重複除外したファイル数
    published: bool = True                                  # v3: 実際に公開したか
    publish_hold_reason: str = ''                           # v3: 見送った理由
    digest_paths: list = field(default_factory=list)        # v3: 人間向け読解キット


def _make_excerpt(config: RunConfig, chunk_text: str) -> str:
    """B6: JSONL の text_excerpt。原本は本文全体の複製でサイズが約2倍だった。"""
    if config.jsonl_full_excerpt:
        return chunk_text
    limit = config.jsonl_excerpt_chars
    if len(chunk_text) <= limit:
        return chunk_text
    return chunk_text[:limit] + '...'


class _NullJsonlWriter:
    """ドライラン用: JSONL 書き込みを捨てる."""

    def write(self, _text: str) -> None:
        pass


def collect_files(config: RunConfig, source_files, emitter: Emitter, stop_event) -> list[Path]:
    files = []
    iterable = source_files if source_files is not None else config.search_root.rglob('*')
    for path in iterable:
        if stop_event.is_set():
            emitter.log('AI用コンテキスト生成を停止しました')
            break
        path = Path(path)
        if not path.is_file():
            continue
        if path.name.startswith('_AI_CONTEXT_'):
            continue
        if path.suffix.lower() not in TARGET_EXTENSIONS:
            continue
        if config.skip_temp_files and is_temp_file(path.name):
            continue
        files.append(path)
    return files


def relative_of(path: Path, config: RunConfig) -> Path:
    try:
        return path.relative_to(config.search_root)
    except Exception:
        return Path(path.name)


def order_files(config: RunConfig, files: list[Path]) -> list[Path]:
    """改善⑤: 収録優先度。既定 (path) は原本と同じ辞書順。"""
    prio = [p.strip('/\\') for p in config.priority_folders if p.strip()]

    def prio_index(path: Path) -> int:
        rel = relative_of(path, config).as_posix()
        for i, folder in enumerate(prio):
            norm = folder.replace('\\', '/')
            if rel == norm or rel.startswith(norm + '/'):
                return i
        return len(prio)

    if config.sort_mode == 'mtime_desc':
        def key(path: Path):
            try:
                mtime = path.stat().st_mtime
            except Exception:
                mtime = 0.0
            return (prio_index(path), -mtime, str(path).lower())
        return sorted(files, key=key)

    if prio:
        return sorted(files, key=lambda p: (prio_index(p), str(p).lower()))
    return sorted(files, key=lambda p: str(p).lower())


def group_of(path: Path, config: RunConfig) -> str:
    """改善⑤: サブフォルダ分割時のグループキー。"""
    if not config.split_by_subfolder:
        return ''
    rel = relative_of(path, config)
    parts = rel.parts
    if len(parts) <= 1:
        return '_root'
    return parts[0]


def make_summary(config: RunConfig, text: str) -> str:
    if config.summary_mode == 'headings':
        return heading_summary(text)
    return simple_summary(text)


def make_chunks(config: RunConfig, text: str) -> list[str]:
    if config.chunk_mode == 'semantic':
        return split_text_semantic(text, config.max_chars_per_record, config.chunk_overlap_ratio)
    return split_text_for_context(text, config.max_chars_per_record)


def _extract_with_timeout(path, ctx):
    """B5: 1ファイルの解析が固まっても実行全体を止めない。

    Python はスレッドを強制終了できないため、タイムアウトしたスレッドは
    バックグラウンドに残る。目的は「夜間バッチが1ファイルで永久に止まる」
    ことの回避であり、完全な中断ではない。
    """
    seconds = getattr(ctx.config, 'extract_timeout_seconds', 0)
    if not seconds:
        return extract(path, ctx)

    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='extract')
    try:
        future = pool.submit(extract, path, ctx)
        try:
            return future.result(timeout=seconds)
        except FutureTimeout:
            return ExtractResult(
                status='error',
                reason=f'解析が {seconds} 秒を超えたため打ち切りました',
            )
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _extract_with_cache(config, path, st, ctx, cache, stats, count_stats=True, refreshed=None):
    """キャッシュ経由の抽出（プリパス・本ループ共通）.

    B4: full_rescan は「前回までのキャッシュを信用しない」意味であり、
    今回の実行で抽出し直したものは再利用してよい。これを区別しないと、
    重複検出のプリパスと本ループで同じファイルを2回抽出していた。
    """
    result = None
    from_cache = False
    already_refreshed = refreshed is not None and path in refreshed
    if cache is not None and (not config.full_rescan or already_refreshed):
        result = cache.get(path, st.st_size, st.st_mtime)
        from_cache = result is not None
    if result is None:
        result = _extract_with_timeout(path, ctx)
        if refreshed is not None:
            refreshed.add(path)
        if cache is not None:
            cache.put(path, st.st_size, st.st_mtime, result)
    if cache is not None and count_stats:
        if from_cache:
            stats.cache_hits += 1
        else:
            stats.cache_misses += 1
    return result, from_cache


def _dedupe_prepass(config, files, ctx, cache, stats, coverage, emitter, refreshed=None):
    """F6: 全ファイルの署名を計算して類似グループを求める。

    戻り値: exclude モード時に除外するファイル {path: 残置path}。
    抽出結果はキャッシュに載るため、本ループの抽出は実質ゼロコスト。
    """
    entries = []  # (path, DocSignature, mtime)
    for path in files:
        if ctx.stopped():
            break
        try:
            st = path.stat()
            result, _ = _extract_with_cache(config, path, st, ctx, cache, stats,
                                            count_stats=cache is not None, refreshed=refreshed)
            text = normalize_text(result.text)
            if not text:
                continue
            entries.append((path, make_signature(text), st.st_mtime))
        except Exception:
            continue

    groups_idx = find_similar_groups([e[1] for e in entries], config.dedupe_threshold)

    excluded: dict[Path, Path] = {}
    report_groups = []
    for members in groups_idx:
        # 更新日時が最新のものを残す（同時刻はパス辞書順）
        ordered = sorted(members, key=lambda i: (entries[i][2], str(entries[i][0]).lower()),
                         reverse=True)
        keep_i = ordered[0]
        keep_path = entries[keep_i][0]
        group_report = []
        for i in ordered:
            path = entries[i][0]
            kept = i == keep_i
            similarity = 1.0 if kept else estimate_jaccard(entries[keep_i][1], entries[i][1])
            group_report.append((relative_of(path, config).as_posix(), kept, similarity))
            if not kept and config.dedupe_mode == 'exclude':
                excluded[path] = keep_path
        report_groups.append(group_report)

    coverage.dedupe_mode = config.dedupe_mode
    coverage.dedupe_groups = report_groups
    stats.dedupe_groups = len(report_groups)
    stats.dedupe_excluded_files = len(excluded)

    if report_groups:
        emitter.log(f"類似文書グループ: {len(report_groups)} 組（モード: {config.dedupe_mode}）")
    if excluded:
        emitter.log(f"重複のため収録から除外: {len(excluded)} ファイル（詳細はレポート参照）")
    return excluded


def build_ai_context(
    config: RunConfig,
    emitter: Emitter,
    stop_event: threading.Event,
    source_files=None,
    skipped_temp: list[str] | None = None,
    cloud_only_skipped: list[str] | None = None,
    cloud_only_downloaded: list[str] | None = None,
) -> PipelineStats:
    config.context_output_dir.mkdir(parents=True, exist_ok=True)
    if config.dry_run:
        emitter.log('AI用コンテキスト生成開始（ドライラン: 見積のみ）')
    else:
        emitter.log('AI用コンテキスト生成開始')

    stats = PipelineStats(dry_run=config.dry_run)
    coverage = CoverageReport(
        skipped_temp=skipped_temp or [],
        cloud_only_skipped=cloud_only_skipped or [],
        cloud_only_downloaded=cloud_only_downloaded or [],
    )

    files = collect_files(config, source_files, emitter, stop_event)
    files = order_files(config, files)
    total = len(files)
    stats.total_files = total

    emitter.log(f"AI用コンテキスト対象ファイル数: {total}")

    generated_at = now_text()
    generated_stamp = filename_timestamp()

    # v3 柱0: 生成物はいったんステージングへ書き、成功時のみ本番へ差し替える。
    # write_config は出力先だけをステージングへ向けた複製（管理フォルダ等は共有）。
    staging_dir = None
    write_config = config
    if not config.dry_run:
        cleanup_orphan_staging(config.context_output_dir)
        staging_dir = staging_dir_for(config, generated_stamp)
        staging_dir.mkdir(parents=True, exist_ok=True)
        write_config = dataclasses.replace(
            config, context_output_dir=staging_dir, final_output_dir=config.context_output_dir
        )

    md = MarkdownWriter(write_config, generated_at, generated_stamp, total)

    packers: dict[str, M365Packer] = {}

    def packer_for(group: str) -> M365Packer:
        if group not in packers:
            if group == '':
                packers[group] = M365Packer(config)
            else:
                basename = f"{M365_CONTEXT_BASENAME}_{clean_filename(group)}"
                scope = config.search_root if group == '_root' else config.search_root / group
                packers[group] = M365Packer(config, basename=basename, scope=scope)
        return packers[group]

    ctx = ExtractorContext(config=config, stop_event=stop_event)

    sens = SensitiveScanner(config) if config.sensitive_scan != 'off' else None
    coverage.sensitive_mode = config.sensitive_scan

    cache_cm = None
    cache = None
    temp_cache_dir = None
    diff = DiffReport()
    if config.use_cache:
        cache_cm = ExtractCache(config.cache_db_path, now_text)
        cache = cache_cm.__enter__()
        if not config.dry_run:
            # ドライランは実行履歴（差分の基準）を進めない
            cache.begin_run()
    elif config.dedupe_mode != 'off':
        # B4: キャッシュ無効でも、重複検出のプリパスと本ループで
        # 同じファイルを2回抽出しないよう、実行中だけ有効な一時キャッシュを使う
        temp_cache_dir = tempfile.TemporaryDirectory(prefix='contextgen_runcache_')
        cache_cm = ExtractCache(Path(temp_cache_dir.name) / 'run.db', now_text)
        cache = cache_cm.__enter__()

    file_summaries: dict[str, dict[str, str]] = {}  # group -> {relative: summary}
    digest_entries: list[dict] = []                 # v3 柱2: 読解キットの一覧

    try:
        dedupe_excluded: dict[Path, Path] = {}
        prepass_counted = False
        refreshed: set[Path] = set()   # B4: 今回すでに抽出し直したファイル
        if config.dedupe_mode != 'off':
            dedupe_excluded = _dedupe_prepass(config, files, ctx, cache, stats, coverage,
                                              emitter, refreshed=refreshed)
            prepass_counted = cache is not None

        inventory: list[tuple[str, int, float]] = []

        if config.dry_run:
            jsonl_cm = contextlib.nullcontext(_NullJsonlWriter())
        else:
            jsonl_cm = open(write_config.context_jsonl_path, 'w', encoding='utf-8')

        with jsonl_cm as jsonl_file:
            for index, path in enumerate(files, start=1):
                if stop_event.is_set():
                    stats.stopped = True
                    break

                try:
                    emitter.emit('current', f"AIコンテキスト生成中... {index}/{total} {path.name}")

                    st = path.stat()
                    size = st.st_size
                    mtime = st.st_mtime

                    if cache is not None:
                        inventory.append((str(path), size, mtime))

                    # F6: 重複除外（exclude モード）
                    if path in dedupe_excluded:
                        kept = relative_of(dedupe_excluded[path], config)
                        coverage.add(FileOutcome(
                            relative_path=relative_of(path, config).as_posix(),
                            extension=path.suffix.lower(),
                            size=size,
                            status='dedupe_excluded',
                            reason=f"「{kept}」と重複/類似のため除外",
                        ))
                        continue

                    result, from_cache = _extract_with_cache(
                        config, path, st, ctx, cache, stats,
                        count_stats=not prepass_counted, refreshed=refreshed,
                    )

                    text = normalize_text(result.text)
                    # v2.1.1 F3: OSネイティブの区切り文字ではなく常に "/" で
                    # 表記する（Windows実機での往復検証で判明: レポート・
                    # JSONL・M365パッケージがOS依存でぶれると原本互換の
                    # 前提が崩れる）
                    relative = relative_of(path, config).as_posix()
                    group = group_of(path, config)

                    # v2.1 F5: 機密情報スキャン（mask は要約・チャンクの前に適用）
                    if sens is not None:
                        if config.sensitive_scan == 'mask':
                            text, sensitive_hits = sens.mask(text)
                        else:
                            sensitive_hits = sens.scan(text)
                        if sensitive_hits:
                            coverage.sensitive_findings.append((relative, sensitive_hits))

                    summary = make_summary(config, text)
                    if sens is not None and config.sensitive_scan == 'block':
                        summary, _ = sens.mask(summary)

                    coverage.add(FileOutcome(
                        relative_path=relative,
                        extension=path.suffix.lower(),
                        size=size,
                        status=result.status,
                        reason=result.reason,
                        text_length=len(text),
                        token_estimate=config.estimate_tokens(text),
                        from_cache=from_cache,
                        ocr_used=bool(result.meta.get('ocr')),
                        units_total=result.units_total,
                        units_ok=result.units_ok,
                        unit_failures=list(result.unit_failures),
                        mtime=mtime,
                    ))
                    file_summaries.setdefault(group, {})[relative] = summary

                    # v3 柱2: 人間向け読解キット（機密マスク後の本文を使う）
                    if config.human_digest and not config.dry_run and text:
                        try:
                            digest_path, digest = write_document_digest(
                                write_config.context_output_dir, path, relative, text,
                                size, result.status, result.coverage,
                            )
                            digest_entries.append(summarize_entry(relative, digest_path, digest))
                        except Exception as e:
                            emitter.log(f"読解キット生成エラー: {relative} / {e}")

                    chunks = make_chunks(config, text)
                    chunk_count = len(chunks)
                    stats.estimated_total_tokens += sum(config.estimate_tokens(c) for c in chunks)

                    for chunk_index, chunk_text in enumerate(chunks, start=1):
                        if sens is not None and config.sensitive_scan == 'block':
                            if sens.scan(chunk_text):
                                coverage.sensitive_blocked_chunks += 1
                                continue

                        stats.jsonl_records += 1

                        record = {
                            'index': index,
                            'chunk_index': chunk_index,
                            'chunk_count': chunk_count,
                            'file_name': path.name,
                            'relative_path': relative,
                            'extension': path.suffix.lower(),
                            'size_bytes': size,
                            'size_text': format_size(size),
                            'summary': summary,
                            'text_length': len(text),
                            'text_excerpt': _make_excerpt(config, chunk_text),
                            'text': chunk_text,
                        }
                        if config.index_enriched:
                            record['token_estimate'] = config.estimate_tokens(chunk_text)
                            record['extract_status'] = result.status

                        jsonl_file.write(json.dumps(record, ensure_ascii=False) + '\n')

                        if not config.dry_run:
                            section_title = f"### {index}. {path.name}"
                            if chunk_count > 1:
                                section_title = f"### {index}-{chunk_index}. {path.name}"

                            section_lines = [
                                section_title,
                                '',
                                f"- パス: `{relative}`",  # relative は既に .as_posix() 済み
                                f"- 種別: `{path.suffix.lower()}`",
                                f"- サイズ: {format_size(size)}",
                                f"- 抽出文字数: {len(text)}",
                                f"- 本文分割: {chunk_index}/{chunk_count}",
                                '',
                                '#### 要約 / 抜粋',
                                '',
                                summary,
                                '',
                                '#### 抽出本文',
                                '',
                            ]
                            section_lines.extend(markdown_code_block(chunk_text))
                            section_lines.extend(['', '---', ''])
                            md.append_section(section_lines)

                        m365_section = build_m365_section(
                            index,
                            chunk_index,
                            chunk_count,
                            path,
                            relative,
                            size,
                            len(text),
                            summary,
                            chunk_text,
                        )
                        packer_for(group).append(m365_section, {
                            'index': index,
                            'chunk_index': chunk_index,
                            'chunk_count': chunk_count,
                            'file_name': path.name,
                            'relative_path': relative,
                        })

                    if index % 20 == 0:
                        emitter.log(f"AIコンテキスト生成中: {index}/{total}")
                except Exception as e:
                    emitter.log(f"AIコンテキスト生成エラー: {path}")
                    emitter.log(str(e))
                    coverage.add(FileOutcome(
                        relative_path=relative_of(path, config).as_posix(),
                        extension=path.suffix.lower(),
                        size=0,
                        status='error',
                        reason=str(e),
                    ))

        if cache is not None and config.use_cache and not config.dry_run:
            cache.record_inventory(inventory)
            diff = cache.diff_from_previous()
            cache.cleanup()
            coverage.cache_hits = stats.cache_hits
            coverage.cache_misses = stats.cache_misses
            coverage.diff_lines = diff.summary_lines()
    finally:
        if cache_cm is not None:
            cache_cm.__exit__(None, None, None)
        if temp_cache_dir is not None:
            temp_cache_dir.cleanup()

    if not packers:
        packer_for('' if not config.split_by_subfolder else '_root')

    for group, packer in sorted(packers.items()):
        stats.m365_parts_needed[group] = len(packer.parts)
        stats.overflow_count += packer.overflow_count

    for outcome in coverage.outcomes:
        stats.status_counts[outcome.status] = stats.status_counts.get(outcome.status, 0) + 1

    stats.sensitive_files = len(coverage.sensitive_findings)
    stats.sensitive_blocked_chunks = coverage.sensitive_blocked_chunks
    if coverage.sensitive_findings:
        emitter.log(f"機密情報検知: {stats.sensitive_files} ファイル"
                    f"（モード: {config.sensitive_scan}。詳細はレポート参照）")

    if config.dry_run:
        _log_dry_run_summary(config, stats, emitter)
        return stats

    stats.md_part_paths = md.finish()

    excluded_by_group: dict[str, list[tuple[str, str]]] = {}
    for excluded_path, kept_path in dedupe_excluded.items():
        excluded_by_group.setdefault(group_of(excluded_path, config), []).append(
            (relative_of(excluded_path, config).as_posix(), relative_of(kept_path, config).as_posix())
        )

    for group, packer in sorted(packers.items()):
        extra_sections: list[str] = []
        if config.index_enriched:
            extra_sections.extend(_enriched_sections(
                packer, file_summaries.get(group, {}),
                diff if config.use_cache else None,
                excluded_by_group.get(group, []),
            ))
        # ステージングへの書き出しログは伏せ、公開後に実パスで記録する
        index_path, fixed_paths, _, _ = write_m365_package(
            write_config, packer, generated_at, generated_stamp, NullEmitter(),
            extra_index_sections=extra_sections or None,
        )
        stats.m365_fixed_paths[group] = [index_path] + fixed_paths

    if config.human_digest and digest_entries:
        write_digest_index(write_config.context_output_dir, digest_entries, generated_at)
        stats.digest_paths = [e['digest_name'] for e in digest_entries]

    if config.write_health:
        write_health_report(write_config, coverage, stats, generated_at)

    if config.write_report:
        write_coverage_report(write_config, coverage, generated_at)

    # ---- v3 柱0: 公開判定（壊れた新版より無事な旧版を優先する）----
    decision = decide_publish(
        config, stats.jsonl_records, config.context_output_dir,
        stopped=stats.stopped, had_source=total > 0,
    )
    stats.published = decision.publish
    stats.publish_hold_reason = '' if decision.publish else decision.reason

    if not decision.publish:
        discard_staging(staging_dir)
        write_hold_notice(config.context_output_dir, decision, generated_at)
        emitter.log('====================================')
        emitter.log(f"公開を見送りました: {decision.reason}")
        emitter.log('公開中のナレッジは前回成功時のまま維持されています（上書きしていません）')
        emitter.log(f"詳細: {config.context_output_dir / HOLD_NOTICE_FILENAME}")
        emitter.log('====================================')
        return stats

    publish_staging(staging_dir, config.context_output_dir, emitter)
    clear_hold_notice(config.context_output_dir)

    # ステージング上のパスを、公開後の実パスへ読み替える
    stats.m365_fixed_paths = {
        group: [config.context_output_dir / p.name for p in paths]
        for group, paths in stats.m365_fixed_paths.items()
    }
    stats.md_part_paths = [config.context_output_dir / p.name for p in stats.md_part_paths]

    for paths in stats.m365_fixed_paths.values():
        for path in paths:
            emitter.log(f"M365 Copilot投入用TXT作成: {path}")

    if config.write_upload_note:
        all_fixed = [p for paths in stats.m365_fixed_paths.values() for p in paths]
        note = write_upload_note(config, all_fixed, generated_at, emitter)
        stats.upload_needed = note.upload_needed
        stats.upload_removed = note.removed

    if stats.digest_paths:
        emitter.log(f"人間向け読解キット作成: {len(stats.digest_paths)} 件"
                    f" → {config.context_output_dir / '_HUMAN_DIGEST'}")

    for part_path in stats.md_part_paths:
        emitter.log(f"AI用Markdown作成: {part_path}")

    emitter.log(f"AI用Markdown一覧作成: {config.context_md_path}")
    emitter.log(f"AI用JSONL作成: {config.context_jsonl_path}")
    emitter.log(f"AI用JSONLレコード数: {stats.jsonl_records}")
    if stats.overflow_count:
        emitter.log(f"M365 Copilot投入用TXTの20ファイル上限により未収録チャンク数: {stats.overflow_count}")

    if config.use_cache:
        emitter.log(f"抽出キャッシュ: ヒット {stats.cache_hits} / 再抽出 {stats.cache_misses}")
        if diff.has_previous:
            emitter.log(f"前回実行との差分: 追加 {len(diff.added)} / 変更 {len(diff.changed)} / 削除 {len(diff.removed)}")

    if config.write_report:
        emitter.log(f"抽出レポート作成: {config.report_path}")

    emitter.log('AI用コンテキスト生成完了')
    return stats


def _log_dry_run_summary(config: RunConfig, stats: PipelineStats, emitter: Emitter) -> None:
    """F2: ドライランの見積サマリ."""
    emitter.log('----- ドライラン見積 -----')
    emitter.log(f"対象ファイル: {stats.total_files} / チャンク: {stats.jsonl_records}"
                f" / 推定トークン合計: {stats.estimated_total_tokens:,}")
    for group, parts in sorted(stats.m365_parts_needed.items()):
        label = f"[{group}] " if group else ''
        emitter.log(f"{label}M365パッケージ予測: 本文 {parts} ファイル + INDEX"
                    f"（本文上限 {M365_CONTEXT_MAX_BODY_FILES}）")
    if stats.overflow_count:
        emitter.log(f"予測あふれチャンク数: {stats.overflow_count}"
                    "（--sort mtime_desc / --priority-folder / --split-by-subfolder を検討）")
    else:
        emitter.log('20ファイル上限に収まる見込みです')
    if stats.status_counts:
        summary = ' / '.join(f"{k}: {v}" for k, v in sorted(stats.status_counts.items()))
        emitter.log(f"抽出ステータス内訳: {summary}")
    if config.use_cache:
        emitter.log(f"抽出キャッシュ: ヒット {stats.cache_hits} / 再抽出 {stats.cache_misses}"
                    "（今回の抽出結果はキャッシュに保存済み。本実行は高速です）")
    emitter.log('ドライラン完了（ファイルは書き込んでいません）')


def _one_line(text: str, limit: int = 160) -> str:
    flat = ' / '.join(part for part in text.splitlines() if part.strip())
    if len(flat) > limit:
        flat = flat[:limit] + '...'
    return flat


def _enriched_sections(packer: M365Packer, summaries: dict[str, str], diff: DiffReport | None,
                       excluded_files: list[tuple[str, str]] | None = None) -> list[str]:
    """改善①⑤ + F6: INDEX への追記セクション."""
    lines: list[str] = []

    if summaries:
        lines.extend(['', '## FileSummaries'])
        for relative, summary in summaries.items():
            lines.append(f"- {relative}: {_one_line(summary)}")

    if excluded_files:
        lines.extend(['', '## ExcludedFiles'])
        lines.append('- 以下は内容が重複/類似するため未収録（残置ファイル側に同内容があります）')
        for excluded, kept in excluded_files:
            lines.append(f"- {excluded} → 残置: {kept}")

    if packer.overflow_entries:
        lines.extend(['', '## ExcludedChunks'])
        lines.append('- 以下のチャンクは 20 ファイル上限のため未収録（全文は _AI_CONTEXT_DATA.jsonl 参照）')
        for entry in packer.overflow_entries:
            lines.append(
                f"- {entry['file_name']} | Chunk {entry['chunk_index']}/{entry['chunk_count']}"
                f" | {entry['relative_path']}"
            )

    if diff is not None:
        lines.extend(['', '## LastDiff'])
        lines.extend(diff.summary_lines())

    return lines
