"""Retrieval evaluation: Recall@k, NDCG@10, MRR per search mode, plus abstention separability.

Fixture benchmark (indexes eval/corpus as the source "eval-fixture", then evaluates):
    python -m eval.runners.retrieval_eval

Personal benchmark over sources you already indexed:
    python -m eval.runners.retrieval_eval --golden eval/golden/personal.yaml --no-index

Gate against a committed baseline (CI):
    python -m eval.runners.retrieval_eval --modes lexical,hybrid --baseline eval/reports/baseline-ci.json

Run inside the api container (`.\\make.ps1 eval`) so it sees the same database and models.
"""

import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from app.config import settings
from app.db.models import Chunk, Document, Source
from app.db.session import SessionLocal, engine
from app.schemas.search import SearchFilters, SearchRequest
from app.services.embedding.factory import get_embedder, get_reranker
from app.services.ingestion.pipeline import Pipeline, start_run, summarize
from app.services.retrieval.search import search
from sqlalchemy import select

from eval.runners.metrics import (
    Label,
    best_threshold,
    matches,
    ndcg_at,
    percentile,
    recall_at,
    reciprocal_rank,
)

EVAL_ROOT = Path(__file__).resolve().parents[1]
ALL_MODES = ["lexical", "vector", "hybrid", "rerank"]
POOL = 50  # hits fetched per query: enough for Recall@50


async def ensure_indexed(name: str, corpus: Path) -> int:
    async with SessionLocal() as session:
        source = (await session.execute(select(Source).where(Source.name == name))).scalar_one_or_none()
        if source is None:
            source = Source(name=name, kind="local", uri=str(corpus))
            session.add(source)
        # The corpus lives at different paths on the host and in the container.
        source.uri = str(corpus)
        await session.commit()
        source_id = source.id
        run_id = await start_run(session, source_id)
    stats = await Pipeline(SessionLocal, source_id, run_id).run()
    print(f"indexed {name}: {summarize(stats)}", file=sys.stderr)
    for warning in stats.get("warnings", []):
        print(f"  warning: {warning}", file=sys.stderr)
    return source_id


async def source_ids(names: list[str]) -> list[int]:
    async with SessionLocal() as session:
        rows = (await session.execute(select(Source.id, Source.name).where(Source.name.in_(names)))).all()
    missing = set(names) - {r.name for r in rows}
    if missing:
        raise SystemExit(f"sources not found: {', '.join(sorted(missing))}")
    return [r.id for r in rows]


async def unmatched_labels(queries: list[dict], ids: list[int] | None) -> list[str]:
    """Labels that match no chunk in the index: typos, or a chunker change that moved things."""
    async with SessionLocal() as session:
        stmt = (
            select(Document.path, Source.name, Chunk.symbol, Chunk.symbols, Chunk.meta)
            .join(Document, Document.id == Chunk.document_id)
            .join(Source, Source.id == Chunk.source_id)
        )
        if ids:
            stmt = stmt.where(Chunk.source_id.in_(ids))
        chunks = [
            {
                "path": r.path,
                "source_name": r.name,
                "symbol": r.symbol,
                "symbols": r.symbols,
                "meta": r.meta,
            }
            for r in (await session.execute(stmt)).all()
        ]
    problems = []
    for query in queries:
        for label in query["labels"]:
            if not any(matches(label, chunk) for chunk in chunks):
                problems.append(f"{query['id']}: {label.describe()}")
    return problems


def available_modes(requested: list[str]) -> tuple[list[str], list[str]]:
    modes, skipped = [], []
    for mode in requested:
        if mode in ("vector", "hybrid", "rerank") and get_embedder() is None:
            skipped.append(f"{mode} (EMBEDDER=none)")
        elif mode == "rerank" and get_reranker() is None:
            skipped.append(f"{mode} (RERANKER=none)")
        else:
            modes.append(mode)
    return modes, skipped


