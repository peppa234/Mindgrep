"""Finding ideas in notes, deterministically. What a person marked as an idea, and nothing else:

  * a note tagged #idea, typed `type: idea` in its frontmatter, or kept in an `ideas/` folder
    is one idea: its title, and its first paragraph as the summary;
  * a line in any other note that starts with "Idea:" (as a list item or heading too) is one
    idea: the sentence after the colon, with the rest of its paragraph.

The frontmatter may also say what became of it (`status: done`, `status: abandoned`) and
where (`implemented_by: task-board`). That is a declaration, and it outranks matching.
Ideas nobody marked are the LLM layer's job (services/ideas/extract.py), fenced in the same
way concept extraction is.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import PurePosixPath
from typing import Any

from app.services.graph.technologies import normalize
from app.services.parsing.markdown import FENCED_BLOCK_RE, FRONTMATTER_RE, WIKILINK_RE

IDEA_TAGS = {"idea", "ideas", "project-idea", "project-ideas", "someday"}
IDEA_DIRS = {"idea", "ideas", "project-ideas", "someday"}
NOT_AN_IDEA = {"readme", "index", "_index", "overview", "template"}  # the folder's own index
TYPE_KEYS = ("type", "kind", "category")
DATE_KEYS = ("created", "date", "created_at", "written", "day")
PROJECT_KEYS = ("implemented_by", "implemented_in", "project", "repo", "repository")
DECLARED = {
    "implemented": "implemented", "done": "implemented", "shipped": "implemented",
    "built": "implemented", "complete": "implemented", "completed": "implemented",
    "finished": "implemented", "live": "implemented",
    "partial": "partial", "wip": "partial", "in progress": "partial", "in-progress": "partial",
    "started": "partial", "prototype": "partial", "prototyped": "partial", "mvp": "partial",
    "abandoned": "abandoned", "dropped": "abandoned", "dead": "abandoned",
    "wontfix": "abandoned", "won't do": "abandoned", "cancelled": "abandoned",
    "canceled": "abandoned", "shelved": "abandoned", "killed": "abandoned",
}  # fmt: skip

INLINE_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s+|[-*+]\s+(?:\[[ xX]\]\s+)?)?(?:\*\*|__)?idea(?:\*\*|__)?"
    r"(?:\s*[:：]|\s+[—–-]\s+)\s*(?:\*\*|__)?\s*(?P<text>\S.*)$",
    re.IGNORECASE,
)
_LIST_OR_HEADING = re.compile(r"^\s{0,3}(?:[-*+]\s|\d+[.)]\s|#{1,6}\s|>)")
_MARKUP = re.compile(r"(\*\*|__|`|~~)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
MAX_SUMMARY = 600
MAX_TITLE = 90
MIN_INLINE_WORDS = 3


@dataclass
class NoteDoc:
    """What detection needs of a Markdown document that belongs to no project."""

    id: int
    path: str
    title: str | None
    meta: dict[str, Any]
    modified_at: datetime | None = None


@dataclass
class IdeaDraft:
    key: str
    document_id: int
    title: str
    summary: str
    extractor: str  # note | inline
    line: int | None
    evidence: str | None
    written_on: date | None
    declared_status: str | None = None
    declared_project: str | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """What matching compares against the projects."""
        return f"{self.title}. {self.summary}".strip()


def _plain(text: str) -> str:
    text = WIKILINK_RE.sub(lambda m: m.group(1), text)
    text = _LINK.sub(lambda m: m.group(1), text)
    return re.sub(r"\s+", " ", _MARKUP.sub("", text)).strip()


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _first(frontmatter: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if frontmatter.get(key) not in (None, "", []):
            return frontmatter[key]
    return None


def declared_status(frontmatter: dict[str, Any]) -> str | None:
    value = frontmatter.get("status")
    if not isinstance(value, str):
        return None
    return DECLARED.get(value.strip().lower())


def declared_project(frontmatter: dict[str, Any]) -> str | None:
    value = _first(frontmatter, PROJECT_KEYS)
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, str):
        return None
    return _plain(value).strip("[] ") or None


def is_idea_note(doc: NoteDoc) -> bool:
    path = PurePosixPath(doc.path)
    if path.stem.lower() in NOT_AN_IDEA:
        return False
    tags = {str(t).lower() for t in doc.meta.get("tags") or []}
    if tags & IDEA_TAGS:
        return True
    frontmatter = doc.meta.get("frontmatter") or {}
    if any(str(frontmatter.get(k, "")).lower() == "idea" for k in TYPE_KEYS):
        return True
    return any(part.lower() in IDEA_DIRS for part in path.parts[:-1])


def _body(text: str) -> tuple[list[str], int]:
    """The note's lines after the frontmatter, and how many lines the frontmatter took."""
    match = FRONTMATTER_RE.match(text)
    offset = text[: match.end()].count("\n") if match else 0
    body = text[match.end() :] if match else text
    return [line.rstrip("\r") for line in body.split("\n")], offset


