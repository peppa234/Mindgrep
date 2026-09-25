# Python 3.12 rather than 3.13: several wheels (tree-sitter grammars, the torch stack in the
# model server) still lag a release behind.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# git: cloning GitHub sources, and per-file commit metadata for every repo we index.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Dependencies install in their own layer, so editing application code
# does not invalidate the (slow) dependency layer on rebuild.
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml --extra dev

# Never run as root. /data/repos is created here so the named volume inherits the owner.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data/repos \
    && chown -R app:app /data /srv
USER app
# Bind-mounted folders from Windows/macOS are owned by another uid; without this, git
# refuses to read their history ("dubious ownership").
RUN git config --global --add safe.directory '*'

COPY --chown=app:app alembic.ini ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app app ./app
COPY --chown=app:app tests ./tests

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
