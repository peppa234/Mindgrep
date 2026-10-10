# MemoryOS V1 — Developer Second Brain
## Architecture, Cost, and Build Plan for a Solo Developer

**Scope:** Software engineers and AI engineers only. Markdown notes, PDFs, GitHub repositories.
**Constraint:** One developer, 4–6 months, near-zero budget.
**Status:** Buildable plan, not a wish list.

> ### Where the build stands (2026-10-10)
>
> The 10 phases below were condensed into three: **The Index** (Phases 0–4), **The Brain**
> (5–6) and **The Product** (7–8, 10). Phase 9 (multi-user auth) was cut first, as §10.1 says.
>
> | Phase | State | What is still open |
> |---|---|---|
> | 0. Setup | ✅ | — |
> | 1. Ingestion | ✅ tree-sitter for 6 languages, Markdown, PyMuPDF, manifests, ARQ, idempotent | Docling OCR (scanned PDFs are flagged `needs_ocr`, not read) |
> | 2. Chunking & embeddings | ✅ AST chunking, embedding cache, HNSW | LLM contextual headers (headers are deterministic instead) |
> | 3. Eval harness | ✅ 44 + 12 unanswerable fixture queries, CI gates for retrieval, graph and ideas | **60–100 queries over your own data** (`eval/golden/personal.example.yaml` is still a template) |
> | 4. Hybrid + rerank | ✅ three channels, RRF, bge-reranker, metadata filters, measured | Lift is not yet shown: on the fixture, vector alone ties hybrid+rerank. Needs the personal benchmark |
> | 5. RAG chat | ✅ fallback chain (Gemini models → Groq → Ollama), cited SSE, two-layer abstention, history, feedback | Chat eval numbers; Langfuse tracing |
> | 6. Knowledge graph | ✅ deterministic edges, alias table, verified LLM concepts, neighbourhood CTE | Graph-augmented retrieval (entity in query → seed chunks) |
> | 7. Idea ↔ implementation gap | ✅ detection, matching with evidence, built / partial / abandoned / never, overrides | LLM idea extraction or LLM judge, only if the personal benchmark asks for it |
> | 8. Frontend | ✅ every page, redesign, landing, styleguide, SVG ego-network (instead of Cytoscape) | Lighthouse ≥ 85 and keyboard-only gates; a real ⌘K palette |
> | 9. Auth & multi-user | ✂️ cut | RLS + the cross-tenant leak test, if anyone else ever uses it |
> | 10. Deploy & docs | 🟡 prod compose, Caddy, backups, deploy workflow, six ADRs | Live URL, screenshots, demo video, license, Sentry |
>
> Departures from this plan, on purpose: Valkey instead of Redis, ideas are detected
> deterministically (tag, folder, `Idea:` line) rather than by LLM, `/ideas` instead of
> `/insights`, and no Pydantic AI (structured output is plain JSON schema + verification).

---

## 0. The Simplification You Just Unlocked

Your three sources — local Markdown, PDFs, GitHub repos — are **all files on a disk**. A GitHub repo is `git clone` → a folder. A notes vault is a folder. PDFs are a folder.

That means V1 has **one ingestion pipeline**, not three. No OAuth token refresh, no rate limits, no webhook infrastructure, no per-connector sync state machines, no pagination bugs. You just need a file walker, a router by extension, and Git as a bonus metadata source.

This single fact removes about six weeks from the build. Design around it deliberately: **the ingestion interface is a path, not an API.**

The second thing worth naming up front: of your five example queries, four are ordinary retrieval. One is not.

> "What AI ideas have I never implemented?"

That query requires joining *ideas extracted from notes* against *implementations detected in code*, and returning the **negative space** — the set difference. No RAG tutorial does this. It is the query that makes your project memorable instead of "another chat-with-docs app." Design the data model so it is possible, and build it in V1 even in a crude form. §7 covers this.

---

## 1. Tech Stack

### 1.1 The stack

| Layer | Choice | Why |
|---|---|---|
| **Frontend** | Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui | You already know React/Next. Server components handle the heavy browse views; SSE handles streamed answers. shadcn gives you a professional look in days, not weeks — and this project's screenshots matter. |
| **Backend** | FastAPI (Python 3.12) + Pydantic v2 | The retrieval and ML ecosystem is Python-only. Pydantic models double as API schemas *and* LLM structured-output schemas — one definition, three uses. |
| **ORM / migrations** | SQLAlchemy 2.0 + Alembic | Migrations from day one. Retrofitting them at month 3 is miserable. |
| **Primary DB** | **PostgreSQL 16 + pgvector + pg_trgm** | One database for relational data, vectors, full-text search, *and* the graph. See §1.2 — this is the most important decision in the document. |
| **Vector DB** | **pgvector (inside Postgres). No Qdrant in V1.** | Your corpus is ~50k–500k chunks. pgvector with HNSW handles millions comfortably. A separate vector store adds a second system to deploy, back up, monitor, and keep consistent — for zero benefit at your scale. |
| **Knowledge graph** | **Postgres tables (`nodes`, `edges`) + recursive CTEs. No Neo4j in V1.** | See §1.2. |
| **Cache / queue** | **Redis** (or Valkey) | Job queue backend, embedding cache, session cache, rate limiting. One system, four jobs. |
| **Background jobs** | **ARQ** (asyncio + Redis) | Celery is heavier than you need and its async story is awkward. ARQ is ~200 lines of concepts, natively async like FastAPI, and Redis-only. If you already know Celery, use Celery — not worth the learning cost either way. |
| **Auth** | **Better Auth** or **Clerk free tier**; fallback = FastAPI JWT + Argon2 | You are a security person, so you *can* build it — but it will cost you 2 weeks and add zero portfolio value here. If it's single-user or self-hosted, a single API key is honestly enough for V1. |
| **LLM framework** | **Direct SDK calls + Pydantic AI for structured extraction. LangGraph only in Phase 6.** | Do not start with LangGraph. For V1, your "agent" is: classify intent → retrieve → synthesize. That's a function. Introduce LangGraph when you actually need branching, checkpointing, and multi-turn state — not before. Frameworks obscure the retrieval logic you're supposed to be learning. |
| **Embeddings** | Local **Qwen3-Embedding-0.6B** (dev) → cloud API (prod). Code chunks get a code-tuned model. | §3. |
| **Code parsing** | **tree-sitter** (+ `py-tree-sitter`) | This is the technical heart of the product. §8.1. |
| **Doc parsing** | **PyMuPDF** (fast path) + **Docling** (hard PDFs) | 90% of your PDFs are born-digital papers → PyMuPDF is instant and free. Docling only for scans. |
| **Deployment** | **Docker Compose on a single VPS** (Hetzner CX22, ~€4/mo) | Not Kubernetes. Not serverless. One box, one compose file, Caddy for TLS. You can move later; you almost certainly won't need to. |
| **Frontend hosting** | Vercel free tier (or serve Next.js from the same VPS) | |
| **Containers** | Docker + Docker Compose, multi-stage builds | Dev/prod parity, and it's the thing recruiters check. |
| **Monitoring** | **Langfuse** (self-hosted, free) + structured JSON logs + Sentry free tier | Langfuse is the one non-obvious pick: LLM traces, token counts, cost per query, prompt versioning, eval scores. Standard APM cannot tell you *why an answer was wrong*. |
| **Testing** | pytest + pytest-asyncio + testcontainers + **a retrieval eval harness** | The eval harness is the differentiator. §6 Phase 3. |
| **CI/CD** | GitHub Actions → lint, type-check, test, eval gate, build image, deploy over SSH | Free for public repos. |

