"""Search orchestration: (vector ∥ lexical ∥ symbol) -> RRF -> rerank -> hydrate.

Each stage can be switched off by `mode`, which is what lets the eval harness attribute
quality to stages. A missing model server degrades the request (reported in `degraded`)
instead of failing it: lexical search needs no model at all.
"""

import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Chunk, Document, Source
from app.schemas.search import SearchHit, SearchRequest, SearchResponse
from app.services.embedding.base import ModelUnavailable
from app.services.embedding.factory import get_embedder, get_reranker
from app.services.retrieval import channels
from app.services.retrieval.fusion import Fused, rrf
from app.services.retrieval.query import analyze

log = logging.getLogger(__name__)

RERANK_TEXT_MAX_CHARS = 2000


async def search(session: AsyncSession, request: SearchRequest) -> SearchResponse:
    timings: dict[str, float] = {}
    degraded: list[str] = []
    started = time.perf_counter()

    def lap(name: str, since: float) -> float:
        now = time.perf_counter()
        timings[name] = round((now - since) * 1000, 1)
        return now

    mode = request.mode
    if mode == "auto":
        mode = "rerank" if get_reranker() is not None else "hybrid"
    use_vector = mode in ("vector", "hybrid", "rerank")
    use_lexical = mode in ("lexical", "hybrid", "rerank")
    pool = settings.candidates_per_channel
    analyzed = analyze(request.q)
    ranked: dict[str, list[int]] = {}

    t = time.perf_counter()
    if use_vector:
        embedder = get_embedder()
        if embedder is None:
            degraded.append("vector: no embedder configured")
        else:
            try:
                [query_vector] = await embedder.embed([request.q], "query")
                t = lap("embed_query", t)
                ranked["vector"] = await channels.vector_candidates(
                    session, query_vector, request.filters, pool
                )
                t = lap("vector", t)
            except ModelUnavailable as exc:
                degraded.append(f"vector: {exc}")

    if use_lexical:
        if analyzed.tsquery:
            ranked["lexical"] = await channels.lexical_candidates(
                session, analyzed.tsquery, request.filters, pool
            )
            t = lap("lexical", t)
        if analyzed.identifiers:
            ranked["symbol"] = await channels.symbol_candidates(
                session, analyzed.identifiers, request.filters, pool
            )
            t = lap("symbol", t)

    fused = rrf(ranked)
    candidates = len(fused)

    rerank_scores: dict[int, float] = {}
    if mode == "rerank" and fused:
        reranker = get_reranker()
        if reranker is None:
            degraded.append("rerank: no reranker configured")
        else:
            pool_ids = [f.chunk_id for f in fused[: settings.rerank_candidates]]
            texts = await _rerank_texts(session, pool_ids)
            try:
                scores = await reranker.rerank(request.q, [texts[i] for i in pool_ids])
                rerank_scores = dict(zip(pool_ids, scores, strict=True))
                by_id = {f.chunk_id: f for f in fused}
                fused = sorted(
                    (by_id[i] for i in pool_ids),
                    key=lambda f: (-rerank_scores[f.chunk_id], f.chunk_id),
                )
                t = lap("rerank", t)
            except ModelUnavailable as exc:
                degraded.append(f"rerank: {exc}")

    top = fused[: request.k]
    hits = await _hydrate(session, top, rerank_scores)
    lap("hydrate", t)
    timings["total"] = round((time.perf_counter() - started) * 1000, 1)
    return SearchResponse(
        query=request.q,
        mode=mode,
        hits=hits,
        candidates=candidates,
        degraded=degraded,
        timings_ms=timings,
    )


async def _rerank_texts(session: AsyncSession, ids: list[int]) -> dict[int, str]:
    rows = (
        await session.execute(
            select(Chunk.id, Chunk.header, Chunk.content).where(Chunk.id.in_(ids))
        )
    ).all()
    return {r.id: (r.header + "\n\n" + r.content)[:RERANK_TEXT_MAX_CHARS] for r in rows}


async def _hydrate(
    session: AsyncSession, fused: list[Fused], rerank_scores: dict[int, float]
) -> list[SearchHit]:
    if not fused:
        return []
    ids = [f.chunk_id for f in fused]
    rows = (
        await session.execute(
            select(Chunk, Document, Source.name)
            .join(Document, Document.id == Chunk.document_id)
            .join(Source, Source.id == Chunk.source_id)
            .where(Chunk.id.in_(ids))
        )
    ).all()
    by_id = {chunk.id: (chunk, document, source_name) for chunk, document, source_name in rows}
    hits = []
    for f in fused:
        if f.chunk_id not in by_id:
            continue  # deleted between candidate generation and hydration
        chunk, document, source_name = by_id[f.chunk_id]
        rerank_score = rerank_scores.get(f.chunk_id)
        hits.append(
            SearchHit(
                chunk_id=chunk.id,
                document_id=document.id,
                source_id=chunk.source_id,
                source_name=source_name,
                path=document.path,
                doc_kind=document.kind,
                language=document.language,
                title=document.title,
                chunk_kind=chunk.kind,
                symbol=chunk.symbol,
                symbols=chunk.symbols,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                header=chunk.header,
                content=chunk.content,
                modified_at=document.modified_at,
                git_commit=document.git_commit,
                meta=chunk.meta,
                score=rerank_score if rerank_score is not None else round(f.score, 6),
                rerank_score=rerank_score,
                ranks=f.ranks,
            )
        )
    return hits
