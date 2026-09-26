"""Test configuration.

Unit tests need nothing running. Integration tests need Postgres (with pgvector) and use a
separate database, `<name>_test`, created and migrated on first use; they are skipped when
Postgres is unreachable. Models are never needed: the hashing embedder and a deterministic
fake chat model stand in.
"""

import asyncio
import os
import sys
from pathlib import Path

# Settings are read at import time, so the environment is fixed before `app` is imported.
REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = REPO_ROOT / "eval" / "corpus"
if not CORPUS.exists():  # inside the api container, eval/ is mounted at /srv/eval
    REPO_ROOT = Path(__file__).resolve().parents[1]
    CORPUS = REPO_ROOT / "eval" / "corpus"
os.environ["EMBEDDER"] = "hash"
os.environ["RERANKER"] = "none"
# The deterministic fake chat model: tests never reach a real provider, even with keys in .env.
os.environ["LLM_PROVIDERS"] = "fake"
os.environ["EXTRACTION_PROVIDERS"] = "fake"
os.environ["EVAL_CORPUS_DIR"] = str(CORPUS)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))  # makes `eval.runners` importable

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import settings  # noqa: E402

_DEV_URL = make_url(settings.database_url)
TEST_DATABASE_URL = make_url(
    os.environ.get("TEST_DATABASE_URL") or _DEV_URL.set(database=f"{_DEV_URL.database}_test")
)


def _render(url) -> str:
    return url.render_as_string(hide_password=False)


async def _prepare_database() -> None:
    url = TEST_DATABASE_URL
    admin = create_async_engine(_render(url.set(database="postgres")), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        await admin.dispose()

    from alembic.config import Config

    from alembic import command

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", _render(url))
    # Alembic's env.py calls asyncio.run(), which cannot nest inside this loop.
    await asyncio.to_thread(command.upgrade, config, "head")


@pytest.fixture(scope="session")
async def db_engine():
    try:
        await _prepare_database()
    except (OSError, ConnectionError) as exc:
        pytest.skip(f"Postgres unavailable for integration tests: {exc}")
    except Exception as exc:  # asyncpg raises its own connection errors
        if "connect" in str(exc).lower() or "refused" in str(exc).lower():
            pytest.skip(f"Postgres unavailable for integration tests: {exc}")
        raise
    engine = create_async_engine(_render(TEST_DATABASE_URL))
    yield engine
    await engine.dispose()


@pytest.fixture
async def sessions(db_engine):
    """A session factory on a clean test database."""
    async with db_engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE sources, conversations, llm_extractions RESTART IDENTITY CASCADE")
        )
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
def corpus() -> Path:
    return CORPUS