### 1.2 The two decisions you'll be tempted to get wrong

**Decision A: Neo4j — skip it in V1.**

| Option | For | Against | Verdict |
|---|---|---|---|
| Neo4j | Cypher is genuinely elegant for paths; looks impressive | A second database: separate deploy, backup, consistency problem, transaction boundary problem. You'd be syncing entity state between Postgres and Neo4j and *that sync will break*. Adds ~2GB RAM to your VPS. | ❌ V1 |
| **Postgres `nodes` + `edges` tables** | One transaction covers the memory and the graph. Zero new infra. 1-hop and 2-hop queries are indexed joins — genuinely fast. Recursive CTEs handle 3–4 hops fine at your scale. | Deep traversal (5+ hops) gets awkward; no Cypher | ✅ **V1** |
| Apache AGE (Cypher inside Postgres) | Cypher without a second DB | Extension availability on managed hosts is patchy; adds a dependency for a syntax preference | ⚠️ Optional later |

Be honest about what your queries actually need. "Which project used PostgreSQL?" is `SELECT ... JOIN edges WHERE target = 'PostgreSQL' AND type = 'uses'`. That is one hop. You do not need a graph database for one hop. Nine out of ten "we need Neo4j" decisions are one-hop queries in disguise.

**Add Neo4j when** — and only when — you measure that multi-hop traversal is >5% of queries and your recursive CTEs exceed 200ms. Write that trigger down.

**Decision B: Qdrant — skip it in V1.**

pgvector with an HNSW index over 500k chunks on a 4GB VPS returns top-100 in well under 100ms. Qdrant is better at 50M+ vectors, filtered search at scale, and quantization. You will not have 50M vectors. Adding it now costs you a second store to keep in sync with Postgres, which is the classic source of "my search returns deleted documents" bugs.

**Add Qdrant when** vector count passes ~5M or p95 ANN latency passes 150ms.

### 1.3 What this stack means

You are deploying **three containers**: `api` (FastAPI), `worker` (ARQ), `postgres`. Plus `redis` and `caddy`. Five containers on one €4 box, one `docker compose up`. That is a stack a solo developer can actually operate while also being a final-year student.

---

## 2. Cost

### 2.1 During development: genuinely $0

Everything below runs on your own laptop. **Do not pay for anything in months 1–4.**

| Technology | Free? | Open source? | Dev cost | Notes |
|---|---|---|---|---|
| Next.js, React, Tailwind, shadcn | ✅ | ✅ | $0 | |
| FastAPI, Pydantic, SQLAlchemy, Alembic | ✅ | ✅ | $0 | |
| PostgreSQL + pgvector | ✅ | ✅ | $0 | Docker locally |
| Redis / Valkey | ✅ | ⚠️ Redis is SSPL since 2024; **Valkey** is the true-OSS fork | $0 | Use Valkey if licensing matters to you |
| ARQ | ✅ | ✅ | $0 | |
| tree-sitter | ✅ | ✅ | $0 | |
| PyMuPDF | ✅ | ⚠️ AGPL — matters only if you go closed-source commercial | $0 | Docling (Apache-2.0) is the permissive alternative |
| Docling | ✅ | ✅ | $0 | |
| Docker / Compose | ✅ | ✅ | $0 | |
| Langfuse (self-hosted) | ✅ | ✅ | $0 | Also has a free cloud tier |
| GitHub Actions | ✅ | — | $0 | Unlimited minutes on public repos |
| Sentry | ✅ free tier | ✅ core | $0 | 5k errors/mo |
| pytest, Playwright | ✅ | ✅ | $0 | |
| **Local embeddings (Qwen3-Embedding-0.6B via sentence-transformers / Ollama)** | ✅ | ✅ | $0 | Runs on your laptop GPU |
| **Local reranker (bge-reranker-v2-m3)** | ✅ | ✅ | $0 | ~600MB, CPU-viable |
| **Local LLM (Qwen3 / Llama / DeepSeek distills via Ollama)** | ✅ | ✅ | $0 | For extraction tasks |
| **Cloud LLM free tiers** | ✅ | — | $0 | See 2.2 |

**Total development cost: $0.** Not "cheap." Zero. Your laptop is the entire infrastructure.

### 2.2 Free LLM APIs worth wiring up (as of mid-2026)

The free-tier landscape is real but volatile — <cite index="45-1">every provider enforces rate limits and the only truly unlimited path is self-hosting open weights.</cite> The correct strategy is to <cite index="44-1">register keys with several providers on day one</cite> and route with fallback.

| Provider | What you get | Best used for |
|---|---|---|
| **Google AI Studio (Gemini Flash)** | <cite index="40-1">Free tier with up to 1M-token context and multimodal input</cite> | Long documents, PDF understanding, synthesis |
| **Groq** | <cite index="43-1">Generous daily request limits, no credit card, open-weight models</cite> | Fast extraction, classification, routing |
| **Cerebras, Mistral, GitHub Models, OpenRouter free slots** | Additional headroom | Fallback lanes |

Two warnings, both important:

1. <cite index="42-1">Free tiers are generally funded by your prompts — assume your data may be used for training.</cite> Since your corpus is *your own code and notes*, decide consciously whether you're comfortable with that. For a portfolio project: probably fine. If you ever onboard another user: absolutely not — move to paid or local.
2. Build a **provider abstraction with fallback** in week 1. Free tiers change monthly. Your code should not care which provider answered.

### 2.3 When you deploy (month 4+)

