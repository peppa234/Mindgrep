# Evaluation

You cannot improve retrieval you cannot measure. Everything here exists to turn "search feels
better" into a number that goes up or down.

## Retrieval: two benchmarks

| | Fixture (`golden/fixture.yaml`) | Personal (`golden/personal.yaml`) |
|---|---|---|
| Corpus | `corpus/`: 5 small repos (Python, TS, Go, Rust, Java), a notes vault, 2 PDFs | Your real notes and repos |
| Queries | 44 answerable + 12 unanswerable, in 5 categories | 60–100, written by you |
| Purpose | Regression gate in CI; proves the pipeline works | The number for the README |
| Committed | Yes, all of it | Reports only (labels are gitignored) |

## Labels

Labels are stable keys, never database ids, so re-indexing and re-chunking never invalidate
them: `path` plus an optional `symbol` (function, `Class.method`, or Markdown heading) or
`page` (PDF), with a `grade` (2 = the answer, 1 = useful context). The runner refuses to run
if any label matches no indexed chunk, so a typo or a chunker change cannot silently
deflate the score.

## Metrics

- **Recall@10 / @50**: share of labels found in the top 10 / 50.
- **NDCG@10**: graded, rank-aware; the headline number.
- **MRR**: 1 / rank of the first relevant hit.
- **Abstention** (rerank mode): the reranker-score threshold that best separates answerable
  from unanswerable queries. It becomes the chat's "I couldn't find that" threshold.

Every mode is evaluated separately (`lexical`, `vector`, `hybrid`, `rerank`), so each stage's
contribution is visible rather than assumed.

## Knowledge graph

`golden/graph.yaml` lists hand-checked facts about the fixture corpus: which projects use a
technology (asked the way a person types it: `postgres`, `springboot`, `golang`), each
project's exact stack, and whether the chat routes a question to the graph or to RAG.
`runners/graph_eval.py` reports precision and recall, and CI fails below 1.0: the
deterministic extractors have no excuse for noise, so any miss is a bug.

## Ideas

`golden/ideas.yaml` lists every idea in the fixture notes (tagged notes, the `ideas/` folder,
an `Idea:` line in a journal) with what matching alone should conclude from the code
(`matched`: implemented, partial, unimplemented), the project, and what the user should see
after the note's own frontmatter (`status`). `runners/idea_eval.py` reports:

- detection precision and recall (anything detected that is not labelled is a false positive);
- matching status accuracy and project accuracy;
- **false never** (built or half-built, reported as never implemented) and **false built**,
  counted separately because they do not cost the same;
- the ideas each chat question lists ("What AI ideas have I never implemented?");
- a threshold sweep per signal (coverage, similarity): the thresholds that would have been
  best on the labelled set, which is how `IDEA_COVERAGE_*` / `IDEA_SIMILARITY_*` get set.

CI runs it with word coverage only and gates detection at 1.0, declared statuses at 1.0,
false built at 0, and false never at 1 (the half-built vector database, which only the
reranker's similarity catches). With the real models it scores 1.0 across the board.

## Chat

`runners/chat_eval.py` runs the retrieval golden set through the whole chat pipeline and
reports abstention accuracy (abstained exactly on the unanswerable queries), answer rate,
citation precision (cited sources that match a label), and grounded rate. `--threshold
0.05,0.1,0.2` compares abstention thresholds side by side. It is meaningful only with the real
reranker and a real chat model, so it is not a CI gate.

## Running

```powershell
.\make.ps1 eval                            # fixture, all modes, real models -> reports/fixture-<date>.md
.\make.ps1 label "query"                   # candidates + ready-to-paste labels
.\make.ps1 eval-personal                   # your benchmark over what you have indexed
.\make.ps1 eval-graph                      # knowledge-graph precision/recall and routing
.\make.ps1 eval-chat                       # end-to-end chat: abstention and citations
.\make.ps1 eval-ideas                      # idea <-> implementation gap, threshold sweep
```

CI runs the fixture with `EMBEDDER=hash` (no model download) and fails if NDCG@10, Recall@10
or MRR drop more than 0.02 below `reports/baseline-ci.json`. When a change is *meant* to move
the numbers, regenerate the baseline in the same PR:

```powershell
.\make.ps1 eval-baseline
```

## Files

- `corpus/`: the fixture corpus. Byte-exact (`.gitattributes` disables line-ending conversion).
- `golden/`: query sets.
- `runners/`: `retrieval_eval.py` (the harness), `graph_eval.py`, `idea_eval.py`, `chat_eval.py`, `metrics.py`,
  `label.py`.
- `reports/`: committed results, one pair of `.md` + `.json` per run worth keeping.
- `tools/build_pdfs.py`: regenerates the fixture PDFs.
