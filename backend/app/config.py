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
    # A cloned repository larger than this on disk is deleted and the run fails.
    max_repo_bytes: int = 2_000_000_000
    # Git URLs must resolve to public addresses; true allows a Git server on your own network.
    git_allow_private_hosts: bool = False

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

    # --- Chat models ---
    # Tried in order; a provider without its key (or model, for ollama) is skipped. Every
    # provider speaks the OpenAI chat-completions protocol, so one client serves them all.
    # fake: a deterministic extractive model with no network, used by tests and CI.
    llm_providers: str = "gemini,groq,ollama"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    # Gemini 3.x models think before they write. At the default effort the first token took
    # 22 s on a 3k-token prompt (and the answer arrived in one piece); real chat prompts
    # passed the read timeout. "low" brought it to ~4 s, streamed. Empty = provider default.
    gemini_reasoning_effort: str = "low"
    # Tried, in order, after gemini_model fails (503 "high demand", timeout): a different model
    # usually has capacity when one is overloaded. Comma-separated; empty = none.
    gemini_fallback_models: str = "gemini-3.5-flash-lite"
    # Silence allowed before falling back to the next model (the read timeout, between chunks).
    gemini_timeout_s: float = 30.0
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    ollama_model: str = ""
    ollama_base_url: str = "http://host.docker.internal:11434/v1"
    llm_timeout_s: float = 60.0
    # Extraction runs in bulk; it may use a cheaper lane than the answer the user reads.
    extraction_providers: str = ""  # empty = same chain as llm_providers

    # --- Chat ---
    chat_context_chunks: int = 8
    chat_context_tokens: int = 6000
    chat_history_turns: int = 3
    # Below this top reranker score the chat answers "not in your memory" without asking the
    # model. Measure it with `.\make.ps1 eval` (the Abstention line) and set it from there.
    abstain_threshold: float = 0.008

    # --- Ideas: when does a project count as implementing an idea?
    # coverage: IDF-weighted share of the idea's distinctive words found in the project.
    # similarity: reranker score of the idea against the project's best chunk (0..1).
    # Either signal can decide. Calibrate with `.\make.ps1 eval-ideas`.
    idea_coverage_implemented: float = 0.45
    idea_coverage_partial: float = 0.3
    idea_similarity_implemented: float = 0.5
    idea_similarity_partial: float = 0.15


settings = Settings()
