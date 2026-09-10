"""JSONL → プロファイル別パッケージ変換."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from importlib import resources
from pathlib import Path


@dataclass
class Profile:
    name: str
    display_name: str
    basename: str
    file_extension: str
    max_body_files: int
    target_chars_per_file: int
    include_index: bool = True
    upload_limit_note: str = ''
    retrieval_notes: list[str] = field(default_factory=list)
    how_to_use: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, name: str) -> "Profile":
        path = resources.files('crossai_packager') / 'profiles' / f"{name}.json"
        data = json.loads(path.read_text(encoding='utf-8'))
        return cls(**data)

    @classmethod
    def available(cls) -> list[str]:
        folder = resources.files('crossai_packager') / 'profiles'
        return sorted(p.name.removesuffix('.json') for p in folder.iterdir()
                      if p.name.endswith('.json'))


@dataclass
class PackResult:
    index_path: Path | None
    body_paths: list[Path]
    total_chunks: int
    overflow_chunks: int


def load_records(jsonl_path: Path) -> list[dict]:
    records = []
    with open(jsonl_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def build_section(record: dict) -> str:
    """レコード1件をプラットフォーム中立な Source セクションにする."""
    lines = [
        f"### Source {record['index']}-{record['chunk_index']}",
        '',
        f"FileName: {record['file_name']}",
        f"FileType: {record.get('extension', '')}",
        f"SourcePath: {record['relative_path']}",
        f"Size: {record.get('size_text', '')}",
        f"TextLength: {record.get('text_length', '')}",
        f"Chunk: {record['chunk_index']} / {record['chunk_count']}",
        '',
        'Summary:',
        record.get('summary') or '本文抽出不可。ファイル名・パス・拡張子を参照。',
        '',
        'Text:',
        record.get('text') or '本文抽出不可。ファイル名・パス・拡張子を参照。',
        '',
        '---',
    ]
    return '\n'.join(lines)


def part_header(profile: Profile, source_scope: str, generated_at: str, part_no: int,
                part_count: int, total_files: int, total_chunks: int) -> list[str]:
    return [
        f"# {profile.display_name} Context {part_no:03d}",
        '',
        f"GeneratedAt: {generated_at}",
        f"Profile: {profile.name}",
        f"Part: {part_no:03d} / {part_count:03d}",
        f"SourceScope: {source_scope}",
        'FileRole: body',
        f"SourceFileCount: {total_files}",
        f"SourceChunkCount: {total_chunks}",
        f"TargetCharactersPerFile: {profile.target_chars_per_file}",
        '',
        '## Retrieval Notes',
        *profile.retrieval_notes,
        '',
        '## Content',
        '',
    ]


def pack(records: list[dict], profile: Profile, output_dir: Path,
         source_scope: str = '') -> PackResult:
    """レコード列をプロファイル制約に合わせて output_dir に書き出す."""
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 既存の同プロファイル固定名ファイルを掃除
    for old in output_dir.glob(f"{profile.basename}_*{profile.file_extension}"):
        old.unlink()

    parts: list[list[str]] = [[]]
    sizes = [0]
    packed_entries: list[dict] = []
    overflow = 0

    for record in records:
        section = build_section(record).rstrip() + '\n\n'
        size = len(section)
        current = len(parts) - 1
        if sizes[current] > 0 and sizes[current] + size > profile.target_chars_per_file:
            if len(parts) < profile.max_body_files:
                parts.append([])
                sizes.append(0)
                current += 1
            else:
                overflow += 1
                continue
        parts[current].append(section)
        sizes[current] += size
        packed_entries.append({**record, '_part': current + 1})

    total_files = len({r['relative_path'] for r in records})
    total_chunks = len(records)
    part_count = len(parts)

    body_paths = []
    for part_no, sections in enumerate(parts, start=1):
        path = output_dir / f"{profile.basename}_{part_no:03d}{profile.file_extension}"
        lines = part_header(profile, source_scope, generated_at, part_no, part_count,
                            total_files, total_chunks)
        lines.extend(sections)
        path.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')
        body_paths.append(path)

    index_path = None
    if profile.include_index:
        index_path = output_dir / f"{profile.basename}_INDEX{profile.file_extension}"
        index_lines = [
            f"# {profile.display_name} Context Index",
            '',
            f"GeneratedAt: {generated_at}",
            f"Profile: {profile.name}",
            f"SourceScope: {source_scope}",
            'FileRole: index',
            f"BodyFileCount: {part_count}",
            f"TotalFileCountForUpload: {part_count + 1}",
            f"UploadLimitPolicy: {profile.upload_limit_note}",
            f"SourceChunkCount: {total_chunks}",
            f"OverflowChunkCount: {overflow}",
            '',
            '## How To Use',
            *profile.how_to_use,
            '',
            '## RequiredFiles',
            f"- {index_path.name}",
        ]
        for path in body_paths:
            index_lines.append(f"- {path.name}")

        index_lines.extend(['', '## SourceChunkIndex'])
        for entry in packed_entries:
            index_lines.append(
                f"- Part {entry['_part']:03d} | {entry['file_name']} | Chunk "
                f"{entry['chunk_index']}/{entry['chunk_count']} | {entry['relative_path']}"
            )

        if overflow:
            index_lines.extend([
                '',
                '## OverflowWarning',
                f"- {overflow} chunks were not included due to the {profile.max_body_files}-file limit.",
                '- Narrow the source folder or split into multiple knowledge sets.',
            ])

        index_path.write_text('\n'.join(index_lines).rstrip() + '\n', encoding='utf-8')

    return PackResult(
        index_path=index_path,
        body_paths=body_paths,
        total_chunks=total_chunks,
        overflow_chunks=overflow,
    )
