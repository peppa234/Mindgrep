# ADR-0003: Three retrieval channels fused with RRF, then a cross-encoder

- Status: accepted
- Date: 2026-09-25

## Context

The corpus mixes prose (notes, papers) and code. Dense embeddings are good at paraphrase ("the
function that retries with growing delays") and weak at exact identifiers
(`generate_jwt_token`). Full-text search is the opposite. Neither handles a half-remembered
identifier (`limit_login` for `limit_login_attempts`).

## Decision

Three candidate channels, 60 candidates each:

1. **vector**: pgvector cosine over `header + content` embeddings.
2. **lexical**: weighted `tsvector`. Weight A holds symbol names and path words, B holds the
   text, and C holds camelCase/snake_case identifiers split into words (Postgres cannot split
   `generateJwtToken` itself).
3. **symbol**: `pg_trgm` word similarity on defined names, used when the query contains
   identifier-like tokens.

They are fused with Reciprocal Rank Fusion (k = 60), which uses ranks only, so incomparable
scores never need normalising. The top 60 are reranked by bge-reranker-v2-m3, whose sigmoid
scores are comparable across queries; that makes them usable as an abstention threshold.

Each stage is individually selectable (`mode` = lexical | vector | hybrid | rerank), and the
eval harness reports every mode separately, so each stage's contribution is measured rather
than assumed.

## Consequences

- Exact identifiers, paraphrases, and partial names each have a channel that finds them.
- Reranking costs one cross-encoder pass over 60 short texts (tens of ms on the GPU).
- Chunks carry a header (`source/path :: Class.method (lines a-b)` plus the imports they
  use) that is embedded and reranked with the text, so a chunk always says where it is from.
