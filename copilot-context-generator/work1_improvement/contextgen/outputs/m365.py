"""M365 Copilot 投入用固定名 TXT パッケージ.

restored 版の m365_part_header / build_m365_section / append_m365_section /
write_m365_agent_context_files を移植。既定（sequential / chars / enrich なし）
では出力は原本と同一。

改善⑤:
- m365_packing='bestfit' で空きの大きいパートに詰めて余白を削減
- m365_capacity_mode='tokens' で推定トークン基準の容量管理
- index_enriched=True で INDEX にファイル別要約・未収録チャンク・差分を追記
- グループ（サブフォルダ）ごとの複数パッケージ生成
"""
from __future__ import annotations

import re
from pathlib import Path

from ..config import (
    M365_CONTEXT_ARCHIVE_DIR_NAME,
    M365_CONTEXT_BASENAME,
    M365_CONTEXT_MAX_BODY_FILES,
    M365_CONTEXT_TARGET_CHARS_PER_FILE,
    RunConfig,
)
from ..textutil import format_size


def m365_fixed_file_pattern():
    base = re.escape(M365_CONTEXT_BASENAME)
    # 既定: M365AgentContext_001.txt / M365AgentContext_INDEX.txt
    # グループ: M365AgentContext_<group>_001.txt / ..._INDEX.txt
    return re.compile(f"^{base}(?:_.+)?_(INDEX|\\d{{3}})\\.txt$|^{base}_(INDEX|\\d{{3}})\\.txt$")


def cleanup_m365_fixed_files(output_dir: Path, emitter) -> None:
    pattern = m365_fixed_file_pattern()
    for path in output_dir.glob(f"{M365_CONTEXT_BASENAME}_*.txt"):
        if not path.is_file():
            continue
        if not pattern.match(path.name):
            continue
        try:
            path.unlink()
        except Exception as e:
            emitter.log(f"M365固定名ファイル削除エラー: {path}")
            emitter.log(str(e))


def m365_part_header(scope, generated_at, generated_stamp, part_no, part_count, total_files, total_chunks):
    return [
        f"# M365 Agent Context {part_no:03d}",
        '',
        f"GeneratedAt: {generated_at}",
        f"GeneratedStamp: {generated_stamp}",
        f"Part: {part_no:03d} / {part_count:03d}",
        f"SourceScope: {scope}",
        'ContentType: measurement-context',
        'FileRole: body',
        f"SourceFileCount: {total_files}",
        f"SourceChunkCount: {total_chunks}",
        f"TargetCharactersPerFile: {M365_CONTEXT_TARGET_CHARS_PER_FILE}",
        '',
        '## Retrieval Notes',
        '- This file is generated for Microsoft 365 Copilot agent knowledge.',
        '- Use SourcePath, FileName, Page, Sheet, Row, Slide, and Chunk fields when answering.',
        '- Prefer precise source references when the answer depends on a specific file.',
        '',
        '## Content',
        '',
    ]


def build_m365_section(index, chunk_index, chunk_count, path, relative, size, text_length, summary, chunk_text):
    lines = [
        f"### Source {index}-{chunk_index}",
        '',
        f"FileName: {path.name}",
        f"FileType: {path.suffix.lower()}",
        f"SourcePath: {relative}",
        f"Size: {format_size(size)}",
        f"TextLength: {text_length}",
        f"Chunk: {chunk_index} / {chunk_count}",
        '',
        'Summary:',
        summary or '本文抽出不可。ファイル名・パス・拡張子を参照。',
        '',
        'Text:',
        chunk_text or '本文抽出不可。ファイル名・パス・拡張子を参照。',
        '',
        '---',
    ]
    return '\n'.join(lines)


class M365Packer:
    """本文チャンクを最大19パートへ詰める。"""

    def __init__(self, config: RunConfig, basename: str = M365_CONTEXT_BASENAME, scope=None):
        self.config = config
        self.basename = basename
        self.scope = scope if scope is not None else config.search_root
        self.parts: list[list[str]] = [[]]
        self.part_sizes: list[int] = [0]
        self.entries: list[dict] = []
        self.overflow_count = 0
        self.overflow_chars = 0
        self.overflow_entries: list[dict] = []

    def _measure(self, text: str) -> int:
        if self.config.m365_capacity_mode == 'tokens':
            return self.config.estimate_tokens(text)
        return len(text)

    @property
    def _capacity(self) -> int:
        if self.config.m365_capacity_mode == 'tokens':
            return self.config.m365_target_tokens
        return self.config.m365_target_chars

    def append(self, section_text: str, index_entry: dict) -> bool:
        text = section_text.rstrip() + '\n\n'
        size = self._measure(text)

        if self.config.m365_packing == 'bestfit':
            target = self._find_bestfit(size)
        else:
            target = self._find_sequential(size)

        if target is None:
            self.overflow_count += 1
            self.overflow_chars += len(text)
            self.overflow_entries.append(index_entry)
            return False

        index_entry['m365_part'] = target + 1
        self.parts[target].append(text)
        self.part_sizes[target] += size
        self.entries.append(index_entry)
        return True

    def _find_sequential(self, size: int):
        """原本互換: 常に末尾パートへ。あふれたら新パート or オーバーフロー。"""
        current = len(self.parts) - 1
        if self.part_sizes[current] > 0 and self.part_sizes[current] + size > self._capacity:
            if len(self.parts) < M365_CONTEXT_MAX_BODY_FILES:
                self.parts.append([])
                self.part_sizes.append(0)
                current += 1
            else:
                return None
        return current

    def _find_bestfit(self, size: int):
        """改善⑤: 入る中で残り容量が最小のパートに詰める。"""
        best = None
        best_remaining = None
        for i, used in enumerate(self.part_sizes):
            if used > 0 and used + size > self._capacity:
                continue
            remaining = self._capacity - used
            if best_remaining is None or remaining < best_remaining:
                best = i
                best_remaining = remaining
        if best is not None:
            return best
        if len(self.parts) < M365_CONTEXT_MAX_BODY_FILES:
            self.parts.append([])
            self.part_sizes.append(0)
            return len(self.parts) - 1
        return None


