---
title: Reciprocal Rank Fusion
tags: [retrieval, learning]
---

# Reciprocal Rank Fusion

Combine several ranked lists without looking at their scores:

    score(d) = sum over lists of 1 / (k + rank(d))

with k = 60 from the original paper (Cormack, Clarke, Büttcher 2009).

## Why ranks and not scores

BM25 scores are unbounded, cosine similarities live in [-1, 1], and neither is calibrated.
Normalising them (min-max, z-score) is fragile because the distribution changes per query.
Ranks are always comparable.

## When it fails

If one retriever is much worse than the other, RRF still gives it half the vote. Weighted RRF
or a cross-encoder reranker on the fused top-50 fixes most of that.
