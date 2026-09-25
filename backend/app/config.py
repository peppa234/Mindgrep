from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://memoryos:memoryos@localhost:5432/memoryos"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"

    # --- Ingestion ---
    # Host folders are bind-mounted here; a local source's path must live under it.
    sources_root: str = "/sources"
    # GitHub repositories are cloned here (a named volume in compose).
    repos_dir: str = "/data/repos"
    # The versioned benchmark corpus (eval/corpus), mounted into the api container.
    eval_corpus_dir: str = "/srv/eval/corpus"
    max_file_bytes: int = 1_000_000
    max_pdf_bytes: int = 50_000_000

    # --- Models ---
    # http: the model server (GPU on the host, or the CPU container).
    # hash: deterministic feature-hashing vectors. No model, used by tests and CI.
    # none: skip embedding; search runs lexical-only.
    embedder: Literal["http", "hash", "none"] = "http"
    reranker: Literal["http", "none"] = "http"
    model_server_url: str = "http://host.docker.internal:8001"
    model_server_timeout_s: float = 120.0
    embedding_dim: int = 1024
    embed_batch_size: int = 32

    # --- Retrieval ---
    candidates_per_channel: int = 60
    rerank_candidates: int = 60


settings = Settings()
