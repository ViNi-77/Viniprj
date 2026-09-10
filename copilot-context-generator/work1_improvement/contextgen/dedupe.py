"""v2.1 F6: 重複・類似文書検出.

抽出テキストの5文字シングルの bottom-k スケッチで Jaccard 類似度を推定し、
閾値以上のファイルをグループ化する。完全一致は SHA256 で先に判定。
1回の実行内でのみ比較するため、ハッシュは組み込み hash() で足りる。
"""
from __future__ import annotations

import hashlib
import heapq
import re
from dataclasses import dataclass

SHINGLE_SIZE = 5
SKETCH_SIZE = 200

_WS_RE = re.compile(r'\s+')


@dataclass
class DocSignature:
    sha256: str
    sketch: list[int]   # 昇順
    length: int


def make_signature(text: str) -> DocSignature:
    norm = _WS_RE.sub(' ', text).strip().lower()
    sha = hashlib.sha256(norm.encode('utf-8')).hexdigest()
    if len(norm) < SHINGLE_SIZE:
        shingles = {hash(norm)} if norm else set()
    else:
        shingles = {hash(norm[i:i + SHINGLE_SIZE]) for i in range(len(norm) - SHINGLE_SIZE + 1)}
    sketch = sorted(heapq.nsmallest(SKETCH_SIZE, shingles))
    return DocSignature(sha256=sha, sketch=sketch, length=len(norm))


def estimate_jaccard(a: DocSignature, b: DocSignature) -> float:
    if a.sha256 == b.sha256:
        return 1.0
    if not a.sketch or not b.sketch:
        return 0.0
    set_a, set_b = set(a.sketch), set(b.sketch)
    k = min(SKETCH_SIZE, len(set_a | set_b))
    union_smallest = heapq.nsmallest(k, set_a | set_b)
    hits = sum(1 for h in union_smallest if h in set_a and h in set_b)
    return hits / k if k else 0.0


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, i: int, j: int) -> None:
        ri, rj = self.find(i), self.find(j)
        if ri != rj:
            self.parent[rj] = ri


def find_similar_groups(signatures: list[DocSignature], threshold: float) -> list[list[int]]:
    """threshold 以上で類似するインデックスのグループ（サイズ2以上）を返す."""
    n = len(signatures)
    uf = _UnionFind(n)

    for i in range(n):
        for j in range(i + 1, n):
            a, b = signatures[i], signatures[j]
            # 長さ比が閾値未満なら Jaccard も閾値未満（上界）なのでスキップ
            if a.length == 0 or b.length == 0:
                continue
            ratio = min(a.length, b.length) / max(a.length, b.length)
            if ratio < threshold * 0.9:
                continue
            if a.sha256 == b.sha256 or estimate_jaccard(a, b) >= threshold:
                uf.union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)
    return [members for members in groups.values() if len(members) > 1]
