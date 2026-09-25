"""Model identity is configuration. Swap local GPU, CPU container, or hashing with one env var."""

from functools import cache

import redis.asyncio as redis

from app.config import settings
from app.services.embedding.base import Embedder, Reranker
from app.services.embedding.cache import CachedEmbedder
from app.services.embedding.hashing import HashEmbedder
from app.services.embedding.http import HttpEmbedder, HttpReranker


@cache
def _cache_client() -> redis.Redis:
    # Binary client: vectors are stored as packed float32, not strings.
    return redis.from_url(settings.redis_url, decode_responses=False)


@cache
def get_embedder() -> Embedder | None:
    if settings.embedder == "none":
        return None
    if settings.embedder == "hash":
        return HashEmbedder(settings.embedding_dim)
    inner = HttpEmbedder(
        settings.model_server_url, settings.model_server_timeout_s, settings.embedding_dim
    )
    return CachedEmbedder(inner, _cache_client())


@cache
def get_reranker() -> Reranker | None:
    if settings.reranker == "none":
        return None
    return HttpReranker(settings.model_server_url, settings.model_server_timeout_s)
