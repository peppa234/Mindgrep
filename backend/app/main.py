import logging
from contextlib import asynccontextmanager

import redis.asyncio as redis
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1 import chat, documents, graph, ideas, search, sources
from app.config import settings
from app.core.csrf import CrossSiteGuard
from app.core.logging import configure_logging
from app.db.session import engine
from app.services.embedding.base import ModelUnavailable
from app.services.embedding.factory import get_embedder, get_reranker
from app.services.llm.factory import get_chat, get_extraction_chat

configure_logging(settings.log_level)
log = logging.getLogger("mindgrep")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    app.state.arq = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    yield
    await app.state.arq.aclose()
    await app.state.redis.aclose()
    await engine.dispose()


app = FastAPI(
    title="Mindgrep",
    version="0.4.0",
    description=(
        "Index notes, PDFs and repositories; search them with hybrid retrieval, ask questions "
        "with cited answers, query the knowledge graph built from them, and find the ideas "
        "you wrote down and never implemented."
    ),
    lifespan=lifespan,
)
app.add_middleware(CrossSiteGuard)

for module in (sources, search, documents, chat, graph, ideas):
    app.include_router(module.router, prefix="/api/v1")


@app.get("/health/live", tags=["health"])
async def live() -> dict:
    """Bare liveness for an uptime monitor: the one route Caddy serves without the password,
    so it says nothing about versions, models or errors."""
    return {"status": "ok"}


@app.get("/health", tags=["health"])
async def health() -> JSONResponse:
    """Liveness plus real dependency checks.

    Reports which Postgres extensions are actually installed, because a missing
    `vector` extension fails much later and much more confusingly at query time.
    The model server is reported but does not fail the check: without it, search
    degrades to lexical-only rather than going down.
    """
    checks: dict[str, dict] = {}

    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT extname, extversion FROM pg_extension "
                    "WHERE extname IN ('vector', 'pg_trgm') ORDER BY extname"
                )
            )
            rows = result.all()
            checks["postgres"] = {
                "ok": True,
                "extensions": [r[0] for r in rows],
                "versions": {r[0]: r[1] for r in rows},
            }
    except Exception as exc:
        log.exception("postgres health check failed")
        checks["postgres"] = {"ok": False, "error": str(exc)}

    try:
        pong = await app.state.redis.ping()
        checks["valkey"] = {"ok": bool(pong)}
    except Exception as exc:
        log.exception("valkey health check failed")
        checks["valkey"] = {"ok": False, "error": str(exc)}

    healthy = all(c["ok"] for c in checks.values())

    models: dict[str, object] = {"embedder": settings.embedder, "reranker": settings.reranker}
    embedder, reranker = get_embedder(), get_reranker()
    try:
        if embedder is not None:
            models["embedding_model"] = await embedder.model_name()
        if reranker is not None:
            models["reranker_model"] = await reranker.model_name()
        models["ok"] = True
    except ModelUnavailable as exc:
        models.update(ok=False, error=str(exc))
    checks["models"] = models

    chat, extraction = get_chat(), get_extraction_chat()
    checks["chat"] = {
        "configured": chat is not None,
        "models": [m.name for m in chat.models] if chat else [],
        "extraction": [m.name for m in extraction.models] if extraction else [],
    }

    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )
