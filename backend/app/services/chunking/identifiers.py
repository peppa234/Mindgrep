"""Identifier handling for lexical search.

Postgres' text parser treats `generate_jwt_token` as three words but `generateJwtToken` as one
opaque token, so a search for "jwt token" misses camelCase code entirely. These helpers split
identifiers into their words so both styles, and plain-English queries, meet in the same index.
"""

import re

IDENTIFIER_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_CAMEL_PARTS_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def split_identifier(name: str) -> list[str]:
    """`parseHTTPResponse_v2` -> ["parse", "http", "response", "v2"]."""
    words: list[str] = []
    for part in re.split(r"[_$\-.]+", name):
        if not part:
            continue
        pieces = _CAMEL_PARTS_RE.findall(part)
        # Keep letter+digit suffixes together: "v2", "sha256".
        merged: list[str] = []
        for piece in pieces:
            if piece.isdigit() and merged:
                merged[-1] += piece
            else:
                merged.append(piece)
        words.extend(p.lower() for p in merged)
    return [w for w in words if len(w) > 1]


def is_compound(name: str) -> bool:
    """True for identifiers that the Postgres parser would not split correctly."""
    return len(split_identifier(name)) > 1


def identifier_terms(text: str, limit: int = 400) -> str:
    """Split every compound identifier in `text` into words, de-duplicated, in first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for match in IDENTIFIER_RE.finditer(text):
        ident = match.group(0)
        if ident in seen or not is_compound(ident):
            continue
        seen.add(ident)
        out.append(" ".join(split_identifier(ident)))
        if len(out) >= limit:
            break
    return " ".join(out)


def path_terms(path: str) -> str:
    """`src/authService/jwt_utils.py` -> "src auth service jwt utils py"."""
    words: list[str] = []
    for segment in re.split(r"[/\\]+", path):
        words.extend(split_identifier(segment))
    return " ".join(words)


def symbol_terms(symbols: list[str]) -> str:
    """The symbols as written plus their split words, for the weight-A part of the index."""
    out: list[str] = []
    for sym in symbols:
        out.append(sym)
        for ident in IDENTIFIER_RE.findall(sym):
            out.extend(split_identifier(ident))
    return " ".join(out)
