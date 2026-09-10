"""v2.1 F1: 再アップロード指示書 (_AI_CONTEXT_UPLOAD.md).

固定名ファイル（INDEX + 本文）の「実質内容ハッシュ」を前回実行と比較し、
どのファイルを M365 Copilot エージェントのナレッジで置き換えるべきかを
明示する。生成時刻だけが変わったファイルは「変更なし」として扱う。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from ..cache import load_package_state, save_package_state
from ..config import RunConfig

UPLOAD_NOTE_FILENAME = '_AI_CONTEXT_UPLOAD.md'

# 実行のたびに必ず変わる行（内容の実質比較から除外する）
VOLATILE_PREFIXES = ('GeneratedAt:', 'GeneratedStamp:', '- 生成日時:')


@dataclass
class UploadNote:
    new: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def upload_needed(self) -> list[str]:
        return self.new + self.changed


def content_hash(path: Path) -> str:
    """生成時刻行と LastDiff セクション（実行履歴メタデータ）を除いた内容の SHA256."""
    lines = []
    in_lastdiff = False
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip() == '## LastDiff':
            in_lastdiff = True
            continue
        if in_lastdiff:
            if line.startswith('## '):
                in_lastdiff = False
            else:
                continue
        if line.startswith(VOLATILE_PREFIXES):
            continue
        lines.append(line)
    return hashlib.sha256('\n'.join(lines).encode('utf-8')).hexdigest()


def write_upload_note(config: RunConfig, fixed_paths: list[Path],
                      generated_at: str, emitter) -> UploadNote:
    current = {path.name: content_hash(path) for path in fixed_paths if path.exists()}
    previous = load_package_state(config.cache_db_path)

    note = UploadNote()
    for name in sorted(current):
        if name not in previous:
            note.new.append(name)
        elif previous[name] != current[name]:
            note.changed.append(name)
        else:
            note.unchanged.append(name)
    note.removed = sorted(set(previous) - set(current))

    lines = [
        '# M365 ナレッジ再アップロード指示書',
        '',
        f"- 生成日時: {generated_at}",
        f"- 固定名ファイル数: {len(current)}",
        '- 生成時刻だけが変わったファイルは「変更なし」として扱っています。',
        '',
        f"## 要再アップロード（{len(note.upload_needed)}件）",
        '',
    ]
    if note.upload_needed:
        lines.append('エージェントのナレッジで以下を置き換え/追加してください。')
        for name in note.changed:
            lines.append(f"- {name} （内容更新）")
        for name in note.new:
            lines.append(f"- {name} （新規）")
    else:
        lines.append('ありません。ナレッジは最新の状態です。')

    lines.extend(['', f"## 変更なし（{len(note.unchanged)}件）— 作業不要", ''])
    for name in note.unchanged:
        lines.append(f"- {name}")

    if note.removed:
        lines.extend(['', f"## 前回から削除（{len(note.removed)}件）— ナレッジからも削除してください", ''])
        for name in note.removed:
            lines.append(f"- {name}")

    note_path = config.context_output_dir / UPLOAD_NOTE_FILENAME
    note_path.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')

    save_package_state(config.cache_db_path, current, generated_at)

    if note.upload_needed:
        emitter.log(f"再アップロード指示書: 要アップロード {len(note.upload_needed)} 件"
                    f"（{', '.join(note.upload_needed[:5])}"
                    f"{' ほか' if len(note.upload_needed) > 5 else ''}） → {note_path.name}")
    else:
        emitter.log(f"再アップロード指示書: 変更なし（アップロード作業は不要） → {note_path.name}")

    return note
