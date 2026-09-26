"""The Chat interface. Model identity is configuration; callers never know which provider
answered until it tells them (the `Served` marker at the start of a stream)."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

Messages = list[dict[str, str]]  # [{"role": "system" | "user" | "assistant", "content": ...}]


class LLMUnavailable(RuntimeError):
    """No answer from this model: unreachable, rate limited, bad key, or a server error.
    The fallback chain moves on to the next provider."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True)
class Served:
    """First item of every stream: the model that is answering."""

    model: str


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    usage: Usage | None = None


StreamPart = str | Usage | Served


class ChatModel(Protocol):
    name: str  # "<provider>:<model>"

    def stream(
        self, messages: Messages, *, temperature: float = 0.2, max_tokens: int | None = None
    ) -> AsyncIterator[StreamPart]:
        """Text deltas as they arrive; possibly a Usage at the end."""
        ...

    async def complete(
        self,
        messages: Messages,
        *,
        schema: type[BaseModel] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> Completion:
        """One full response. With `schema`, the provider is asked for JSON matching it
        (structured output where supported); callers still validate."""
        ...
