"""Import statements -> the modules they import, per language.

The code chunker already collected each file's import statements (documents.meta.imports);
this turns them into module names the technology table can resolve. Relative imports are
the project's own code and are dropped here.
"""

import re

_PY_FROM_RE = re.compile(r"^\s*from\s+([\w.]+)\s+import\b")
_PY_IMPORT_RE = re.compile(r"^\s*import\s+(.+)$")
_QUOTED_RE = re.compile(r"""["']([^"'\s]+)["']""")
_JS_FROM_RE = re.compile(
    r"""(?:\bfrom|^\s*import|\brequire\s*\(|\bimport\s*\()\s*["']([^"']+)["']"""
)
_RUST_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:use|extern\s+crate)\s+(?:::)?([\w]+)")
_JAVA_RE = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)")


def modules_in(statement: str, language: str) -> list[str]:
    if language == "python":
        match = _PY_FROM_RE.match(statement)
        if match:
            return [] if match.group(1).startswith(".") else [match.group(1)]
        match = _PY_IMPORT_RE.match(statement)
        if match:
            names = [part.strip().split(" as ")[0].strip() for part in match.group(1).split(",")]
            return [n for n in names if re.fullmatch(r"[\w.]+", n)]
        return []
    if language in ("javascript", "typescript", "tsx"):
        return [m for m in _JS_FROM_RE.findall(statement) if not m.startswith((".", "/"))]
    if language == "go":
        return [m for m in _QUOTED_RE.findall(statement)]
    if language == "rust":
        match = _RUST_RE.match(statement)
        return [match.group(1)] if match else []
    if language == "java":
        match = _JAVA_RE.match(statement)
        return [match.group(1)] if match else []
    return []
