# Evaluation

You cannot improve retrieval you cannot measure. Everything here exists to turn "search feels
better" into a number that goes up or down.

## Two benchmarks

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

## Running

```powershell
.\make.ps1 eval                            # fixture, all modes, real models -> reports/fixture-<date>.md
.\make.ps1 label "query"                   # candidates + ready-to-paste labels
.\make.ps1 eval-personal                   # your benchmark over what you have indexed
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
- `runners/`: `retrieval_eval.py` (the harness), `metrics.py`, `label.py`.
- `reports/`: committed results, one pair of `.md` + `.json` per run worth keeping.
- `tools/build_pdfs.py`: regenerates the fixture PDFs.
