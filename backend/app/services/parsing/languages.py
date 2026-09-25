"""Per-language tree-sitter configuration.

Adding a language means adding one LangSpec here and its extension in the router. The
chunker itself is language-agnostic: it only needs to know which node types are definitions,
which of those contain other definitions, and which wrap a definition (decorators, `export`).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache

import tree_sitter as ts
import tree_sitter_go
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_rust
import tree_sitter_typescript


@dataclass(frozen=True)
class LangSpec:
    grammar: Callable[[], object]
    # Node type -> chunk kind for definitions at any level.
    definitions: dict[str, str]
    # Definition types whose body holds member definitions (split into members when too large).
    containers: frozenset[str]
    # Nodes that wrap a definition and should stay attached to it (decorators, `export`).
    wrappers: frozenset[str] = frozenset()
    imports: frozenset[str] = frozenset()
    comments: frozenset[str] = frozenset({"comment"})
    # JS/TS: `const handler = async () => {}` is a function in everything but syntax.
    variable_declarations: frozenset[str] = frozenset()
    function_values: frozenset[str] = frozenset()
    # Inside a container, these definition kinds are reported as methods.
    method_kinds: frozenset[str] = field(default_factory=lambda: frozenset({"function"}))


_JS_DEFS = {
    "function_declaration": "function",
    "generator_function_declaration": "function",
    "class_declaration": "class",
    "method_definition": "method",
}
_TS_DEFS = {
    **_JS_DEFS,
    "abstract_class_declaration": "class",
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    "enum_declaration": "enum",
}
_JS_COMMON = dict(
    wrappers=frozenset({"export_statement"}),
    imports=frozenset({"import_statement"}),
    variable_declarations=frozenset({"lexical_declaration", "variable_declaration"}),
    function_values=frozenset(
        {"arrow_function", "function_expression", "function", "generator_function"}
    ),
)

LANGUAGES: dict[str, LangSpec] = {
    "python": LangSpec(
        grammar=tree_sitter_python.language,
        definitions={"function_definition": "function", "class_definition": "class"},
        containers=frozenset({"class_definition"}),
        wrappers=frozenset({"decorated_definition"}),
        imports=frozenset({"import_statement", "import_from_statement"}),
    ),
    "javascript": LangSpec(
        grammar=tree_sitter_javascript.language,
        definitions=_JS_DEFS,
        containers=frozenset({"class_declaration"}),
        **_JS_COMMON,
    ),
    "typescript": LangSpec(
        grammar=tree_sitter_typescript.language_typescript,
        definitions=_TS_DEFS,
        containers=frozenset({"class_declaration", "abstract_class_declaration"}),
        **_JS_COMMON,
    ),
    "tsx": LangSpec(
        grammar=tree_sitter_typescript.language_tsx,
        definitions=_TS_DEFS,
        containers=frozenset({"class_declaration", "abstract_class_declaration"}),
        **_JS_COMMON,
    ),
    "go": LangSpec(
        grammar=tree_sitter_go.language,
        definitions={
            "function_declaration": "function",
            "method_declaration": "method",
            "type_declaration": "type",
            "const_declaration": "variable",
            "var_declaration": "variable",
        },
        containers=frozenset(),
        imports=frozenset({"import_declaration"}),
    ),
    "rust": LangSpec(
        grammar=tree_sitter_rust.language,
        definitions={
            "function_item": "function",
            "struct_item": "type",
            "enum_item": "type",
            "union_item": "type",
            "type_item": "type",
            "trait_item": "trait",
            "impl_item": "impl",
            "mod_item": "module",
            "macro_definition": "macro",
            "const_item": "variable",
            "static_item": "variable",
        },
        containers=frozenset({"impl_item", "trait_item", "mod_item"}),
        imports=frozenset({"use_declaration"}),
        comments=frozenset({"line_comment", "block_comment"}),
    ),
    "java": LangSpec(
        grammar=tree_sitter_java.language,
        definitions={
            "class_declaration": "class",
            "interface_declaration": "interface",
            "enum_declaration": "enum",
            "record_declaration": "class",
            "method_declaration": "method",
            "constructor_declaration": "method",
        },
        containers=frozenset(
            {"class_declaration", "interface_declaration", "enum_declaration", "record_declaration"}
        ),
        imports=frozenset({"import_declaration"}),
        comments=frozenset({"line_comment", "block_comment"}),
    ),
}


@cache
def language_for(language: str) -> ts.Language:
    return ts.Language(LANGUAGES[language].grammar())


def parser_for(language: str) -> ts.Parser:
    # The Language is cached for the life of the process: a Parser must never outlive the
    # grammar it points into. Parsers are cheap and not thread-safe, so each caller gets one.
    return ts.Parser(language_for(language))
