"""End-to-end chat evaluation over the retrieval golden set: does the chat abstain when the
answer is not there, and do its citations point at the right chunks when it is?

    python -m eval.runners.chat_eval                           # fixture, whatever models are configured
    python -m eval.runners.chat_eval --threshold 0.05,0.1,0.2  # compare abstention thresholds

Metrics:
  abstention accuracy : share of queries where "abstained" == "unanswerable"
  answer rate         : answerable queries that got an answer (not an abstention)
  citation precision  : cited sources that match a golden label, over all cited sources
  citation hit rate   : answered queries whose citations include at least one labelled chunk
  grounded rate       : answers that cite anything at all

Run it with the real models (`.\\make.ps1 eval-chat`): with the hashing embedder, no reranker
and the fake chat model the numbers only prove that the pipeline runs.
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from app.config import settings
from app.db.models import Chunk
from app.db.session import SessionLocal, engine
from app.schemas.chat import ChatRequest
from app.schemas.search import SearchFilters
from app.services.chat.service import respond
from app.services.embedding.factory import get_reranker
from app.services.llm.factory import get_chat
from sqlalchemy import select

from eval.runners.metrics import Label, matches
from eval.runners.retrieval_eval import ensure_indexed

EVAL_ROOT = Path(__file__).resolve().parents[1]


async def run_query(q: str, source_id: int) -> dict[str, Any]:
    request = ChatRequest(message=q, filters=SearchFilters(source_ids=[source_id]))
    sources: list[dict] = []
    done: dict[str, Any] = {}
    async for event in respond(SessionLocal, request):
        if event.name == "sources":
            sources = event.data["sources"]
        elif event.name == "done":
            done = event.data
        elif event.name == "error":
            done = {"error": event.data["message"], "abstained": False, "citations": []}
    return {"sources": sources, "done": done}


def score(rows: list[dict]) -> dict[str, Any]:
    answerable = [r for r in rows if r["answerable"]]
    answered = [r for r in answerable if not r["abstained"]]
    cited = [c for r in answered for c in r["cited_match"]]
    return {
        "queries": len(rows),
        "abstention_accuracy": round(sum(r["abstained"] != r["answerable"] for r in rows) / len(rows), 4),
        "answer_rate": round(len(answered) / len(answerable), 4) if answerable else 0.0,
        "citation_precision": round(sum(cited) / len(cited), 4) if cited else 0.0,
        "citation_hit_rate": round(sum(any(r["cited_match"]) for r in answered) / len(answered), 4)
        if answered
        else 0.0,
        "grounded_rate": round(sum(bool(r["cited_match"]) for r in answered) / len(answered), 4) if answered else 0.0,
        "errors": sum(1 for r in rows if r.get("error")),
    }


async def chunk_keys(chunk_ids: list[int]) -> dict[int, dict]:
    """What a label matches against (path, symbols, page), for the cited chunks."""
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Chunk.id, Chunk.symbol, Chunk.symbols, Chunk.meta).where(Chunk.id.in_(chunk_ids or [0]))
            )
        ).all()
    return {r.id: {"symbol": r.symbol, "symbols": r.symbols, "meta": r.meta} for r in rows}


async def evaluate(queries: list[dict], source_id: int) -> dict[str, Any]:
    rows = []
    for query in queries:
        result = await run_query(query["q"], source_id)
        done, sources = result["done"], result["sources"]
        by_n = {s["n"]: s for s in sources}
        cited = [by_n[n] for n in done.get("citations", []) if n in by_n]
        keys = await chunk_keys([s["chunk_id"] for s in cited if s.get("chunk_id")])
        cited_match = [
            any(matches(label, source | keys.get(source.get("chunk_id"), {})) for label in query["labels"])
            for source in cited
        ]
        rows.append(
            {
                "id": query["id"],
                "answerable": query["answerable"],
                "abstained": bool(done.get("abstained")),
                "intent": done.get("intent"),
                "cited_match": cited_match,
                "error": done.get("error"),
            }
        )
    return {"summary": score(rows), "rows": rows}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--golden", type=Path, default=EVAL_ROOT / "golden" / "fixture.yaml")
    parser.add_argument("--corpus", type=Path, default=Path(settings.eval_corpus_dir))
    parser.add_argument("--source", default="eval-fixture")
    parser.add_argument("--threshold", default=None, help="comma-separated abstention thresholds to compare")
    parser.add_argument("--out", type=Path, default=EVAL_ROOT / "reports")
    parser.add_argument("--name", default=None)
    args = parser.parse_args()

    golden = yaml.safe_load(args.golden.read_text(encoding="utf-8"))
    queries = [
        {
            "id": raw["id"],
            "q": raw["q"],
            "answerable": raw.get("answerable", True),
            "labels": [Label.parse(r) for r in raw.get("relevant", [])],
        }
        for raw in golden["queries"]
    ]
    source_id = await ensure_indexed(args.source, args.corpus.resolve())
    chat = get_chat()
    thresholds = [float(t) for t in args.threshold.split(",")] if args.threshold else [settings.abstain_threshold]

    report: dict[str, Any] = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "chat_model": chat.name if chat else None,
        "reranker": await get_reranker().model_name() if get_reranker() else None,
        "runs": {},
    }
    for threshold in thresholds:
        settings.abstain_threshold = threshold
        print(f"threshold {threshold} ...", file=sys.stderr)
        report["runs"][str(threshold)] = await evaluate(queries, source_id)

    lines = [
        "# Chat eval: fixture",
        "",
        f"- Date: {report['created_at']}",
        f"- Chat model: `{report['chat_model']}`; reranker: `{report['reranker']}`",
        "",
        "| Threshold | Abstention acc. | Answer rate | Citation precision | Citation hit rate | Grounded | Errors |",
        "|---|---|---|---|---|---|---|",
    ]
    for threshold, run in report["runs"].items():
        s = run["summary"]
        lines.append(
            f"| {threshold} | **{s['abstention_accuracy']:.3f}** | {s['answer_rate']:.3f} | "
            f"{s['citation_precision']:.3f} | {s['citation_hit_rate']:.3f} | {s['grounded_rate']:.3f} | {s['errors']} |"
        )
    text = "\n".join(lines) + "\n"
    print(text)
    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.name or f"chat-{datetime.now(UTC):%Y-%m-%d}"
    (args.out / f"{stem}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.out / f"{stem}.md").write_text(text, encoding="utf-8")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