| Item | Option | Monthly |
|---|---|---|
| VPS (5 containers, 4GB RAM) | Hetzner CX22 | **~€4** |
| Domain | Namecheap/Porkbun | ~$1 (annualized) |
| Postgres | On the same VPS in Docker | $0 |
| Alternative: managed Postgres | <cite index="56-1">Neon and Supabase have permanent free tiers</cite> — Supabase includes pgvector natively; Neon gives 0.5GB with scale-to-zero | $0 |
| Redis | On the VPS, or Upstash free tier (<cite index="51-1">256MB, 500K commands/month</cite>) | $0 |
| Frontend | Vercel hobby | $0 |
| LLM inference | Free tiers + local | $0–5 |
| **Realistic total** | | **~$5–8/month** |

**GitHub Student Developer Pack.** You're at ENSIA — apply if you haven't. It typically includes DigitalOcean credits, Namecheap domain, JetBrains, and various API credits. That can cover your entire first year.

If you ever hit real usage, the cheapest paid step for inference is a budget provider like DeepSeek; but at portfolio scale you will not get there.

---

## 3. AI Models

### 3.1 Recommended for V1

| Task | Local (dev, $0) | Cloud (prod) | Why |
|---|---|---|---|
| **Text embedding (notes, PDFs)** | **Qwen3-Embedding-0.6B** — Apache-2.0, ~1.2GB, runs on your GPU, strong for its size | Gemini Embedding or Voyage-3.x | 0.6B is the sweet spot: near-4B quality at laptop cost. Start here, benchmark before upgrading. |
| **Code embedding** | **jina-embeddings-v2-base-code** or **Qwen3-Embedding-0.6B with a code-aware prompt prefix** | voyage-code-3 (best-in-class for code, paid) | Code retrieval is a *different* task from prose retrieval. Function names, call sites, and identifiers behave unlike natural language. Use a separate collection/namespace and measure the difference. |
| **Reranker** | **bge-reranker-v2-m3** — Apache-2.0, 100+ languages, 8k context, CPU-runnable | Cohere Rerank (free eval tier) | The single highest quality-per-effort component in your whole pipeline. Retrieve 60, rerank to 10. |
| **Sparse / lexical** | Postgres `tsvector` + `pg_trgm` | same | Free, and it catches exact identifiers (`generate_jwt_token`) that embeddings miss. **Mandatory** for code search. |
| **Extraction LLM** (entities, relations, summaries) | Qwen3-8B or similar via Ollama | Groq (Llama/Qwen) or Gemini Flash | High volume, low difficulty. Optimize for cost. Use strict JSON schema enforcement, not "please return JSON." |
| **Synthesis LLM** (the answer the user reads) | — (too slow locally for good UX) | **Gemini Flash free tier**, upgrade to a frontier model if quality demands | This is the product. Do not economize here — economize on extraction. |
| **PDF parsing** | **PyMuPDF** for born-digital | — | Instant, free, handles 90% of papers |
| **OCR (scanned PDFs only)** | **Docling** (Granite-Docling-258M, Apache-2.0) or **MinerU** | Mistral OCR / LlamaParse | Route by detection: if PyMuPDF extracts <100 chars/page, it's scanned → OCR path. |
| **Code understanding** | **tree-sitter** (AST) + LLM for semantics | — | See below — this is not a model choice, it's an architecture choice. |

### 3.2 On "code understanding" — the most important paragraph here

There is no "code understanding model" you should reach for. Code understanding in V1 is **tree-sitter + a schema + a cheap LLM**, in that order:

1. **tree-sitter** parses each file into an AST and gives you *structural* facts for free, deterministically, with zero hallucination: function names, class names, signatures, imports, decorators, line spans, docstrings. This is 70% of the value at 0% of the cost.
2. **Chunk on AST boundaries**, never on character count. One function = one chunk (splitting further if huge). This alone beats every naive RAG implementation of code search.
3. **Dependency files** (`requirements.txt`, `package.json`, `pyproject.toml`, `go.mod`, `Dockerfile`, `docker-compose.yml`) give you `Project uses Technology` edges *deterministically*. "Which project used PostgreSQL?" should be answered by a parsed dependency list, not by an LLM guessing from prose. **Deterministic extraction beats LLM extraction every time it's available.**
4. **LLM only for semantics** the AST can't give you: "what does this module do," "what architectural pattern is this," "is this an auth implementation." Run it at Tier 1 on important files only.

If you get 1–3 right, your product will already outperform most commercial code-chat tools on your specific queries. That's your technical story.

### 3.3 Model abstraction

Wrap everything behind four interfaces: `Embedder`, `Reranker`, `Chat`, `Parser`. Model identity is config. This lets you develop entirely locally and flip to cloud with an env var — and it is what makes the free-tier volatility survivable.

---

## 4. Database Architecture

### 4.1 What lives where

**PostgreSQL — everything structural, and in V1 that includes vectors and the graph.**

| Table group | Contents |
|---|---|
| `users`, `api_keys` | Identity |
| `sources` | A registered folder/repo: path, type, sync state, last indexed commit |
| `documents` | One row per file: path, type, language, size, content hash, git metadata (last commit, author, date) |
| `chunks` | The retrievable unit: text, contextual header, `document_id`, char/line span, symbol name, chunk kind (`function`/`class`/`markdown_section`/`pdf_page`), **`embedding vector(1024)`**, `tsv tsvector` |
| `nodes` | Graph entities: `Project`, `Technology`, `Concept`, `Document`, `Idea`, `Person`, `Paper` |
| `edges` | `source_id`, `target_id`, `type`, `confidence`, `provenance_chunk_ids[]`, `created_at` |
| `ideas` | Extracted ideas from notes, with `implemented_by_project_id` nullable ← **this nullable FK is the "never implemented" query** |
| `queries`, `feedback` | Every query, its retrieved set, and accept/reject — your eval data and your learning signal |

Indexes: HNSW on `embedding`, GIN on `tsv`, GIN on `edges(target_id, type)`, trigram on `nodes.name`.

**Redis**
- ARQ job queue (ingestion, embedding, extraction tasks)
- Embedding cache keyed by `hash(text) + model_version` — **saves you enormous re-embedding time during development, when you'll re-index the same corpus fifty times**
- Query result cache (short TTL)
- Rate limiting, session state

**Qdrant — nothing in V1.** Trigger to add: >5M chunks or ANN p95 >150ms.

**Neo4j — nothing in V1.** Trigger to add: multi-hop >5% of queries and recursive CTE p95 >200ms.

Write both triggers into your README as "planned scaling path." It shows judgment: choosing *not* to use a technology, with a stated condition, reads far more senior than using it prematurely.

### 4.2 Architecture diagram

