# Mindgrep

**Grep your own mind.** A second brain for developers that remembers, connects, and understands
everything you build.

Point it at your notes, your PDFs, and your Git repositories, then search them the way you
remember them: *"the function that retried with growing delays"*, *"my notes on HNSW
parameters"*, `limit_login`. Answers come back as the exact function, section, or page, with
file, line range, and the commit date.

The query it is ultimately built for is the one no ordinary search can answer:

> **"What ideas have I written down and never implemented?"**

Answering that means extracting ideas from notes, detecting implementations in code, and
returning the *difference* between them: retrieval over the absence of things.

It answers that one now. Every idea you wrote down (a note tagged `#idea`, a note in an
`ideas/` folder, a line starting with `Idea:`) is checked against the code of every project
you indexed, and comes back as built, partly built, or never built, with the evidence:

> **2 of 2 ideas** about **AI** have no implementation in your 5 indexed projects (oldest first):
> - **Code review bot**, 2023-11-02 [1]: A GitHub app that comments on pull requests…
>   (closest: auth-service, 19% of its distinctive words; nowhere in your code: *bot, comments, downgrade, linter, migration*)
> - **RAG for Darija**, 2024-02-11 [2]: Retrieval-augmented question answering over Algerian and Moroccan Darija…
>   (no project comes close; nowhere in your code: *algerian, answering, augmented, big, french*)

