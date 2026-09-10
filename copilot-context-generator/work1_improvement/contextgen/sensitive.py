"""v2.1 F5: 機密情報スキャン.

組み込みパターン（個人番号・電話・メール・カード番号疑い）と、
部署管理の辞書ファイル（管理フォルダ/sensitive_patterns.txt）で
チャンク収録前のテキストを検査する。

辞書ファイルの書式（1行1件）:
    # コメント行
    取引先A株式会社          ← リテラル（そのまま検知）
    regex:極秘|社外秘         ← regex: プレフィックスで正規表現
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import RunConfig

DICTIONARY_FILENAME = 'sensitive_patterns.txt'

MASK_TEXT = '＜伏字＞'

# 順序に意味あり: 長い数字列（カード）を先に判定する
BUILTIN_PATTERNS: list[tuple[str, re.Pattern]] = [
    ('クレジットカード番号疑い', re.compile(
        r'(?<![\d-])\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}(?![\d-])|(?<!\d)\d{15,16}(?!\d)'
    )),
    ('マイナンバー疑い', re.compile(
        r'(?<![\d-])\d{12}(?!\d)|(?<![\d-])\d{4}-\d{4}-\d{4}(?!-?\d)'
    )),
    ('電話番号', re.compile(
        r'(?<![\d-])0\d{1,4}-\d{1,4}-\d{4}(?![\d-])'
    )),
    ('メールアドレス', re.compile(
        r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
    )),
]


def load_dictionary(path: Path) -> list[tuple[str, re.Pattern]]:
    patterns: list[tuple[str, re.Pattern]] = []
    if not path.is_file():
        return patterns
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        try:
            if line.startswith('regex:'):
                patterns.append(('辞書', re.compile(line[len('regex:'):])))
            else:
                patterns.append(('辞書', re.compile(re.escape(line))))
        except re.error:
            continue
    return patterns


@dataclass
class SensitiveScanner:
    config: RunConfig
    patterns: list[tuple[str, re.Pattern]] = field(default_factory=list)

    def __post_init__(self):
        self.patterns = list(BUILTIN_PATTERNS)
        self.patterns += load_dictionary(self.config.base_dir / DICTIONARY_FILENAME)

    def scan(self, text: str) -> dict[str, int]:
        """{種類: 件数} を返す。検知した値そのものは保持しない."""
        findings: dict[str, int] = {}
        if not text:
            return findings
        for kind, pattern in self.patterns:
            count = sum(1 for _ in pattern.finditer(text))
            if count:
                findings[kind] = findings.get(kind, 0) + count
        return findings

    def mask(self, text: str) -> tuple[str, dict[str, int]]:
        """検知箇所を伏字に置換したテキストと {種類: 件数} を返す."""
        findings: dict[str, int] = {}
        if not text:
            return text, findings
        for kind, pattern in self.patterns:
            text, count = pattern.subn(MASK_TEXT, text)
            if count:
                findings[kind] = findings.get(kind, 0) + count
        return text, findings


def merge_findings(total: dict[str, int], found: dict[str, int]) -> None:
    for kind, count in found.items():
        total[kind] = total.get(kind, 0) + count
