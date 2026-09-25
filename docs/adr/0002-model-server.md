# ADR-0002: Models run in a separate server, on the host GPU

- Status: accepted
- Date: 2026-09-25

## Context

Embedding (Qwen3-Embedding-0.6B) and reranking (bge-reranker-v2-m3) need PyTorch. On the
development machine (Windows laptop, RTX 5050) GPU passthrough into Docker Desktop is fragile,
and a CUDA PyTorch install adds ~3 GB to any image that contains it.

## Decision

A small FastAPI model server (`app/modelserver`) owns the models and exposes `/embed` and
`/rerank`. The api and worker talk to it over HTTP (`MODEL_SERVER_URL`) through the `Embedder`
and `Reranker` interfaces. It runs natively on the host GPU (`.\make.ps1 models`); a CPU
container (`docker compose --profile models up`) exists for machines without one.

## Consequences

- The api and worker images stay small and CUDA-free; one copy of the weights serves both.
- Model identity is configuration. `EMBEDDER=hash` swaps in a deterministic, model-free
  embedder, which is what CI uses.
- If the model server is down, indexing still completes (chunks are lexically searchable and
  embedded later) and search degrades to lexical with an explicit `degraded` notice. Nothing
  crashes.
- Embeddings are cached in Valkey by `sha256(text)` + model, so re-indexing after a chunking
  change only embeds chunks whose text changed.
- One more process to start in development.
