import subprocess

import pytest

from app.services.ingestion import git
from app.services.ingestion.walker import is_secret, walk


def write(path, text="x = 1\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_walker_filters(tmp_path):
    write(tmp_path / "src" / "main.py")
    write(tmp_path / "src" / "generated.py")
    write(tmp_path / "node_modules" / "lib" / "index.js")
    write(tmp_path / "myenv" / "pyvenv.cfg", "home = /usr")
    write(tmp_path / "myenv" / "lib" / "site.py")
    write(tmp_path / ".env", "SECRET=1")
    write(tmp_path / ".env.example", "SECRET=")
    write(tmp_path / "keys" / "id_ed25519", "-----BEGIN")
    write(tmp_path / "package-lock.json", "{}")
    write(tmp_path / "image.png", "not really")
    write(tmp_path / "notes" / "keep.md", "# keep")
    write(tmp_path / "notes" / "drafts" / "skip.md", "# skip")
    write(tmp_path / "empty.py", "")
    # Nested .gitignore files and negation, with Git's semantics.
    write(tmp_path / ".gitignore", "src/generated.py\nnotes/drafts/\n")
    write(tmp_path / "logs" / ".gitignore", "*\n!important.txt\n")
    write(tmp_path / "logs" / "debug.txt")
    write(tmp_path / "logs" / "important.txt")

    result = walk(tmp_path, max_bytes=1_000_000, max_pdf_bytes=1_000_000)
    paths = {f.rel_path for f in result.files}
    assert paths == {"src/main.py", ".env.example", "notes/keep.md", "logs/important.txt"}
    assert result.skipped["secret"] == 2
    assert result.skipped["denied_dir"] == 2  # node_modules and the virtualenv
    assert result.skipped["empty"] == 1


def test_size_cap(tmp_path):
    write(tmp_path / "big.py", "x = 1\n" * 1000)
    result = walk(tmp_path, max_bytes=100, max_pdf_bytes=100)
    assert result.files == [] and result.skipped["too_large"] == 1


@pytest.mark.parametrize(
    "name,secret",
    [
        (".env", True),
        (".env.production", True),
        (".env.example", False),
        ("server.pem", True),
        ("id_rsa.pub", True),
        ("credentials.json", True),
        ("config.py", False),
    ],
)
def test_secret_names(name, secret):
    assert is_secret(name) is secret


@pytest.mark.parametrize(
    "url",
    [
        "ext::sh -c touch% /tmp/pwned",
        "file:///etc/passwd",
        "git@github.com:a/b.git",
        "http://github.com/a/b",
        "https://github.com/a/b; rm -rf /",
        "--upload-pack=evil",
    ],
)
def test_git_url_validation_rejects_dangerous_urls(url):
    with pytest.raises(ValueError):
        git.validate_url(url)


def test_git_url_validation_accepts_github():
    assert git.validate_url(" https://github.com/peppa234/mindgrep.git ") == (
        "https://github.com/peppa234/mindgrep.git"
    )


def test_file_history_and_repo_discovery(tmp_path):
    repo = tmp_path / "projects" / "demo"
    write(repo / "a.py")
    write(repo / "sub" / "b.py")

    def run(*args):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    run("init", "-q")
    run("-c", "user.name=First", "-c", "user.email=f@x", "add", ".")
    run("-c", "user.name=First", "-c", "user.email=f@x", "commit", "-q", "-m", "one")
    write(repo / "a.py", "x = 2\n")
    run("-c", "user.name=Second", "-c", "user.email=s@x", "commit", "-q", "-am", "two")

    history = git.file_history(repo)
    assert history["a.py"].author == "Second"
    assert history["sub/b.py"].author == "First"

    result = walk(tmp_path, max_bytes=1_000_000, max_pdf_bytes=1_000_000)
    assert result.repo_roots == ["projects/demo"]


def _signed_repo(tmp_path):
    """A repository whose own .git/config names a program for `git log` to run: log.showSignature
    asks git to verify signatures, gpg.program says with what, and HEAD is a signed commit."""
    repo = tmp_path / "downloaded"
    write(repo / "a.py")
    marker = tmp_path / "ran"
    program = tmp_path / "fake-gpg"
    program.write_text(f"#!/bin/sh\ntouch '{marker.as_posix()}'\n", encoding="utf-8")
    program.chmod(0o755)

    def run(*args, stdin=None):
        return (
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, input=stdin)
            .stdout.decode()
            .strip()
        )

    run("init", "-q")
    run("add", ".")
    tree = run("write-tree")
    commit = (
        f"tree {tree}\nauthor A <a@x> 1700000000 +0000\ncommitter A <a@x> 1700000000 +0000\n"
        "gpgsig -----BEGIN PGP SIGNATURE-----\n \n abc\n -----END PGP SIGNATURE-----\n\nsigned\n"
    )
    run(
        "update-ref",
        "HEAD",
        run("hash-object", "-t", "commit", "-w", "--stdin", stdin=commit.encode()),
    )
    run("config", "log.showSignature", "true")
    run("config", "gpg.program", program.as_posix())
    return repo, marker


def test_repository_config_cannot_run_programs(tmp_path):
    repo, marker = _signed_repo(tmp_path)
    # Plain git does run it: the fixture is a live attack, not a no-op.
    subprocess.run(["git", "log", "-1"], cwd=repo, capture_output=True)
    assert marker.exists()
    marker.unlink()

    assert "a.py" in git.file_history(repo)
    git.authors(repo)
    git.toplevel(repo)
    assert not marker.exists()


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost/a/b",
        "https://127.0.0.1/a/b",
        "https://10.0.0.8/a/b",
        "https://192.168.1.20:3000/a/b",
        "https://169.254.169.254/latest/meta-data",
        "https://0.0.0.0/a/b",
    ],
)
def test_git_hosts_must_be_public(url):
    with pytest.raises(ValueError, match="not a public address"):
        git.check_public_host(git.validate_url(url))
    git.check_public_host(url, allow_private=True)


def test_oversized_clone_is_removed(tmp_path, monkeypatch):
    dest = tmp_path / "source-1"
    write(dest / ".git" / "HEAD", "ref: refs/heads/main\n")
    write(dest / "big.bin", "x" * 5000)
    monkeypatch.setattr(git, "check_public_host", lambda url, allow_private=False: None)
    monkeypatch.setattr(git, "run_git", lambda args, cwd=None, timeout=900: "")
    with pytest.raises(git.GitError, match="MAX_REPO_BYTES"):
        git.clone_or_update("https://github.com/a/b", dest, max_bytes=1000)
    assert not dest.exists()
