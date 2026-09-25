"""PDFs via PyMuPDF.

Born-digital papers (the common case) extract instantly. Scanned PDFs have almost no text
layer; those are recorded with status `needs_ocr` rather than indexed as empty noise. OCR
(Docling) is a later addition behind the same detection.
"""

import re

import pymupdf

from app.services.chunking.text_chunker import paragraph_windows
from app.services.chunking.types import (
    MERGE_TARGET_TOKENS,
    MIN_TOKENS,
    ChunkDraft,
    ParsedDocument,
    estimate_tokens,
)

# Below this many non-whitespace characters per page on average, treat the PDF as scanned.
SCANNED_CHARS_PER_PAGE = 100


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"-\n(?=[a-z])", "", text)  # re-join words hyphenated across lines
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_pdf(data: bytes, path: str) -> ParsedDocument:
    stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        metadata = doc.metadata or {}
        pages = [_clean(page.get_text("text")) for page in doc]

    visible = sum(len(re.sub(r"\s", "", p)) for p in pages)
    meta = {"pages": len(pages), "author": metadata.get("author") or None}
    first_line = next(
        (line.strip() for line in (pages[0] if pages else "").split("\n") if line.strip()), ""
    )
    title = (metadata.get("title") or "").strip() or (first_line[:200] if first_line else stem)

    if not pages or visible / len(pages) < SCANNED_CHARS_PER_PAGE:
        return ParsedDocument(
            kind="pdf", language=None, title=title, chunks=[], status="needs_ocr", meta=meta
        )

    # Merge consecutive short pages (title pages, figure pages), split long ones by paragraph.
    groups: list[tuple[int, int, str]] = []  # (first page, last page, text), 1-based pages
    for number, text in enumerate(pages, start=1):
        if not text:
            continue
        if groups:
            first, _, prev = groups[-1]
            combined = prev + "\n\n" + text
            if (
                estimate_tokens(prev) < MIN_TOKENS or estimate_tokens(text) < MIN_TOKENS
            ) and estimate_tokens(combined) <= MERGE_TARGET_TOKENS:
                groups[-1] = (first, number, combined)
                continue
        groups.append((number, number, text))

    chunks: list[ChunkDraft] = []
    for first, last, text in groups:
        lines = text.split("\n")
        windows = paragraph_windows(lines, 0, len(lines) - 1)
        for i, (a, b) in enumerate(windows, start=1):
            content = "\n".join(lines[a : b + 1]).strip()
            if not content:
                continue
            label = f"p. {first}" if first == last else f"pp. {first}-{last}"
            context = [f"part {i} of {len(windows)}"] if len(windows) > 1 else []
            chunks.append(
                ChunkDraft(
                    kind="pdf_page",
                    content=content,
                    symbol=label,
                    symbols=[],
                    context=context,
                    meta={"page_start": first, "page_end": last},
                )
            )
    return ParsedDocument(kind="pdf", language=None, title=title, chunks=chunks, meta=meta)
