from collections.abc import AsyncIterator

from arq import ArqRedis
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import SessionLocal


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """For streaming endpoints, which open sessions as they go: a request-scoped session
    would be closed before the response body finishes."""
    return SessionLocal


def get_arq(request: Request) -> ArqRedis:
    return request.app.state.arq
