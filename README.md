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

**Status:** Phase 2 of 3 (*The Brain*) is complete: chat with cited, streamed answers that
abstain when the answer is not in your data, and a knowledge graph of your projects built
from manifests, imports and git, with an LLM layer on top. Phase 1 (*The Index*) is below it.
See [Roadmap](#roadmap).

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

**"Which project used PostgreSQL?" is answered from a graph, not by a model.** Dependency
manifests, Dockerfiles, imports and git history become `Project -uses-> Technology` edges,
each citing the manifest line it came from. A curated alias table makes `asyncpg`,
`psycopg2-binary`, `pgx` and the `pgvector/pgvector` image all mean PostgreSQL, and never
merges on similarity (React is not Preact). Graph questions are answered without an LLM:
exact, free, and cited ([ADR-0005](docs/adr/0005-knowledge-graph.md)).

**It says "not in your memory".** Two abstention layers: below a calibrated reranker score
the model is never called, and a model that finds no answer in the sources must say exactly
`NO_ANSWER`, which is caught mid-stream. Every claim cites a numbered source (file and line
range). Invented citation numbers are dropped, and an answer citing nothing is flagged
([ADR-0004](docs/adr/0004-chat-pipeline.md)).

**Quality is measured, not claimed.** A labelled retrieval benchmark (Recall@k, NDCG@10,
MRR per search mode, including *unanswerable* queries), a graph benchmark (precision and
recall of extracted facts), and an end-to-end chat eval (abstention accuracy, citation
precision). The first two gate CI. See [Evaluation](#evaluation).

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

**Knowledge graph** (`eval/golden/graph.yaml`, gated in CI at 1.0):

| Check | Items | Precision | Recall |
|---|---|---|---|
| "which projects use X" (X typed the way a person would: `postgres`, `springboot`, `golang`) | 27 | 1.000 | 1.000 |
| project stacks | 5 | 1.000 | 1.000 |
| chat routing (graph vs. RAG) | 13 | accuracy 1.000 | |

**Chat** (`.\make.ps1 eval-chat`): abstention accuracy and citation precision over the same
56 queries. It needs the real reranker and a real chat model to mean anything, so its numbers
land here with the first real-model run.

---

## Architecture

One database. Postgres 16 holds the relational data, the vectors (pgvector + HNSW), the
full-text index (`tsvector` + `pg_trgm`), the knowledge graph, and the conversations
([ADR-0001](docs/adr/0001-postgres-for-everything.md)). Models run in a separate server on the
GPU ([ADR-0002](docs/adr/0002-model-server.md)).

```
Next.js ──/api proxy──> FastAPI ─────────────────────────────────> Postgres 16
 chat · search ·           │  chat (SSE): condense → intent ─┬─> graph answer (no model)
 projects · sources ·      │                                 └─> search → abstain? → LLM
 document view             │  search: vector ∥ fts ∥ symbol → RRF → rerank
                           │                                          chunks: HNSW · tsvector · pg_trgm
                           │  Gemini ┐                                nodes · edges (graph)
                           │  Groq   ├ fallback chain, one            conversations · feedback
                           │  Ollama ┘ OpenAI-compatible client
                           │ enqueue
                        Valkey <──> ARQ worker ──> sync (git) → walk (.gitignore, secrets)
                        queue +     → parse (tree-sitter · Markdown · PyMuPDF) → chunk
                        emb. cache  → graph (manifests, imports, git, wikilinks) → embed
                                    · on demand: LLM concept extraction (cached, verified)
                                         │
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
file gets the last commit from its own repo, and each repo becomes a project. Then ask, or
search.

For written answers, put a free key in `.env`: `GEMINI_API_KEY` (Google AI Studio) and/or
`GROQ_API_KEY`, or run Ollama locally and set `OLLAMA_MODEL`. Without one, graph questions
still get full answers and every other question gets its sources. To add LLM-extracted
concepts from your notes on top of the deterministic graph: `.\make.ps1 extract <source id>`.

| URL | What it is |
|---|---|
| http://localhost:3000 | The app: chat, search, projects, sources, and a document view that shows every chunk boundary |
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
| 2. **The Brain** | 8–15 | RAG chat with citations and abstention; knowledge graph (deterministic extraction from manifests, imports and git first, LLM extraction after); chat + projects UI | ✅ done |
| 3. **The Product** | 16–20 | Idea ↔ implementation gap, ego-network graph view, polish, deploy | next |

The eval harness landed *before* the retrieval work it judges. That ordering is the point:
you cannot improve what you cannot measure.

---

## Repository layout

```
backend/app/services/  ingestion (walker, git, pipeline) · parsing · chunking · embedding · retrieval
                       graph (manifests, technologies, builder, queries, concepts) · llm · chat
backend/app/modelserver/  the GPU model server
backend/tests/         unit + integration (real Postgres, no models needed)
eval/                  corpus, golden queries, runners, committed reports
frontend/              Next.js 15 + Tailwind
docs/adr/              architecture decisions and their revisit triggers
```

---

## License

Not yet chosen.
