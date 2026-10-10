"""Which chat models exist is configuration: LLM_PROVIDERS lists them in fallback order, and a
provider without its key (or, for Ollama, a model name) is simply not in the chain."""

from functools import cache

from app.config import settings
from app.services.llm.base import ChatModel
from app.services.llm.fake import FakeChat
from app.services.llm.openai_compat import OpenAICompatible
from app.services.llm.router import FallbackChat


def _gemini() -> list[ChatModel]:
    """gemini_model, then each fallback model: one overloaded Gemini model (503 "high demand")
    rarely means all of them are."""
    effort = settings.gemini_reasoning_effort
    extra = {"reasoning_effort": effort} if effort else {}
    fallbacks = (m.strip() for m in settings.gemini_fallback_models.split(","))
    names = [settings.gemini_model, *fallbacks]
    unique = list(dict.fromkeys(n for n in names if n))
    return [
        OpenAICompatible(
            "gemini",
            settings.gemini_base_url,
            model,
            settings.gemini_api_key,
            settings.gemini_timeout_s,
            extra=extra,
        )
        for model in unique
    ]


def _provider(name: str) -> list[ChatModel]:
    timeout = settings.llm_timeout_s
    if name == "fake":
        return [FakeChat()]
    if name == "gemini" and settings.gemini_api_key:
        return _gemini()
    if name == "groq" and settings.groq_api_key:
        return [
            OpenAICompatible(
                "groq", settings.groq_base_url, settings.groq_model, settings.groq_api_key, timeout
            )
        ]
    if name == "ollama" and settings.ollama_model:
        return [
            OpenAICompatible("ollama", settings.ollama_base_url, settings.ollama_model, "", timeout)
        ]
    return []


def _chain(spec: str) -> FallbackChat | None:
    names = [n.strip().lower() for n in spec.split(",") if n.strip()]
    models = [m for n in names for m in _provider(n)]
    return FallbackChat(models) if models else None


@cache
def get_chat() -> FallbackChat | None:
    """The model that writes answers. None when no provider is configured."""
    return _chain(settings.llm_providers)


@cache
def get_extraction_chat() -> FallbackChat | None:
    """The model for bulk extraction; defaults to the answer chain."""
    return _chain(settings.extraction_providers or settings.llm_providers)
