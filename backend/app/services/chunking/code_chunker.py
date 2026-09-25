"""AST-boundary code chunking.

The rules, in order:
  1. One definition (function, class, method, type) = one chunk, with its decorators,
     `export` keyword and doc comments attached.
  2. A container (class, impl, trait) too large for one chunk is split into its members;
     each member keeps the container's signature in its header.
  3. A function too large for one chunk is split between top-level statements of its body;
     each part keeps the function's signature in its header.
  4. Small neighbouring pieces (tiny helpers, constants) are merged up to a target size.
  5. Import-only fragments are dropped; the imports each chunk actually uses go in its header.

Line numbers are 1-based and inclusive throughout.
"""

from dataclasses import dataclass, field
from typing import Any

import tree_sitter as ts

from app.services.chunking.identifiers import IDENTIFIER_RE
from app.services.chunking.types import (
    MAX_TOKENS,
    MERGE_TARGET_TOKENS,
    MIN_TOKENS,
    ChunkDraft,
)
from app.services.parsing.languages import LANGUAGES, LangSpec, parser_for

CHARS_PER_TOKEN = 4
MAX_IMPORT_LINES = 6

# Tokens that appear in import statements but are never the name code refers to.
_IMPORT_NOISE = {
    "import",
    "from",
    "as",
    "use",
    "crate",
    "self",
    "super",
    "require",
    "const",
    "let",
    "var",
    "static",
    "type",
    "default",
    "com",
    "org",
    "net",
    "io",
    "github",
    "java",
    "javax",
    "pub",
    "mod",
    "package",
    "std",
    "v1",
    "v2",
    "v3",
    "v4",
    "v5",
}


