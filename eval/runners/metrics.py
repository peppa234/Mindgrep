"""Retrieval metrics over graded, stable labels.

A label matches a hit by path plus, optionally, a symbol (code name or Markdown heading) or a
PDF page. Each label earns credit once, at the first hit that matches it: a function split
into three parts does not count three times.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Label:
    path: str
    symbol: str | None = None
    page: int | None = None
    source: str | None = None
    grade: int = 1

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "Label":
        return cls(
            path=str(raw["path"]),
            symbol=str(raw["symbol"]) if raw.get("symbol") is not None else None,
            page=int(raw["page"]) if raw.get("page") is not None else None,
            source=raw.get("source"),
            grade=int(raw.get("grade", 1)),
        )

    def describe(self) -> str:
        detail = f" :: {self.symbol}" if self.symbol else f" p.{self.page}" if self.page else ""
        return f"{self.source + '/' if self.source else ''}{self.path}{detail}"


def matches(label: Label, hit: Mapping[str, Any]) -> bool:
    if hit["path"] != label.path:
        return False
    if label.source is not None and hit.get("source_name") != label.source:
        return False
    if label.symbol is not None:
        symbols = hit.get("symbols") or []
        trail = (hit.get("symbol") or "").split(" > ")
        if label.symbol not in symbols and label.symbol not in trail:
            return False
    if label.page is not None:
        meta = hit.get("meta") or {}
        start, end = meta.get("page_start"), meta.get("page_end")
        if start is None or not (start <= label.page <= end):
            return False
    return True


def gains(hits: Sequence[Mapping[str, Any]], labels: Sequence[Label]) -> list[int]:
    """Grade earned at each rank (0 if the hit matches no unclaimed label)."""
    claimed: set[int] = set()
    out = []
    for hit in hits:
        grade = 0
        for i, label in enumerate(labels):
            if i not in claimed and matches(label, hit):
                claimed.add(i)
                grade = max(grade, label.grade)
        out.append(grade)
    return out


def recall_at(hits: Sequence[Mapping[str, Any]], labels: Sequence[Label], k: int) -> float:
    if not labels:
        return 0.0
    found = sum(any(matches(label, h) for h in hits[:k]) for label in labels)
    return found / len(labels)


def ndcg_at(hits: Sequence[Mapping[str, Any]], labels: Sequence[Label], k: int) -> float:
    def dcg(grades: Sequence[int]) -> float:
        return sum((2**g - 1) / math.log2(rank + 2) for rank, g in enumerate(grades[:k]))

    ideal = dcg(sorted((label.grade for label in labels), reverse=True))
    return dcg(gains(hits, labels)) / ideal if ideal > 0 else 0.0


def reciprocal_rank(hits: Sequence[Mapping[str, Any]], labels: Sequence[Label]) -> float:
    for rank, hit in enumerate(hits, start=1):
        if any(matches(label, hit) for label in labels):
            return 1.0 / rank
    return 0.0


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def best_threshold(answerable: Sequence[float], unanswerable: Sequence[float]) -> dict[str, float]:
    """The top-1 score cut-off that best separates answerable from unanswerable queries.

    Accuracy here = share of queries where "top score >= threshold" equals "answerable".
    This is the starting abstention threshold for chat; it is only meaningful for scores
    that are comparable across queries (the reranker's, not RRF's)."""
    if not answerable or not unanswerable:
        return {}
    candidates = sorted(set(answerable) | set(unanswerable))
    total = len(answerable) + len(unanswerable)
    best = (0.0, 0.0)
    for t in candidates:
        correct = sum(s >= t for s in answerable) + sum(s < t for s in unanswerable)
        if correct / total > best[0]:
            best = (correct / total, t)
    return {"accuracy": round(best[0], 4), "threshold": round(best[1], 4)}
