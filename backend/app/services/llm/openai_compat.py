"""One client for every provider: Gemini, Groq, Ollama (and OpenRouter, Cerebras, vLLM...)
all serve the OpenAI chat-completions protocol. No SDKs, so no SDK churn."""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import BaseModel

from app.services.llm.base import Completion, LLMUnavailable, Messages, Served, StreamPart, Usage

THINK_OPEN, THINK_CLOSE = "<think>", "</think>"


class ThinkStripper:
    """Drops <think>...</think> blocks that reasoning models (Qwen3, DeepSeek-R1 distills)
    put in the content, including tags split across stream deltas."""

    def __init__(self) -> None:
        self._pending = ""
        self._inside = False

    def feed(self, text: str) -> str:
        self._pending += text
        out = []
        while self._pending:
            if self._inside:
                end = self._pending.find(THINK_CLOSE)
                if end < 0:
                    # Keep a possible partial closing tag, drop the rest of the thinking.
                    self._pending = self._pending[-(len(THINK_CLOSE) - 1) :]
                    break
                self._pending = self._pending[end + len(THINK_CLOSE) :].lstrip("\n")
                self._inside = False
            else:
                start = self._pending.find(THINK_OPEN)
                if start >= 0:
                    out.append(self._pending[:start])
                    self._pending = self._pending[start + len(THINK_OPEN) :]
                    self._inside = True
                    continue
                hold = _partial_suffix(self._pending, THINK_OPEN)
                out.append(self._pending[: len(self._pending) - hold])
                self._pending = self._pending[len(self._pending) - hold :]
                break
        return "".join(out)

    def flush(self) -> str:
        rest, self._pending = ("" if self._inside else self._pending), ""
        return rest


def _partial_suffix(text: str, tag: str) -> int:
    """Length of the longest suffix of `text` that is a proper prefix of `tag`."""
    for size in range(min(len(tag) - 1, len(text)), 0, -1):
        if tag.startswith(text[-size:]):
            return size
    return 0


def _usage(data: dict[str, Any]) -> Usage | None:
    usage = data.get("usage") or (data.get("x_groq") or {}).get("usage")
    if not usage:
        return None
    return Usage(usage.get("prompt_tokens"), usage.get("completion_tokens"))


class OpenAICompatible:
    def __init__(
        self,
        provider: str,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_s: float = 60,
        transport: httpx.AsyncBaseTransport | None = None,  # tests pass a MockTransport
        extra: dict[str, Any] | None = None,  # provider-specific request fields
    ) -> None:
        self.provider = provider
        self.model = model
        self.name = f"{provider}:{model}"
        self._extra = extra or {}
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            # Streams can be long; the read timeout applies between chunks, not in total.
            timeout=httpx.Timeout(timeout_s, connect=10),
            transport=transport,
        )

    def _payload(self, messages: Messages, temperature: float, max_tokens: int | None) -> dict:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            **self._extra,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        return payload

    async def _raise_for(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        body = (await response.aread()).decode("utf-8", "replace")[:300]
        raise LLMUnavailable(
            f"{self.name} returned HTTP {response.status_code}: {body}", response.status_code
        )

    async def stream(
        self, messages: Messages, *, temperature: float = 0.2, max_tokens: int | None = None
    ) -> AsyncIterator[StreamPart]:
        payload = self._payload(messages, temperature, max_tokens) | {"stream": True}
        stripper = ThinkStripper()
        served = False
        try:
            async with self._client.stream("POST", "/chat/completions", json=payload) as response:
                await self._raise_for(response)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if "error" in chunk:
                        raise LLMUnavailable(f"{self.name}: {chunk['error']}")
                    for choice in chunk.get("choices") or []:
                        text = stripper.feed((choice.get("delta") or {}).get("content") or "")
                        if text:
                            if not served:
                                served = True
                                yield Served(self.name)
                            yield text
                    usage = _usage(chunk)
                    if usage is not None:
                        yield usage
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"{self.name} unreachable: {exc!r}") from exc
        except json.JSONDecodeError as exc:
            raise LLMUnavailable(f"{self.name} sent a malformed stream: {exc}") from exc
        tail = stripper.flush()
        if not served:
            yield Served(self.name)
        if tail:
            yield tail

    async def complete(
        self,
        messages: Messages,
        *,
        schema: type[BaseModel] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> Completion:
        payload = self._payload(messages, temperature, max_tokens)
        formats: list[dict | None] = [None]
        if schema is not None:
            # Strict schema where the provider supports it, plain JSON mode where it does not.
            formats = [
                {
                    "type": "json_schema",
                    "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
                },
                {"type": "json_object"},
            ]
        last_error: LLMUnavailable | None = None
        for response_format in formats:
            body = payload | ({"response_format": response_format} if response_format else {})
            try:
                response = await self._client.post("/chat/completions", json=body)
                await self._raise_for(response)
                data = response.json()
            except httpx.HTTPError as exc:
                raise LLMUnavailable(f"{self.name} unreachable: {exc!r}") from exc
            except LLMUnavailable as exc:
                last_error = exc
                if exc.status == 400 and response_format is not formats[-1]:
                    continue  # this provider rejects the schema form; try the next one
                raise
            choices = data.get("choices") or []
            text = ((choices[0].get("message") or {}).get("content") or "") if choices else ""
            stripper = ThinkStripper()
            text = (stripper.feed(text) + stripper.flush()).strip()
            return Completion(text, self.name, _usage(data))
        raise last_error or LLMUnavailable(f"{self.name}: no response")
