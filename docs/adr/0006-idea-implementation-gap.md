# ADR-0006: The idea ↔ implementation gap is decided by evidence, and a person has the last word

- Status: accepted
- Date: 2026-09-29

## Context

"What ideas have I written down and never implemented?" is retrieval over the absence of
things. Search cannot answer it on its own: it ranks, and a ranking always has a first
result. Saying "nothing implements this" needs an absolute signal per project, and it needs
to be right in the direction that matters. Telling someone they never built a thing they
did build costs the feature its credibility at once; missing that a half-built prototype
exists is a smaller error than that, but still an error.

Ideas are also ambiguous. "RAG for Darija": did I build it? A prototype that died? A
binary built / not built flag would hide the ambiguity instead of modelling it.

## Decision

**Ideas are what the person marked as ideas.** A note tagged `#idea`, typed `type: idea`, or
kept in an `ideas/` folder is one idea (title plus first paragraph). A line starting with
`Idea:` in any other note is one idea (the sentence plus its paragraph). This runs as an
indexing stage, is deterministic, and cites the note and line. An LLM layer for ideas nobody
marked can come later, fenced the way concept extraction is (ADR-0005).

**Three layers of status, the most deliberate one wins**, each stored separately:

1. what the user said on the Ideas page (`user_status`, `user_project_id`), which survives
   every re-index;
2. what the note itself declares in its frontmatter (`status: done | wip | abandoned`,
   `implemented_by: <project>`);
3. what matching concluded from the code (`status`, `implemented_by_id`), recomputed after
   every index run.

`abandoned` exists only in the first two layers; nothing infers it.

**Matching uses two absolute signals per project, and either can decide:**

- *coverage*: the IDF-weighted share of the idea's distinctive words (stemmed exactly as the
  full-text index stems them, words in more than 5% of chunks dropped) that occur anywhere in
  the project's code and docs. It needs no model and explains itself: the words matched, the
  words no project contains, the file holding the most of them.
- *similarity*: the cross-encoder's score (sigmoid, 0 to 1) for the idea against the
  project's closest chunk, from the normal search pipeline. It catches the paraphrase coverage
  misses: "drag cards between columns" against a `moveTask` function.

A project clearing a *partial* threshold on either signal makes the idea partly built; an
*implemented* threshold, built. A `[[wikilink]]` from the idea's note to a project counts as
partial evidence. The idea is "never implemented" only when no project clears any bar. OR
rather than AND leans on purpose toward finding an implementation.

**Every verdict ships with its evidence.** The candidates (top 3 projects with coverage,
similarity, matched words and closest chunk), and the idea's distinctive words that no
project contains, are stored with the idea and shown on the page and in the chat answer.
The `implemented_by` graph edge cites the chunk that matched, like every other edge.

**The chat answers idea questions without a model.** "What AI ideas have I never
implemented?" routes (by rules, like the other graph intents) to a listing built from the
table, with a topic filter (tags, words, technology aliases, and a fixed vocabulary for "AI").

## Consequences

- The idea eval (`eval/golden/ideas.yaml`, `runners/idea_eval.py`) reports detection
  precision/recall, matching accuracy, and the two errors separately: *false never* (built,
  called unimplemented) and *false built*. CI gates detection at 1.0, declared statuses at 1.0,
  false built at 0, and matching with coverage alone at its current floor.
- With coverage alone (CI: no models), the half-built vector database in the fixture is
  missed: "a tiny exact nearest-neighbour store" shares few words with "a vector database
  with an HNSW index". That is the case the reranker's similarity exists for, and the eval
  measures whether it closes it.
- Thresholds live in settings (`IDEA_COVERAGE_*`, `IDEA_SIMILARITY_*`). The eval prints the
  best thresholds per signal on the labelled set, which is how they are set for a real corpus.
- Coverage grows with project size: a very large monorepo contains many rare words. If that
  shows up as false *built* on a real corpus, weight the best single file's coverage over the
  whole project's (both are already computed and stored).
- Revisit with an LLM judge (idea + README + closest chunks → built / partial / not) if the
  personal benchmark shows the two signals disagreeing often. It would be one more signal
  with evidence, not a replacement for them.
