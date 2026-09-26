"""Query understanding: which path answers this question, and is it about a point in time.

Rules, not a model. The graph questions have a small number of shapes ("which projects use
X", "what stack does P use"), and a regex that misses one only costs a fallback to RAG, which
still answers. A classifier would cost a model call on every question to save a few regexes.
The entity in the question is resolved afterwards against the graph; if it names nothing
known, the question goes to RAG as well.
"""

import re
from dataclasses import dataclass
from typing import Literal

_PROJECTS = r"(?:projects?|repos?|repositories|apps?|codebases?)"
_USE = (
    r"(?:use[sd]?|using|used|built\s+(?:with|on)|written\s+in|depend(?:s|ed)?\s+on|"
    r"rel(?:y|ies|ied)\s+on|made\s+with|have|had|include[sd]?)"
)

PROJECTS_USING = [
    # which projects use X / which of my repos used X / what projects have I built with X
    re.compile(
        rf"\b(?:which|what)\s+(?:of\s+my\s+)?{_PROJECTS}\s+(?:(?:have|did|do|does)\s+"
        rf"(?:i\s+)?)?{_USE}\s+(?P<subject>.+)",
        re.IGNORECASE,
    ),
    # show / list every project where I used X
    re.compile(
        rf"\b(?:show|list|find|give|tell)\b.*?\b{_PROJECTS}\b.*?\b(?:where|in\s+which|that|"
        rf"which)\s+(?:i\s+)?(?:have\s+|had\s+)?(?:ever\s+)?{_USE}\s+(?P<subject>.+)",
        re.IGNORECASE,
    ),
    # projects using X / repos that use X
    re.compile(
        rf"^\s*(?:all\s+|my\s+)?{_PROJECTS}\s+(?:using|that\s+use[sd]?|with|built\s+with|"
        rf"written\s+in)\s+(?P<subject>.+)",
        re.IGNORECASE,
    ),
    # where did I use X / have I ever used X (the answer is a list of projects)
    re.compile(
        r"\b(?:where|in\s+which\s+projects?)\s+(?:have|did)\s+i\s+(?:ever\s+)?used?\s+"
        r"(?P<subject>.+)",
        re.IGNORECASE,
    ),
    re.compile(r"\bhave\s+i\s+ever\s+used\s+(?P<subject>.+)", re.IGNORECASE),
]

PROJECT_STACK = [
    # what technologies / stack / libraries does P use
    re.compile(
        r"\bwhat\s+(?:tech(?:nolog(?:y|ies))?|stack|tech\s+stack|libraries|frameworks|"
        r"dependencies|languages?|databases?)\s+(?:does|did|do|is)\s+(?P<subject>.+?)\s+"
        r"(?:use|using|built\s+(?:with|on)|depend\s+on|have|written\s+in)\b",
        re.IGNORECASE,
    ),
    # (tech) stack of P / dependencies of P
    re.compile(
        r"\b(?:tech\s+stack|stack|dependencies|technologies)\s+(?:of|for|in|behind)\s+"
        r"(?:the\s+|my\s+)?(?P<subject>.+)",
        re.IGNORECASE,
    ),
    # what is P built with
    re.compile(
        r"\bwhat\s+(?:is|was)\s+(?P<subject>.+?)\s+(?:built|written|made)\s+(?:with|in|on)\b",
        re.IGNORECASE,
    ),
]

EARLIEST = re.compile(
    r"\b(?:original(?:ly)?|first|initial(?:ly)?|earliest|oldest|v1|at\s+the\s+(?:start|"
    r"beginning)|back\s+when|used\s+to)\b",
    re.IGNORECASE,
)
LATEST = re.compile(
    r"\b(?:latest|current(?:ly)?|now|newest|most\s+recent|recent(?:ly)?|today|these\s+days)\b",
    re.IGNORECASE,
)

# Words that trail the entity name in a question and are not part of it.
_TRAILING = re.compile(
    r"(?:\s+(?:in|for|at|on|before|so\s+far|ever|already|anywhere|project|projects|"
    r"repo|repos|at\s+all|and\s+where|and\s+how))+\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QueryIntent:
    kind: Literal["rag", "graph_projects", "graph_stack"]
    subject: str | None = None  # the words naming the entity, for graph intents
    temporal: Literal["earliest", "latest"] | None = None


def _clean(subject: str) -> str:
    subject = re.sub(r"[?!.]+\s*$", "", subject.strip())
    subject = re.sub(r"^(?:the|a|an|my)\s+", "", subject, flags=re.IGNORECASE)
    return _TRAILING.sub("", subject).strip(" ,;:")


def detect(question: str) -> QueryIntent:
    temporal = None
    if EARLIEST.search(question):
        temporal = "earliest"
    elif LATEST.search(question):
        temporal = "latest"
    for pattern in PROJECTS_USING:
        match = pattern.search(question)
        if match and (subject := _clean(match.group("subject"))):
            return QueryIntent("graph_projects", subject, temporal)
    for pattern in PROJECT_STACK:
        match = pattern.search(question)
        if match and (subject := _clean(match.group("subject"))):
            return QueryIntent("graph_stack", subject, temporal)
    return QueryIntent("rag", None, temporal)
