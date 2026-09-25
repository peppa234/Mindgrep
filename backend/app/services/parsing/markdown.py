"""Markdown notes: frontmatter, title, wikilinks, tags, then heading-aware chunks."""

import re
from datetime import date, datetime
from typing import Any

import yaml

from app.services.chunking.text_chunker import chunk_markdown
from app.services.chunking.types import ParsedDocument

FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]|#\n]+)(?:#[^\]|\n]*)?(?:\|[^\]\n]*)?\]\]")
TAG_RE = re.compile(r"(?<![\w&/#])#([A-Za-z][\w/-]{1,50})")
H1_RE = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.MULTILINE)
FENCED_BLOCK_RE = re.compile(r"^(```|~~~).*?^\1", re.DOTALL | re.MULTILINE)


def _jsonable(value: Any) -> Any:
    """YAML parses dates into date objects; JSONB wants strings."""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def parse_markdown(text: str, path: str) -> ParsedDocument:
    frontmatter: dict[str, Any] = {}
    offset = 0
    body = text
    match = FRONTMATTER_RE.match(text)
    if match:
        try:
            loaded = yaml.safe_load(match.group(1))
            if isinstance(loaded, dict):
                frontmatter = _jsonable(loaded)
        except yaml.YAMLError:
            pass  # Malformed frontmatter is still stripped from the body, just not parsed.
        offset = text[: match.end()].count("\n")
        body = text[match.end() :]

    h1 = H1_RE.search(FENCED_BLOCK_RE.sub("", body))
    stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    title = str(frontmatter.get("title") or (h1.group(1) if h1 else None) or stem)

    prose = FENCED_BLOCK_RE.sub("", body)
    links = sorted({m.group(1).strip() for m in WIKILINK_RE.finditer(prose)})
    tags = {m.group(1) for m in TAG_RE.finditer(prose)}
    fm_tags = frontmatter.get("tags") or []
    if isinstance(fm_tags, str):
        fm_tags = [t.strip() for t in re.split(r"[,\s]+", fm_tags) if t.strip()]
    tags |= {str(t).lstrip("#") for t in fm_tags}

    lines = [line.rstrip("\r") for line in body.split("\n")]
    chunks = chunk_markdown(lines, title=title, offset=offset)

    return ParsedDocument(
        kind="markdown",
        language="markdown",
        title=title,
        chunks=chunks,
        meta={"frontmatter": frontmatter, "links": links, "tags": sorted(tags)},
    )
