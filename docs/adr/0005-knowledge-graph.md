# ADR-0005: A deterministic graph first, and an LLM layer that cannot overwrite it

- Status: accepted
- Date: 2026-09-26

## Context

"Which projects use PostgreSQL?" has an exact answer sitting in dependency manifests. LLM
extraction of entities from prose is expensive, non-deterministic, and hallucinates. And
entity resolution is where graphs quietly rot: `postgres`, `psycopg2-binary`, `asyncpg`,
`pgx` and the `pgvector/pgvector` image are one technology, while `React` and `Preact` embed
almost identically and are two.

## Decision

**Postgres tables, not a graph database** (ADR-0001). `nodes(kind, key, name)` and `edges(src,
dst, type)`. One-hop questions are indexed joins; the ego-network view is one recursive CTE.

**Deterministic extraction runs as an indexing stage** (`sync -> walk -> parse -> graph ->
embed`):

| Fact | Read from |
|---|---|
| Project | Git working trees; outside them, the shallowest folder with a root manifest |
| Project `depends_on` Package | pyproject, requirements, Pipfile, setup.py, package.json, go.mod, Cargo.toml, pom.xml, Gradle, Gemfile, composer.json |
| Project `uses` Technology | curated packages in those manifests; Dockerfile and compose images; curated imports; file languages above a 10% share |
| Person `authored` Project | `git log` per project |
| Note `links_to` / `mentions` / `tagged` | `[[wikilinks]]` and `#tags` |

**A curated alias table** (`services/graph/technologies.py`, ~200 entries) maps names, package
names per ecosystem, import names and Docker images to one canonical technology. Resolution is
exact after normalisation. Nothing is ever merged on embedding similarity. Uncurated
dependencies still exist as `package` nodes, so "which projects depend on bincode" works too.

**Every edge has provenance.** The document, the line, the chunk containing that line, the
evidence text, the extractor, and a confidence. Graph answers cite it, and the project page
shows it under "why?".

**Rebuilds are idempotent.** A source's deterministic edges are replaced in one transaction
under an advisory lock. Nodes are upserted by `(kind, key)`, and shared nodes nothing points
at any more are pruned.

**The LLM layer comes second and is fenced in** (`services/graph/concepts.py`, run on demand):
notes and READMEs only; cached by `(chunk hash, prompt version)`; an item survives only if its
evidence quote really occurs in the chunk; technologies join a curated node only by exact
alias; everything else becomes a `concept` node at confidence 0.7. Its edges
(`extractor = llm`) survive deterministic rebuilds and never replace deterministic ones.

## Consequences

- The fixture graph eval (CI) requires precision and recall of 1.0. A miss is a bug in a parser
  or the alias table, and it is caught before merge.
- A technology with no manifest, image or import (Kubernetes YAML, a SaaS API called over
  plain HTTP) is invisible to the deterministic layer. The chat then falls back to search, not
  to a false "you never used it".
- Adding a technology is a one-line change to the alias table.
- Revisit Neo4j under the trigger in ADR-0001 (multi-hop > 5% of queries and CTE p95 > 200 ms).
