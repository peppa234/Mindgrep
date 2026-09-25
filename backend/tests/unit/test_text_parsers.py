from app.services.chunking.identifiers import (
    identifier_terms,
    path_terms,
    split_identifier,
    symbol_terms,
)
from app.services.chunking.text_chunker import chunk_plain
from app.services.ingestion.router import route
from app.services.parsing.dispatch import parse_document
from app.services.parsing.markdown import parse_markdown


def test_split_identifier_handles_every_style():
    assert split_identifier("generateJwtToken") == ["generate", "jwt", "token"]
    assert split_identifier("generate_jwt_token") == ["generate", "jwt", "token"]
    assert split_identifier("parseHTTPResponse") == ["parse", "http", "response"]
    assert split_identifier("sha256Digest") == ["sha256", "digest"]
    assert split_identifier("x") == []


def test_identifier_terms_only_expands_compound_names():
    assert identifier_terms("return fetchWithRetry(url) + value") == "fetch with retry"


def test_path_and_symbol_terms():
    assert path_terms("src/authService/jwt_utils.py") == "src auth service jwt utils py"
    assert symbol_terms(["Crawler.Run"]) == "Crawler.Run crawler run"


def test_markdown_frontmatter_title_links_tags_and_line_numbers():
    text = """---
title: My Note
tags: [idea, rag]
created: 2024-02-11
---

# Heading One

Intro with a [[Wiki Link]] and a #inline-tag. Enough words here to make the section count
as a real section rather than something tiny that should be merged into the next one.

## Second

```python
# not a heading
x = 1
```
"""
    parsed = parse_markdown(text, "notes/my-note.md")
    assert parsed.title == "My Note"
    assert parsed.meta["links"] == ["Wiki Link"]
    assert set(parsed.meta["tags"]) == {"idea", "rag", "inline-tag"}
    assert parsed.meta["frontmatter"]["created"] == "2024-02-11"
    first = parsed.chunks[0]
    assert first.start_line == 7  # counted from the top of the file, frontmatter included
    assert first.symbol == "My Note > Heading One"
    headings = [h for c in parsed.chunks for h in c.symbols]
    assert "not a heading" not in " ".join(headings)
    assert "Second" in headings


def test_markdown_without_h1_is_prefixed_with_title():
    parsed = parse_markdown("## Only H2\n\nbody text", "notes/plain-note.md")
    assert parsed.title == "plain-note"
    assert parsed.chunks[0].symbol == "plain-note > Only H2"


def test_long_plain_text_is_windowed():
    text = "\n\n".join(f"paragraph {i} " + "word " * 200 for i in range(20))
    drafts = chunk_plain(text)
    assert len(drafts) > 1
    assert drafts[0].start_line == 1


def test_router():
    assert route("a/b.py").language == "python"
    assert route("x.tsx").language == "tsx"
    assert route("Dockerfile").language == "dockerfile"
    assert route("notes/x.MD").kind == "markdown"
    assert route("data.json").max_bytes == 200_000
    assert route("image.png") is None


def test_pdf_text_and_scanned(corpus):
    bm25 = corpus / "papers" / "bm25-notes.pdf"
    parsed = parse_document("papers/bm25-notes.pdf", bm25.read_bytes(), route("x.pdf"))
    assert parsed.status == "indexed"
    assert parsed.title == "Notes on Okapi BM25 and Sparse Retrieval"
    assert [c.meta["page_start"] for c in parsed.chunks] == [1, 2, 3]

    scan = corpus / "papers" / "whiteboard-scan.pdf"
    parsed = parse_document("papers/whiteboard-scan.pdf", scan.read_bytes(), route("x.pdf"))
    assert parsed.status == "needs_ocr"
    assert parsed.chunks == []
