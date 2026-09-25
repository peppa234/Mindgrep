"""Filesystem traversal.

Three filters, cheapest first:
  1. A hard deny-list of directories that are never worth indexing (`node_modules`, `.venv`,
     build output). Without it, 90% of the index is dependency code.
  2. Every `.gitignore` on the way down, with Git's own semantics (nested files, negation).
  3. A secrets deny-list. A private key or a `.env` must never reach the index, whatever
     the `.gitignore` says.
Then the router decides whether the extension is indexable at all, and size caps apply.
"""

import fnmatch
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pathspec

from app.services.ingestion.router import Route, route

DENY_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "bower_components",
    "jspm_packages",
    ".venv",
    "venv",
    ".env",
    "virtualenv",
    "__pycache__",
    ".tox",
    ".nox",
    ".eggs",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".hypothesis",
    ".ipynb_checkpoints",
    "dist",
    "build",
    "out",
    "target",
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".turbo",
    ".parcel-cache",
    ".gradle",
    ".idea",
    ".vscode",
    ".vs",
    "coverage",
    "htmlcov",
    ".terraform",
    ".dart_tool",
    ".pub-cache",
    "Pods",
    "DerivedData",
    "vendor",
    ".obsidian",
    ".trash",
}

SECRET_PATTERNS = [
    ".env",
    ".env.*",
    "*.env",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    "id_rsa*",
    "id_dsa*",
    "id_ecdsa*",
    "id_ed25519*",
    "*.ppk",
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".htpasswd",
    "credentials",
    "credentials.json",
    "secrets.*",
    "*.secret",
    "*.secrets",
    "service-account*.json",
    "*.tfstate",
    "*.tfstate.*",
]
# Templates are documentation, not secrets.
SECRET_EXCEPTIONS = {".env.example", ".env.sample", ".env.template"}

DENY_FILE_PATTERNS = [
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "uv.lock",
    "Cargo.lock",
    "go.sum",
    "composer.lock",
    "Gemfile.lock",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.bundle.js",
    "*.chunk.js",
]


def is_secret(name: str) -> bool:
    if name in SECRET_EXCEPTIONS:
        return False
    return any(fnmatch.fnmatch(name, pattern) for pattern in SECRET_PATTERNS)


@dataclass
class WalkedFile:
    rel_path: str  # relative to the source root, forward slashes
    abs_path: Path
    size: int
    mtime: float
    route: Route


@dataclass
class WalkResult:
    files: list[WalkedFile] = field(default_factory=list)
    skipped: Counter[str] = field(default_factory=Counter)
    # Directories (relative to root, "" for the root) that are Git working trees. A folder of
    # projects holds many repos, and each file's history comes from its nearest one.
    repo_roots: list[str] = field(default_factory=list)


def _load_gitignore(directory: Path) -> pathspec.PathSpec | None:
    ignore_file = directory / ".gitignore"
    if not ignore_file.is_file():
        return None
    try:
        lines = ignore_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    return pathspec.GitIgnoreSpec.from_lines(lines)


def walk(root: Path, max_bytes: int, max_pdf_bytes: int) -> WalkResult:
    root = root.resolve()
    result = WalkResult()
    # (directory relative to root, its compiled .gitignore)
    specs: dict[str, pathspec.PathSpec] = {}

    def ignored(rel: str, is_dir: bool) -> bool:
        parts = rel.split("/")
        for depth in range(len(parts)):
            base = "/".join(parts[:depth])
            spec = specs.get(base)
            if spec is None:
                continue
            candidate = "/".join(parts[depth:]) + ("/" if is_dir else "")
            if spec.match_file(candidate):
                return True
        return False

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        rel_dir = current.relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        spec = _load_gitignore(current)
        if spec is not None:
            specs[rel_dir] = spec
        if ".git" in dirnames or ".git" in filenames:
            result.repo_roots.append(rel_dir)

        kept = []
        for name in sorted(dirnames):
            rel = f"{rel_dir}/{name}" if rel_dir else name
            if name in DENY_DIRS or name.endswith(".egg-info"):
                result.skipped["denied_dir"] += 1
            elif (current / name / "pyvenv.cfg").exists():
                result.skipped["denied_dir"] += 1  # a virtualenv under any name
            elif (current / name).is_symlink():
                result.skipped["symlink"] += 1
            elif ignored(rel, is_dir=True):
                result.skipped["gitignored_dir"] += 1
            else:
                kept.append(name)
        dirnames[:] = kept  # prune in place: os.walk will not descend into the rest

        for name in sorted(filenames):
            rel = f"{rel_dir}/{name}" if rel_dir else name
            path = current / name
            if is_secret(name):
                result.skipped["secret"] += 1
                continue
            if any(fnmatch.fnmatch(name, pattern) for pattern in DENY_FILE_PATTERNS):
                result.skipped["denied_file"] += 1
                continue
            if path.is_symlink():
                result.skipped["symlink"] += 1
                continue
            if ignored(rel, is_dir=False):
                result.skipped["gitignored"] += 1
                continue
            file_route = route(rel)
            if file_route is None:
                result.skipped["unsupported_type"] += 1
                continue
            try:
                stat = path.stat()
            except OSError:
                result.skipped["unreadable"] += 1
                continue
            cap = max_pdf_bytes if file_route.kind == "pdf" else max_bytes
            if file_route.max_bytes is not None:
                cap = min(cap, file_route.max_bytes)
            if stat.st_size > cap:
                result.skipped["too_large"] += 1
                continue
            if stat.st_size == 0:
                result.skipped["empty"] += 1
                continue
            result.files.append(WalkedFile(rel, path, stat.st_size, stat.st_mtime, file_route))

    return result
