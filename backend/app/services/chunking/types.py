from dataclasses import dataclass, field
from typing import Any

# Bump whenever parsing or chunking output changes. Documents indexed under an older
# version are re-chunked on the next run even if their content hash is unchanged.
PARSER_VERSION = 1

# Token budgets, estimated at ~4 characters per token (see estimate_tokens).
MAX_TOKENS = 1200  # split anything larger
MIN_TOKENS = 60  # merge anything smaller with its neighbours
MERGE_TARGET_TOKENS = 500  # stop merging once a group reaches this size


@dataclass
class ChunkDraft:
    """A chunk before it has a database identity. Produced by every chunker."""

    kind: str
    content: str
    symbol: str | None = None
    symbols: list[str] = field(default_factory=list)
    start_line: int | None = None
    end_line: int | None = None
    # Extra lines for the header: enclosing class signature, "part 2 of 3", imports used.
    context: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    kind: str  # code | markdown | pdf | text
    language: str | None
    title: str | None
    chunks: list[ChunkDraft]
    status: str = "indexed"  # indexed | needs_ocr | error
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def estimate_tokens(text: str) -> int:
    """Cheap token estimate. Good enough for budgeting; no tokenizer dependency."""
    return max(1, len(text) // 4)