def write_m365_package(
    config: RunConfig,
    packer: M365Packer,
    generated_at: str,
    generated_stamp: str,
    emitter,
    extra_index_sections: list[str] | None = None,
):
    """packer の内容を固定名 TXT + Archive + INDEX として書き出す。

    固定名ファイルの削除（cleanup）は呼び出し側で先に行うこと。
    """
    archive_dir = config.context_output_dir / M365_CONTEXT_ARCHIVE_DIR_NAME
    archive_dir.mkdir(parents=True, exist_ok=True)

    m365_parts = packer.parts
    if not m365_parts:
        m365_parts = [['No content was extracted.']]

    m365_entries = packer.entries
    part_count = len(m365_parts)
    fixed_paths = []
    archive_paths = []
    total_files = len({entry['relative_path'] for entry in m365_entries})
    total_chunks = len(m365_entries)

    for part_no, section_texts in enumerate(m365_parts, start=1):
        fixed_path = config.context_output_dir / f"{packer.basename}_{part_no:03d}.txt"
        archive_path = archive_dir / f"{packer.basename}_{generated_stamp}_{part_no:03d}.txt"
        body_lines = m365_part_header(
            packer.scope, generated_at, generated_stamp, part_no, part_count, total_files, total_chunks
        )
        body_lines.extend(section_texts)
        text = '\n'.join(body_lines).rstrip() + '\n'

        fixed_path.write_text(text, encoding='utf-8')
        archive_path.write_text(text, encoding='utf-8')
        fixed_paths.append(fixed_path)
        archive_paths.append(archive_path)

    fixed_index_path = config.context_output_dir / f"{packer.basename}_INDEX.txt"
    archive_index_path = archive_dir / f"{packer.basename}_{generated_stamp}_INDEX.txt"

    index_lines = [
        '# M365 Agent Context Index',
        '',
        f"GeneratedAt: {generated_at}",
        f"GeneratedStamp: {generated_stamp}",
        f"SourceScope: {packer.scope}",
        'ContentType: measurement-context',
        'FileRole: index',
        f"BodyFileCount: {part_count}",
        f"TotalFileCountForUpload: {part_count + 1}",
        f"UploadLimitPolicy: 1 index file + up to {M365_CONTEXT_MAX_BODY_FILES} body files = 20 files",
        f"TargetCharactersPerBodyFile: {M365_CONTEXT_TARGET_CHARS_PER_FILE}",
        f"SourceChunkCount: {total_chunks}",
        f"OverflowChunkCount: {packer.overflow_count}",
        f"OverflowCharacterCount: {packer.overflow_chars}",
        '',
        '## How To Use',
        '- Add this INDEX file and all body files listed in RequiredFiles to the Microsoft 365 Copilot agent knowledge sources.',
        '- Keep the fixed file names unchanged so the agent can continue to reference the same files after regeneration.',
        '- The Archive folder keeps timestamped copies for traceability and normally does not need to be added to the agent.',
        '',
        '## RequiredFiles',
        f"- {fixed_index_path.name}",
    ]

    for path in fixed_paths:
        index_lines.append(f"- {path.name}")

    index_lines.extend([
        '',
        '## BodyFileMap',
    ])

    for part_no, path in enumerate(fixed_paths, start=1):
        entry_count = sum(1 for entry in m365_entries if entry.get('m365_part') == part_no)
        index_lines.append(f"- {path.name}: {entry_count} chunks")

    index_lines.extend([
        '',
        '## SourceChunkIndex',
    ])

    for entry in m365_entries:
        index_lines.append(
            f"- Part {entry['m365_part']:03d} | {entry['file_name']} | Chunk "
            f"{entry['chunk_index']}/{entry['chunk_count']} | {entry['relative_path']}"
        )

    if packer.overflow_count:
        index_lines.extend([
            '',
            '## OverflowWarning',
            f"- {packer.overflow_count} chunks were not included in the fixed 20-file M365 package.",
            '- The full extracted text remains available in _AI_CONTEXT_DATA.jsonl and the timestamped Markdown files.',
            '- Narrow the source folder, split by topic, or create multiple agents if all overflow content is required.',
        ])

    if extra_index_sections:
        index_lines.extend(extra_index_sections)

    index_text = '\n'.join(index_lines).rstrip() + '\n'
    fixed_index_path.write_text(index_text, encoding='utf-8')
    archive_index_path.write_text(index_text, encoding='utf-8')

    for path in [fixed_index_path] + fixed_paths:
        emitter.log(f"M365 Copilot投入用TXT作成: {path}")

    emitter.log(f"M365 Copilot履歴保存先: {archive_dir}")

    return fixed_index_path, fixed_paths, archive_index_path, archive_paths
