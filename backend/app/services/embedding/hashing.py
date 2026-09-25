"""A deterministic, model-free embedder: signed feature hashing of words and identifier parts.

It is a bag-of-words in vector form, so it is weak at paraphrase, but it is fast, needs no
download, and gives CI a reproducible vector channel to test the full hybrid pipeline with.
"""

import hashlib
import math
import re

from app.services.chunking.identifiers import IDENTIFIER_RE, split_identifier
from app.services.embedding.base import InputType

_WORD_RE = re.compile(r"[a-z0-9]+")


def _features(text: str) -> list[str]:
    words = _WORD_RE.findall(text.lower())
    for ident in IDENTIFIER_RE.findall(text):
        words.extend(split_identifier(ident))
    return [w for w in words if len(w) > 1]


class HashEmbedder:
    MODEL = "hash-v1"

    def __init__(self, dim: int) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    async def model_name(self) -> str:
        return self.MODEL

    def embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        for feature in _features(text):
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self._dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    async def embed(self, texts: list[str], input_type: InputType) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]
