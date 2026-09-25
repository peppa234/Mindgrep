"""Labelling helper for the personal benchmark.

Shows the top candidates for a query across every channel, each with a ready-to-paste label.
Judge them yourself, copy the relevant ones into eval/golden/personal.yaml, and set grades.

    python -m eval.runners.label "where did I implement JWT authentication"
    python -m eval.runners.label --k 30 "notes about the student portal"

Use the widest pool you can (hybrid, not rerank), so the labels don't inherit one ranker's
blind spots. Then also search for the answer you *know* exists by name: if it isn't in the
candidates, that is exactly the miss the benchmark should record.
"""

import argparse
import asyncio

from app.db.session import SessionLocal, engine
from app.schemas.search import SearchRequest
from app.services.retrieval.search import search


def label_line(hit) -> str:
    fields = [f"source: {hit.source_name}", f"path: {hit.path}"]
    if hit.doc_kind == "pdf" and hit.meta.get("page_start"):
        fields.append(f"page: {hit.meta['page_start']}")
    elif hit.symbols:
        symbol = hit.symbols[0]
        fields.append(f'symbol: "{symbol}"' if any(c in symbol for c in ":#,") else f"symbol: {symbol}")
    return "- { " + ", ".join(fields) + ", grade: 2 }"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query")
    parser.add_argument("--k", type=int, default=20)
    parser.add_argument("--mode", default="hybrid")
    args = parser.parse_args()

    async with SessionLocal() as session:
        response = await search(session, SearchRequest(q=args.query, k=args.k, mode=args.mode))
    for rank, hit in enumerate(response.hits, start=1):
        preview = " ".join(hit.content.split())[:110]
        print(f"{rank:>2}. {hit.source_name}/{hit.path}  {hit.symbol or ''}")
        print(f"    {preview}")
        print(f"    {label_line(hit)}")
    if response.degraded:
        print("\n(degraded: " + "; ".join(response.degraded) + ")")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
