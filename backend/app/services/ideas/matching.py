"""Does any project implement this idea? Retrieval over the absence of things.

A search engine always returns *something*, ranked; it cannot say "nothing here". This needs
absolute evidence per project, so two signals that each mean something on their own:

  coverage    Which of the words that make the idea distinctive occur in the project's code
              and docs, weighted by rarity (IDF over every chunk). "robots", "crawler" and
              "broken" in link-checker say more than "tool" and "use" anywhere. Needs no
              model, and it can explain itself: matched words, missing words.
  similarity  The cross-encoder's score for the idea against the project's best chunk
              (sigmoid, 0..1), when the reranker is up. Catches the paraphrase coverage
              misses ("drag cards between columns" vs `moveTask`).

A project whose signals clear the thresholds implements the idea (or partly does); the idea
is "never implemented" only when no project comes close on any signal. The thresholds lean
towards finding an implementation: a false "you never built this" about something you did
build is the error that costs the feature its credibility.
"""

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import bindparam, func, select, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Text

from app.config import settings
from app.db.models import Chunk, Node
from app.schemas.search import SearchRequest
from app.services.embedding.factory import get_reranker
from app.services.retrieval.search import search

log = logging.getLogger(__name__)

MIN_LEXEME = 3
MAX_TERMS = 24
# A word in more than this share of all chunks tells nothing about any one idea. Small
# corpora keep a floor, or a 200-chunk fixture would lose half its vocabulary.
MAX_DF_SHARE = 0.05
MIN_DF_CAP = 25
SEARCH_K = 30
CANDIDATES_SHOWN = 3

# Each stemmed lexeme with the word it came from: search runs on "quantiz", people read
# "quantization".
_LEXEMES = text(
    "SELECT lower(d.token) AS word, l.lexeme FROM ts_debug('english', :t) AS d, "
    "unnest(d.lexemes) AS l(lexeme)"
)
_DF = text(
    """
    SELECT l.lexeme, count(c.id) AS df
    FROM unnest(:lexemes) AS l(lexeme)
    LEFT JOIN chunks c ON c.tsv @@ CAST(quote_literal(l.lexeme) AS tsquery)
    GROUP BY l.lexeme
    """
).bindparams(bindparam("lexemes", type_=ARRAY(Text)))
_WHERE = text(
    """
    SELECT DISTINCT l.lexeme, d.id AS document_id, d.source_id, d.path
    FROM unnest(:lexemes) AS l(lexeme)
    JOIN chunks c ON c.tsv @@ CAST(quote_literal(l.lexeme) AS tsquery)
    JOIN documents d ON d.id = c.document_id
    """
).bindparams(bindparam("lexemes", type_=ARRAY(Text)))


@dataclass(frozen=True)
class ProjectScope:
    id: int
    name: str
    source_id: int
    root: str

    def contains(self, source_id: int, path: str) -> bool:
        return source_id == self.source_id and (
            self.root == "" or path == self.root or path.startswith(self.root + "/")
        )


class Projects:
    """Every project, and which one (the deepest) a file belongs to."""

    def __init__(self, scopes: list[ProjectScope]) -> None:
        self.all = scopes
        self._by_source: dict[int, list[ProjectScope]] = defaultdict(list)
        for scope in sorted(scopes, key=lambda s: -len(s.root)):
            self._by_source[scope.source_id].append(scope)

    def owner(self, source_id: int, path: str) -> ProjectScope | None:
        return next(
            (p for p in self._by_source.get(source_id, []) if p.contains(source_id, path)), None
        )

    @classmethod
    async def load(cls, session: AsyncSession) -> "Projects":
        rows = (
            await session.execute(
                select(Node.id, Node.name, Node.source_id, Node.meta).where(
                    Node.kind == "project", Node.source_id.is_not(None)
                )
            )
        ).all()
        return cls(
            [ProjectScope(r.id, r.name, r.source_id, (r.meta or {}).get("root", "")) for r in rows]
        )


@dataclass
class Term:
    lexeme: str
    word: str
    df: int
    idf: float


@dataclass
class Candidate:
    project: ProjectScope
    coverage: float = 0.0
    matched: list[str] = field(default_factory=list)
    similarity: float | None = None
    best: dict[str, Any] | None = None  # the chunk that looks most like the idea
    best_document: dict[str, Any] | None = None  # the file with the most of its words
    linked: bool = False

    @property
    def closeness(self) -> float:
        return max(self.coverage, self.similarity or 0.0)

    def level(self) -> str | None:
        s = settings
        sim = self.similarity if self.similarity is not None else -1.0
        if self.coverage >= s.idea_coverage_implemented or sim >= s.idea_similarity_implemented:
            return "implemented"
        if (
            self.coverage >= s.idea_coverage_partial
            or sim >= s.idea_similarity_partial
            or self.linked
        ):
            return "partial"
        return None

    def out(self) -> dict[str, Any]:
        return {
            "project_id": self.project.id,
            "project": self.project.name,
            "coverage": round(self.coverage, 3),
            "similarity": None if self.similarity is None else round(self.similarity, 3),
            "matched": self.matched,
            "linked": self.linked,
            "best": self.best,
            "best_document": self.best_document,
        }


@dataclass
class Match:
    status: str  # implemented | partial | unimplemented
    project: ProjectScope | None
    score: float
    details: dict[str, Any]


async def corpus_size(session: AsyncSession) -> int:
    return (await session.execute(select(func.count(Chunk.id)))).scalar_one()


