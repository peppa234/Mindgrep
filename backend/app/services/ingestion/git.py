"""Git as a metadata source: clone, update, and per-file last-commit information.

Commit dates are ground truth for "when did I write this", which is what makes temporal
queries ("a function from two years ago") answerable later without guessing.
"""

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# https only: no ssh keys live in the container, and this rules out `ext::` and `file://`
# transports, which would let a registered "URL" execute commands or read local files.
GIT_URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+(:\d+)?/[A-Za-z0-9._~/-]+?(\.git)?/?$")


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class FileCommit:
    commit: str
    author: str
    date: datetime


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        GIT_TERMINAL_PROMPT="0",  # never hang waiting for credentials
        GIT_ALLOW_PROTOCOL="https",
        GIT_CONFIG_NOSYSTEM="1",
    )
    return env


def run_git(args: list[str], cwd: Path | None = None, timeout: int = 900) -> str:
    command = next((a for a in args if not a.startswith("-") and "=" not in a), "?")
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=_env(),
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {command} timed out after {timeout}s") from exc
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", "replace").strip()
        raise GitError(f"git {command} failed: {stderr[-500:]}")
    return completed.stdout.decode("utf-8", "replace")


def validate_url(url: str) -> str:
    url = url.strip()
    if not GIT_URL_RE.match(url):
        raise ValueError(
            "Only public https:// Git URLs are supported, e.g. https://github.com/user/repo"
        )
    return url


def is_repo(path: Path) -> bool:
    return (path / ".git").exists()


def clone_or_update(url: str, dest: Path) -> None:
    """Partial clone (--filter=blob:none): full commit history for metadata, but only the
    blobs at HEAD are downloaded. Much faster than a full clone on large repositories."""
    url = validate_url(url)
    if is_repo(dest):
        run_git(["fetch", "--prune", "--no-tags", "origin"], cwd=dest)
        run_git(["reset", "--hard", "origin/HEAD"], cwd=dest)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_git(["clone", "--filter=blob:none", "--no-tags", "--", url, str(dest)])


def head_commit(repo: Path) -> str | None:
    try:
        return run_git(["rev-parse", "HEAD"], cwd=repo).strip() or None
    except GitError:
        return None


def toplevel(path: Path) -> Path | None:
    """The working tree containing `path`, if any."""
    try:
        return Path(run_git(["rev-parse", "--show-toplevel"], cwd=path).strip())
    except (GitError, FileNotFoundError, NotADirectoryError):
        return None


def file_history(repo: Path) -> dict[str, FileCommit]:
    """Last commit touching each path at HEAD, from one `git log` walk (newest first, so
    the first time a path appears is its most recent change)."""
    try:
        output = run_git(
            # quotePath=false: otherwise non-ASCII paths come back octal-escaped and quoted.
            [
                "-c",
                "core.quotePath=false",
                "log",
                "--no-renames",
                "--name-only",
                "--format=%x1e%H%x1f%an%x1f%aI",
                "HEAD",
            ],
            cwd=repo,
        )
    except GitError:
        return {}  # empty repository, or not a repository at all
    latest: dict[str, FileCommit] = {}
    for record in output.split("\x1e"):
        if not record.strip():
            continue
        header, _, names = record.partition("\n")
        parts = header.split("\x1f")
        if len(parts) != 3:
            continue
        commit, author, date = parts
        info = FileCommit(commit, author, datetime.fromisoformat(date))
        for name in names.splitlines():
            name = name.strip()
            if name and name not in latest:
                latest[name] = info
    return latest
