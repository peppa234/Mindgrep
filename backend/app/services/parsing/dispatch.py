from pathlib import PurePosixPath

from app.services.chunking.code_chunker import chunk_code, supported
from app.services.chunking.text_chunker import chunk_plain
from app.services.chunking.types import ParsedDocument
from app.services.ingestion.router import Route
from app.services.parsing.markdown import parse_markdown
from app.services.parsing.pdf import parse_pdf


def decode(data: bytes) -> str:
    return data.decode("utf-8-sig", errors="replace")


def parse_document(path: str, data: bytes, route: Route) -> ParsedDocument:
    """Parse one file into chunk drafts. Pure: no I/O, no database."""
    name = PurePosixPath(path).name
    if route.kind == "pdf":
        return parse_pdf(data, path)
    if route.kind == "markdown":
        return parse_markdown(decode(data), path)
    if route.kind == "code" and supported(route.language):
        # tree-sitter wants the raw bytes; a BOM would shift every byte offset.
        raw = data[3:] if data.startswith(b"\xef\xbb\xbf") else data
        drafts, meta = chunk_code(raw, route.language)  # type: ignore[arg-type]
        return ParsedDocument(
            kind="code", language=route.language, title=name, chunks=drafts, meta=meta
        )
    return ParsedDocument(
        kind=route.kind, language=route.language, title=name, chunks=chunk_plain(decode(data))
    )