**Status:** Phase 3 of 3 (*The Product*) is underway: the idea ↔ implementation gap, the
ego-network graph view, measured numbers with the real models, a production deployment setup,
and a full visual redesign with a landing page are in. Still to come: the personal benchmark,
screenshots and a demo, and the first live deploy. Phases 1 (*The Index*)
and 2 (*The Brain*) are complete. See [Roadmap](#roadmap).

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

**"Never implemented" is a verdict with evidence, and you have the last word.** For each
idea and each project, two absolute signals: the share of the idea's distinctive words
(IDF-weighted) that occur in the project, and the reranker's score for the idea against the
project's closest code. The idea is "never built" only when no project clears either bar,
and the page shows the words no project contains. Frontmatter (`status: abandoned`,
`implemented_by: task-board`) and your corrections on the Ideas page outrank matching and
survive every re-index ([ADR-0006](docs/adr/0006-idea-implementation-gap.md)).

**Quality is measured, not claimed.** A labelled retrieval benchmark (Recall@k, NDCG@10,
MRR per search mode, including *unanswerable* queries), a graph benchmark (precision and
recall of extracted facts), and an end-to-end chat eval (abstention accuracy, citation
precision), and an idea benchmark (detection, and matching errors in both directions). All
but the chat eval (which needs a real model) gate CI. See [Evaluation](#evaluation).

---

## Evaluation

Fixture benchmark: 44 answerable + 12 unanswerable queries over five small repos (five
languages), a notes vault, and two PDFs ([eval/](eval/README.md)).

**Retrieval, real models** (Qwen3-Embedding-0.6B + bge-reranker-v2-m3 on an RTX 5050 laptop
GPU; [report](eval/reports/fixture-2026-09-29.md)):

| Mode | Recall@10 | NDCG@10 | MRR | p50 latency |
|---|---|---|---|---|
| lexical (full-text + symbol) | 0.977 | 0.854 | 0.844 | 21 ms |
| vector (Qwen3-Embedding) | **1.000** | **0.935** | 0.936 | 411 ms |
| hybrid (RRF) | 0.989 | 0.914 | 0.920 | 75 ms |
| hybrid + rerank | 0.989 | 0.931 | **0.940** | 1.4 s |

What this says, honestly: on a corpus this small, a good embedder alone is already at the
ceiling, and fusing it with lexical search costs a little NDCG (fusion helps identifiers, which
are already at 1.0). The reranker wins most of it back and gives the best MRR. Its other job is
abstention: a top score of 0.008 separates answerable from unanswerable queries with 98%
accuracy (no answerable query refused, 1 of 12 unanswerable let through to the model's own
`NO_ANSWER` check), which is where the `ABSTAIN_THRESHOLD` default comes from. The personal
benchmark over my own notes and repos is what will settle whether fusion earns its place.

**Idea ↔ implementation gap** (`eval/golden/ideas.yaml`: 7 ideas, built, partly built,
abandoned and never built; [report](eval/reports/ideas-2026-09-29.md)):

| Check | Word coverage only (CI) | + reranker similarity |
|---|---|---|
| ideas found (precision / recall) | 1.000 / 1.000 | 1.000 / 1.000 |
| matching status accuracy | 0.857 | **1.000** |
| false "never built" (it was built) | 1 | **0** |
| false "built" (it never was) | 0 | 0 |
| "What AI ideas have I never implemented?" (precision / recall) | 1.000 / 1.000 | 1.000 / 1.000 |

The one miss without models is the half-built vector database: *"a tiny exact
nearest-neighbour vector store"* in the code shares few words with *"a vector database with an
HNSW index"* in the note. The reranker scores the pair 0.41 and gets it.

**Knowledge graph** (`eval/golden/graph.yaml`, gated in CI at 1.0):

| Check | Items | Precision | Recall |
|---|---|---|---|
| "which projects use X" (X typed the way a person would: `postgres`, `springboot`, `golang`) | 27 | 1.000 | 1.000 |
| project stacks | 5 | 1.000 | 1.000 |
| chat routing (graph vs. ideas vs. RAG) | 17 | accuracy 1.000 | |

**CI baseline** (model-free: hashing embedder, no reranker; every PR is gated on it):

| Mode | Recall@10 | NDCG@10 | MRR |
|---|---|---|---|
| lexical | 0.977 | 0.854 | 0.844 |
| vector (hashing) | 0.807 | 0.702 | 0.703 |
| hybrid (RRF) | 0.989 | 0.814 | 0.777 |

A regression floor, not a quality claim. It dropped by 0.02 to 0.04 NDCG when the idea notes
joined the corpus: they describe the same things the code does, and now compete with it (the
"broken link crawler" note outranks `crawler.go` for a vague description of it). The labels
were left alone; harder is more realistic.

**Chat, end to end** (the same 56 queries through the full pipeline; Gemini 3.5 Flash-Lite
answering, real embedder and reranker; [report](eval/reports/chat-2026-10-10.md)):

| Abstention accuracy | Answer rate | Citation hit rate | Citation precision | Errors |
|---|---|---|---|---|
| **1.000** | 1.000 | 0.977 | 0.725 | 0 |

Every unanswerable query was refused (11 by the reranker threshold before any model call, 1
by the model's own `NO_ANSWER`), and every answerable one was answered. 43 of 44 answers
cite a labelled source; the other cites nothing and is flagged as ungrounded. Citation
precision is the soft number: answers often cite a second or third source that supports
the claim but is not in the (deliberately sparse) labels, so read it as a lower bound.

---

## Architecture

One database. Postgres 16 holds the relational data, the vectors (pgvector + HNSW), the
full-text index (`tsvector` + `pg_trgm`), the knowledge graph, and the conversations
([ADR-0001](docs/adr/0001-postgres-for-everything.md)). Models run in a separate server on the
GPU ([ADR-0002](docs/adr/0002-model-server.md)).

```
Next.js ──/api proxy──> FastAPI ─────────────────────────────────> Postgres 16
 chat · search · ideas ·   │  chat (SSE): condense → intent ─┬─> graph / ideas answer (no model)
 graph · projects ·        │                                 └─> search → abstain? → LLM
 sources · documents       │  search: vector ∥ fts ∥ symbol → RRF → rerank
                           │                                          chunks: HNSW · tsvector · pg_trgm
                           │  Gemini ┐                                nodes · edges · ideas
                           │  Groq   ├ fallback chain, one            conversations · feedback
                           │  Ollama ┘ OpenAI-compatible client
                           │ enqueue
                        Valkey <──> ARQ worker ──> sync (git) → walk (.gitignore, secrets)
                        queue +     → parse (tree-sitter · Markdown · PyMuPDF) → chunk
                        emb. cache  → graph (manifests, imports, git, wikilinks) → embed
                                    → ideas (detect in notes, match against every project)
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
git clone https://github.com/peppa234/mindgrep
cd mindgrep
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
| http://localhost:3000 | The app: chat, search, ideas, the graph, projects, sources, and a document view that shows every chunk boundary |
| http://localhost:8000/docs | Swagger UI for the API |

**No GPU?** `docker compose --profile models up -d`, then set `MODEL_SERVER_URL=http://models:8001`
in `.env`. Slower, same results. With no model server at all, indexing still works and search
falls back to lexical, saying so.

**Deploying** to a VPS (Caddy with TLS and basic auth, nightly backups, a manual deploy
workflow): [docs/deploy.md](docs/deploy.md).

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

## Security

Mindgrep is single-user: whoever reaches it can read everything it indexed. So:

- **Locally, nothing listens beyond your machine.** Every port in `docker-compose.yml` and the
  model server binds to `127.0.0.1`.
- **Deployed, everything sits behind Caddy** (TLS, basic auth). Only `/health/live` answers
  without the password, and it says `{"status":"ok"}` and nothing else.
- **Other websites cannot act for you.** Writes whose `Sec-Fetch-Site` is not `same-origin` are
  refused, since a browser would otherwise attach your credentials to them. A
  Content-Security-Policy allows no script, frame or connection from another origin.
- **Indexed content is data, never code.** Answers render as React elements, never as HTML.
  Git runs with a repository's own hooks, fsmonitor and signature programs switched off.
  Clone URLs must be public `https://` hosts (no `localhost`, private networks or cloud
  metadata), and a clone over `MAX_REPO_BYTES` is deleted.
- **Dependencies are locked and audited.** `uv.lock` is installed with hashes, and CI runs
  `pip-audit` and `npm audit` on every push.

---

## Roadmap

| Phase | Weeks | What it delivers | Status |
|---|---|---|---|
| 1. **The Index** | 1–7 | Ingestion, AST chunking, embeddings, eval harness, hybrid search + rerank; sources + search UI | ✅ done |
| 2. **The Brain** | 8–15 | RAG chat with citations and abstention; knowledge graph (deterministic extraction from manifests, imports and git first, LLM extraction after); chat + projects UI | ✅ done |
| 3. **The Product** | 16–20 | Idea ↔ implementation gap ✅, ego-network graph view ✅, real-model numbers ✅ (chat eval included), deploy setup ✅, redesign + landing page ✅; personal benchmark, chunking ablation (fixed-size vs AST), screenshots and demo, first live deploy | in progress |

Deliberately left out of V1: multi-user auth (a single-user deploy sits behind Caddy basic
auth), OCR for scanned PDFs (they are flagged, not read), and LLM tracing (Langfuse).

The eval harness landed *before* the retrieval work it judges. That ordering is the point:
you cannot improve what you cannot measure.

---

## Repository layout

```
backend/app/services/  ingestion (walker, git, pipeline) · parsing · chunking · embedding · retrieval
                       graph (manifests, technologies, builder, queries, concepts) · ideas · llm · chat
backend/app/modelserver/  the GPU model server
backend/tests/         unit + integration (real Postgres, no models needed)
eval/                  corpus, golden queries, runners, committed reports
frontend/              Next.js 15 + Tailwind
docs/adr/              architecture decisions and their revisit triggers
docs/deploy.md         production: compose override, Caddy, backups, deploy workflow
infra/                 Caddyfile, deploy.sh, backup.sh, Postgres init
```

---

## License

[MIT](LICENSE).
