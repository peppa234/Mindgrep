# Retrieval eval: fixture

- Date: 2026-09-25T20:25:36+00:00
- Queries: 44 answerable, 12 unanswerable
- Embedding model: `hash-v1`; reranker: `None`

| Mode | Recall@10 | Recall@50 | NDCG@10 | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| lexical | 0.989 | 0.989 | **0.885** | 0.883 | 21 | 103 |
| vector | 0.830 | 1.000 | **0.727** | 0.740 | 39 | 98 |
| hybrid | 0.989 | 1.000 | **0.839** | 0.818 | 59 | 99 |

NDCG@10 by query category:

| Mode | identifier | keyword | note | pdf | vague |
|---|---|---|---|---|---|
| lexical | 1.000 | 0.862 | 0.891 | 1.000 | 0.812 |
| vector | 0.811 | 0.926 | 0.909 | 0.667 | 0.496 |
| hybrid | 0.954 | 0.931 | 0.913 | 1.000 | 0.666 |

Weakest queries in `hybrid` (NDCG@10 < 0.5):

- `vague-01` first relevant at rank 7; top 3: ['notes/learning/reciprocal-rank-fusion.md :: Reciprocal Rank Fusion', 'papers/bm25-notes.pdf :: p. 2', 'notes/cheatsheets/docker.md :: Docker notes']
- `vague-05` first relevant at rank 8; top 3: ['notes/journal/2024-03-12.md :: 2024-03-12', 'notes/learning/hnsw.md :: HNSW notes > HNSW (Hierarchical Navigable Small World) > Parameters', 'repos/auth-service/app/security.py :: verify_password, hash_password, _hasher']
- `vague-09` first relevant at rank 3; top 3: ['notes/projects/student-portal-architecture.md :: Student Portal architecture > Current design (v2, 2024)', 'repos/auth-service/app/models.py :: User, Base, RevokedToken', 'repos/task-board/src/store/tasks.ts :: reindex, TaskState, Task']
- `vague-10` first relevant at rank 5; top 3: ['repos/task-board/src/store/tasks.ts :: reindex, TaskState, Task', 'notes/learning/hnsw.md :: HNSW notes > HNSW (Hierarchical Navigable Small World) > Things that bit me', 'repos/task-board/src/components/TaskList.tsx :: TaskList']
- `note-03` first relevant at rank 5; top 3: ['papers/bm25-notes.pdf :: p. 1', 'notes/learning/hnsw.md :: HNSW notes > HNSW (Hierarchical Navigable Small World) > Things that bit me', 'repos/vecstore/src/lib.rs :: VecStore, VecStore.new, VecStore.insert']
