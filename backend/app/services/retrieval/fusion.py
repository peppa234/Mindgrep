"""Reciprocal Rank Fusion (Cormack, Clarke & Büttcher, 2009).

Fuses ranked lists using only ranks, never raw scores, so a cosine similarity and a
ts_rank never have to be put on the same scale. k=60 is the value from the paper and the
de-facto default; it damps the advantage of the very top ranks.
"""

from dataclasses import dataclass, field

RRF_K = 60


@dataclass
class Fused:
    chunk_id: int
    score: float
    ranks: dict[str, int] = field(default_factory=dict)  # channel -> 1-based rank


def rrf(ranked_lists: dict[str, list[int]], k: int = RRF_K) -> list[Fused]:
    fused: dict[int, Fused] = {}
    for channel, ids in ranked_lists.items():
        for rank, chunk_id in enumerate(ids, start=1):
            entry = fused.setdefault(chunk_id, Fused(chunk_id, 0.0))
            entry.score += 1.0 / (k + rank)
            entry.ranks[channel] = rank
    # Ties broken by best single rank, then id, so results are deterministic.
    return sorted(fused.values(), key=lambda f: (-f.score, min(f.ranks.values()), f.chunk_id))
