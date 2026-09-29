# Retrieval eval: fixture

- Date: 2026-09-29T20:24:02+00:00
- Queries: 44 answerable, 12 unanswerable
- Embedding model: `hash-v1`; reranker: `None`

| Mode | Recall@10 | Recall@50 | NDCG@10 | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| lexical | 0.977 | 0.989 | **0.854** | 0.844 | 25 | 35 |
| vector | 0.807 | 1.000 | **0.702** | 0.703 | 31 | 54 |
| hybrid | 0.989 | 1.000 | **0.814** | 0.777 | 31 | 65 |

NDCG@10 by query category:

| Mode | identifier | keyword | note | pdf | vague |
|---|---|---|---|---|---|
| lexical | 1.000 | 0.862 | 0.838 | 1.000 | 0.761 |
| vector | 0.811 | 0.926 | 0.875 | 0.667 | 0.450 |
| hybrid | 0.954 | 0.931 | 0.877 | 1.000 | 0.622 |

Weakest queries in `hybrid` (NDCG@10 < 0.5):

- `vague-01` first relevant at rank 8; top 3: ['notes/learning/reciprocal-rank-fusion.md :: Reciprocal Rank Fusion', 'papers/bm25-notes.pdf :: p. 2', 'notes/cheatsheets/docker.md :: Docker notes']
- `vague-04` first relevant at rank 2; top 3: ['notes/ideas/broken-link-crawler.md :: Broken link crawler', 'repos/link-checker/crawler.go :: Crawler, BrokenLink, job', 'repos/link-checker/crawler.go :: Crawler.fetch, Crawler.record']
- `vague-05` first relevant at rank 10; top 3: ['notes/journal/2024-03-12.md :: 2024-03-12', 'notes/journal/2024-05-02.md :: 2024-05-02', 'notes/learning/hnsw.md :: HNSW notes > HNSW (Hierarchical Navigable Small World) > Parameters']
- `vague-09` first relevant at rank 5; top 3: ['notes/ideas/study-group-kanban.md :: Kanban board for the study group', 'repos/auth-service/app/models.py :: User, Base, RevokedToken', 'notes/projects/student-portal-architecture.md :: Student Portal architecture > Current design (v2, 2024)']
- `vague-10` first relevant at rank 6; top 3: ['notes/ideas/vector-database-from-scratch.md :: Vector database from scratch', 'repos/task-board/src/store/tasks.ts :: reindex, TaskState, Task', 'notes/learning/hnsw.md :: HNSW notes > HNSW (Hierarchical Navigable Small World) > Things that bit me']
- `vague-14` first relevant at rank 4; top 3: ['notes/ideas/broken-link-crawler.md :: Broken link crawler', 'repos/link-checker/crawler.go :: Crawler.fetch, Crawler.record', 'repos/link-checker/crawler.go :: Crawler.Run']
- `note-03` first relevant at rank 6; top 3: ['notes/ideas/vector-database-from-scratch.md :: Vector database from scratch', 'papers/bm25-notes.pdf :: p. 1', 'notes/learning/hnsw.md :: HNSW notes > HNSW (Hierarchical Navigable Small World) > Things that bit me']
