"""Prompts live in files named `<name>.v<version>.md`. The version is recorded with every
answer and every cached extraction, so a prompt change is visible in traces and invalidates
exactly the cached results it should."""

from dataclasses import dataclass
from functools import cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str  # "answer.v1"
    text: str


@cache
def load(name: str) -> Prompt:
    """The highest version of prompt `name`."""
    candidates = sorted(
        PROMPTS_DIR.glob(f"{name}.v*.md"), key=lambda p: int(p.name.split(".v")[1].split(".")[0])
    )
    if not candidates:
        raise FileNotFoundError(f"no prompt named {name!r} in {PROMPTS_DIR}")
    path = candidates[-1]
    return Prompt(name, path.name.removesuffix(".md"), path.read_text(encoding="utf-8").strip())
