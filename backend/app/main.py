import logging
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.db.session import engine

logging.basicConfig(level=settings.log_level)
log = logging.getLogger("memoryos")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    yield
    await app.state.redis.aclose()
    await engine.dispose()


app = FastAPI(title="MemoryOS", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> JSONResponse:
    """Liveness plus real dependency checks.

    Reports which Postgres extensions are actually installed, because a missing
    `vector` extension fails much later and much more confusingly at query time.
    """
    checks: dict[str, object] = {}

    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm')")
            )
            checks["postgres"] = {"ok": True, "extensions": sorted(r[0] for r in result)}
    except Exception as exc:
        log.exception("postgres health check failed")
        checks["postgres"] = {"ok": False, "error": str(exc)}

    try:
        pong = await app.state.redis.ping()
        checks["valkey"] = {"ok": bool(pong)}
    except Exception as exc:
        log.exception("valkey health check failed")
        checks["valkey"] = {"ok": False, "error": str(exc)}

    healthy = all(c["ok"] for c in checks.values())  # type: ignore[index]
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )
