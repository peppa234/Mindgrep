"""Fallback across providers. Free tiers change monthly and rate-limit daily; the code that
asks for an answer should not care which of them gave it."""

import logging
import time
from collections.abc import AsyncIterator

from pydantic import BaseModel

from app.services.llm.base import (
    ChatModel,
    Completion,
    LLMUnavailable,
    Messages,
    Served,
    StreamPart,
)

log = logging.getLogger(__name__)

# A provider that answered 429 is skipped for this long, instead of being asked (and failing)
# again on every request while its quota refills.
RATE_LIMIT_COOLDOWN_S = 60.0


class FallbackChat:
    def __init__(self, models: list[ChatModel]) -> None:
        if not models:
            raise ValueError("FallbackChat needs at least one model")
        self.models = models
        self.name = " -> ".join(m.name for m in models)
        self._cooling: dict[str, float] = {}

    def _order(self) -> list[ChatModel]:
        now = time.monotonic()
        ready = [m for m in self.models if self._cooling.get(m.name, 0) <= now]
        cooling = [m for m in self.models if m not in ready]
        return ready + cooling  # everything cooling down is still a last resort

    def _failed(self, model: ChatModel, exc: LLMUnavailable, errors: list[str]) -> None:
        if exc.status == 429:
            self._cooling[model.name] = time.monotonic() + RATE_LIMIT_COOLDOWN_S
        log.warning("chat model %s failed: %s", model.name, exc)
        errors.append(str(exc))

    async def stream(
        self, messages: Messages, *, temperature: float = 0.2, max_tokens: int | None = None
    ) -> AsyncIterator[StreamPart]:
        errors: list[str] = []
        for model in self._order():
            started = False
            try:
                async for part in model.stream(
                    messages, temperature=temperature, max_tokens=max_tokens
                ):
                    if isinstance(part, Served):
                        started = True
                    yield part
                return
            except LLMUnavailable as exc:
                if started:
                    raise  # half an answer from one model cannot be finished by another
                self._failed(model, exc, errors)
        raise LLMUnavailable("every chat model failed: " + " | ".join(errors))

    async def complete(
        self,
        messages: Messages,
        *,
        schema: type[BaseModel] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> Completion:
        errors: list[str] = []
        for model in self._order():
            try:
                return await model.complete(
                    messages, schema=schema, temperature=temperature, max_tokens=max_tokens
                )
            except LLMUnavailable as exc:
                self._failed(model, exc, errors)
        raise LLMUnavailable("every chat model failed: " + " | ".join(errors))
