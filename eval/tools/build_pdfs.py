"""Regenerate the PDFs in eval/corpus/papers. They are committed; run this only to change them.

backend/.venv/Scripts/python eval/tools/build_pdfs.py
"""

from pathlib import Path

import pymupdf

PAPERS = Path(__file__).resolve().parents[1] / "corpus" / "papers"

BM25_PAGES = [
    """Notes on Okapi BM25 and Sparse Retrieval

A reading summary

These notes summarise the probabilistic relevance framework behind BM25, why it remains
a strong baseline for keyword search, and how learned sparse models build on it.

BM25 is still the default ranking function in Lucene, Elasticsearch and OpenSearch. On
many benchmarks (BEIR in particular) it beats dense retrievers that were not trained on
the target domain, which is why hybrid search keeps it in the loop.""",
    """The BM25 scoring function

For a query Q with terms q1..qn and a document D, BM25 sums, over the query terms, the
inverse document frequency of the term multiplied by a saturating function of its term
frequency in D:

score(D, Q) = sum IDF(qi) * f(qi, D) * (k1 + 1) / (f(qi, D) + k1 * (1 - b + b * |D| / avgdl))

Two parameters matter. k1 (typically 1.2 to 2.0) controls term frequency saturation: after
a few occurrences, more repetitions of a word add almost nothing. b (typically 0.75)
controls document length normalisation: b = 1 fully normalises by length relative to the
average document length avgdl, b = 0 ignores length entirely.

The IDF term downweights words that appear in most documents, so stop words contribute
little even when they are not removed.""",
    """Learned sparse retrieval

SPLADE keeps the inverted index but learns the term weights with a masked language
model. Each document is expanded with related vocabulary it never literally contains,
which fixes the vocabulary mismatch problem that plain BM25 suffers from, while queries
still run on a standard inverted index.

Practical takeaway: start with BM25 plus a dense retriever fused with reciprocal rank
fusion, add a cross-encoder reranker, and only consider learned sparse models when the
evaluation set shows a vocabulary mismatch problem that the hybrid does not solve.""",
]


def write_text_pdf(path: Path, pages: list[str], title: str) -> None:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page(width=595, height=842)  # A4 in points
        page.insert_textbox(pymupdf.Rect(60, 60, 535, 790), text, fontsize=11, fontname="helv")
    doc.set_metadata({"title": title, "author": "MemoryOS eval corpus"})
    doc.save(path, garbage=4, deflate=True)


def write_scanned_pdf(path: Path) -> None:
    """Only vector drawings, no text layer: stands in for a scanned whiteboard photo."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for i in range(12):
        page.draw_rect(pymupdf.Rect(60 + i * 20, 80 + i * 30, 300 + i * 15, 110 + i * 30), color=(0, 0, 0))
    page.draw_circle(pymupdf.Point(400, 600), 80, color=(0.2, 0.2, 0.2))
    doc.save(path, garbage=4, deflate=True)


if __name__ == "__main__":
    PAPERS.mkdir(parents=True, exist_ok=True)
    write_text_pdf(PAPERS / "bm25-notes.pdf", BM25_PAGES, "Notes on Okapi BM25 and Sparse Retrieval")
    write_scanned_pdf(PAPERS / "whiteboard-scan.pdf")
    print("wrote", *sorted(p.name for p in PAPERS.glob("*.pdf")))
