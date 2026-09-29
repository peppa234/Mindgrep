---
title: Vector database from scratch
created: 2023-10-08
tags: [idea, databases]
---

# Vector database from scratch

Write my own vector database to understand approximate nearest neighbour search: an HNSW graph
index, product quantization to shrink the stored vectors, snapshots persisted to disk, and a
gRPC endpoint so other services can query it.

Start with exact brute-force search as the baseline to measure recall against.
