# MemoryOS

An AI operating system for developers that remembers, connects, and understands everything you build.

Point it at your notes, your PDFs, and your Git repositories, then ask questions in plain
language and get answers with citations down to the file and line range.

The query it is really built for is the one no ordinary search can answer:

> **"What ideas have I written down and never implemented?"**

Answering that means extracting ideas from notes, detecting implementations in code, and
returning the *difference* between them — retrieval over the absence of things.

**Status:** early. Phase 0 of 10. The stack boots; nothing is indexed yet. See [Roadmap](#roadmap).

---

## Why this is not another chat-with-your-docs project

Three deliberate choices, each of which will be measured rather than asserted:

**Code is chunked on AST boundaries, not character counts.** A function is a chunk. Splitting a
function in half — which every fixed-size chunker does — destroys the thing you were searching
for. `tree-sitter` gives these boundaries deterministically, with no model and no hallucination.

**Retrieval is hybrid, then reranked.** Nobody searches for "the function that makes the token";
they search for `generate_token`. Dense embeddings are weak at exact identifiers, so lexical
search runs alongside vector search and a cross-encoder reranks the merged set.

**Quality is measured, not claimed.** A hand-labelled benchmark of real queries against a real
corpus, with Recall@k, NDCG@10 and MRR reported here and gated in CI. It includes
*unanswerable* queries, because a system that never says "I don't know" is a system that
hallucinates.

---

## Architecture

One database. Postgres 16 holds the relational data, the vectors (pgvector + HNSW), the
full-text index (`tsvector` + `pg_trgm`), and the knowledge graph (`nodes` / `edges` tables
queried with recursive CTEs).

There is no Neo4j and no Qdrant, deliberately. The conditions under which that would change
are written down rather than left to taste:

| Deferred | Added when |
|---|---|
| Qdrant | chunk count passes ~5M, **or** ANN p95 latency passes 150 ms |
| Neo4j | multi-hop traversal exceeds 5% of queries **and** recursive-CTE p95 passes 200 ms |

```
Next.js  ──REST + SSE──>  FastAPI  ──>  Postgres 16
                             │           pgvector (HNSW) · full-text (GIN) · graph (CTE)
                             │
                          Valkey  <──>  ARQ workers
                          queue +       walk · parse · chunk
                          cache         embed · extract · link
```

---

## Quickstart

Requires Docker Desktop.

```powershell
git clone https://github.com/peppa234/MemoryOs
cd MemoryOs
copy .env.example .env
.\make.ps1 up
.\make.ps1 health
```

Expected output:

```json
{"status":"ok","checks":{"postgres":{"ok":true,"extensions":["pg_trgm","vector"]},"valkey":{"ok":true}}}
```

Then browse the API. FastAPI generates these from the code, so they are never out of date:

| URL | What it is |
|---|---|
| http://localhost:8000/docs | Swagger UI — every endpoint, with a **Try it out** button that sends real requests |
| http://localhost:8000/redoc | The same API as a clean reference page |
| http://localhost:8000/openapi.json | The raw OpenAPI schema; the typed frontend client is generated from this later |

`.\make.ps1 docs` opens Swagger UI for you.

On Linux or macOS, `make up` and `make health` do the same thing. Run `.\make.ps1` with no
arguments to list every task.

---

## Roadmap

| Phase | What it delivers | Status |
|---|---|---|
| 0 | Stack boots: Postgres + pgvector, Valkey, FastAPI, CI | in progress |
| 1 | Ingestion — walk folders and repos, parse code/Markdown/PDF into `documents` | |
| 2 | AST-boundary chunking, embeddings, pgvector index, `/search` | |
| 3 | **Evaluation harness** — golden queries, NDCG@10, `make eval` | |
| 4 | Hybrid retrieval, RRF fusion, cross-encoder reranking | |
| 5 | RAG chat: streamed, cited, and willing to abstain | |
| 6 | Knowledge graph — deterministic extraction first, LLM second | |
| 7 | Idea ↔ implementation gap detection | |
| 8 | Frontend and UX | |
| 9 | Auth and multi-user | |
| 10 | Deployment and documentation | |

The eval harness lands *before* the retrieval work it is meant to judge. That ordering is the
point: you cannot improve what you cannot measure.

---

## License

Not yet chosen.
