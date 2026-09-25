from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.schemas.search import SearchMode, SearchRequest, SearchResponse
from app.services.retrieval.search import search

router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search_post(
    body: SearchRequest, session: AsyncSession = Depends(get_session)
) -> SearchResponse:
    """Hybrid search over every indexed chunk. Filters narrow by source, type, path, or date."""
    return await search(session, body)


@router.get("", response_model=SearchResponse)
async def search_get(
    q: str = Query(min_length=1, max_length=2000),
    k: int = Query(10, ge=1, le=50),
    mode: SearchMode = "auto",
    session: AsyncSession = Depends(get_session),
) -> SearchResponse:
    """Same as POST, without filters. Handy from a browser or curl."""
    return await search(session, SearchRequest(q=q, k=k, mode=mode))
