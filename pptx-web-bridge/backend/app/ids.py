"""ID 生成。決定的（同じ入力順なら同じID）にして、試験と差分確認をしやすくする。"""
from __future__ import annotations


class IdFactory:
    def __init__(self, prefix: str = ""):
        self.prefix = prefix
        self.counters: dict[str, int] = {}

    def next(self, kind: str) -> str:
        n = self.counters.get(kind, 0) + 1
        self.counters[kind] = n
        return f"{self.prefix}{kind}{n:03d}"
