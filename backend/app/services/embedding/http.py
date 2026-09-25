"""Clients for the model server (app/modelserver). Keeps torch out of the api/worker images."""

import httpx

from app.services.embedding.base import InputType, ModelUnavailable


class _ModelServerClient:
    def __init__(self, base_url: str, timeout_s: float) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_s)
        self._info: dict | None = None

    async def info(self) -> dict:
        if self._info is None:
            self._info = await self._request("GET", "/info")
        return self._info

    async def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        try:
            response = await self._client.request(method, path, json=json)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            self._info = None  # the server may come back with a different model
            raise ModelUnavailable(
                f"model server at {self._client.base_url} unavailable: {exc!r}"
            ) from exc


class HttpEmbedder(_ModelServerClient):
    def __init__(self, base_url: str, timeout_s: float, dim: int) -> None:
        super().__init__(base_url, timeout_s)
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    async def model_name(self) -> str:
        info = await self.info()
        if info["embedding_dim"] != self._dim:
            raise ModelUnavailable(
                f"model server embeds at {info['embedding_dim']} dims, "
                f"the index expects {self._dim}"
            )
        return info["embedding_model"]

    async def embed(self, texts: list[str], input_type: InputType) -> list[list[float]]:
        if not texts:
            return []
        await self.model_name()
        data = await self._request("POST", "/embed", {"texts": texts, "input_type": input_type})
        return data["vectors"]


class HttpReranker(_ModelServerClient):
    async def model_name(self) -> str:
        return (await self.info())["reranker_model"]

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        data = await self._request("POST", "/rerank", {"query": query, "documents": documents})
        return data["scores"]
