from collections.abc import AsyncIterator

from arq import ArqRedis
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


def get_arq(request: Request) -> ArqRedis:
    return request.app.state.arq
