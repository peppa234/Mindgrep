"""Query analysis for the lexical channels. (Intent and temporal parsing arrive with chat.)"""

import re
from dataclasses import dataclass

from app.services.chunking.identifiers import IDENTIFIER_RE, is_compound, split_identifier

_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_MAX_TERMS = 32


@dataclass(frozen=True)
class AnalyzedQuery:
    text: str
    terms: list[str]
    # Tokens that look like code: snake_case, camelCase, dotted.paths, or `backticked`.
    identifiers: list[str]
    # OR of all terms, for to_tsquery('english', ...). None when nothing searchable remains.
    tsquery: str | None


def analyze(text: str) -> AnalyzedQuery:
    identifiers: list[str] = []
    for quoted in _BACKTICK_RE.findall(text):
        identifiers.extend(IDENTIFIER_RE.findall(quoted))
    for token in re.findall(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*", text):
        for part in token.split("."):
            if is_compound(part) or "." in token:
                identifiers.append(part)

    terms: list[str] = []
    for word in _WORD_RE.findall(text):
        terms.append(word.lower())
    for ident in identifiers:
        terms.extend(split_identifier(ident))
    unique = list(dict.fromkeys(t for t in terms if len(t) > 1 or t.isdigit()))[:_MAX_TERMS]

    identifiers = list(dict.fromkeys(i for i in identifiers if len(i) > 2))[:5]
    tsquery = " | ".join(unique) if unique else None
    return AnalyzedQuery(text=text, terms=unique, identifiers=identifiers, tsquery=tsquery)
