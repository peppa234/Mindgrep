import asyncio
import shutil

from arq import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, IndexRun, Source
from app.deps import get_arq, get_session
from app.schemas.source import RunOut, SourceCreate, SourceOut
from app.services.ingestion import git
from app.services.ingestion.pipeline import repo_dir, resolve_local, start_run
from app.services.llm.factory import get_extraction_chat

router = APIRouter(prefix="/sources", tags=["sources"])

BUSY = ("queued", "indexing")


async def _counts(session: AsyncSession, source_ids: list[int]) -> dict[int, dict]:
    counts: dict[int, dict] = {
        sid: {"documents": 0, "chunks": 0, "embedded": 0, "documents_by_kind": {}}
        for sid in source_ids
    }
    if not source_ids:
        return counts
    for sid, kind, n in (
        await session.execute(
            select(Document.source_id, Document.kind, func.count())
            .where(Document.source_id.in_(source_ids))
            .group_by(Document.source_id, Document.kind)
        )
    ).all():
        counts[sid]["documents"] += n
        counts[sid]["documents_by_kind"][kind] = n
    for sid, total, embedded in (
        await session.execute(
            select(Chunk.source_id, func.count(), func.count(Chunk.embedding))
            .where(Chunk.source_id.in_(source_ids))
            .group_by(Chunk.source_id)
        )
    ).all():
        counts[sid]["chunks"], counts[sid]["embedded"] = total, embedded
    return counts


async def _latest_runs(session: AsyncSession, source_ids: list[int]) -> dict[int, IndexRun]:
    if not source_ids:
        return {}
    latest = (
        select(IndexRun.source_id, func.max(IndexRun.id).label("id"))
        .where(IndexRun.source_id.in_(source_ids))
        .group_by(IndexRun.source_id)
        .subquery()
    )
    runs = (
        await session.execute(select(IndexRun).join(latest, IndexRun.id == latest.c.id))
    ).scalars()
    return {run.source_id: run for run in runs}


async def _out(session: AsyncSession, sources: list[Source]) -> list[SourceOut]:
    ids = [s.id for s in sources]
    counts = await _counts(session, ids)
    runs = await _latest_runs(session, ids)
    out = []
    for source in sources:
        item = SourceOut.model_validate(source)
        item.documents = counts[source.id]["documents"]
        item.chunks = counts[source.id]["chunks"]
        item.embedded = counts[source.id]["embedded"]
        item.documents_by_kind = counts[source.id]["documents_by_kind"]
        run = runs.get(source.id)
        item.latest_run = RunOut.model_validate(run) if run else None
        out.append(item)
    return out


async def _get(session: AsyncSession, source_id: int) -> Source:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"source {source_id} not found")
    return source


async def _enqueue_index(session: AsyncSession, arq: ArqRedis, source_id: int) -> int:
    run_id = await start_run(session, source_id)
    await arq.enqueue_job("index_source", source_id, run_id, _job_id=f"index-run-{run_id}")
    return run_id


@router.get("", response_model=list[SourceOut])
async def list_sources(session: AsyncSession = Depends(get_session)) -> list[SourceOut]:
    sources = list((await session.execute(select(Source).order_by(Source.name))).scalars())
    return await _out(session, sources)


@router.post("", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
async def create_source(
    body: SourceCreate,
    session: AsyncSession = Depends(get_session),
    arq: ArqRedis = Depends(get_arq),
) -> SourceOut:
    try:
        if body.kind == "local":
            await asyncio.to_thread(resolve_local, body.uri)
            uri = body.uri
        else:
            uri = git.validate_url(body.uri)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    if (await session.execute(select(Source.id).where(Source.name == body.name))).first():
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"a source named {body.name!r} already exists"
        )
    source = Source(name=body.name, kind=body.kind, uri=uri)
    session.add(source)
    await session.commit()
    if body.index_now:
        await _enqueue_index(session, arq, source.id)
    await session.refresh(source)
    return (await _out(session, [source]))[0]


@router.get("/{source_id}", response_model=SourceOut)
async def get_source(source_id: int, session: AsyncSession = Depends(get_session)) -> SourceOut:
    return (await _out(session, [await _get(session, source_id)]))[0]


@router.post("/{source_id}/index", response_model=SourceOut, status_code=status.HTTP_202_ACCEPTED)
async def reindex_source(
    source_id: int,
    force: bool = Query(
        False, description="Enqueue even if a run looks active (e.g. after a worker crash)"
    ),
    session: AsyncSession = Depends(get_session),
    arq: ArqRedis = Depends(get_arq),
) -> SourceOut:
    source = await _get(session, source_id)
    if source.status in BUSY and not force:
        raise HTTPException(status.HTTP_409_CONFLICT, f"source is already {source.status}")
    await _enqueue_index(session, arq, source_id)
    await session.refresh(source)
    return (await _out(session, [source]))[0]


@router.post("/{source_id}/embed", status_code=status.HTTP_202_ACCEPTED)
async def embed_source(
    source_id: int,
    session: AsyncSession = Depends(get_session),
    arq: ArqRedis = Depends(get_arq),
) -> dict:
    """Embed chunks left without vectors, e.g. when the model server was down during indexing."""
    await _get(session, source_id)
    job = await arq.enqueue_job("embed_source", source_id)
    return {"job_id": job.job_id if job else None}


@router.post("/{source_id}/extract", status_code=status.HTTP_202_ACCEPTED)
async def extract_source(
    source_id: int,
    max_chunks: int = Query(500, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
    arq: ArqRedis = Depends(get_arq),
) -> dict:
    """LLM concept extraction over the source's notes and READMEs, on top of the deterministic
    graph that indexing already built. Spends chat-model quota; cached results are reused."""
    await _get(session, source_id)
    if get_extraction_chat() is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "no chat model configured: set GEMINI_API_KEY, GROQ_API_KEY or OLLAMA_MODEL",
        )
    job = await arq.enqueue_job("extract_source_concepts", source_id, max_chunks)
    return {"job_id": job.job_id if job else None}


@router.get("/{source_id}/runs", response_model=list[RunOut])
async def list_runs(
    source_id: int,
    limit: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[RunOut]:
    await _get(session, source_id)
    runs = (
        await session.execute(
            select(IndexRun)
            .where(IndexRun.source_id == source_id)
            .order_by(IndexRun.id.desc())
            .limit(limit)
        )
    ).scalars()
    return [RunOut.model_validate(r) for r in runs]


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(source_id: int, session: AsyncSession = Depends(get_session)) -> None:
    source = await _get(session, source_id)
    if source.status in BUSY:
        raise HTTPException(status.HTTP_409_CONFLICT, "wait for indexing to finish before deleting")
    kind = source.kind
    await session.delete(source)  # documents, chunks and runs cascade
    await session.commit()
    if kind == "git":
        await asyncio.to_thread(shutil.rmtree, repo_dir(source_id), True)
