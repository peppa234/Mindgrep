---
title: RAG for Darija
created: 2024-02-11
tags: [idea, nlp, rag]
status: idea
---

# RAG for Darija

Retrieval-augmented question answering over Algerian and Moroccan Darija. Nobody serves
this well: the big models answer in MSA or French and miss dialect vocabulary.

## Why it is hard

- No standard orthography. The same word shows up in Arabic script and in Arabizi
  ("3lach", "wach", "kifach") with numbers standing in for letters.
- Code-switching mid-sentence between Darija, French and MSA.
- Almost no labelled retrieval data.

## Rough plan

1. Normalise Arabizi to Arabic script with a character-level transliteration model.
2. Embed with a multilingual model (bge-m3) and test whether it clusters dialect with MSA.
3. Build a small evaluation set from community forum questions.

Related: [[Multilingual embeddings]], [[Reciprocal Rank Fusion]]
