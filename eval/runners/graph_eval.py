"""Knowledge-graph evaluation: precision and recall of extracted facts, and chat routing.

Indexes the fixture corpus (which builds the deterministic graph), then checks it against
eval/golden/graph.yaml:

    python -m eval.runners.graph_eval                 # report
    python -m eval.runners.graph_eval --gate          # CI: fail below the required scores

"Which projects use PostgreSQL?" is only worth answering from the graph if the graph is
right, so the fixture gate is strict: precision and recall of 1.0 on projects_using and
stacks, and every routing decision correct.
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
from app.db.models import Node
from app.db.session import SessionLocal, engine
from app.services.chat import graph_answer
from app.services.chat.intent import detect
from app.services.graph import queries
from sqlalchemy import select

from eval.runners.retrieval_eval import ensure_indexed

EVAL_ROOT = Path(__file__).resolve().parents[1]


def prf(expected: set[str], found: set[str]) -> tuple[int, int, int]:
    """(true positives, false positives, false negatives)"""
    return len(expected & found), len(found - expected), len(expected - found)


def ratio(num: int, den: int) -> float:
    return round(num / den, 4) if den else 1.0


async def projects_using(q: str, source_id: int) -> set[str]:
    async with SessionLocal() as session:
        entities = await queries.resolve_entities(session, q, ("technology", "package"))
        found: set[str] = set()
        for entity in entities:
            for project in await queries.projects_using(session, entity):
                found.add(project.name)
    return found


async def stack(name: str, source_id: int) -> set[str] | None:
    async with SessionLocal() as session:
        project = (
            await session.execute(
                select(Node).where(Node.kind == "project", Node.name == name, Node.source_id == source_id)
            )
        ).scalar_one_or_none()
        if project is None:
            return None
        technologies = await queries.related(session, project.id, "out", ("uses",), ("technology",))
    return {t.name for t in technologies}


async def routed(question: str) -> str:
    intent = detect(question)
    if intent.kind == "rag" or not intent.subject:
        return "rag"
    async with SessionLocal() as session:
        entities = await graph_answer.resolve(session, intent.kind, intent.subject)
    return intent.kind if entities else "rag"


def section(rows: list[dict]) -> dict[str, Any]:
    tp = sum(r["tp"] for r in rows)
    fp = sum(r["fp"] for r in rows)
    fn = sum(r["fn"] for r in rows)
    return {
        "items": len(rows),
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "exact": ratio(sum(1 for r in rows if r["fp"] == r["fn"] == 0), len(rows)),
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Graph eval: fixture",
        "",
        f"- Date: {report['created_at']}",
        "",
        "| Check | Items | Precision | Recall | Exact |",
        "|---|---|---|---|---|",
    ]
    for name in ("projects_using", "stacks"):
        s = report[name]["summary"]
        lines.append(f"| {name} | {s['items']} | {s['precision']:.3f} | {s['recall']:.3f} | {s['exact']:.3f} |")
    r = report["routing"]["summary"]
    lines += ["", f"Routing accuracy: **{r['accuracy']:.3f}** over {r['items']} questions."]
    misses = [
        f"- `{row['q']}`: missing {row['missing']}, unexpected {row['unexpected']}"
        for name in ("projects_using", "stacks")
        for row in report[name]["rows"]
        if row["fp"] or row["fn"]
    ]
    misses += [
        f"- routing `{row['q']}`: expected {row['expected']}, got {row['got']}"
        for row in report["routing"]["rows"]
        if row["expected"] != row["got"]
    ]
    if misses:
        lines += ["", "Misses:", "", *misses]
    return "\n".join(lines) + "\n"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--golden", type=Path, default=EVAL_ROOT / "golden" / "graph.yaml")
    parser.add_argument("--corpus", type=Path, default=Path(settings.eval_corpus_dir))
    parser.add_argument("--source", default="eval-fixture")
    parser.add_argument("--out", type=Path, default=None, help="write <name>.json/.md here")
    parser.add_argument("--name", default=None)
    parser.add_argument("--gate", action="store_true", help="exit 1 below the required scores")
    parser.add_argument("--min-precision", type=float, default=1.0)
    parser.add_argument("--min-recall", type=float, default=1.0)
    parser.add_argument("--min-routing", type=float, default=1.0)
    args = parser.parse_args()

    golden = yaml.safe_load(args.golden.read_text(encoding="utf-8"))
    source_id = await ensure_indexed(args.source, args.corpus.resolve())

    using_rows = []
    for item in golden["projects_using"]:
        expected, found = set(item["expected"]), await projects_using(item["q"], source_id)
        tp, fp, fn = prf(expected, found)
        using_rows.append(
            {"q": item["q"], "tp": tp, "fp": fp, "fn": fn,
             "missing": sorted(expected - found), "unexpected": sorted(found - expected)}
        )  # fmt: skip

    stack_rows = []
    for name, techs in golden["stacks"].items():
        expected = set(techs)
        found = await stack(name, source_id)
        if found is None:
            stack_rows.append({"q": name, "tp": 0, "fp": 0, "fn": len(expected),
                               "missing": ["<project not detected>"], "unexpected": []})  # fmt: skip
            continue
        tp, fp, fn = prf(expected, found)
        stack_rows.append(
            {"q": name, "tp": tp, "fp": fp, "fn": fn,
             "missing": sorted(expected - found), "unexpected": sorted(found - expected)}
        )  # fmt: skip

    routing_rows = [
        {"q": item["q"], "expected": item["intent"], "got": await routed(item["q"])} for item in golden["routing"]
    ]
    report = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "projects_using": {"summary": section(using_rows), "rows": using_rows},
        "stacks": {"summary": section(stack_rows), "rows": stack_rows},
        "routing": {
            "summary": {
                "items": len(routing_rows),
                "accuracy": ratio(sum(r["expected"] == r["got"] for r in routing_rows), len(routing_rows)),
            },
            "rows": routing_rows,
        },
    }
    text = markdown(report)
    print(text)
    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        stem = args.name or f"graph-{datetime.now(UTC):%Y-%m-%d}"
        (args.out / f"{stem}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (args.out / f"{stem}.md").write_text(text, encoding="utf-8")
    await engine.dispose()

    if args.gate:
        failures = []
        for name in ("projects_using", "stacks"):
            s = report[name]["summary"]
            if s["precision"] < args.min_precision:
                failures.append(f"{name} precision {s['precision']} < {args.min_precision}")
            if s["recall"] < args.min_recall:
                failures.append(f"{name} recall {s['recall']} < {args.min_recall}")
        if report["routing"]["summary"]["accuracy"] < args.min_routing:
            failures.append(f"routing accuracy {report['routing']['summary']['accuracy']} < {args.min_routing}")
        if failures:
            print("graph eval gate failed: " + "; ".join(failures), file=sys.stderr)
            return 1
        print("graph eval gate passed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