async def evaluate_mode(mode: str, queries: list[dict], ids: list[int] | None) -> dict[str, Any]:
    per_query = []
    for query in queries:
        request = SearchRequest(q=query["q"], k=POOL, mode=mode, filters=SearchFilters(source_ids=ids))
        started = time.perf_counter()
        async with SessionLocal() as session:
            response = await search(session, request)
        latency = (time.perf_counter() - started) * 1000
        if response.degraded:
            raise SystemExit(f"mode {mode} degraded, refusing to report it: {response.degraded}")
        hits = [h.model_dump() for h in response.hits]
        labels = query["labels"]
        top_score = hits[0]["score"] if hits else 0.0
        row = {
            "id": query["id"],
            "category": query["category"],
            "answerable": query["answerable"],
            "top_score": round(float(top_score), 4),
            "latency_ms": round(latency, 1),
            "top3": [f"{h['path']} :: {h['symbol']}" for h in hits[:3]],
        }
        if query["answerable"]:
            first = next(
                (rank for rank, h in enumerate(hits, 1) if any(matches(lb, h) for lb in labels)),
                None,
            )
            row.update(
                recall_10=recall_at(hits, labels, 10),
                recall_50=recall_at(hits, labels, 50),
                ndcg_10=ndcg_at(hits, labels, 10),
                mrr=reciprocal_rank(hits, labels),
                first_relevant_rank=first,
            )
        per_query.append(row)
    return {"summary": summarize_rows(per_query, mode), "queries": per_query}


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def summarize_rows(rows: list[dict], mode: str) -> dict[str, Any]:
    answerable = [r for r in rows if r["answerable"]]
    by_category: dict[str, list[dict]] = defaultdict(list)
    for r in answerable:
        by_category[r["category"]].append(r)
    summary = {
        "queries": len(answerable),
        "recall_10": _mean([r["recall_10"] for r in answerable]),
        "recall_50": _mean([r["recall_50"] for r in answerable]),
        "ndcg_10": _mean([r["ndcg_10"] for r in answerable]),
        "mrr": _mean([r["mrr"] for r in answerable]),
        "latency_p50_ms": round(percentile([r["latency_ms"] for r in rows], 0.5), 1),
        "latency_p95_ms": round(percentile([r["latency_ms"] for r in rows], 0.95), 1),
        "ndcg_10_by_category": {c: _mean([r["ndcg_10"] for r in rs]) for c, rs in sorted(by_category.items())},
    }
    if mode == "rerank":
        # Only reranker scores are calibrated across queries; RRF scores are rank artefacts.
        summary["abstention"] = best_threshold(
            [r["top_score"] for r in rows if r["answerable"]],
            [r["top_score"] for r in rows if not r["answerable"]],
        )
    return summary


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Retrieval eval: {report['benchmark']}",
        "",
        f"- Date: {report['created_at']}",
        f"- Queries: {report['answerable']} answerable, {report['unanswerable']} unanswerable",
        f"- Embedding model: `{report['models'].get('embedding')}`; reranker: `{report['models'].get('reranker')}`",
        "",
        "| Mode | Recall@10 | Recall@50 | NDCG@10 | MRR | p50 ms | p95 ms |",
        "|---|---|---|---|---|---|---|",
    ]
    for mode, result in report["modes"].items():
        s = result["summary"]
        lines.append(
            f"| {mode} | {s['recall_10']:.3f} | {s['recall_50']:.3f} | **{s['ndcg_10']:.3f}** | "
            f"{s['mrr']:.3f} | {s['latency_p50_ms']:.0f} | {s['latency_p95_ms']:.0f} |"
        )
    categories = sorted({c for r in report["modes"].values() for c in r["summary"]["ndcg_10_by_category"]})
    if categories:
        lines += [
            "",
            "NDCG@10 by query category:",
            "",
            "| Mode | " + " | ".join(categories) + " |",
            "|---|" + "---|" * len(categories),
        ]
        for mode, result in report["modes"].items():
            by = result["summary"]["ndcg_10_by_category"]
            lines.append(f"| {mode} | " + " | ".join(f"{by.get(c, 0):.3f}" for c in categories) + " |")
    rerank = report["modes"].get("rerank", {}).get("summary", {}).get("abstention")
    if rerank:
        lines += [
            "",
            f"Abstention: a reranker top-score threshold of **{rerank['threshold']}** separates "
            f"answerable from unanswerable queries with {rerank['accuracy']:.0%} accuracy.",
        ]
    if report["skipped_modes"]:
        lines += ["", "Skipped modes: " + ", ".join(report["skipped_modes"])]
    final_mode = next(reversed(report["modes"]), None)  # the most complete pipeline evaluated
    if final_mode:
        misses = [q for q in report["modes"][final_mode]["queries"] if q["answerable"] and q["ndcg_10"] < 0.5]
        if misses:
            lines += ["", f"Weakest queries in `{final_mode}` (NDCG@10 < 0.5):", ""]
            for q in misses:
                lines.append(f"- `{q['id']}` first relevant at rank {q['first_relevant_rank']}; top 3: {q['top3']}")
    return "\n".join(lines) + "\n"


