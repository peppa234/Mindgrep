# ADR-0001: Postgres holds the vectors, the full-text index, and (later) the graph

- Status: accepted
- Date: 2026-09-25

## Context

Mindgrep needs relational data (sources, documents, runs), dense vectors, lexical search, and
in Phase 2 a knowledge graph. The expected corpus is 50k–500k chunks from one person's notes
and repositories.

## Decision

One Postgres 16 database: pgvector (HNSW, cosine) for vectors, a weighted `tsvector` plus
`pg_trgm` for lexical and identifier search, and `nodes`/`edges` tables with recursive CTEs
for the graph. No Qdrant, no Elasticsearch, no Neo4j.

## Consequences

- A document, its chunks, and their vectors change in one transaction. Deleting a file cannot
  leave orphan vectors behind in a second store ("search returns deleted documents").
- One thing to back up, migrate (Alembic), and run in CI (`pgvector/pgvector:pg16`).
- pgvector 0.8's iterative index scans keep filtered vector search from returning too few rows.
- We give up Qdrant's quantisation and very-large-scale filtering, and Cypher's syntax.

## Revisit when

| Add | Trigger |
|---|---|
| Qdrant | more than ~5M chunks, or ANN p95 latency above 150 ms |
| Neo4j | multi-hop traversal above 5% of queries **and** recursive-CTE p95 above 200 ms |

Latency for every search mode is in each eval report, so the first trigger is measured, not guessed.
