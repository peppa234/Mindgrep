"""Git as a metadata source: clone, update, and per-file last-commit information.

Commit dates are ground truth for "when did I write this", which is what makes temporal
queries ("a function from two years ago") answerable later without guessing.
"""

import ipaddress
import os
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

# https only: no ssh keys live in the container, and this rules out `ext::` and `file://`
# transports, which would let a registered "URL" execute commands or read local files.
GIT_URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+(:\d+)?/[A-Za-z0-9._~/-]+?(\.git)?/?$")


# Command-line config outranks every config file, including a repository's own .git/config.
# Local sources are folders on disk that may hold a repository someone else wrote, and the
# image trusts every directory (safe.directory '*'), so nothing that config can name may run:
# no fsmonitor daemon, no hooks, no signature checker, no credential helper.
SAFE_CONFIG = {
    "core.fsmonitor": "false",
    "core.hooksPath": os.devnull,
    "log.showSignature": "false",
    "credential.helper": "",
}


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
        GIT_CONFIG_COUNT=str(len(SAFE_CONFIG)),
    )
    for i, (key, value) in enumerate(SAFE_CONFIG.items()):
        env[f"GIT_CONFIG_KEY_{i}"] = key
        env[f"GIT_CONFIG_VALUE_{i}"] = value
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


def check_public_host(url: str, allow_private: bool = False) -> None:
    """The server clones whatever it is given: a URL naming localhost, a private network or
    a cloud metadata address would make it a probe of the network it runs in. Checked again
    right before each clone, since DNS can change in between."""
    if allow_private:
        return
    host = urlsplit(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"cannot resolve {host!r}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise ValueError(
                f"{host} resolves to {address}, which is not a public address "
                "(set GIT_ALLOW_PRIVATE_HOSTS=true for a Git server on your own network)"
            )


def tree_bytes(path: Path) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for name in filenames:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
    return total


def is_repo(path: Path) -> bool:
    return (path / ".git").exists()


def clone_or_update(
    url: str, dest: Path, max_bytes: int | None = None, allow_private: bool = False
) -> None:
    """Partial clone (--filter=blob:none): full commit history for metadata, but only the
    blobs at HEAD are downloaded. Much faster than a full clone on large repositories.

    A clone over `max_bytes` on disk is deleted again, so one oversized repository cannot fill
    the volume for good (the clone timeout bounds the transient cost)."""
    url = validate_url(url)
    check_public_host(url, allow_private)
    if is_repo(dest):
        run_git(["fetch", "--prune", "--no-tags", "origin"], cwd=dest)
        run_git(["reset", "--hard", "origin/HEAD"], cwd=dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        run_git(["clone", "--filter=blob:none", "--no-tags", "--", url, str(dest)])
    if max_bytes is not None and (size := tree_bytes(dest)) > max_bytes:
        shutil.rmtree(dest, ignore_errors=True)
        raise GitError(
            f"the repository takes {size / 1e9:.1f} GB on disk, over the "
            f"{max_bytes / 1e9:.1f} GB limit (MAX_REPO_BYTES)"
        )


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


@dataclass(frozen=True)
class AuthorStats:
    name: str
    email: str
    commits: int
    first: datetime
    last: datetime


def authors(repo: Path, subpath: str = "") -> list[AuthorStats]:
    """Who committed to `subpath` of `repo` (the whole repo if empty), most commits first."""
    args = ["log", "--no-merges", "--format=%an%x1f%ae%x1f%aI", "HEAD"]
    if subpath:
        args += ["--", subpath]
    try:
        output = run_git(args, cwd=repo, timeout=120)
    except (GitError, FileNotFoundError, NotADirectoryError):
        return []
    stats: dict[str, list] = {}
    for line in output.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        name, email, date = parts
        when = datetime.fromisoformat(date)
        key = (email or name).lower()
        entry = stats.setdefault(key, [name, email, 0, when, when])
        entry[2] += 1
        entry[3] = min(entry[3], when)
        entry[4] = max(entry[4], when)
    return sorted(
        (AuthorStats(*entry) for entry in stats.values()), key=lambda a: (-a.commits, a.name)
    )
