"""Sliding-window rate limiting on top of a Redis sorted set.

Each attempt is a member scored by its timestamp. Old members are trimmed, the rest are
counted, and the request is rejected once the window is full. Unlike a fixed window this
has no burst at the window boundary.
"""

import time
from uuid import uuid4

import redis.asyncio as redis
from fastapi import HTTPException, Request, status

from app.config import settings

_client = redis.from_url(settings.redis_url)
WINDOW_SECONDS = 60


async def allow_request(key: str, limit: int, window: int = WINDOW_SECONDS) -> bool:
    now = time.time()
    member = f"{now}:{uuid4().hex}"
    pipe = _client.pipeline()
    pipe.zremrangebyscore(key, 0, now - window)
    pipe.zadd(key, {member: now})
    pipe.zcard(key)
    pipe.expire(key, window)
    _, _, count, _ = await pipe.execute()
    return count <= limit


async def limit_login_attempts(request: Request) -> None:
    """Dependency for the login route: at most N attempts per client IP per minute."""
    client_ip = request.client.host if request.client else "unknown"
    if not await allow_request(f"login:{client_ip}", settings.login_attempts_per_minute):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts")
