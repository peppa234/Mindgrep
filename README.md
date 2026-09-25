# MemoryOS

An AI operating system for developers that remembers, connects, and understands everything you build.

Point it at your notes, your PDFs, and your Git repositories, then search them the way you
remember them: *"the function that retried with growing delays"*, *"my notes on HNSW
parameters"*, `limit_login`. Answers come back as the exact function, section, or page, with
file, line range, and the commit date.

The query it is ultimately built for is the one no ordinary search can answer:

> **"What ideas have I written down and never implemented?"**

Answering that means extracting ideas from notes, detecting implementations in code, and
returning the *difference* between them: retrieval over the absence of things.

**Status:** Phase 1 of 3 (*The Index*) is complete: ingestion, AST chunking, embeddings,
hybrid search with reranking, an evaluation harness, and a sources + search UI. No chat yet,
by design. See [Roadmap](#roadmap).

---

## Why this is not another chat-with-your-docs project

**Code is chunked on AST boundaries, not character counts.** A function is a chunk, with its
decorators and doc comment attached and its enclosing class and used imports in its header.
Large classes split into methods and large functions split between statements, never
mid-statement. `tree-sitter` gives these boundaries deterministically for Python, JavaScript,
TypeScript/TSX, Go, Rust, and Java.

**Retrieval is hybrid, then reranked.** Three channels (dense vectors, weighted full-text with
camelCase/snake_case splitting, and trigram matching on symbol names) are fused with
Reciprocal Rank Fusion and reordered by a cross-encoder. Each catches what the others miss:
paraphrases, exact identifiers, half-remembered names ([ADR-0003](docs/adr/0003-hybrid-retrieval.md)).

**Quality is measured, not claimed.** A labelled benchmark with Recall@k, NDCG@10 and MRR
per search mode, including *unanswerable* queries, gated in CI. See [Evaluation](#evaluation).

---

## Evaluation

Fixture benchmark: 44 answerable + 12 unanswerable queries over five small repos (five
languages), a notes vault, and two PDFs ([eval/](eval/README.md)).

**With the real models** (Qwen3-Embedding-0.6B + bge-reranker-v2-m3, RTX 5050 laptop GPU):
run `.\make.ps1 eval` to produce `eval/reports/fixture-<date>.md`. That report, and the
personal benchmark over my own notes and repos, are the numbers this section will carry.

**CI baseline** (model-free: hashing embedder, no reranker; every PR is gated on it):

| Mode | Recall@10 | NDCG@10 | MRR |
|---|---|---|---|
| lexical (full-text + symbol) | 0.989 | 0.885 | 0.883 |
| vector (hashing) | 0.830 | 0.727 | 0.740 |
| hybrid (RRF) | 0.989 | 0.839 | 0.818 |

The CI numbers are a regression floor, not a quality claim: a bag-of-words "embedding" drags
hybrid below lexical on vague descriptions (NDCG 0.67). That gap is exactly what the real
embedder and the reranker have to close, and the per-category report shows whether they do.

---

## Architecture

One database. Postgres 16 holds the relational data, the vectors (pgvector + HNSW), the
full-text index (`tsvector` + `pg_trgm`), and in Phase 2 the knowledge graph
([ADR-0001](docs/adr/0001-postgres-for-everything.md)). Models run in a separate server on the
GPU ([ADR-0002](docs/adr/0002-model-server.md)).

```
Next.js ──/api proxy──> FastAPI ─────────────────> Postgres 16
 search · sources ·        │  search: vector ∥ fts ∥ symbol    pgvector HNSW · tsvector GIN · pg_trgm
 document view             │          → RRF → rerank
                           │ enqueue
                        Valkey <──> ARQ worker ──> sync (git clone/pull) → walk (.gitignore, secrets)
                        queue +     → parse (tree-sitter · Markdown · PyMuPDF) → chunk → embed
                        emb. cache       │
                                         └──HTTP──> model server (host GPU)
                                                    Qwen3-Embedding-0.6B · bge-reranker-v2-m3
```

Indexing is idempotent: files are re-parsed only when their content hash or the parser version
changes, deleted files are removed, and embeddings are cached by content, so a re-index after
editing one file does one file's work.

Deliberately deferred, with the conditions that would change that:

| Deferred | Added when |
|---|---|
| Qdrant | chunk count passes ~5M, **or** ANN p95 latency passes 150 ms |
| Neo4j | multi-hop traversal exceeds 5% of queries **and** recursive-CTE p95 passes 200 ms |

---

## Quickstart

Requires Docker Desktop. For the models: an NVIDIA GPU and [uv](https://docs.astral.sh/uv/)
(or see *No GPU?* below).

```powershell
git clone https://github.com/peppa234/MemoryOs
cd MemoryOs
copy .env.example .env      # then set SOURCES_DIR to the folder holding your notes and repos
.\make.ps1 up               # postgres, valkey, api, worker, frontend
.\make.ps1 models           # in a second terminal: model server on the GPU (first run downloads ~5 GB)
.\make.ps1 health
```

Open http://localhost:3000, go to **Sources**, and add a folder (a path relative to
`SOURCES_DIR`) or a public GitHub URL. A folder that contains many repositories is fine: each
file gets the last commit from its own repo. Then search.

| URL | What it is |
|---|---|
| http://localhost:3000 | The app: search, sources, and a document view that shows every chunk boundary |
| http://localhost:8000/docs | Swagger UI for the API |

**No GPU?** `docker compose --profile models up -d`, then set `MODEL_SERVER_URL=http://models:8001`
in `.env`. Slower, same results. With no model server at all, indexing still works and search
falls back to lexical, saying so.

Run `.\make.ps1` with no arguments for every task (`test`, `eval`, `label`, `logs worker`, …).
On Linux or macOS, `make <task>` does the same.

---

## What gets indexed

| Type | Parsed with | Chunked by |
|---|---|---|
| Python, JS, TS/TSX, Go, Rust, Java | tree-sitter | definition (function, class, method), members of large classes, statements of large functions |
| Other code (C, C#, Kotlin, SQL, shell, …) | text | paragraph windows |
| Markdown | frontmatter, headings, `[[wikilinks]]`, `#tags` | heading section, small sections merged |
| PDF | PyMuPDF (scanned PDFs are flagged `needs_ocr`) | page, short pages merged |
| Config (TOML, YAML, small JSON, Dockerfile) | text | paragraph windows |

Never indexed: anything in `.gitignore`, dependency and build directories (`node_modules`,
virtualenvs, `dist`, …), lockfiles, binaries, and secrets (`.env`, private keys, credential
files), whatever the `.gitignore` says.

---

## Roadmap

| Phase | Weeks | What it delivers | Status |
|---|---|---|---|
| 1. **The Index** | 1–7 | Ingestion, AST chunking, embeddings, eval harness, hybrid search + rerank; sources + search UI | ✅ done |
| 2. **The Brain** | 8–15 | RAG chat with citations and abstention; knowledge graph (deterministic extraction from manifests, imports and git first, LLM extraction after) | next |
| 3. **The Product** | 16–20 | Idea ↔ implementation gap, ego-network graph view, polish, deploy | |

The eval harness landed *before* the retrieval work it judges. That ordering is the point:
you cannot improve what you cannot measure.

---

## Repository layout

```
backend/app/services/  ingestion (walker, git, pipeline) · parsing · chunking · embedding · retrieval
backend/app/modelserver/  the GPU model server
backend/tests/         unit + integration (real Postgres, no models needed)
eval/                  corpus, golden queries, runners, committed reports
frontend/              Next.js 15 + Tailwind
docs/adr/              architecture decisions and their revisit triggers
```

---

## License

Not yet chosen.
