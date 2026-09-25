from typing import Literal, Protocol

InputType = Literal["query", "document"]


class ModelUnavailable(RuntimeError):
    """The model backend could not be reached or failed. Callers degrade instead of crashing."""


class Embedder(Protocol):
    @property
    def dim(self) -> int: ...

    async def model_name(self) -> str: ...

    async def embed(self, texts: list[str], input_type: InputType) -> list[list[float]]: ...


class Reranker(Protocol):
    async def model_name(self) -> str: ...

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        """One relevance score per document, in input order. Higher is more relevant."""
        ...
