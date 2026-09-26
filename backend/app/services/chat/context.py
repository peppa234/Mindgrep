"""From search hits to what the model reads: a numbered, deduplicated, budgeted set of
sources, and from what the model wrote back to which of them it actually cited."""

import re
from collections.abc import AsyncIterator

from app.schemas.chat import ChatSource
from app.schemas.search import SearchHit
from app.services.chunking.types import estimate_tokens

NO_ANSWER = "NO_ANSWER"
MIN_TRUNCATED_TOKENS = 150  # a chunk cut shorter than this is not worth including
CITATION_RE = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")


def _page(hit: SearchHit) -> int | None:
    page = hit.meta.get("page_start")
    return page if isinstance(page, int) else None


def _overlaps(a: SearchHit, b: ChatSource) -> bool:
    """Same document and one line range inside the other: showing both wastes budget."""
    if a.document_id != b.document_id or a.start_line is None or b.start_line is None:
        return False
    a_end, b_end = a.end_line or a.start_line, b.end_line or b.start_line
    inside = b.start_line <= a.start_line and a_end <= b_end
    contains = a.start_line <= b.start_line and b_end <= a_end
    return inside or contains


def assemble(hits: list[SearchHit], max_sources: int, budget_tokens: int) -> list[ChatSource]:
    """Keep hits in rank order until the source count or token budget runs out."""
    sources: list[ChatSource] = []
    remaining = budget_tokens
    for hit in hits:
        if len(sources) >= max_sources or remaining < MIN_TRUNCATED_TOKENS:
            break
        if any(_overlaps(hit, s) for s in sources):
            continue
        content = hit.content
        cost = estimate_tokens(hit.header) + estimate_tokens(content)
        if cost > remaining:
            content = content[: max(0, (remaining - estimate_tokens(hit.header)) * 4)]
            if estimate_tokens(content) < MIN_TRUNCATED_TOKENS:
                continue
            content += "\n[… truncated]"
            cost = remaining
        remaining -= cost
        sources.append(
            ChatSource(
                n=len(sources) + 1,
                kind="chunk",
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                source_name=hit.source_name,
                path=hit.path,
                doc_kind=hit.doc_kind,
                language=hit.language,
                symbol=hit.symbol,
                title=hit.title,
                start_line=hit.start_line,
                end_line=hit.end_line,
                page=_page(hit),
                modified_at=hit.modified_at,
                content=content,
                score=hit.rerank_score if hit.rerank_score is not None else hit.score,
            )
        )
    return sources


def source_label(source: ChatSource) -> str:
    where = f"{source.source_name}/{source.path}"
    if source.symbol and source.doc_kind != "pdf":
        where += f" :: {source.symbol}"
    if source.start_line is not None:
        where += f" (lines {source.start_line}-{source.end_line})"
    elif source.page is not None:
        where += f" (page {source.page})"
    parts = [where]
    if source.language and source.doc_kind == "code":
        parts.append(source.language)
    if source.modified_at is not None:
        parts.append(f"last changed {source.modified_at.date().isoformat()}")
    return " · ".join(parts)


def render_sources(sources: list[ChatSource]) -> str:
    blocks = []
    for source in sources:
        fence = "```" + (source.language or "" if source.doc_kind == "code" else "")
        blocks.append(f"[{source.n}] {source_label(source)}\n{fence}\n{source.content}\n```")
    return "\n\n".join(blocks)


def citations(text: str, count: int) -> list[int]:
    """Valid source numbers cited in `text`, in order of first citation. Numbers the model
    invented (beyond the sources it was given) are dropped, not trusted."""
    found: list[int] = []
    for group in CITATION_RE.findall(text):
        for part in re.split(r"[,;]", group):
            n = int(part.strip())
            if 1 <= n <= count and n not in found:
                found.append(n)
    return found


def strip_citations(text: str) -> str:
    """For conversation history: old [n] markers point at sources the model no longer sees."""
    return re.sub(r"\s*" + CITATION_RE.pattern, "", text)


async def detect_abstention(parts: AsyncIterator[str]) -> AsyncIterator[str | None]:
    """Pass text through, but hold the start back until it cannot be the NO_ANSWER sentinel.
    Yields None (and nothing else) if the model abstained, so the sentinel never reaches the
    user as if it were an answer."""
    buffer = ""
    decided = False
    async for part in parts:
        if decided:
            yield part
            continue
        buffer += part
        head = buffer.lstrip()
        if head.startswith(NO_ANSWER):
            decided = True
            yield None
            return
        if len(head) >= len(NO_ANSWER) or not NO_ANSWER.startswith(head):
            decided = True
            yield buffer
    if not decided:
        yield None if buffer.strip() in ("", NO_ANSWER) else buffer
