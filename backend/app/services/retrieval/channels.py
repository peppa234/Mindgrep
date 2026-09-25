"""The three candidate generators. Each returns chunk ids, best first.

vector  : dense similarity (pgvector HNSW, cosine). Good at paraphrase and vague descriptions.
lexical : weighted full-text (tsvector). Good at exact words, names, rare terms.
symbol  : trigram match on defined symbol names. Good at half-remembered identifiers
          ("generate_jwt" finds `generate_jwt_token`), which both of the others miss.
"""

from sqlalchemy import ColumnElement, and_, func, literal, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document
from app.schemas.search import SearchFilters


def filter_clause(filters: SearchFilters) -> tuple[list[ColumnElement[bool]], bool]:
    """(conditions, needs the documents join)."""
    conditions: list[ColumnElement[bool]] = []
    needs_document = False
    if filters.source_ids:
        conditions.append(Chunk.source_id.in_(filters.source_ids))
    if filters.chunk_kinds:
        conditions.append(Chunk.kind.in_(filters.chunk_kinds))
    if filters.doc_kinds:
        conditions.append(Document.kind.in_(filters.doc_kinds))
        needs_document = True
    if filters.languages:
        conditions.append(Document.language.in_(filters.languages))
        needs_document = True
    if filters.path_prefix:
        escaped = filters.path_prefix.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        conditions.append(Document.path.like(escaped + "%", escape="\\"))
        needs_document = True
    if filters.modified_after:
        conditions.append(Document.modified_at >= filters.modified_after)
        needs_document = True
    if filters.modified_before:
        conditions.append(Document.modified_at < filters.modified_before)
        needs_document = True
    return conditions, needs_document


def _base(columns: list, filters: SearchFilters):
    conditions, needs_document = filter_clause(filters)
    stmt = select(*columns).select_from(Chunk)
    if needs_document:
        stmt = stmt.join(Document, Document.id == Chunk.document_id)
    return stmt, conditions


async def vector_candidates(
    session: AsyncSession, query_vector: list[float], filters: SearchFilters, limit: int
) -> list[int]:
    # ef_search must be >= limit for HNSW to return `limit` results at all. Iterative scan
    # (pgvector >= 0.8) keeps searching when filters discard most of the nearest neighbours.
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {max(100, limit * 2)}"))
    await session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    distance = Chunk.embedding.cosine_distance(query_vector)
    stmt, conditions = _base([Chunk.id], filters)
    stmt = (
        stmt.where(and_(Chunk.embedding.is_not(None), *conditions)).order_by(distance).limit(limit)
    )
    return list((await session.execute(stmt)).scalars())


async def lexical_candidates(
    session: AsyncSession, tsquery: str, filters: SearchFilters, limit: int
) -> list[int]:
    query = func.to_tsquery("english", tsquery)
    # Normalisation 1 divides by 1 + log(length): long chunks don't win just by being long.
    rank = func.ts_rank_cd(Chunk.tsv, query, 1)
    stmt, conditions = _base([Chunk.id], filters)
    stmt = (
        stmt.where(and_(Chunk.tsv.op("@@")(query), *conditions))
        .order_by(rank.desc(), Chunk.id)
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars())


async def symbol_candidates(
    session: AsyncSession, identifiers: list[str], filters: SearchFilters, limit: int
) -> list[int]:
    if not identifiers:
        return []
    best: dict[int, float] = {}
    for ident in identifiers:
        needle = literal(ident.lower())
        similarity = func.word_similarity(needle, Chunk.symbol_text)
        stmt, conditions = _base([Chunk.id, similarity], filters)
        # `<%` is pg_trgm's indexed word-similarity test (threshold 0.6 by default).
        stmt = (
            stmt.where(and_(needle.op("<%")(Chunk.symbol_text), *conditions))
            .order_by(similarity.desc(), Chunk.id)
            .limit(limit)
        )
        for chunk_id, score in (await session.execute(stmt)).all():
            best[chunk_id] = max(best.get(chunk_id, 0.0), float(score))
    return [cid for cid, _ in sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))][:limit]
