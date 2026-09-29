"""'What ideas have I never implemented?', answered from the ideas table. No model writes it:
each idea cites the note (and line) it was written in, and an "unimplemented" verdict comes
with what was checked, so it can be disputed rather than trusted blindly."""

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.chat import ChatSource
from app.schemas.idea import IdeaOut
from app.services.chat.graph_answer import GraphAnswer
from app.services.graph import technologies
from app.services.graph.technologies import normalize
from app.services.ideas import queries

AI_TOPICS = {
    "ai", "a.i.", "ml", "machine learning", "deep learning", "llm", "llms", "nlp", "genai",
    "gen ai", "artificial intelligence", "ai/ml", "data science",
}  # fmt: skip
AI_TAGS = {"ai", "ml", "llm", "llms", "nlp", "rag", "machine-learning", "deep-learning", "genai"}
AI_WORDS = re.compile(
    r"\b(?:ai|ml|llms?|nlp|rag|retrieval[- ]augmented|machine\s+learning|deep\s+learning|"
    r"neural|embeddings?|language\s+models?|transformers?|gpt|agents?|chatbots?|"
    r"classif(?:y|ier|ication)|fine-?tun\w*|computer\s+vision|reinforcement\s+learning)\b",
    re.IGNORECASE,
)
SUMMARY_CHARS = 180
MISSING_SHOWN = 5
LISTED = 25
NOWHERE_NEAR = 0.05  # below this, naming the "closest" project would only mislead


def matches_topic(idea: IdeaOut, topic: str | None) -> bool:
    if not topic:
        return True
    text = f"{idea.title} {idea.summary}"
    tags = set(idea.tags)
    wanted = topic.lower().strip()
    if wanted in AI_TOPICS:
        return bool(tags & AI_TAGS) or bool(AI_WORDS.search(text))
    if normalize(topic) in {normalize(t) for t in tags}:
        return True
    tech = technologies.by_name(topic)
    names = {topic} | ({tech.name} if tech else set())
    return any(
        re.search(rf"\b{re.escape(name)}s?\b", text, re.IGNORECASE)
        or normalize(name) in {normalize(t) for t in tags}
        for name in names
    )


def _source(n: int, idea: IdeaOut) -> ChatSource:
    return ChatSource(
        n=n,
        kind="evidence",
        chunk_id=idea.chunk_id,
        document_id=idea.document_id,
        source_name=idea.source_name,
        path=idea.path,
        doc_kind="markdown",
        title=idea.title,
        symbol=f"line {idea.line}" if idea.line else None,
        start_line=idea.line,
        end_line=idea.line,
        content=idea.summary or idea.title,
        score=idea.score,
    )


def _short(text: str) -> str:
    if len(text) <= SUMMARY_CHARS:
        return text
    return text[:SUMMARY_CHARS].rsplit(" ", 1)[0] + "…"


def _when(idea: IdeaOut) -> str:
    return f", {idea.written_on.isoformat()}" if idea.written_on else ""


def _why_not(idea: IdeaOut) -> str:
    missing = ", ".join(idea.missing[:MISSING_SHOWN])
    closest = idea.closest
    if closest is None or closest.closeness < NOWHERE_NEAR:
        near = "no project comes close"
    else:
        near = f"closest: {closest.project}, {closest.coverage:.0%} of its distinctive words"
        if closest.similarity is not None:
            near += f", similarity {closest.similarity:.2f}"
    return f"{near}; nowhere in your code: *{missing}*" if missing else near


def _how_found(idea: IdeaOut) -> str:
    if idea.origin == "user":
        return "you marked it"
    if idea.origin == "declared":
        return "its note says so"
    closest = idea.closest
    if closest is None:
        return "matched"
    parts = [f"{closest.coverage:.0%} of its distinctive words"]
    if closest.similarity is not None:
        parts.append(f"similarity {closest.similarity:.2f}")
    if closest.linked:
        parts.append("linked from the note")
    return ", ".join(parts)


def _label(status: str) -> str:
    return {
        "unimplemented": "never implemented",
        "partial": "partly built",
        "implemented": "implemented",
        "abandoned": "abandoned",
    }[status]


async def ideas(session: AsyncSession, status: str, topic: str | None) -> GraphAnswer:
    every = await queries.list_ideas(session, "all", "oldest")
    pool = [i for i in every if matches_topic(i, topic)]
    about = f" about **{topic}**" if topic else ""
    if not every:
        return GraphAnswer(
            "I have not found any ideas in your notes yet. I look for notes tagged `#idea`, "
            "notes in an `ideas/` folder, and lines that start with `Idea:`."
        )
    if not pool:
        return GraphAnswer(f"None of your {len(every)} ideas is{about}.")

    sources: list[ChatSource] = []

    def cite(idea: IdeaOut) -> int:
        sources.append(_source(len(sources) + 1, idea))
        return len(sources)

    projects = (await queries.counts(session))["projects"]
    lines: list[str] = []
    wanted = (
        ["unimplemented", "partial", "implemented", "abandoned"] if status == "all" else [status]
    )
    for state in wanted:
        group = [i for i in pool if i.status == state]
        if status == "all" and not group:
            continue
        noun = "idea" if len(group) == 1 else "ideas"
        if state == "unimplemented":
            verb = "has" if len(group) == 1 else "have"
            head = (
                f"**{len(group)} of {len(pool)} ideas**{about} {verb} no implementation in "
                f"your {projects} indexed projects (oldest first):"
                if group
                else f"All {len(pool)} of your ideas{about} have an implementation, or were "
                "marked otherwise."
            )
        else:
            head = f"**{len(group)} {noun}**{about} {_label(state)}:"
            if not group:
                head = f"No idea{about} is {_label(state)}."
        lines += ["", head] if lines else [head]
        for idea in group[:LISTED]:
            n = cite(idea)
            if state == "unimplemented":
                lines.append(f"- **{idea.title}**{_when(idea)} [{n}]: {_short(idea.summary)}")
                lines.append(f"  ({_why_not(idea)})")
            elif state in ("implemented", "partial") and idea.project:
                lines.append(
                    f"- **{idea.title}**{_when(idea)} [{n}] → **{idea.project.name}** "
                    f"({_how_found(idea)})"
                )
            else:
                note = f": {idea.user_note}" if idea.user_note else ""
                lines.append(f"- **{idea.title}**{_when(idea)} [{n}]{note}")
        if len(group) > LISTED:
            lines.append(f"- … and {len(group) - LISTED} more on the Ideas page")

    if status == "unimplemented":
        started = [i for i in pool if i.status == "partial"]
        if started:
            names = ", ".join(
                f"**{i.title}** → {i.project.name if i.project else '?'} [{cite(i)}]"
                for i in started[:10]
            )
            lines += ["", f"Started but not finished: {names}."]
        signals = "their distinctive words were looked for in every project's code and docs"
        if any("similarity" in i.signals for i in pool):
            signals += ", and a reranker compared each idea with the closest code"
        lines += [
            "",
            f"How I checked: {signals}. If one of these exists after all, mark it on the "
            "Ideas page and I will remember.",
        ]
    return GraphAnswer("\n".join(lines), sources)