```
┌──────────────────────────────────────────────────────────────┐
│                    Next.js Frontend (Vercel)                 │
│   Chat · Search · Projects · Graph (ego-view) · Ingest UI    │
└───────────────────────────┬──────────────────────────────────┘
                            │ REST + SSE
┌───────────────────────────▼──────────────────────────────────┐
│                     FastAPI  (Docker)                        │
│  ┌────────────┬─────────────┬──────────────┬──────────────┐  │
│  │  routers   │  retrieval  │   graph      │   ingest     │  │
│  │            │  hybrid+RRF │  CTE queries │   enqueue    │  │
│  │            │  +rerank    │              │              │  │
│  └────────────┴─────────────┴──────────────┴──────────────┘  │
└──────┬──────────────────────┬─────────────────────┬──────────┘
       │                      │                     │
       │                 ┌────▼────┐          ┌─────▼──────────┐
       │                 │  Redis  │◄────────►│  ARQ Workers   │
       │                 │ queue + │          │  ┌──────────┐  │
       │                 │  cache  │          │  │ walk     │  │
       │                 └─────────┘          │  │ parse    │  │
       │                                      │  │ chunk    │  │
       │                                      │  │ embed    │  │
       │                                      │  │ extract  │  │
       │                                      │  │ link     │  │
       │                                      │  └──────────┘  │
       │                                      └───────┬────────┘
┌──────▼──────────────────────────────────────────────▼────────┐
│                      PostgreSQL 16                           │
│  ┌───────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ documents │ │  chunks  │ │  nodes   │ │ ideas          │  │
│  │ sources   │ │ +vector  │ │  edges   │ │ queries        │  │
│  │ users     │ │ +tsvector│ │          │ │ feedback       │  │
│  └───────────┘ └──────────┘ └──────────┘ └────────────────┘  │
│         pgvector (HNSW)  ·  full-text (GIN)  ·  graph (CTE)  │
└──────────────────────────────────────────────────────────────┘
       │                                              │
┌──────▼───────────┐                        ┌─────────▼────────┐
│  Local filesystem│                        │  Model providers │
│  notes/ repos/   │                        │  Gemini · Groq · │
│  pdfs/           │                        │  local Ollama    │
└──────────────────┘                        └──────────────────┘
                                                     │
                                            ┌────────▼────────┐
                                            │    Langfuse     │
                                            │ traces · cost   │
                                            └─────────────────┘
```

### 4.3 The read path in one line

`query → intent + entity resolution → (vector ∥ BM25 ∥ graph seed) → RRF → rerank → assemble → stream cited answer`

---

## 5. Project Structure

```
memoryos/
├── docker-compose.yml            # api, worker, postgres, redis, caddy
├── docker-compose.dev.yml
├── Makefile                      # make dev / make test / make eval / make index
├── .env.example
├── README.md                     # ← treat this as a deliverable, not an afterthought
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic/
│   │   └── versions/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py             # pydantic-settings
│   │   ├── deps.py
│   │   │
│   │   ├── api/v1/
│   │   │   ├── auth.py
│   │   │   ├── sources.py        # register folder / repo, trigger index
│   │   │   ├── chat.py           # SSE streaming answers
│   │   │   ├── search.py
│   │   │   ├── documents.py
│   │   │   ├── graph.py
│   │   │   ├── projects.py
│   │   │   └── insights.py       # "ideas never implemented"
│   │   │
│   │   ├── db/
│   │   │   ├── session.py
│   │   │   ├── base.py
│   │   │   └── models/
│   │   │       ├── user.py
│   │   │       ├── source.py
│   │   │       ├── document.py
│   │   │       ├── chunk.py
│   │   │       ├── node.py
│   │   │       ├── edge.py
│   │   │       ├── idea.py
│   │   │       └── feedback.py
│   │   │
│   │   ├── schemas/              # Pydantic — API + LLM structured output
│   │   │   ├── chat.py
│   │   │   ├── extraction.py     # the schemas the LLM must fill
│   │   │   └── graph.py
│   │   │
│   │   ├── services/
│   │   │   ├── ingestion/
│   │   │   │   ├── walker.py          # filesystem traversal, .gitignore-aware
│   │   │   │   ├── git.py             # clone, pull, commit metadata, blame
│   │   │   │   ├── router.py          # extension → parser
│   │   │   │   └── dedupe.py          # content hashing
│   │   │   ├── parsing/
│   │   │   │   ├── code.py            # tree-sitter AST extraction
│   │   │   │   ├── markdown.py        # heading-aware, frontmatter, wikilinks
│   │   │   │   ├── pdf.py             # PyMuPDF → Docling fallback
│   │   │   │   └── manifests.py       # requirements.txt, package.json, etc.
│   │   │   ├── chunking/
│   │   │   │   ├── code_chunker.py    # AST-boundary chunks
│   │   │   │   ├── text_chunker.py    # structure-aware
│   │   │   │   └── contextual.py      # LLM-generated chunk headers
│   │   │   ├── embedding/
│   │   │   │   ├── base.py            # Embedder interface
│   │   │   │   ├── local.py
│   │   │   │   ├── cloud.py
│   │   │   │   └── cache.py
│   │   │   ├── retrieval/
│   │   │   │   ├── query_understanding.py
│   │   │   │   ├── vector.py
│   │   │   │   ├── lexical.py
│   │   │   │   ├── fusion.py          # RRF
│   │   │   │   ├── rerank.py
│   │   │   │   └── assembler.py       # context budget, dedupe, ordering
│   │   │   ├── graph/
│   │   │   │   ├── extractor.py       # LLM relation extraction
│   │   │   │   ├── resolver.py        # entity dedup (conservative!)
│   │   │   │   ├── builder.py
│   │   │   │   └── queries.py         # recursive CTEs
│   │   │   ├── insights/
│   │   │   │   └── unimplemented.py   # the signature feature
│   │   │   └── llm/
│   │   │       ├── base.py            # Chat interface
│   │   │       ├── providers/         # gemini.py, groq.py, ollama.py
│   │   │       ├── router.py          # fallback chain across free tiers
│   │   │       └── prompts/           # versioned .md/.jinja templates
│   │   │
│   │   ├── agents/                    # Phase 6+ only
│   │   │   ├── orchestrator.py
│   │   │   └── tools.py
│   │   │
│   │   ├── workers/
│   │   │   ├── main.py                # ARQ WorkerSettings
│   │   │   └── tasks/
│   │   │       ├── index_source.py
│   │   │       ├── embed_batch.py
│   │   │       ├── extract_graph.py
│   │   │       └── consolidate.py
│   │   │
│   │   └── core/
│   │       ├── logging.py
│   │       ├── errors.py
│   │       ├── security.py
│   │       └── telemetry.py           # Langfuse wiring
│   │
│   └── tests/
│       ├── unit/
│       ├── integration/               # testcontainers postgres
│       └── conftest.py
│
├── eval/                              # ← your differentiator
│   ├── corpus/                        # a fixed, versioned test corpus
│   ├── golden/
│   │   └── queries.yaml               # query → expected chunk ids + expected behaviour
│   ├── runners/
│   │   ├── retrieval_eval.py          # Recall@k, NDCG@10, MRR
│   │   ├── extraction_eval.py         # entity/relation precision
│   │   └── e2e_eval.py                # groundedness, correctness
│   └── reports/                       # committed results over time
│
├── frontend/
│   ├── Dockerfile
│   ├── app/
│   │   ├── (auth)/
│   │   ├── chat/page.tsx
│   │   ├── search/page.tsx
│   │   ├── projects/[id]/page.tsx
│   │   ├── documents/[id]/page.tsx
│   │   ├── graph/page.tsx
│   │   ├── insights/page.tsx
│   │   └── sources/page.tsx
│   ├── components/
│   │   ├── chat/                      # message, citation chip, source panel
│   │   ├── graph/                     # cytoscape ego-network
│   │   ├── code/                      # syntax-highlighted chunk viewer
│   │   └── ui/                        # shadcn
│   ├── lib/
│   │   ├── api.ts                     # typed client
│   │   └── sse.ts
│   └── types/                         # generated from OpenAPI
│
├── infra/
│   ├── caddy/Caddyfile
│   └── deploy.sh
│
├── docs/
│   ├── adr/                           # ADR-0001: why no Neo4j in V1, etc.
│   ├── architecture.md
│   └── screenshots/
│
└── .github/workflows/
    ├── ci.yml
    └── deploy.yml
```

