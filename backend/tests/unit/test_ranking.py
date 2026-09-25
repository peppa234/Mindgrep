import math

from eval.runners.metrics import Label, best_threshold, gains, ndcg_at, recall_at, reciprocal_rank

from app.services.embedding.hashing import HashEmbedder
from app.services.retrieval.fusion import rrf
from app.services.retrieval.query import analyze


def test_rrf_rewards_agreement_between_channels():
    fused = rrf({"vector": [1, 2, 3], "lexical": [3, 4, 1]})
    assert [f.chunk_id for f in fused][:2] == [1, 3]
    assert fused[0].ranks == {"vector": 1, "lexical": 3}
    assert math.isclose(fused[0].score, 1 / 61 + 1 / 63)


def test_rrf_is_deterministic_on_ties():
    assert [f.chunk_id for f in rrf({"a": [5, 6], "b": [6, 5]})] == [5, 6]


def test_query_analysis():
    analyzed = analyze("where is `generateJwtToken` used with redis_client?")
    assert analyzed.identifiers == ["generateJwtToken", "redis_client"]
    assert "jwt" in analyzed.terms and "generate" in analyzed.terms
    assert analyzed.tsquery is not None and "|" in analyzed.tsquery
    # Only [a-z0-9] reaches to_tsquery: no operator injection.
    assert set(analyze("jwt & !token | (auth:*)").tsquery) <= set(
        "abcdefghijklmnopqrstuvwxyz0123456789 |"
    )


async def test_hash_embedder_is_normalised_and_deterministic():
    embedder = HashEmbedder(64)
    [a], [b] = (
        await embedder.embed(["jwt token"], "query"),
        await embedder.embed(["jwt token"], "document"),
    )
    assert a == b
    assert math.isclose(sum(v * v for v in a), 1.0, rel_tol=1e-6)


def hit(path, symbols=(), symbol=None, page=None):
    meta = {"page_start": page, "page_end": page} if page else {}
    return {"path": path, "symbols": list(symbols), "symbol": symbol, "meta": meta}


def test_label_matching_and_metrics():
    labels = [Label("a.py", symbol="f", grade=2), Label("notes.md", symbol="Plan", grade=1)]
    hits = [
        hit("b.py", ["g"]),
        hit("a.py", ["f", "h"]),
        hit("a.py", ["f"]),  # second part of the same function: no double credit
        hit("notes.md", ["Plan"], symbol="Note > Plan"),
    ]
    assert gains(hits, labels) == [0, 2, 0, 1]
    assert recall_at(hits, labels, 2) == 0.5
    assert recall_at(hits, labels, 10) == 1.0
    assert reciprocal_rank(hits, labels) == 0.5
    ideal = 3 / math.log2(2) + 1 / math.log2(3)
    assert math.isclose(ndcg_at(hits, labels, 10), (3 / math.log2(3) + 1 / math.log2(5)) / ideal)


def test_pdf_page_label():
    assert gains([hit("p.pdf", page=2)], [Label("p.pdf", page=2)]) == [1]
    assert gains([hit("p.pdf", page=3)], [Label("p.pdf", page=2)]) == [0]


def test_best_threshold():
    result = best_threshold([0.9, 0.8, 0.7], [0.2, 0.75])
    assert result == {"accuracy": 0.8, "threshold": 0.7}
