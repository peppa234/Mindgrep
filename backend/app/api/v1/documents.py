from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, Source
from app.deps import get_session
from app.schemas.source import StatsOut

router = APIRouter(tags=["documents"])


class ChunkOut(BaseModel):
    id: int
    ordinal: int
    kind: str
    symbol: str | None
    symbols: list[str]
    header: str
    content: str
    start_line: int | None
    end_line: int | None
    token_count: int
    embedded: bool
    meta: dict[str, Any]


class DocumentOut(BaseModel):
    id: int
    source_id: int
    source_name: str
    path: str
    kind: str
    language: str | None
    title: str | None
    size_bytes: int
    status: str
    error: str | None
    modified_at: datetime | None
    git_commit: str | None
    git_author: str | None
    meta: dict[str, Any]
    chunks: list[ChunkOut]


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: int, session: AsyncSession = Depends(get_session)
) -> DocumentOut:
    """A document and all of its chunks, in order: what the index actually holds for a file."""
    row = (
        await session.execute(
            select(Document, Source.name)
            .join(Source, Source.id == Document.source_id)
            .where(Document.id == document_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"document {document_id} not found")
    document, source_name = row
    chunks = (
        await session.execute(
            select(Chunk, Chunk.embedding.is_not(None))
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.ordinal)
        )
    ).all()
    return DocumentOut(
        id=document.id,
        source_id=document.source_id,
        source_name=source_name,
        path=document.path,
        kind=document.kind,
        language=document.language,
        title=document.title,
        size_bytes=document.size_bytes,
        status=document.status,
        error=document.error,
        modified_at=document.modified_at,
        git_commit=document.git_commit,
        git_author=document.git_author,
        meta=document.meta,
        chunks=[
            ChunkOut(
                id=c.id,
                ordinal=c.ordinal,
                kind=c.kind,
                symbol=c.symbol,
                symbols=c.symbols,
                header=c.header,
                content=c.content,
                start_line=c.start_line,
                end_line=c.end_line,
                token_count=c.token_count,
                embedded=embedded,
                meta=c.meta,
            )
            for c, embedded in chunks
        ],
    )


@router.get("/stats", response_model=StatsOut, tags=["stats"])
async def stats(session: AsyncSession = Depends(get_session)) -> StatsOut:
    """Counts across the whole index: the Phase 1 "report counts by type" deliverable."""

    async def grouped(column, table_count) -> dict[str, int]:
        rows = (
            await session.execute(
                select(column, func.count()).select_from(table_count).group_by(column)
            )
        ).all()
        return {str(k): v for k, v in rows if k is not None}

    chunk_total, embedded = (
        await session.execute(select(func.count(Chunk.id), func.count(Chunk.embedding)))
    ).one()
    by_status = await grouped(Document.status, Document)
    return StatsOut(
        sources=(await session.execute(select(func.count(Source.id)))).scalar_one(),
        documents=sum(by_status.values()),
        chunks=chunk_total,
        embedded=embedded,
        documents_by_kind=await grouped(Document.kind, Document),
        documents_by_language=await grouped(Document.language, Document),
        chunks_by_kind=await grouped(Chunk.kind, Chunk),
        needs_ocr=by_status.get("needs_ocr", 0),
        failed=by_status.get("error", 0),
    )