**Note the `eval/` directory sitting as a first-class citizen next to `backend/`.** That placement is deliberate and it is the thing that will make an experienced reviewer take the repo seriously.

---

## 6. Development Phases

I've reordered your proposed sequence. Two changes matter a lot:

- **Authentication moves to near-last.** Auth is a solved, boring problem that teaches you nothing and blocks nothing. Build single-user with a hardcoded user ID for months. Adding auth to a working system takes 4 days; building auth first delays the interesting work by two weeks and produces the same result.
- **The eval harness moves to Phase 3, before RAG.** You cannot improve retrieval you cannot measure. Every hour spent here saves five hours of guessing later. This is the single most important reordering in the plan.

Estimates assume **~15–20 hours/week** (realistic for a final-year student with other commitments).

### Phase 0 — Setup & Skeleton
| | |
|---|---|
| **Goal** | `docker compose up` gives you a working API, DB, worker, and frontend that talk to each other |
| **Features** | Repo scaffold, Docker Compose (postgres+pgvector, redis, api, worker), Alembic initial migration, FastAPI health endpoint, Next.js shell, GitHub Actions CI running lint+tests, Makefile |
| **Time** | 1 week |
| **Difficulty** | ⭐⭐ |
| **Depends on** | — |
| **Deliverable** | One command boots the whole stack. CI green on `main`. |

> Do not skip CI here. Adding it at month 4 means retrofitting tests you never wrote.

### Phase 1 — Ingestion & Parsing
| | |
|---|---|
| **Goal** | Point at a folder or GitHub URL; every file lands in Postgres as structured `documents` |
| **Features** | Filesystem walker (`.gitignore`-aware, binary/size filters), git clone + pull + commit metadata, extension router, **tree-sitter code parsing** (Python, JS/TS, + 2 more), Markdown parser (headings, frontmatter, wikilinks), PDF parser (PyMuPDF → Docling fallback), manifest parsers (`requirements.txt`, `package.json`, `pyproject.toml`, `Dockerfile`), content-hash dedupe, ARQ job pipeline, indexing progress API |
| **Time** | 2.5 weeks |
| **Difficulty** | ⭐⭐⭐ |
| **Depends on** | Phase 0 |
| **Deliverable** | Index 10 of your own real repos + your notes vault + 30 PDFs. Report counts by type. Re-running is idempotent. |

> This is the least glamorous phase and the one most people rush. A messy ingestion layer poisons everything downstream. Get idempotency and dedupe right *now*.

### Phase 2 — Chunking & Embeddings
| | |
|---|---|
| **Goal** | Every document becomes searchable chunks with vectors |
| **Features** | **AST-boundary code chunking** (one function/class per chunk, with signature + docstring + file path in the header), structure-aware Markdown chunking, PDF page/section chunking, LLM-generated contextual headers, local embedding service with batching, Redis embedding cache, pgvector HNSW index, basic `/search` returning top-k |
| **Time** | 2 weeks |
| **Difficulty** | ⭐⭐⭐⭐ |
| **Depends on** | Phase 1 |
| **Deliverable** | `POST /search {"q": "jwt token generation"}` returns your actual auth code from the right repo. |

> The embedding cache is not optional. You will re-index your corpus dozens of times; without the cache each pass costs 20+ minutes of GPU time.

### Phase 3 — Evaluation Harness ⚠️ *do not skip*
| | |
|---|---|
| **Goal** | You can measure whether a retrieval change made things better or worse |
| **Features** | Fixed versioned test corpus, 60–100 golden queries written by hand against **your own real data** with labelled expected chunk IDs, Recall@10/@50, NDCG@10, MRR runners, a `make eval` command, results committed to `eval/reports/`, CI job that runs eval and posts the diff on PRs |
| **Time** | 1 week |
| **Difficulty** | ⭐⭐ (tedious, not hard) |
| **Depends on** | Phase 2 |
| **Deliverable** | A number. A single, honest, reproducible NDCG@10 you can improve. |

> Include ~15 **unanswerable** queries — questions with no answer in your corpus. These test whether the system abstains instead of hallucinating. Almost nobody builds this, and it is the difference between a demo and a system.

### Phase 4 — Hybrid Retrieval & Reranking
| | |
|---|---|
| **Goal** | Retrieval quality that actually works on code |
| **Features** | Postgres full-text (`tsvector`) + trigram identifier search, Reciprocal Rank Fusion, **cross-encoder reranking (bge-reranker-v2-m3)**, metadata filters (project, language, file type, date range), query understanding (intent classification, temporal parsing, technology-name detection) |
| **Time** | 1.5 weeks |
| **Difficulty** | ⭐⭐⭐ |
| **Depends on** | Phase 3 |
| **Deliverable** | Eval report showing measured lift over Phase 2. Expect roughly +0.10–0.20 NDCG — and now you can *prove* it. |

