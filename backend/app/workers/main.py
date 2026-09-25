"""ARQ worker. Run with: arq app.workers.main.WorkerSettings"""

import logging
from typing import Any

from arq.connections import RedisSettings

from app.config import settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.services.ingestion.pipeline import Pipeline, embed_pending, summarize

log = logging.getLogger("memoryos.worker")


async def index_source(ctx: dict[str, Any], source_id: int, run_id: int) -> dict[str, Any]:
    stats = await Pipeline(SessionLocal, source_id, run_id).run()
    log.info("source %s indexed: %s", source_id, summarize(stats))
    return stats


async def embed_source(ctx: dict[str, Any], source_id: int | None = None) -> dict[str, Any]:
    """Embed chunks left pending (e.g. the model server was down during indexing)."""
    embedded, pending, warning = await embed_pending(SessionLocal, source_id)
    log.info("embedded %d chunks (%d pending) %s", embedded, pending, warning or "")
    return {"embedded": embedded, "pending": pending, "warning": warning}


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging(settings.log_level)
    log.info(
        "worker ready (embedder=%s, model server=%s)", settings.embedder, settings.model_server_url
    )


class WorkerSettings:
    functions = [index_source, embed_source]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    # A large repo on a CPU-only model server can take a long time to embed.
    job_timeout = 6 * 60 * 60
    # Indexing is CPU- and model-bound; parallel sources just contend for the same GPU.
    max_jobs = 2
    keep_result = 24 * 60 * 60