async def informative_terms(session: AsyncSession, idea_text: str, total: int) -> list[Term]:
    """The idea's words (stemmed as the index stems them) that are rare enough to count."""
    words: dict[str, str] = {}
    for row in (await session.execute(_LEXEMES, {"t": idea_text})).all():
        if len(row.lexeme) >= MIN_LEXEME and not row.lexeme.isdigit():
            words.setdefault(row.lexeme, row.word)
    if not words:
        return []
    rows = (await session.execute(_DF, {"lexemes": list(words)})).all()
    cap = max(total * MAX_DF_SHARE, MIN_DF_CAP)
    terms = [
        Term(r.lexeme, words[r.lexeme], r.df, math.log((total + 1) / (r.df + 0.5)))
        for r in rows
        if r.df <= cap
    ]
    terms.sort(key=lambda t: (-t.idf, t.lexeme))
    return terms[:MAX_TERMS]


async def coverage(
    session: AsyncSession, terms: list[Term], projects: Projects
) -> dict[int, Candidate]:
    """Per project: the IDF-weighted share of the idea's terms found anywhere in it, and the
    single file holding the largest share (the one to show as evidence)."""
    candidates: dict[int, Candidate] = {}
    total = sum(t.idf for t in terms)
    if not terms or total <= 0:
        return candidates
    idf = {t.lexeme: t.idf for t in terms}
    word = {t.lexeme: t.word for t in terms}
    in_project: dict[int, set[str]] = defaultdict(set)
    in_document: dict[tuple[int, int], set[str]] = defaultdict(set)
    paths: dict[int, str] = {}
    scopes: dict[int, ProjectScope] = {}
    for row in (await session.execute(_WHERE, {"lexemes": list(idf)})).all():
        project = projects.owner(row.source_id, row.path)
        if project is None:  # notes, papers: the idea itself lives there
            continue
        scopes[project.id] = project
        in_project[project.id].add(row.lexeme)
        in_document[(project.id, row.document_id)].add(row.lexeme)
        paths[row.document_id] = row.path
    best_doc: dict[int, tuple[float, int]] = {}
    for (project_id, document_id), lexemes in in_document.items():
        share = sum(idf[lx] for lx in lexemes) / total
        if share > best_doc.get(project_id, (-1.0, 0))[0]:
            best_doc[project_id] = (share, document_id)
    for project_id, lexemes in in_project.items():
        share, document_id = best_doc[project_id]
        candidates[project_id] = Candidate(
            scopes[project_id],
            coverage=sum(idf[lx] for lx in lexemes) / total,
            matched=[word[lx] for lx in sorted(lexemes, key=lambda lx: (-idf[lx], lx))],
            best_document={
                "document_id": document_id,
                "path": paths[document_id],
                "coverage": round(share, 3),
            },
        )
    return candidates


async def similarity(
    session: AsyncSession, idea_text: str, projects: Projects, candidates: dict[int, Candidate]
) -> str | None:
    """The best chunk per project for the idea, from the normal search pipeline. With a
    reranker its score is the similarity signal; without one the chunk is still evidence.
    Returns the search mode that ran, or None if search could not run."""
    reranking = get_reranker() is not None
    result = await search(
        session,
        SearchRequest(q=idea_text[:1000], k=SEARCH_K, mode="rerank" if reranking else "hybrid"),
    )
    scored = reranking and not any(d.startswith("rerank") for d in result.degraded)
    for hit in result.hits:
        project = projects.owner(hit.source_id, hit.path)
        if project is None:
            continue
        candidate = candidates.setdefault(project.id, Candidate(project))
        if candidate.best is not None:
            continue  # hits are best first
        candidate.best = {
            "chunk_id": hit.chunk_id,
            "document_id": hit.document_id,
            "path": hit.path,
            "symbol": hit.symbol,
            "start_line": hit.start_line,
            "end_line": hit.end_line,
        }
        if scored and hit.rerank_score is not None:
            candidate.similarity = hit.rerank_score
    return result.mode if scored else None


def decide(candidates: dict[int, Candidate], terms: list[Term], signals: list[str]) -> Match:
    ranked = sorted(
        candidates.values(),
        key=lambda c: (
            {"implemented": 0, "partial": 1, None: 2}[c.level()],
            -c.closeness,
            c.project.name,
        ),
    )
    best = ranked[0] if ranked else None
    level = best.level() if best else None
    matched = set(best.matched) if best else set()
    details = {
        "signals": signals,
        "terms": [{"term": t.word, "idf": round(t.idf, 2), "df": t.df} for t in terms],
        "missing": [t.word for t in terms if t.word not in matched],
        "candidates": [c.out() for c in ranked[:CANDIDATES_SHOWN]],
        "thresholds": {
            "coverage": [settings.idea_coverage_partial, settings.idea_coverage_implemented],
            "similarity": [settings.idea_similarity_partial, settings.idea_similarity_implemented],
        },
    }
    if best is None or level is None:
        return Match("unimplemented", None, best.closeness if best else 0.0, details)
    return Match(level, best.project, best.closeness, details)


async def match_idea(
    session: AsyncSession,
    idea_text: str,
    projects: Projects,
    total_chunks: int,
    linked_projects: set[int] = frozenset(),  # type: ignore[assignment]
) -> Match:
    terms = await informative_terms(session, idea_text, total_chunks)
    candidates = await coverage(session, terms, projects)
    signals = ["coverage"]
    try:
        mode = await similarity(session, idea_text, projects, candidates)
        if mode == "rerank":
            signals.append("similarity")
    except Exception:  # evidence is a nicety; coverage alone still decides
        log.exception("idea similarity search failed")
    for scope in projects.all:
        if scope.id in linked_projects:
            candidates.setdefault(scope.id, Candidate(scope)).linked = True
    return decide(candidates, terms, signals)
