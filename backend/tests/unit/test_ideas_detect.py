"""Idea detection (what counts as an idea, and what a note declares about it) and the chat
routing of questions about ideas. No database."""

from datetime import date, datetime

import pytest

from app.schemas.idea import IdeaCandidate, IdeaOut
from app.services.chat.idea_answer import matches_topic
from app.services.chat.intent import detect
from app.services.ideas.detect import NoteDoc, is_idea_note
from app.services.ideas.detect import detect as detect_ideas
from app.services.parsing.markdown import parse_markdown


def note(path: str, text: str, modified: datetime | None = None) -> tuple[NoteDoc, str]:
    parsed = parse_markdown(text, path)
    return NoteDoc(1, path, parsed.title, parsed.meta, modified), text


IDEA_NOTE = """---
title: Offline flashcards
created: 2024-01-05
tags: [idea, mobile]
status: wip
implemented_by: "[[flashcards-app]]"
---

# Offline flashcards

A spaced-repetition flashcard app that works **offline** and syncs when a
connection comes back, using [[CRDTs]] for merges.

## Open questions

- which sync protocol?
"""


def test_a_tagged_note_is_one_idea_with_its_first_paragraph():
    [idea] = detect_ideas(*note("notes/misc/flashcards.md", IDEA_NOTE))
    assert idea.extractor == "note" and idea.key == "note:notes/misc/flashcards.md"
    assert idea.title == "Offline flashcards"
    # Markup and wikilink brackets are gone; the paragraph is rejoined across line breaks.
    assert idea.summary == (
        "A spaced-repetition flashcard app that works offline and syncs when a connection "
        "comes back, using CRDTs for merges."
    )
    assert idea.written_on == date(2024, 1, 5)
    assert idea.declared_status == "partial"  # "wip"
    assert idea.declared_project == "flashcards-app"
    assert idea.tags == ["idea", "mobile"]


@pytest.mark.parametrize(
    "path,text,expected",
    [
        ("ideas/cli.md", "# A CLI\n\nSomething.\n", True),  # the folder says so
        ("notes/Project-Ideas/cli.md", "# A CLI\n\nSomething.\n", True),
        ("notes/cli.md", "---\ntype: idea\n---\n# A CLI\n", True),
        ("notes/cli.md", "# A CLI\n\nSomething. #idea\n", True),  # an inline tag
        ("notes/cli.md", "# A CLI\n\nSomething.\n", False),
        ("ideas/README.md", "# My ideas\n\n- one\n- two\n", False),  # the folder's index
        ("notes/ideation.md", "# Ideation workshop\n\n#ideation\n", False),
    ],
)
def test_what_makes_a_note_an_idea(path, text, expected):
    doc, _ = note(path, text)
    assert is_idea_note(doc) is expected


JOURNAL = """---
created: 2024-05-02
tags: [journal]
---

# 2024-05-02

Standup ran long again.

Idea: a CLI that turns the git log of every repository into a weekly changelog,
grouped by author, so standup notes write themselves.

- **Idea:** cache the timetable per group for an hour
- [ ] idea - try bge-m3 on Arabizi
- the idea: nothing (not at the start of the line)

```yaml
idea: not prose, a config key
```

## Idea: A plugin that lints commit messages
"""


def test_inline_ideas_in_a_journal():
    ideas = detect_ideas(*note("notes/journal/2024-05-02.md", JOURNAL))
    assert [(i.line, i.title) for i in ideas] == [
        (10, "A CLI that turns the git log of every repository into a weekly changelog"),
        (13, "Cache the timetable per group for an hour"),
        (14, "Try bge-m3 on Arabizi"),
        (21, "A plugin that lints commit messages"),
    ]
    first = ideas[0]
    assert first.extractor == "inline" and first.written_on == date(2024, 5, 2)
    # The hard-wrapped continuation belongs to the idea.
    assert first.summary.endswith("grouped by author, so standup notes write themselves.")
    assert first.evidence.startswith("Idea: a CLI")
    assert first.key.startswith("line:notes/journal/2024-05-02.md:")