def _blank_fences(lines: list[str]) -> list[str]:
    """Code blocks are not prose: an `idea:` key in a YAML sample is not an idea."""
    joined = "\n".join(lines)
    return FENCED_BLOCK_RE.sub(lambda m: "\n" * m.group(0).count("\n"), joined).split("\n")


def summary_of(lines: list[str]) -> str:
    """The first paragraph of prose under the title: headings, tag lines and lists skipped."""
    paragraph: list[str] = []
    for line in _blank_fences(lines):
        stripped = line.strip()
        if not stripped:
            if paragraph:
                break
            continue
        if _LIST_OR_HEADING.match(line) or re.fullmatch(r"(#[\w/-]+\s*)+", stripped):
            if paragraph:
                break
            continue
        paragraph.append(stripped)
    return _plain(" ".join(paragraph))[:MAX_SUMMARY]


def _title_from(text: str) -> str:
    """A short title for an inline idea: its first clause, when that says enough."""
    sentence = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0].rstrip(".!? ")
    clause = re.split(r",|;|\s+so\s+(?:that\s+)?|\s+because\s+", sentence, maxsplit=1)[0]
    title = clause if len(clause.split()) >= 4 else sentence
    if len(title) > MAX_TITLE:
        title = title[:MAX_TITLE].rsplit(" ", 1)[0] + "…"
    return title[:1].upper() + title[1:]


def inline_ideas(doc: NoteDoc, lines: list[str], offset: int) -> list[IdeaDraft]:
    found: list[IdeaDraft] = []
    prose = _blank_fences(lines)
    i = 0
    while i < len(prose):
        match = INLINE_RE.match(prose[i])
        if not match:
            i += 1
            continue
        parts = [match.group("text").strip()]
        j = i + 1
        # The paragraph continues on hard-wrapped lines, up to a blank line or a new item.
        while j < len(prose) and prose[j].strip() and not _LIST_OR_HEADING.match(prose[j]):
            parts.append(prose[j].strip())
            j += 1
        text = _plain(" ".join(parts))
        if len(text.split()) >= MIN_INLINE_WORDS:
            title = _title_from(text)
            found.append(
                IdeaDraft(
                    key=f"line:{doc.path}:{normalize(title)[:120]}",
                    document_id=doc.id,
                    title=title,
                    summary=text[:MAX_SUMMARY],
                    extractor="inline",
                    line=offset + i + 1,
                    evidence=lines[i].strip()[:500],
                    written_on=None,
                )
            )
        i = j
    return found


def detect(doc: NoteDoc, text: str) -> list[IdeaDraft]:
    """The ideas in one note: the note itself, or the "Idea:" lines inside it."""
    lines, offset = _body(text)
    frontmatter = doc.meta.get("frontmatter") or {}
    written_on = _date(_first(frontmatter, DATE_KEYS)) or (
        doc.modified_at.date() if doc.modified_at else None
    )
    tags = sorted({str(t).lower() for t in doc.meta.get("tags") or []})
    if is_idea_note(doc):
        title = _plain(doc.title or PurePosixPath(doc.path).stem)
        drafts = [
            IdeaDraft(
                key=f"note:{doc.path}",
                document_id=doc.id,
                title=title,
                summary=summary_of(lines),
                extractor="note",
                line=None,
                evidence=None,
                written_on=written_on,
                declared_status=declared_status(frontmatter),
                declared_project=declared_project(frontmatter),
            )
        ]
    else:
        drafts = inline_ideas(doc, lines, offset)
    seen: set[str] = set()
    out = []
    for draft in drafts:
        if draft.key in seen:
            continue
        seen.add(draft.key)
        draft.written_on = draft.written_on or written_on
        draft.tags = tags
        out.append(draft)
    return out