> Lexical search matters enormously for code. Nobody searches for "the function that makes the token" — they search for `generate_token`. Dense embeddings are bad at exact identifiers.

### Phase 5 — RAG Chat with Citations
| | |
|---|---|
| **Goal** | Ask a question, get a grounded, cited, streamed answer |
| **Features** | LLM provider abstraction with free-tier fallback chain, context assembler (budget, dedupe, ordering), citation binding to `chunk_id` + line span, SSE streaming (`sources` event before tokens), abstention when top score is below threshold, conversation history, Langfuse tracing, feedback endpoint (accept/reject) |
| **Time** | 2 weeks |
| **Difficulty** | ⭐⭐⭐ |
| **Depends on** | Phase 4 |
| **Deliverable** | "Where did I implement JWT authentication?" → an answer naming the repo, file, and line range, with a clickable citation. **This is your first demo-able moment.** |

### Phase 6 — Knowledge Graph
| | |
|---|---|
| **Goal** | Projects, technologies, concepts, and documents become a connected, queryable graph |
| **Features** | `nodes`/`edges` schema, **deterministic extraction first** (manifests → `uses`, imports → `depends_on`, git authorship → `authored`, folder structure → `Project`), LLM extraction for concepts and ideas from notes, conservative entity resolution with alias table and normalization (`postgres`/`postgresql`/`PostgreSQL` → one node), recursive-CTE graph queries, graph-augmented retrieval (entity in query → seed chunks), `/graph/neighborhood` API |
| **Time** | 3 weeks |
| **Difficulty** | ⭐⭐⭐⭐⭐ |
| **Depends on** | Phase 5 |
| **Deliverable** | "Which project used PostgreSQL?" and "Show every project where I used FastAPI" answered by graph query, not by LLM guessing. |

> Do the deterministic half first and ship it. It answers two of your five example queries with 100% precision and zero LLM cost. Only then layer LLM extraction on top for the fuzzy concepts.

### Phase 7 — The Signature Feature: Idea ↔ Implementation Gap
| | |
|---|---|
| **Goal** | "What AI ideas have I never implemented?" |
| **Features** | Idea extraction from notes (LLM, structured schema: title, description, domain, date, source chunk), implementation detection (does a project exist whose technologies/concepts/README match this idea?), similarity matching between idea embeddings and project embeddings with a confidence threshold, `implemented_by_project_id` linkage, unimplemented-ideas view sorted by age and by "how close you got", manual override (user marks an idea implemented/abandoned) |
| **Time** | 1.5 weeks |
| **Difficulty** | ⭐⭐⭐⭐ |
| **Depends on** | Phase 6 |
| **Deliverable** | A page listing your own forgotten ideas. **This is the feature people will screenshot.** |

> Keep the matching threshold conservative and always show the evidence ("I think this is unimplemented because no repo mentions these concepts"). A false "you never built this" when you clearly did destroys trust instantly.

### Phase 8 — Frontend & UX
| | |
|---|---|
| **Goal** | It looks like a product, not a thesis |
| **Features** | Chat with streaming + citation chips + source side-panel with syntax-highlighted code, search page with filters, project pages (README, tech stack, linked notes, timeline), document viewer, ego-network graph view (Cytoscape, one focal node, ≤50 nodes), insights page, source management + indexing progress, dark mode, keyboard shortcuts (`⌘K`) |
| **Time** | 3 weeks |
| **Difficulty** | ⭐⭐⭐ |
| **Depends on** | Phase 7 |
| **Deliverable** | Screenshots you're proud to put in the README. |

> Do **not** build a global force-directed graph of every node. It looks impressive for four seconds and is unusable. Ego-networks only.

### Phase 9 — Auth & Multi-User
| | |
|---|---|
| **Goal** | Someone other than you can use it |
| **Features** | Registration/login, sessions, `user_id` scoping on every query, **Postgres Row-Level Security**, per-user source isolation, rate limiting |
| **Time** | 1 week |
| **Difficulty** | ⭐⭐ |
| **Depends on** | Phase 8 |
| **Deliverable** | Two accounts cannot see each other's data — with a test that proves it. |

> Write the cross-tenant leak test. As a security person, that test is a signature move and takes 30 minutes.

### Phase 10 — Deployment & Documentation
| | |
|---|---|
| **Goal** | It's live, and the repo tells the story |
| **Features** | Production Docker Compose, Caddy + TLS, GitHub Actions deploy, backups, Sentry, self-hosted Langfuse, README with architecture diagram + screenshots + eval numbers, ADRs, 2-minute demo video |
| **Time** | 1.5 weeks |
| **Difficulty** | ⭐⭐⭐ |
| **Depends on** | Phase 9 |
| **Deliverable** | A live URL and a repo that explains itself in 60 seconds. |

**Total: ~19.5 weeks ≈ 5 months** at 15–20 hrs/week. That fits your window with roughly two weeks of slack — which you will need, because something always breaks.

---

## 7. MVP Definition

### 7.1 In V1 — the smallest set that still feels revolutionary

| Feature | Why it's essential |
|---|---|
| Index local Markdown, PDFs, GitHub repos from a path or URL | The corpus |
| **AST-aware code chunking** | The technical moat; makes code search actually work |
| Hybrid search (vector + lexical) + reranking | The quality floor |
| Chat with citations to file + line range, and abstention | The core loop |
| Deterministic tech-stack graph (manifests, imports) | Answers 2 of your 5 queries perfectly, cheaply |
| Project pages with auto-detected stack, linked notes, timeline | Makes the graph *visible* |
| **Idea ↔ implementation gap detection** | The one thing nobody else has |
| Ego-network graph view | Proof the graph is real |
| Eval harness with published numbers | Proof the retrieval is real |

That's it. Nine things.

### 7.2 Postponed to V2 — and be ruthless

| Feature | Why it waits |
|---|---|
| Multi-agent orchestration / LangGraph | A single retrieve→synthesize function is better at this scale |
| Neo4j, Qdrant | Zero benefit at your data size (§1.2) |
| Automatic re-indexing / file watchers | Manual "re-index" button is fine; watchers are a rabbit hole |
| Incremental git-diff-based indexing | Full re-index of a repo takes seconds. Optimize later. |
| Insight generation, daily digests, proactive surfacing | High false-positive risk, low V1 value |
| Contradiction detection | Genuinely hard; save it |
| Cross-repo call-graph analysis | Very cool, very expensive |
| Multi-language beyond 4 tree-sitter grammars | Add on demand |
| Team/shared workspaces | Whole permission subsystem |
| VS Code extension | Great V2 distribution play, not V1 scope |
| Fine-tuned embeddings on your code | Needs data you don't have yet |
| Mobile | No |

