"""Idea <-> implementation gap evaluation: are the right ideas found, and does matching say
correctly which ones a project implements?

Indexes the fixture corpus (which detects and matches ideas), then checks eval/golden/ideas.yaml:

    python -m eval.runners.idea_eval                  # report + threshold sweep
    python -m eval.runners.idea_eval --gate           # CI: fail below the required scores

Reported:
  detection       precision / recall of the ideas found in the notes
  matching        status accuracy (implemented / partial / unimplemented) of matching alone,
                  project accuracy, and the two errors that matter:
                    false never  built (or half-built), reported as never implemented
                    false built  never built, reported as (partly) implemented
  effective       status accuracy after the notes' own frontmatter
  questions       precision / recall of the ideas each chat question lists
  sweep           the thresholds that would have been best, per signal, to calibrate
                  IDEA_COVERAGE_* and IDEA_SIMILARITY_* from real data
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
from app.db.session import SessionLocal, engine
from app.schemas.idea import IdeaOut
from app.services.chat.idea_answer import matches_topic
from app.services.chat.intent import detect
from app.services.embedding.factory import get_embedder, get_reranker
from app.services.ideas import queries

from eval.runners.graph_eval import prf, ratio
from eval.runners.retrieval_eval import ensure_indexed

EVAL_ROOT = Path(__file__).resolve().parents[1]
LEVELS = ("unimplemented", "partial", "implemented")
GRID = [round(x * 0.05, 2) for x in range(1, 20)]


def identify(label: dict, ideas: list[IdeaOut]) -> IdeaOut | None:
    for idea in ideas:
        if idea.path != label["path"]:
            continue
        if "title" in label and idea.title == label["title"]:
            return idea
        if "title_contains" in label and label["title_contains"].lower() in idea.title.lower():
            return idea
    return None


def name(idea: IdeaOut) -> str:
    return f"{idea.path} :: {idea.title}"


def level_at(candidate: dict, partial: dict[str, float], implemented: dict[str, float]) -> int:
    """0 = none, 1 = partial, 2 = implemented, for one candidate at the given thresholds."""
    signals = {"coverage": candidate["coverage"], "similarity": candidate.get("similarity")}
    if any(v is not None and v >= implemented[k] for k, v in signals.items()):
        return 2
    if candidate.get("linked") or any(v is not None and v >= partial[k] for k, v in signals.items()):
        return 1
    return 0


def replay(idea: IdeaOut, partial: dict[str, float], implemented: dict[str, float]) -> tuple[str, str | None]:
    """What matching would conclude at other thresholds, from the candidates it recorded."""
    best, project = 0, None
    for c in idea.candidates:
        level = level_at(c.model_dump(), partial, implemented)
        if level > best:
            best, project = level, c.project
    return LEVELS[best], project


def score(rows: list[dict]) -> dict[str, Any]:
    n = len(rows)
    return {
        "items": n,
        "status_accuracy": ratio(sum(r["status_ok"] for r in rows), n),
        "project_accuracy": ratio(
            sum(r["project_ok"] for r in rows if r["expected"] != "unimplemented"),
            sum(1 for r in rows if r["expected"] != "unimplemented"),
        ),
        "false_never": sum(1 for r in rows if r["expected"] != "unimplemented" and r["got"] == "unimplemented"),
        "false_built": sum(1 for r in rows if r["expected"] == "unimplemented" and r["got"] != "unimplemented"),
    }


def evaluate(pairs: list[tuple[dict, IdeaOut]], partial=None, implemented=None) -> list[dict]:
    rows = []
    for label, idea in pairs:
        if partial is None:
            got, project = idea.matched_status, idea.closest.project if idea.matched_status != "unimplemented" else None
        else:
            got, project = replay(idea, partial, implemented)
        rows.append(
            {
                "idea": name(idea),
                "expected": label["matched"],
                "got": got,
                "project": project,
                "status_ok": got == label["matched"],
                "project_ok": label["matched"] == "unimplemented" or project == label.get("project"),
            }
        )
    return rows


def sweep(pairs: list[tuple[dict, IdeaOut]], signal: str) -> dict[str, Any] | None:
    """Best (partial, implemented) thresholds for one signal alone: fewest false nevers, then
    highest status accuracy, then the widest margin."""
    if signal == "similarity" and not any(c.similarity is not None for _, idea in pairs for c in idea.candidates):
        return None
    off = {"coverage": 9.0, "similarity": 9.0}
    best = None
    for lo in GRID:
        for hi in GRID:
            if hi <= lo:
                continue
            partial, implemented = dict(off), dict(off)
            partial[signal], implemented[signal] = lo, hi
            s = score(evaluate(pairs, partial, implemented))
            key = (s["false_never"], -s["status_accuracy"], s["false_built"], -(hi - lo))
            if best is None or key < best[0]:
                best = (key, {"partial": lo, "implemented": hi, **s})
    return best[1] if best else None


def markdown(report: dict[str, Any]) -> str:
    d, m, e = report["detection"], report["matching"]["summary"], report["effective"]
    lines = [
        "# Idea eval: fixture",
        "",
        f"- Date: {report['created_at']}",
        f"- Embedder: `{report['config']['embedder']}` · reranker: `{report['config']['reranker']}`",
        f"- Signals: {', '.join(report['signals']) or 'none'}",
        f"- Thresholds: coverage {report['config']['coverage']}, similarity {report['config']['similarity']}",
        "",
        "| Check | Items | Score |",
        "|---|---|---|",
        f"| detection precision / recall | {d['expected']} | {d['precision']:.3f} / {d['recall']:.3f} |",
        f"| matching: status accuracy | {m['items']} | {m['status_accuracy']:.3f} |",
        f"| matching: right project | | {m['project_accuracy']:.3f} |",
        f"| matching: false never (built, called unimplemented) | | {m['false_never']} |",
        f"| matching: false built (unbuilt, called implemented) | | {m['false_built']} |",
        f"| effective status accuracy (after frontmatter) | {e['items']} | {e['accuracy']:.3f} |",
        f"| declared statuses honoured | | {e['declared_accuracy']:.3f} |",
    ]
    for q in report["questions"]:
        pr = f"{q['precision']:.3f} / {q['recall']:.3f}"
        lines.append(f'| "{q["q"]}" precision / recall | {len(q["expected"])} | {pr} |')
    lines += ["", "| Idea | Expected | Matching | Project | Closest (coverage / similarity) |", "|---|---|---|---|---|"]
    for row in report["matching"]["rows"]:
        mark = "" if row["status_ok"] and row["project_ok"] else " ✗"
        lines.append(
            f"| {row['idea'].split(' :: ')[1]} | {row['expected']} | {row['got']}{mark} | {row['project'] or ''} "
            f"| {row['closest'] or ''} |"
        )
    for signal, best in report["sweep"].items():
        if best:
            lines += [
                "",
                f"Best {signal} thresholds on this set (that signal alone): partial ≥ {best['partial']}, "
                f"implemented ≥ {best['implemented']} → accuracy {best['status_accuracy']:.3f}, "
                f"false never {best['false_never']}, false built {best['false_built']}.",
            ]
    if report["detection"]["unexpected"] or report["detection"]["missing"]:
        lines += ["", "Detection misses:", ""]
        lines += [f"- missing: {x}" for x in report["detection"]["missing"]]
        lines += [f"- unexpected: {x}" for x in report["detection"]["unexpected"]]
    return "\n".join(lines) + "\n"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--golden", type=Path, default=EVAL_ROOT / "golden" / "ideas.yaml")
    parser.add_argument("--corpus", type=Path, default=Path(settings.eval_corpus_dir))
    parser.add_argument("--source", default="eval-fixture")
    parser.add_argument("--no-index", action="store_true", help="evaluate what is already indexed")
    parser.add_argument("--out", type=Path, default=None, help="write <name>.json/.md here")
    parser.add_argument("--name", default=None)
    parser.add_argument("--gate", action="store_true", help="exit 1 below the required scores")
    parser.add_argument("--min-detection", type=float, default=1.0)
    parser.add_argument("--min-accuracy", type=float, default=0.85)
    parser.add_argument("--max-false-never", type=int, default=1)
    parser.add_argument("--max-false-built", type=int, default=0)
    args = parser.parse_args()

    golden = yaml.safe_load(args.golden.read_text(encoding="utf-8"))
    if not args.no_index:
        await ensure_indexed(args.source, args.corpus.resolve())

    async with SessionLocal() as session:
        ideas = await queries.list_ideas(session, "all")
        signals = sorted({s for i in ideas for s in i.signals})
        pairs, missing = [], []
        for label in golden["ideas"]:
            idea = identify(label, ideas)
            if idea is None:
                missing.append(f"{label['path']} :: {label.get('title') or label.get('title_contains')}")
            else:
                pairs.append((label, idea))
        found = {name(i) for _, i in pairs}
        unexpected = sorted(name(i) for i in ideas if name(i) not in found)

        rows = evaluate(pairs)
        for row, (_, idea) in zip(rows, pairs, strict=True):
            c = idea.closest
            sim = "-" if c is None or c.similarity is None else f"{c.similarity:.2f}"
            row["closest"] = f"{c.project} ({c.coverage:.2f} / {sim})" if c else None
        effective = [
            (
                "status" in label,
                idea.status == label.get("status", label["matched"])
                and (
                    idea.status in ("unimplemented", "abandoned")
                    or (idea.project is not None and idea.project.name == label.get("project"))
                ),
            )
            for label, idea in pairs
        ]
        question_rows = []
        for item in golden.get("questions", []):
            intent = detect(item["q"])
            listed = [
                i for i in await queries.list_ideas(session, intent.subject or "all") if matches_topic(i, intent.topic)
            ]
            got = {i.title for i in listed}
            expected = {
                next((t for t in got if e.lower() in t.lower()), e) if e not in got else e for e in item["expected"]
            }
            tp, fp, fn = prf(expected, got)
            question_rows.append(
                {"q": item["q"], "intent": intent.kind, "expected": sorted(expected), "got": sorted(got),
                 "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn)}
            )  # fmt: skip

    tp = len(pairs)
    report = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "config": {
            "embedder": settings.embedder if get_embedder() else "none",
            "reranker": settings.reranker if get_reranker() else "none",
            "coverage": [settings.idea_coverage_partial, settings.idea_coverage_implemented],
            "similarity": [settings.idea_similarity_partial, settings.idea_similarity_implemented],
        },
        "signals": signals,
        "detection": {
            "expected": len(golden["ideas"]),
            "precision": ratio(tp, tp + len(unexpected)),
            "recall": ratio(tp, tp + len(missing)),
            "missing": missing,
            "unexpected": unexpected,
        },
        "matching": {"summary": score(rows), "rows": rows},
        "effective": {
            "items": len(effective),
            "accuracy": ratio(sum(ok for _, ok in effective), len(effective)),
            # The ideas whose note declares a status: frontmatter is exact, so this must be 1.
            "declared_accuracy": ratio(
                sum(ok for declared, ok in effective if declared), sum(1 for d, _ in effective if d)
            ),
        },
        "questions": question_rows,
        "sweep": {signal: sweep(pairs, signal) for signal in ("coverage", "similarity")},
    }
    text = markdown(report)
    print(text)
    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        stem = args.name or f"ideas-{datetime.now(UTC):%Y-%m-%d}"
        (args.out / f"{stem}.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
        (args.out / f"{stem}.md").write_text(text, encoding="utf-8")
    await engine.dispose()

    if args.gate:
        m = report["matching"]["summary"]
        failures = []
        d = report["detection"]
        if min(d["precision"], d["recall"]) < args.min_detection:
            failures.append(f"detection {d['precision']}/{d['recall']} < {args.min_detection}")
        if m["status_accuracy"] < args.min_accuracy:
            failures.append(f"status accuracy {m['status_accuracy']} < {args.min_accuracy}")
        if m["false_never"] > args.max_false_never:
            failures.append(f"false never {m['false_never']} > {args.max_false_never}")
        if m["false_built"] > args.max_false_built:
            failures.append(f"false built {m['false_built']} > {args.max_false_built}")
        if report["effective"]["declared_accuracy"] < 1.0:
            failures.append(f"declared status accuracy {report['effective']['declared_accuracy']} < 1.0")
        if failures:
            print("idea eval gate failed: " + "; ".join(failures), file=sys.stderr)
            return 1
        print("idea eval gate passed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