def test_an_idea_note_does_not_also_yield_its_inline_ideas():
    text = "---\ntags: [idea]\n---\n# Big idea\n\nThe summary.\n\nIdea: a sub-idea of it\n"
    ideas = detect_ideas(*note("notes/big.md", text))
    assert [i.extractor for i in ideas] == ["note"]


def test_the_date_falls_back_to_the_last_commit():
    doc, text = note("ideas/x.md", "# X\n\nA thing.\n", datetime(2022, 3, 4, 10, 0))
    [idea] = detect_ideas(doc, text)
    assert idea.written_on == date(2022, 3, 4)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("done", "implemented"),
        ("Shipped", "implemented"),
        ("in progress", "partial"),
        ("abandoned", "abandoned"),
        ("dropped", "abandoned"),
        ("idea", None),
        ("someday", None),
    ],
)
def test_declared_status(value, expected):
    text = f"---\nstatus: {value}\n---\n# X\n\nA thing.\n"
    [idea] = detect_ideas(*note("ideas/x.md", text))
    assert idea.declared_status == expected


@pytest.mark.parametrize(
    "question,status,topic",
    [
        ("What AI ideas have I never implemented?", "unimplemented", "AI"),
        ("What ideas have I written down and never implemented?", "unimplemented", None),
        ("any ideas I haven't started yet?", "unimplemented", None),
        ("which of my ideas did I build?", "implemented", None),
        ("show my unfinished ideas", "partial", None),
        ("What rust ideas have I abandoned?", "abandoned", "rust"),
        ("list all my ideas", "all", None),
        ("ideas about search that I never built", "unimplemented", "search"),
        (
            "which of my machine learning ideas are unimplemented",
            "unimplemented",
            "machine learning",
        ),
    ],
)
def test_idea_questions_route_to_the_ideas_answer(question, status, topic):
    intent = detect(question)
    assert (intent.kind, intent.subject, intent.topic) == ("ideas", status, topic)


@pytest.mark.parametrize(
    "question",
    [
        "I have an idea for a CLI, how would I implement it?",
        "what is a good idea for caching?",
        "Which projects use postgres?",
    ],
)
def test_other_questions_that_mention_an_idea_do_not(question):
    assert detect(question).kind != "ideas"


def idea(title: str, summary: str, tags: list[str]) -> IdeaOut:
    return IdeaOut(
        id=1, title=title, summary=summary, extractor="note", source_id=1, source_name="n",
        document_id=1, path="ideas/x.md", line=None, written_on=None, tags=tags,
        status="unimplemented", origin="match", project=None, matched_status="unimplemented",
        score=0.0, closest=None, candidates=[], missing=[], signals=["coverage"],
        declared_status=None, declared_project=None, user_note=None, matched_at=None,
    )  # fmt: skip


def test_topic_filter():
    rag = idea("RAG for Darija", "Retrieval-augmented question answering.", ["idea", "nlp"])
    bot = idea("Code review bot", "Comments on pull requests.", ["idea", "llm"])
    crawler = idea("Broken link crawler", "Walks a site and respects robots.txt.", ["idea"])
    go_tool = idea("Port the crawler", "Rewrite it in Golang.", ["idea"])
    assert [matches_topic(i, "AI") for i in (rag, bot, crawler)] == [True, True, False]
    assert matches_topic(crawler, "robots.txt") and not matches_topic(rag, "robots.txt")
    # A technology alias finds the canonical name: "golang" is Go.
    assert matches_topic(go_tool, "golang") and matches_topic(bot, None)


def test_closeness_is_the_stronger_signal():
    candidate = IdeaCandidate(project_id=1, project="p", coverage=0.2, similarity=0.7)
    assert candidate.closeness == 0.7
    assert IdeaCandidate(project_id=1, project="p", coverage=0.4).closeness == 0.4