### 7.3 The honest test for "revolutionary"

Your MVP passes if a stranger can watch a 90-second demo where you ask *"what AI ideas have I never implemented?"* and the system answers correctly from four years of your own notes and repos — with evidence. Everything else in V1 exists to make that moment possible and credible.

---

## 8. Risks & Technical Challenges

### 8.1 The genuinely hard parts

**1. Code chunking (hardest technical problem in V1).**
Naive character-count chunking destroys code — it splits functions mid-body, separates signatures from implementations, and orphans imports. Tree-sitter gives you AST boundaries, but you still have to decide: what about a 900-line function? A file of 200 one-line constants? Deeply nested classes? A `utils.py` with 40 unrelated helpers?

*Approach:* chunk at function/class granularity; if a node exceeds ~1500 tokens, split on inner blocks and prepend the parent signature; if a node is under ~50 tokens, group siblings. **Always prepend a header:** `repo/path/file.py :: ClassName.method_name (lines 40-92)` plus imports used. That header alone measurably improves retrieval.

**2. Entity resolution and normalization.**
`postgres`, `postgresql`, `PostgreSQL`, `psql`, `pg` are one technology. `React`, `react`, `ReactJS`, `react-dom` are one. Get this wrong and "which projects use PostgreSQL?" returns 40% of the truth.

