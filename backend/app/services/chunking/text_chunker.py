"""Structure-aware chunking for prose: Markdown by heading, everything else by paragraph."""

import re
from dataclasses import dataclass, field

from app.services.chunking.types import (
    MAX_TOKENS,
    MERGE_TARGET_TOKENS,
    MIN_TOKENS,
    ChunkDraft,
    estimate_tokens,
)

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


@dataclass
class _Section:
    path: list[str]  # heading trail, outermost first
    start: int  # 0-based row, inclusive
    end: int  # 0-based row, inclusive
    headings: list[str] = field(default_factory=list)


def markdown_sections(lines: list[str], title: str | None, offset: int = 0) -> list[_Section]:
    """Split Markdown lines into sections at ATX headings, ignoring `#` inside code fences."""
    sections: list[_Section] = []
    trail: list[tuple[int, str]] = []  # (level, text)
    current = _Section(path=[title] if title else [], start=0, end=-1)
    in_fence = False

    for row, line in enumerate(lines):
        if FENCE_RE.match(line):
            in_fence = not in_fence
        match = None if in_fence else HEADING_RE.match(line)
        if match is None:
            current.end = row
            continue
        if current.end >= current.start and any(
            lines[r].strip() for r in range(current.start, current.end + 1)
        ):
            sections.append(current)
        level, text = len(match.group(1)), match.group(2).strip()
        trail = [(lvl, t) for lvl, t in trail if lvl < level] + [(level, text)]
        current = _Section(path=[t for _, t in trail], start=row, end=row, headings=[text])

    if current.end >= current.start and any(
        lines[r].strip() for r in range(current.start, current.end + 1)
    ):
        sections.append(current)

    for section in sections:
        section.start += offset
        section.end += offset
    return sections


def _tokens(lines: list[str], start: int, end: int) -> int:
    return estimate_tokens("\n".join(lines[start : end + 1]))


def paragraph_windows(lines: list[str], start: int, end: int) -> list[tuple[int, int]]:
    """Split rows [start, end] into windows under MAX_TOKENS, cutting at blank lines
    outside code fences where possible."""
    if _tokens(lines, start, end) <= MAX_TOKENS:
        return [(start, end)]
    budget = MAX_TOKENS * 4
    windows: list[tuple[int, int]] = []
    window_start, chars, last_break, in_fence = start, 0, None, False
    row = start
    while row <= end:
        line = lines[row]
        if FENCE_RE.match(line):
            in_fence = not in_fence
        chars += len(line) + 1
        if not line.strip() and not in_fence:
            last_break = row
        if chars > budget and row > window_start:
            cut = last_break if last_break is not None and last_break > window_start else row - 1
            windows.append((window_start, cut))
            window_start, chars, last_break, in_fence = cut + 1, 0, None, False
            row = window_start
            continue
        row += 1
    if window_start <= end:
        windows.append((window_start, end))
    return windows


def chunk_markdown(lines: list[str], title: str | None, offset: int = 0) -> list[ChunkDraft]:
    """`lines` is the body after any frontmatter; `offset` is the frontmatter's line count,
    so reported line numbers match the file on disk."""
    sections = markdown_sections(lines, title)

    # Merge runs of small sections (a heading with two lines under it) into their neighbours.
    merged: list[_Section] = []
    for section in sections:
        if merged:
            prev = merged[-1]
            prev_size = _tokens(lines, prev.start, prev.end)
            size = _tokens(lines, section.start, section.end)
            combined = _tokens(lines, prev.start, section.end)
            if (prev_size < MIN_TOKENS or size < MIN_TOKENS) and combined <= MERGE_TARGET_TOKENS:
                prev.end = section.end
                prev.headings += section.headings
                continue
        merged.append(section)

    drafts: list[ChunkDraft] = []
    for section in merged:
        windows = paragraph_windows(lines, section.start, section.end)
        for i, (a, b) in enumerate(windows, start=1):
            content = "\n".join(lines[a : b + 1]).strip("\n")
            if not content.strip():
                continue
            trail = section.path
            if title and (not trail or trail[0] != title):
                trail = [title, *trail]  # an H2-only note still says which note it is
            symbol = " > ".join(trail) if trail else None
            context = [f"part {i} of {len(windows)}"] if len(windows) > 1 else []
            drafts.append(
                ChunkDraft(
                    kind="markdown_section",
                    content=content,
                    symbol=symbol,
                    symbols=section.headings or ([section.path[-1]] if section.path else []),
                    start_line=a + 1 + offset,
                    end_line=b + 1 + offset,
                    context=context,
                )
            )
    return drafts


def chunk_plain(text: str) -> list[ChunkDraft]:
    lines = [line.rstrip("\r") for line in text.split("\n")]
    drafts = []
    for a, b in paragraph_windows(lines, 0, len(lines) - 1):
        content = "\n".join(lines[a : b + 1]).strip("\n")
        if content.strip():
            drafts.append(
                ChunkDraft(kind="text", content=content, start_line=a + 1, end_line=b + 1)
            )
    return drafts
