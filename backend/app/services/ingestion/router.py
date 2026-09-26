"""Extension -> (document kind, language). Anything not listed here is not indexed."""

from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class Route:
    kind: str  # code | markdown | pdf | text
    language: str | None
    max_bytes: int | None = None  # tighter per-type size cap, if any


# Languages with a tree-sitter grammar get AST chunking; the rest are chunked as text
# but still labelled as code so filters and the UI treat them correctly.
CODE_EXTENSIONS = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    # No grammar wired up yet: text-chunked.
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".swift": "swift",
    ".rb": "ruby",
    ".php": "php",
    ".dart": "dart",
    ".scala": "scala",
    ".lua": "lua",
    ".r": "r",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".ps1": "powershell",
    ".sql": "sql",
    ".vue": "vue",
    ".svelte": "svelte",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
}

TEXT_EXTENSIONS = {
    ".txt": None,
    ".rst": "rst",
    ".adoc": "asciidoc",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".ini": "ini",
    ".cfg": "ini",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".tf": "terraform",
}

# Structured data is indexed only when small; large JSON is almost always a data dump.
SMALL_TEXT_EXTENSIONS = {".json": ("json", 200_000)}

MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdx"}

FILENAMES = {
    "Dockerfile": Route("text", "dockerfile"),
    "Makefile": Route("text", "make"),
    "Procfile": Route("text", None),
    "Jenkinsfile": Route("text", "groovy"),
    ".env.example": Route("text", "dotenv"),
    # Dependency manifests without an indexable extension. Indexed so that every graph edge
    # read from them (services/graph/manifests.py) cites a document you can open.
    "go.mod": Route("text", "gomod"),
    "pom.xml": Route("text", "xml"),
    "build.gradle": Route("text", "gradle"),
    "build.gradle.kts": Route("text", "gradle"),
    "Gemfile": Route("text", "ruby"),
    "Pipfile": Route("text", "toml"),
    ".env.sample": Route("text", "dotenv"),
}


def route(path: str) -> Route | None:
    p = PurePosixPath(path)
    if p.name in FILENAMES:
        return FILENAMES[p.name]
    if p.name.startswith("Dockerfile."):
        return Route("text", "dockerfile")
    suffix = p.suffix.lower()
    if suffix in MARKDOWN_EXTENSIONS:
        return Route("markdown", "markdown")
    if suffix == ".pdf":
        return Route("pdf", None)
    if suffix in CODE_EXTENSIONS:
        return Route("code", CODE_EXTENSIONS[suffix])
    if suffix in TEXT_EXTENSIONS:
        return Route("text", TEXT_EXTENSIONS[suffix])
    if suffix in SMALL_TEXT_EXTENSIONS:
        language, cap = SMALL_TEXT_EXTENSIONS[suffix]
        return Route("text", language, max_bytes=cap)
    return None
