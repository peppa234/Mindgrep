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

# Questions about the list of ideas: "what AI ideas have I never implemented?". Plural
# "ideas", or "which/what idea": "I have an idea for X, how do I build it?" is not one.
IDEAS = re.compile(r"\bideas\b|\b(?:which|what)\s+(?:\S+\s+){0,2}idea\b", re.IGNORECASE)
IDEAS_NEVER = re.compile(
    r"\b(?:never|not\s+yet|haven'?t|have\s+not|didn'?t|did\s+not|unimplemented|unbuilt|"
    r"not\s+(?:been\s+)?(?:built|implemented|started|done|made)|still\s+(?:open|to\s+do)|"
    r"forgot(?:ten)?|left\s+(?:behind|undone)|gap)\b",
    re.IGNORECASE,
)
IDEAS_PARTIAL = re.compile(
    r"\b(?:partial(?:ly)?|half[-\s]?(?:built|done|finished|implemented)|started\s+but|"
    r"unfinished|in\s+progress)\b",
    re.IGNORECASE,
)
IDEAS_DONE = re.compile(
    r"\b(?:implemented|built|shipped|finished|completed|made\s+real|turned\s+into|"
    r"did\s+i\s+(?:build|implement|ship|finish|make))\b",
    re.IGNORECASE,
)
IDEAS_ABANDONED = re.compile(r"\b(?:abandon(?:ed)?|dropped|gave\s+up|shelved)\b", re.IGNORECASE)
# The topic in "what AI ideas", "my rust ideas", "ideas about search".
_NOT_TOPIC = {
    "my", "the", "of", "all", "any", "your", "own", "old", "project", "app", "these", "those",
    "other", "new", "good", "best", "unimplemented", "implemented", "unbuilt", "built",
    "abandoned", "partial", "unfinished", "past", "previous", "many", "few", "some", "i",
}  # fmt: skip
IDEA_TOPIC = [
    re.compile(
        r"\b(?:what|which|list|show|all|any|my|the)\s+(?:of\s+)?(?:my\s+)?"
        r"(?P<topic>[\w+#.-]+(?:\s+[\w+#.-]+)?)\s+ideas?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bideas?\s+(?:about|on|for|around|involving|related\s+to|with|in)\s+"
        r"(?P<topic>[\w+#.\s-]+?)(?:\s+(?:that|which|have|did|i|i've|were)\b|[?.!,]|$)",
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
    kind: Literal["rag", "graph_projects", "graph_stack", "ideas"]
    # graph intents: the words naming the entity. ideas: the status asked about
    # (unimplemented | partial | implemented | abandoned | all).
    subject: str | None = None
    temporal: Literal["earliest", "latest"] | None = None
    topic: str | None = None  # ideas: "AI" in "what AI ideas have I never implemented"


def _clean(subject: str) -> str:
    subject = re.sub(r"[?!.]+\s*$", "", subject.strip())
    subject = re.sub(r"^(?:the|a|an|my)\s+", "", subject, flags=re.IGNORECASE)
    return _TRAILING.sub("", subject).strip(" ,;:")


def _idea_topic(question: str) -> str | None:
    for pattern in IDEA_TOPIC:
        match = pattern.search(question)
        if not match:
            continue
        words = [w for w in match.group("topic").split() if w.lower() not in _NOT_TOPIC]
        if words and not IDEAS_NEVER.fullmatch(" ".join(words)):
            return " ".join(words)
    return None


def detect_ideas(question: str) -> QueryIntent | None:
    if not IDEAS.search(question):
        return None
    if IDEAS_ABANDONED.search(question):
        status = "abandoned"
    elif IDEAS_PARTIAL.search(question):
        status = "partial"
    elif IDEAS_NEVER.search(question):
        status = "unimplemented"
    elif IDEAS_DONE.search(question):
        status = "implemented"
    elif re.search(r"\b(?:what|which|list|show|all|any|my)\b", question, re.IGNORECASE):
        status = "all"
    else:
        return None
    return QueryIntent("ideas", status, None, _idea_topic(question))


def detect(question: str) -> QueryIntent:
    if (ideas := detect_ideas(question)) is not None:
        return ideas
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
