"""A deterministic stand-in model: no network, no key, same answer every time.

Tests and CI use it the way they use the hashing embedder. It is extractive, not clever:
it answers from the first numbered source with a citation, says NO_ANSWER when there are no
sources, echoes the last message when asked to condense, and extracts only the curated
technology names it can see when asked for concepts. Enough to exercise every code path.
"""

import json
import re
from collections.abc import AsyncIterator

from pydantic import BaseModel

from app.services.llm.base import Completion, Messages, Served, StreamPart, Usage

SOURCE_RE = re.compile(r"^\[(\d+)\] (.+)$", re.MULTILINE)


class FakeChat:
    name = "fake:extractive"

    def _answer(self, messages: Messages) -> str:
        prompt = messages[-1]["content"]
        sources = SOURCE_RE.findall(prompt)
        if not sources:
            return "NO_ANSWER"
        number, header = sources[0]
        text = f"The closest match is {header.split(' · ')[0]} [{number}]."
        if len(sources) > 1:
            text += f" See also [{sources[1][0]}]."
        return text

    async def stream(
        self, messages: Messages, *, temperature: float = 0.2, max_tokens: int | None = None
    ) -> AsyncIterator[StreamPart]:
        yield Served(self.name)
        for word in re.findall(r"\S+\s*", self._answer(messages)):
            yield word
        yield Usage(sum(len(m["content"]) for m in messages) // 4, None)

    async def complete(
        self,
        messages: Messages,
        *,
        schema: type[BaseModel] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> Completion:
        prompt = messages[-1]["content"]
        if schema is not None and schema.__name__ == "ConceptExtraction":
            return Completion(json.dumps(_concepts(prompt)), self.name)
        match = re.search(r"^Last message: (.+)$", prompt, re.MULTILINE)
        if match:
            return Completion(match.group(1).strip(), self.name)
        return Completion(self._answer(messages), self.name)


def _concepts(prompt: str) -> dict:
    from app.services.graph import technologies
    from app.services.graph.queries import ngrams

    text = prompt.split("Text:", 1)[-1]
    found: dict[str, dict] = {}
    for line in text.splitlines():
        for candidate in ngrams(line, longest=2):
            tech = technologies.by_name(candidate)
            if tech is not None and tech.category != "language" and len(candidate) > 2:
                found.setdefault(
                    tech.name,
                    {"name": candidate, "kind": "technology", "evidence": line.strip()[:200]},
                )
    return {"concepts": list(found.values())[:15]}
