from datetime import UTC, datetime

from arq import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Idea, Node
from app.deps import get_arq, get_session
from app.schemas.idea import IdeaOut, IdeaOverride, IdeaSummary
from app.services.ideas import queries
from app.services.ideas.service import sync_graph

router = APIRouter(prefix="/ideas", tags=["ideas"])


@router.get("", response_model=list[IdeaOut])
async def list_ideas(
    status_: str | None = Query(
        None,
        alias="status",
        description="implemented | partial | unimplemented | abandoned | all",
    ),
    sort: queries.Sort = Query("oldest", description="oldest | newest | closest"),
    session: AsyncSession = Depends(get_session),
) -> list[IdeaOut]:
    """Ideas found in your notes and whether a project implements them, with the evidence:
    the words each project shares with the idea, the ones no project has, and the closest
    chunk of code. `status=unimplemented` is the list of ideas you never built."""
    return await queries.list_ideas(session, status_, sort)


@router.get("/summary", response_model=IdeaSummary)
async def summary(session: AsyncSession = Depends(get_session)) -> IdeaSummary:
    return IdeaSummary.model_validate(await queries.counts(session))


@router.post("/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh(arq: ArqRedis = Depends(get_arq)) -> dict:
    """Re-match every idea against every project (indexing does this on its own)."""
    job = await arq.enqueue_job("refresh_ideas", _job_id="refresh-ideas")
    return {"job_id": job.job_id if job else "refresh-ideas"}


async def _one(session: AsyncSession, idea_id: int) -> IdeaOut:
    found = await queries.list_ideas(session, ids=[idea_id])
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "idea not found")
    return found[0]


@router.get("/{idea_id}", response_model=IdeaOut)
async def get_idea(idea_id: int, session: AsyncSession = Depends(get_session)) -> IdeaOut:
    return await _one(session, idea_id)


async def _resync(session: AsyncSession) -> None:
    await session.flush()
    await sync_graph(session, list((await session.execute(select(Idea))).scalars()))
    await session.commit()


@router.put("/{idea_id}/override", response_model=IdeaOut)
async def override(
    idea_id: int, body: IdeaOverride, session: AsyncSession = Depends(get_session)
) -> IdeaOut:
    """Say what really became of an idea. It outranks matching and the note's frontmatter,
    and survives every re-index."""
    idea = await session.get(Idea, idea_id)
    if idea is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "idea not found")
    project_id = body.project_id
    if body.status in ("unimplemented", "abandoned"):
        project_id = None
    if project_id is not None:
        project = await session.get(Node, project_id)
        if project is None or project.kind != "project":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "not a project node")
    idea.user_status = body.status
    idea.user_project_id = project_id
    idea.user_note = body.note
    idea.overridden_at = datetime.now(UTC)
    await _resync(session)
    return await _one(session, idea_id)


@router.delete("/{idea_id}/override", response_model=IdeaOut)
async def clear_override(idea_id: int, session: AsyncSession = Depends(get_session)) -> IdeaOut:
    idea = await session.get(Idea, idea_id)
    if idea is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "idea not found")
    idea.user_status = idea.user_project_id = idea.user_note = idea.overridden_at = None
    await _resync(session)
    return await _one(session, idea_id)