*Approach:* maintain a curated alias table for the ~200 technologies you actually use (this is a one-evening task and it's worth more than any clever algorithm), plus normalization rules, plus embedding similarity only for the tail. **Never auto-merge on embedding similarity alone** — `React` and `Preact` are 0.94 cosine similar and are not the same thing.

**3. Ideas that are ambiguously implemented.**
"I wanted to build a RAG system for Darija" — did you? Partially? A prototype that died? Binary implemented/not-implemented is wrong.

*Approach:* three states — `implemented`, `partial`, `unimplemented` — with a confidence score, evidence shown, and a user override. Model the ambiguity instead of hiding it.

**4. Query understanding for temporal and scoped queries.**
"What was my *original* architecture for Student Portal?" needs: entity resolution (Student Portal → project), temporal reasoning (*original* = earliest commits / earliest notes), and source-type preference (design docs and early READMEs over current code).

*Approach:* a small intent classifier plus git history as your temporal skeleton — commit dates are ground truth you get for free. This query is where git metadata earns its keep.

**5. Retrieval evaluation without a ground truth.**
You're building over your own data, so nobody has labelled it. Labelling 100 queries by hand is boring and you will want to skip it.

*Approach:* don't skip it. Do 20 queries a day for a week. It is the highest-value week in the project.

### 8.2 Mistakes beginners make (that I'd bet money you'll be tempted by)

| Mistake | Why it happens | What to do instead |
|---|---|---|
| **Adding Neo4j + Qdrant + Elasticsearch on day one** | The architecture diagram looks impressive | Start with Postgres. Document the trigger for adding each one. Restraint reads as seniority. |
| **Building on LangChain/LlamaIndex abstractions immediately** | Tutorials use them | Write the retrieval loop yourself first. You'll understand it, debug it, and interview about it. Add frameworks when you feel the pain they solve. |
| **Fixed-size chunking** | It's the default in every tutorial | Structure-aware chunking. For code, this is the whole ballgame. |
| **Vector search only, no lexical** | Embeddings feel modern | Hybrid always. Especially for code identifiers. |
| **No reranker** | It seems like an optimization | It's the biggest single quality win available. Add it in Phase 4, not "later". |
| **Evaluating by trying 5 queries manually** | Feels faster | You'll make changes that feel better and are measurably worse. Build the harness. |
| **Chasing 100% recall** | Completionism | Precision and abstention matter more. A confident wrong answer is worse than "I couldn't find that." |
| **Building auth, billing, and admin first** | They feel like "real software" | Nobody cares. Ship the retrieval. |
| **Re-embedding the whole corpus on every code change** | No cache | Cache by `hash(text) + model_version` from Phase 2. |
| **Committing API keys** | Speed | `.env`, `.gitignore`, `git-secrets` pre-commit hook. On a public portfolio repo this is a visible, embarrassing failure. |
| **Indexing `node_modules`, `.venv`, `dist/`, `.git/`** | Naive walker | Respect `.gitignore` + a hard deny-list. Otherwise 90% of your index is dependency code and every answer cites `lodash`. |
| **Perfectionism on the frontend before retrieval works** | UI is more fun | The Phase order exists for a reason. |
| **Scope creep into "and it should also do email/voice/images"** | Excitement | You already made this cut. Hold the line. |

### 8.3 Things to actively avoid

- Do not build a file watcher / auto-sync in V1. Manual re-index button. It's a rabbit hole of debouncing, OS differences, and partial states.
- Do not attempt cross-repo call-graph analysis. Fascinating, expensive, V2.
- Do not use an LLM for anything a parser can do deterministically.
- Do not let LLM extraction write to the graph without provenance (`chunk_id` on every edge). Without it you cannot debug or delete.
- Do not run extraction on every file. Tier it: manifests and READMEs always; source files only when they're large, central, or retrieved.

---

## 9. Learning Roadmap

Skip anything you already have — you've already shipped FastAPI + Redis + Postgres work, React/Next, and Docker, so most of Blocks 0–1 is revision.

| # | Before which phase | Learn | Depth needed | Best format |
|---|---|---|---|---|
| **0** | Phase 0 | Docker Compose multi-service, healthchecks, volumes; Makefiles; GitHub Actions basics | Working | Official docs + build it |
| **1** | Phase 0–1 | FastAPI async patterns, dependency injection, Pydantic v2; SQLAlchemy 2.0 async + Alembic | Solid | FastAPI docs are excellent |
| **2** | Phase 1 | **tree-sitter** — grammars, queries, walking the AST via `py-tree-sitter`; GitPython / `git` CLI metadata; PyMuPDF | **Deep — this is your moat** | tree-sitter playground + docs; expect 2–3 days |
| **3** | Phase 1 | ARQ (or Celery) — task definition, retries, scheduling, worker lifecycle | Working | ARQ docs are short |
| **4** | Phase 2 | **Embeddings & vector search fundamentals**: cosine similarity, ANN vs exact, HNSW parameters (`m`, `ef_construction`, `ef_search`), quantization; **pgvector** operators and index tuning | **Deep** | pgvector README + one good HNSW explainer |
| **5** | Phase 2 | sentence-transformers / Ollama, batching, GPU memory management | Working | |
| **6** | Phase 3 | **IR evaluation**: precision/recall@k, MRR, NDCG, graded relevance, why NDCG > accuracy | **Deep — conceptually essential** | Any IR course chapter; this is classic material, not AI hype |
| **7** | Phase 4 | **BM25 & Postgres full-text**: `tsvector`, `tsquery`, ranking, GIN indexes, `pg_trgm` similarity | Solid | Postgres docs |
| **8** | Phase 4 | **Hybrid search & RRF**; cross-encoder vs bi-encoder; reranking | **Deep** | The BGE and RRF papers are short and readable |
| **9** | Phase 5 | Prompt engineering for grounded generation; structured outputs / JSON schema enforcement; SSE streaming in FastAPI + consuming it in Next.js | Solid | |
| **10** | Phase 5 | LLM observability: tracing, token accounting, cost attribution (Langfuse) | Working | |
| **11** | Phase 6 | **Graph data modelling in SQL**: adjacency lists, recursive CTEs, indexing edge tables; when a graph DB is actually justified | **Deep** | Postgres recursive CTE docs + practice |
| **12** | Phase 6 | Entity resolution: blocking, similarity features, clustering, conservative merging | Solid | |
| **13** | Phase 6 | Information extraction with LLMs: schema-constrained output, confidence, provenance | Solid | |
| **14** | Phase 8 | Cytoscape.js; React Server Components + streaming UI patterns | Working | |
| **15** | Phase 9 | Postgres **Row-Level Security**; JWT/session best practice; rate limiting | Solid (you're ahead here) | |
| **16** | Phase 10 | Caddy/reverse proxy, TLS, backups, deploy pipelines | Working | |
| **17** | *After* V1 | **LangGraph** — state machines, checkpointing, HITL interrupts | When you need it | Only once you feel the pain |

**Rule:** learn each block *immediately before* the phase that uses it, and learn it by building that phase. Learning LangGraph in month 1 for a Phase-6 need is how side projects die.

---

## 10. Verdict: Is This Achievable Solo in 4–6 Months?

**Yes — as scoped above. No — as you originally described it.**

The difference is four decisions:

1. **One ingestion path (files), not three connectors.** Saves ~6 weeks.
2. **Postgres only. No Neo4j, no Qdrant.** Saves ~3 weeks of infrastructure and an entire class of sync bugs.
3. **No agent framework in V1.** Saves ~2 weeks of fighting abstractions.
4. **Auth last, eval early.** Saves ~2 weeks of misdirected effort.

That's roughly 13 weeks removed — the difference between "shipped" and "abandoned at 70%."

### 10.1 If you fall behind — the pre-agreed cut list

Decide these *now*, while you're calm, so that at week 14 in a panic you don't cut the wrong thing:

| Cut order | What goes | Impact |
|---|---|---|
| 1st | Phase 9 (multi-user auth) | Ship single-user. Nobody cares for a portfolio project. |
| 2nd | PDF support | Markdown + code alone is a complete story. |
| 3rd | Graph *visualization* (keep graph queries) | The queries are the substance; the viz is decoration. |
| 4th | LLM-based concept extraction (keep deterministic) | Deterministic extraction answers most queries anyway. |
| **Never cut** | AST chunking · hybrid+rerank · citations · eval harness · idea-gap feature | These are the entire value proposition. |

### 10.2 The 10-week emergency version

If your semester explodes: Phases 0–5 plus deterministic-only Phase 6 plus a minimal Phase 8 = **a genuinely excellent "chat with your codebase and notes" tool with measured retrieval quality.** That alone is a strong project. The graph and idea-gap features become V1.1.

Ship something complete and small rather than something ambitious and 70% done. A finished 10-week project beats an abandoned 6-month one — every time, in every context that matters.

---

## 11. Is This Worth Putting on GitHub?

Short answer: **yes — but the repo alone isn't the value. What you do around it is.**

Here's the honest calibration. "RAG over documents" is now the single most common portfolio project in existence; there are tens of thousands of them and reviewers pattern-match them in about four seconds. So the question isn't *should you build it* — it's **what makes yours not look like the other ten thousand.**

Four things do, and you're already positioned for all of them:

**1. The eval harness with published numbers.**
Almost no portfolio RAG project measures anything. If your README says *"NDCG@10: 0.41 → 0.63 after AST-aware chunking + hybrid retrieval + reranking, measured on a 100-query hand-labelled benchmark,"* with a graph — you are instantly in a different category. That single line signals research maturity more than any feature list. It's also exactly the kind of rigor that graduate admissions committees look for and rarely see in applied projects.

**2. AST-aware code chunking as a stated, measured contribution.**
Most code-RAG projects chunk by character count. If you can show a controlled comparison — fixed-size vs AST-boundary chunking on the same corpus and query set — that's a small but real empirical finding. Write it up.

**3. The idea↔implementation gap feature.**
Genuinely novel framing. "Retrieval over the *absence* of things" is not a standard pattern, and it's memorable. Lead the README with it.

**4. Architectural restraint, documented.**
ADRs saying *"we chose not to use Neo4j; here is the query distribution and the latency measurement that justified it, and here is the trigger for revisiting"* — that is what distinguishes an engineer from someone who assembles tutorials. Most juniors add technologies to look impressive. Removing them with evidence is the harder and rarer signal.

**What to do beyond the repo, in order of return:**

1. **A technical writeup.** A blog post or short arXiv-style PDF: "Evaluating chunking strategies for code retrieval." With your benchmark and numbers. This converts a project into something citable.
2. **Release the benchmark.** A small, clean, open dataset of code-retrieval queries with labelled relevant chunks. Datasets get used and cited far out of proportion to their size, and creating one is a real contribution.
3. **A 90-second demo video** at the top of the README. Most people will never run your code.
4. **Screenshots and an architecture diagram** in the README. Non-negotiable.
5. **Clean commit history and real tests.** Anyone senior checks.

**What would make it *not* worth it:** shipping it at 70%, with a README that says "🚧 work in progress," no eval numbers, and five databases in the compose file. That version actively hurts you.

So: build it, cut it aggressively, measure it honestly, and write about it. The measuring and the writing are where the disproportionate return lives — and they're the parts almost everyone skips.

---

*Next concrete step: Phase 0, this week. One `docker-compose.yml`, five services, green CI. Then start hand-labelling those 100 queries in the background while you build Phase 1 — an hour a day, and by Phase 3 the boring part is already done.*