@dataclass
class _Piece:
    kind: str
    names: list[str]
    start_row: int  # 0-based, inclusive
    end_row: int  # 0-based, inclusive
    parent: str | None
    context: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def _text(node: ts.Node | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8", "replace")


class CodeChunker:
    def __init__(self, language: str) -> None:
        self.language = language
        self.spec: LangSpec = LANGUAGES[language]
        self.parser = parser_for(language)

    # ------------------------------------------------------------------ public

    def chunk(self, source: bytes) -> tuple[list[ChunkDraft], dict[str, Any]]:
        text = source.decode("utf-8", "replace")
        self.lines = [line.rstrip("\r") for line in text.split("\n")]
        tree = self.parser.parse(source)
        root = tree.root_node

        imports = self._collect_imports(root)
        pieces = self._units(list(root.named_children), parent=None, context=[])
        if any(p.names for p in pieces):
            pieces = [p for p in pieces if not p.meta.get("imports_only")]
        pieces = self._merge_small(pieces)

        drafts: list[ChunkDraft] = []
        all_names: list[str] = []
        for piece in pieces:
            content = "\n".join(self.lines[piece.start_row : piece.end_row + 1]).strip("\n")
            if not content.strip():
                continue
            context = list(piece.context)
            used = self._imports_used(content, imports)
            if used:
                context.append("uses: " + "; ".join(used))
            all_names.extend(piece.names)
            drafts.append(
                ChunkDraft(
                    kind=piece.kind,
                    content=content,
                    symbol=", ".join(piece.names[:3]) if piece.names else None,
                    symbols=piece.names,
                    start_line=piece.start_row + 1,
                    end_line=piece.end_row + 1,
                    context=context,
                    meta=piece.meta,
                )
            )

        meta = {
            "imports": [stmt for stmt, _ in imports][:100],
            "symbols": all_names[:500],
            "parse_errors": root.has_error,
        }
        return drafts, meta

    # ------------------------------------------------------------ unit discovery

    def _units(self, nodes: list[ts.Node], parent: str | None, context: list[str]) -> list[_Piece]:
        """Turn a list of sibling nodes into pieces: one per definition, plus loose runs."""
        pieces: list[_Piece] = []
        loose: list[ts.Node] = []
        pending_comments: list[ts.Node] = []

        def flush_loose() -> None:
            if not loose:
                return
            only_imports = all(
                n.type in self.spec.imports or n.type in self.spec.comments for n in loose
            )
            start, end = loose[0].start_point.row, loose[-1].end_point.row
            for rows in self._split_rows(
                start, end, [(n.start_point.row, n.end_point.row) for n in loose]
            ):
                pieces.append(
                    _Piece(
                        kind="module",
                        names=[],
                        start_row=rows[0],
                        end_row=rows[1],
                        parent=parent,
                        context=list(context),
                        meta={"imports_only": True} if only_imports else {},
                    )
                )
            loose.clear()

        for node in nodes:
            if node.type in self.spec.comments:
                pending_comments.append(node)
                continue

            found = self._definition(node)
            if found is None:
                loose.extend(pending_comments)
                pending_comments = []
                loose.append(node)
                continue

            # Attach the contiguous comment block directly above (docstrings, JSDoc, `///`).
            split = len(pending_comments)
            expected_row = node.start_point.row
            while split > 0 and pending_comments[split - 1].end_point.row >= expected_row - 1:
                split -= 1
                expected_row = pending_comments[split].start_point.row
            loose.extend(pending_comments[:split])
            attached = pending_comments[split:]
            pending_comments = []
            flush_loose()

            start_row = attached[0].start_point.row if attached else node.start_point.row
            pieces.extend(self._definition_pieces(node, found, start_row, parent, context))

        loose.extend(pending_comments)
        flush_loose()
        return pieces

    def _definition(self, node: ts.Node) -> tuple[ts.Node, str, str] | None:
        """(definition node, chunk kind, name) if `node` is or wraps a definition."""
        spec = self.spec
        if node.type in spec.definitions:
            return node, spec.definitions[node.type], self._name_of(node)

        if node.type in spec.wrappers:
            inner = node.child_by_field_name("definition") or node.child_by_field_name(
                "declaration"
            )
            if inner is None:
                for child in node.named_children:
                    if child.type in spec.definitions or child.type in spec.variable_declarations:
                        inner = child
                        break
            if inner is not None:
                return self._definition(inner)
            # `export default function () {}` and friends.
            for child in node.named_children:
                if child.type in spec.function_values:
                    return child, "function", "default"
            return None

        if node.type in spec.variable_declarations:
            declarators = [c for c in node.named_children if c.type == "variable_declarator"]
            if len(declarators) == 1:
                value = declarators[0].child_by_field_name("value")
                name = _text(declarators[0].child_by_field_name("name")) or "<anonymous>"
                if value is not None and value.type in spec.function_values:
                    return value, "function", name
                if value is not None and value.type in ("class", "class_expression"):
                    return value, "class", name
                # `export const useTaskStore = create(...)`: named, so the symbol channel
                # can find it, even though it is not a function.
                return node, "variable", name

        if self.language == "python" and node.type == "expression_statement":
            assignment = node.named_children[0] if node.named_children else None
            if assignment is not None and assignment.type == "assignment":
                target = assignment.child_by_field_name("left")
                if target is not None and target.type == "identifier":
                    return node, "variable", _text(target)
        return None

    def _name_of(self, node: ts.Node) -> str:
        if node.type == "method_declaration" and self.language == "go":
            receiver = node.child_by_field_name("receiver")
            receiver_type = self._first_descendant(receiver, "type_identifier")
            name = _text(node.child_by_field_name("name"))
            return f"{_text(receiver_type)}.{name}" if receiver_type is not None else name
        if node.type in ("type_declaration", "const_declaration", "var_declaration"):
            specs = [
                c
                for c in node.named_children
                if c.type in ("type_spec", "type_alias", "const_spec", "var_spec")
            ]
            return ", ".join(_text(s.child_by_field_name("name")) for s in specs) or "<decl>"
        if node.type == "impl_item":
            return _text(node.child_by_field_name("type")) or "<impl>"
        return _text(node.child_by_field_name("name")) or "<anonymous>"

    @staticmethod
    def _first_descendant(node: ts.Node | None, node_type: str) -> ts.Node | None:
        if node is None:
            return None
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type == node_type:
                return current
            stack.extend(reversed(current.named_children))
        return None

    # ------------------------------------------------------------ definitions

    def _definition_pieces(
        self,
        node: ts.Node,
        found: tuple[ts.Node, str, str],
        start_row: int,
        parent: str | None,
        context: list[str],
    ) -> list[_Piece]:
        def_node, kind, name = found
        qualified = f"{parent}.{name}" if parent else name
        if parent is not None and kind in self.spec.method_kinds:
            kind = "method"
        end_row = node.end_point.row
        body = def_node.child_by_field_name("body")
        is_container = def_node.type in self.spec.containers and body is not None

        if self._tokens(start_row, end_row) <= MAX_TOKENS:
            names = [qualified]
            if is_container:
                names += self._member_names(body, qualified)
            return [_Piece(kind, names, start_row, end_row, parent, list(context))]

        signature = self._signature(start_row, body)

        if is_container:
            member_context = [*context, f"in {kind} {qualified}: {signature}"]
            members = self._units(
                list(body.named_children), parent=qualified, context=member_context
            )
            body_row = body.start_point.row
            if members and not members[0].names:
                # The container's own prelude (docstring, fields) absorbs its signature line.
                members[0].start_row = start_row
                members[0].kind = kind
                members[0].names = [qualified]
                members[0].context = list(context)
                members[0].meta.pop("imports_only", None)
            else:
                members.insert(
                    0,
                    _Piece(
                        kind,
                        [qualified],
                        start_row,
                        max(start_row, body_row),
                        parent,
                        list(context),
                    ),
                )
            return members

        # An oversized function: split between the top-level statements of its body.
        statements = (
            [(c.start_point.row, c.end_point.row) for c in body.named_children] if body else []
        )
        parts = self._split_rows(start_row, end_row, statements)
        pieces = []
        for i, (a, b) in enumerate(parts, start=1):
            part_context = list(context)
            if i > 1:
                part_context.append(f"continues {kind} {qualified}: {signature}")
            pieces.append(
                _Piece(
                    kind, [qualified], a, b, parent, part_context, {"part": i, "parts": len(parts)}
                )
            )
        return pieces

    def _member_names(self, body: ts.Node, qualified: str) -> list[str]:
        names = []
        for child in body.named_children:
            found = self._definition(child)
            # Methods and nested types, not fields: a class's symbol list stays readable.
            if found is not None and found[1] != "variable":
                names.append(f"{qualified}.{found[2]}")
        return names

    def _signature(self, start_row: int, body: ts.Node | None) -> str:
        """The definition's opening lines, without attached comments or decorators."""
        end_row = body.start_point.row if body is not None else start_row
        rows = [
            line.strip()
            for line in self.lines[start_row : end_row + 1]
            if line.strip() and not line.strip().startswith(("#", "//", "/*", "*", "@"))
        ]
        signature = " ".join(rows)
        return signature[:200]

    # ------------------------------------------------------------ sizing

    def _tokens(self, start_row: int, end_row: int) -> int:
        chars = sum(len(line) + 1 for line in self.lines[start_row : end_row + 1])
        return max(1, chars // CHARS_PER_TOKEN)

    def _split_rows(
        self, start: int, end: int, segments: list[tuple[int, int]]
    ) -> list[tuple[int, int]]:
        """Cover rows [start, end] with windows under MAX_TOKENS, breaking only where a
        segment (a statement, a member) begins. A single oversized segment is line-windowed."""
        if self._tokens(start, end) <= MAX_TOKENS:
            return [(start, end)]
        boundaries = sorted({s for s, _ in segments if start < s <= end}) + [end + 1]
        windows: list[tuple[int, int]] = []
        window_start, last_fit = start, None
        for boundary in boundaries:
            if self._tokens(window_start, boundary - 1) <= MAX_TOKENS:
                last_fit = boundary
                continue
            if last_fit is not None and last_fit > window_start:
                windows.append((window_start, last_fit - 1))
                window_start = last_fit
                if self._tokens(window_start, boundary - 1) <= MAX_TOKENS:
                    last_fit = boundary
                    continue
            windows.extend(self._line_windows(window_start, boundary - 1))
            window_start, last_fit = boundary, None
        if window_start <= end:
            windows.append((window_start, end))
        return windows

    def _line_windows(self, start: int, end: int) -> list[tuple[int, int]]:
        """Last resort for a single oversized statement: fixed windows, cut at blank lines."""
        if self._tokens(start, end) <= MAX_TOKENS:
            return [(start, end)]
        budget = MAX_TOKENS * CHARS_PER_TOKEN
        windows = []
        window_start, chars, last_blank = start, 0, None
        row = start
        while row <= end:
            chars += len(self.lines[row]) + 1
            if not self.lines[row].strip():
                last_blank = row
            if chars > budget and row > window_start:
                cut = (
                    last_blank if last_blank and last_blank > (window_start + row) // 2 else row - 1
                )
                windows.append((window_start, cut))
                window_start, chars, last_blank = cut + 1, 0, None
                row = window_start
                continue
            row += 1
        if window_start <= end:
            windows.append((window_start, end))
        return windows

    def _merge_small(self, pieces: list[_Piece]) -> list[_Piece]:
        merged: list[_Piece] = []
        # The largest named piece in a merged group supplies its kind and primary symbol.
        largest: list[int] = []
        for piece in pieces:
            size = self._tokens(piece.start_row, piece.end_row) if piece.names else 0
            if merged and self._mergeable(merged[-1], piece):
                prev = merged[-1]
                prev.end_row = piece.end_row
                new_names = [n for n in piece.names if n not in prev.names]
                if size > largest[-1]:
                    prev.names = new_names + prev.names
                    prev.kind = piece.kind
                    largest[-1] = size
                else:
                    prev.names = prev.names + new_names
                prev.meta.pop("imports_only", None)
            else:
                merged.append(piece)
                largest.append(size)
        return merged

    def _mergeable(self, a: _Piece, b: _Piece) -> bool:
        if a.parent != b.parent or "part" in a.meta or "part" in b.meta:
            return False
        size_a = self._tokens(a.start_row, a.end_row)
        size_b = self._tokens(b.start_row, b.end_row)
        if size_a >= MIN_TOKENS and size_b >= MIN_TOKENS:
            return False
        return self._tokens(a.start_row, b.end_row) <= MERGE_TARGET_TOKENS

    # ------------------------------------------------------------ imports

    def _collect_imports(self, root: ts.Node) -> list[tuple[str, set[str]]]:
        imports = []
        for node in root.named_children:
            if node.type not in self.spec.imports:
                continue
            statement = " ".join(_text(node).split())
            idents = {
                ident
                for ident in IDENTIFIER_RE.findall(statement)
                if len(ident) > 1 and ident not in _IMPORT_NOISE
            }
            imports.append((statement[:120], idents))
        return imports

    @staticmethod
    def _imports_used(content: str, imports: list[tuple[str, set[str]]]) -> list[str]:
        if not imports:
            return []
        words = set(IDENTIFIER_RE.findall(content))
        used = [stmt for stmt, idents in imports if idents & words]
        return used[:MAX_IMPORT_LINES]


def chunk_code(source: bytes, language: str) -> tuple[list[ChunkDraft], dict[str, Any]]:
    return CodeChunker(language).chunk(source)


def supported(language: str | None) -> bool:
    return language in LANGUAGES
