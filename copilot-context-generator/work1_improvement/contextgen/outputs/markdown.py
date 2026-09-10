"""Markdown 分割ファイル (_AI_CONTEXT_SUMMARY_*.md) と一覧 (_AI_CONTEXT_SUMMARY.md).

restored 版の flush_markdown_part / append_markdown_section /
context_markdown_header / write_latest_markdown_manifest を移植。
"""
from __future__ import annotations

from ..config import MAX_MARKDOWN_CHARS_PER_FILE, RunConfig


def context_markdown_header(config: RunConfig, generated_at, total, part_no):
    return [
        '# AI用コンテキスト要約',
        '',
        f"- 生成日時: {generated_at}",
        f"- 分割番号: {part_no}",
        f"- コンテキスト生成元フォルダ: `{config.search_root}`",
        f"- 生成コンテキスト保存先: `{config.display_output_dir}`",
        f"- 対象ファイル数: {total}",
        f"- 1ファイルあたり最大文字数: {MAX_MARKDOWN_CHARS_PER_FILE}",
        '',
        '## 全体インデックス',
        '',
    ]


class MarkdownWriter:
    def __init__(self, config: RunConfig, generated_at: str, generated_stamp: str, total: int):
        self.config = config
        self.generated_at = generated_at
        self.generated_stamp = generated_stamp
        self.total = total
        self.part_no = 1
        self.part_paths = []
        self.lines = context_markdown_header(config, generated_at, total, self.part_no)
        self.header_line_count = len(self.lines)
        self.char_count = len('\n'.join(self.lines)) + 1

    def flush_part(self):
        part_path = self.config.context_output_dir / (
            f"_AI_CONTEXT_SUMMARY_{self.generated_stamp}_{self.part_no:03d}.md"
        )
        part_path.write_text('\n'.join(self.lines).rstrip() + '\n', encoding='utf-8')
        self.part_paths.append(part_path)

        self.part_no += 1
        self.lines = context_markdown_header(self.config, self.generated_at, self.total, self.part_no)
        self.char_count = len('\n'.join(self.lines)) + 1

    def append_section(self, section_lines):
        section_text = '\n'.join(section_lines) + '\n'

        if self.char_count + len(section_text) > MAX_MARKDOWN_CHARS_PER_FILE and len(self.lines) > self.header_line_count:
            self.flush_part()

        self.lines.extend(section_lines)
        self.lines.append('')
        self.char_count += len(section_text) + 1

    def finish(self):
        if len(self.lines) > self.header_line_count or not self.part_paths:
            self.flush_part()
        self._write_manifest()
        return self.part_paths

    def _write_manifest(self):
        lines = [
            '# AI用コンテキスト要約ファイル一覧',
            '',
            f"- 生成日時: {self.generated_at}",
            f"- 分割ファイル数: {len(self.part_paths)}",
            '',
            '## 分割ファイル',
            '',
        ]
        for path in self.part_paths:
            lines.append(f"- `{path.name}`")
        self.config.context_md_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