def compare(report: dict[str, Any], baseline_path: Path, max_drop: float) -> list[str]:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    failures = []
    for mode, result in report["modes"].items():
        if mode not in baseline["modes"]:
            continue
        for metric in ("ndcg_10", "recall_10", "mrr"):
            before = baseline["modes"][mode]["summary"][metric]
            after = result["summary"][metric]
            status = "FAIL" if after < before - max_drop else "ok"
            print(f"  {status:4s} {mode:8s} {metric:10s} {before:.4f} -> {after:.4f} ({after - before:+.4f})")
            if status == "FAIL":
                failures.append(f"{mode} {metric} dropped {before:.4f} -> {after:.4f}")
    return failures


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--golden", type=Path, default=EVAL_ROOT / "golden" / "fixture.yaml")
    parser.add_argument("--corpus", type=Path, default=Path(settings.eval_corpus_dir))
    parser.add_argument("--source", default="eval-fixture", help="source name for the fixture corpus")
    parser.add_argument("--no-index", action="store_true", help="evaluate what is already indexed")
    parser.add_argument("--modes", default=",".join(ALL_MODES))
    parser.add_argument("--out", type=Path, default=EVAL_ROOT / "reports")
    parser.add_argument("--name", default=None, help="report file stem (default: <golden>-<date>)")
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--max-drop", type=float, default=0.02)
    args = parser.parse_args()

    golden = yaml.safe_load(args.golden.read_text(encoding="utf-8"))
    queries = []
    for raw in golden["queries"]:
        answerable = raw.get("answerable", True)
        queries.append(
            {
                "id": raw["id"],
                "q": raw["q"],
                "category": raw.get("category", "general"),
                "answerable": answerable,
                "labels": [Label.parse(r) for r in raw.get("relevant", [])] if answerable else [],
            }
        )

    if args.no_index:
        names = golden.get("sources")
        ids = await source_ids(names) if names else None
    else:
        ids = [await ensure_indexed(args.source, args.corpus.resolve())]

    problems = await unmatched_labels(queries, ids)
    if problems:
        print(
            "These labels match no indexed chunk. Fix the golden file (or the chunker):",
            file=sys.stderr,
        )
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 2

    modes, skipped = available_modes([m.strip() for m in args.modes.split(",") if m.strip()])
    embedder, reranker = get_embedder(), get_reranker()
    report: dict[str, Any] = {
        "benchmark": args.golden.stem,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "answerable": sum(q["answerable"] for q in queries),
        "unanswerable": sum(not q["answerable"] for q in queries),
        "models": {
            "embedding": await embedder.model_name() if embedder else None,
            "reranker": await reranker.model_name() if reranker else None,
        },
        "skipped_modes": skipped,
        "modes": {},
    }
    for mode in modes:
        print(f"evaluating {mode} ...", file=sys.stderr)
        report["modes"][mode] = await evaluate_mode(mode, queries, ids)

    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.name or f"{args.golden.stem}-{datetime.now(UTC):%Y-%m-%d}"
    (args.out / f"{stem}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.out / f"{stem}.md").write_text(markdown_report(report), encoding="utf-8")
    print(markdown_report(report))
    print(f"wrote {args.out / stem}.{{json,md}}", file=sys.stderr)

    if args.baseline is not None:
        print(f"comparing with {args.baseline} (max drop {args.max_drop}):")
        failures = compare(report, args.baseline, args.max_drop)
        if failures:
            print("eval gate failed: " + "; ".join(failures), file=sys.stderr)
            return 1
    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
