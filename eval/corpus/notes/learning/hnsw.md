---
title: HNSW notes
tags: [vector-search, learning]
---

# HNSW (Hierarchical Navigable Small World)

Graph-based approximate nearest neighbour index. Each vector is a node; search starts at the
top layer (few nodes, long links) and greedily descends to the bottom layer (all nodes, short
links).

## Parameters

- **m**: number of neighbours per node. Higher = better recall, more memory. 16 is a sane default.
- **ef_construction**: size of the candidate list while building. Higher = better graph,
  slower build. 64–200.
- **ef_search**: size of the candidate list at query time. The main recall/latency knob.
  It must be at least k, or you cannot get k results back.

## Things that bit me

With a filter (`WHERE project = ...`) the index returns the nearest neighbours *first* and
filters *after*, so a selective filter can leave you with 3 results instead of 10.
pgvector 0.8 added iterative scans to keep searching until enough rows pass the filter.

Compare with IVFFlat: needs training data up front, worse recall at the same speed, but much
faster to build. See [[Reciprocal Rank Fusion]] for combining vector results with keyword search.
