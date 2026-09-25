"""Embedding cache in Valkey, keyed by model + input type + sha256(text).

During development the same corpus is re-indexed dozens of times. With the cache, a
re-index after a chunking change only embeds the chunks whose text actually changed.
"""

import hashlib
import logging
from array import array

import redis.asyncio as redis

from app.services.embedding.base import Embedder, InputType

log = logging.getLogger(__name__)

TTL_SECONDS = 60 * 60 * 24 * 90


def _key(model: str, input_type: InputType, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"emb:{model}:{input_type}:{digest}"


class CachedEmbedder:
    def __init__(self, inner: Embedder, client: redis.Redis) -> None:
        self.inner = inner
        self.client = client
        self.hits = 0
        self.misses = 0

    @property
    def dim(self) -> int:
        return self.inner.dim

    async def model_name(self) -> str:
        return await self.inner.model_name()

    async def embed(self, texts: list[str], input_type: InputType) -> list[list[float]]:
        if not texts:
            return []
        model = await self.inner.model_name()
        keys = [_key(model, input_type, t) for t in texts]
        try:
            cached = await self.client.mget(keys)
        except redis.RedisError:
            log.warning("embedding cache unavailable; embedding without it", exc_info=True)
            return await self.inner.embed(texts, input_type)

        results: list[list[float] | None] = [
            array("f", raw).tolist() if raw else None for raw in cached
        ]
        missing = [i for i, r in enumerate(results) if r is None]
        self.hits += len(texts) - len(missing)
        self.misses += len(missing)
        if missing:
            vectors = await self.inner.embed([texts[i] for i in missing], input_type)
            try:
                pipe = self.client.pipeline(transaction=False)
                for i, vector in zip(missing, vectors, strict=True):
                    results[i] = vector
                    pipe.set(keys[i], array("f", vector).tobytes(), ex=TTL_SECONDS)
                await pipe.execute()
            except redis.RedisError:
                log.warning("could not write embedding cache", exc_info=True)
                for i, vector in zip(missing, vectors, strict=True):
                    results[i] = vector
        return results  # type: ignore[return-value]
