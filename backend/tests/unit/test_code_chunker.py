from app.services.chunking.code_chunker import chunk_code
from app.services.chunking.types import MAX_TOKENS


def by_symbol(drafts):
    return {name: d for d in drafts for name in d.symbols}


def test_python_function_keeps_decorator_and_docstring():
    source = b'''import os


@app.get("/x")
def handler(request):
    """Serve x."""
    value = os.environ["X"] * 100
    another = value + "padding so this is not merged with anything else nearby"
    return {"x": value, "y": another, "z": [value, another, value, another]}
'''
    drafts, _ = chunk_code(source, "python")
    handler = by_symbol(drafts)["handler"]
    assert handler.content.startswith('@app.get("/x")')
    assert '"""Serve x."""' in handler.content
    assert handler.start_line == 4
    assert handler.end_line == 9
    assert handler.kind == "function"


def test_import_only_fragments_are_dropped_but_listed_in_header():
    source = b"""from jose import jwt
import datetime


def make_token(sub):
    return jwt.encode({"sub": sub, "iat": datetime.datetime.now()}, "k", algorithm="HS256")
"""
    drafts, meta = chunk_code(source, "python")
    assert len(drafts) == 1
    assert drafts[0].symbols == ["make_token"]
    assert "uses: from jose import jwt; import datetime" in drafts[0].context
    assert meta["imports"] == ["from jose import jwt", "import datetime"]


def test_large_class_is_split_into_methods_with_class_context():
    methods = "\n".join(
        f"    def method_{i}(self, argument):\n"
        f"        # a comment explaining step {i} of the long algorithm in some detail\n"
        + "".join(
            f"        value_{j} = argument * {j} + self.helper_function(argument, {j})\n"
            for j in range(12)
        )
        + f"        return value_{i % 12}\n"
        for i in range(12)
    )
    source = f'class Engine(Base):\n    """Docs."""\n\n{methods}'.encode()
    drafts, _ = chunk_code(source, "python")
    assert len(drafts) > 1
    assert all(len(d.content) // 4 <= MAX_TOKENS for d in drafts)
    names = [n for d in drafts for n in d.symbols]
    assert "Engine" in names
    assert "Engine.method_7" in names
    later = [d for d in drafts if "Engine" not in d.symbols]
    assert later and all(any(c.startswith("in class Engine") for c in d.context) for d in later)


def test_oversized_function_is_split_into_parts_with_signature():
    body = "".join(
        f"    step_{i} = compute_something_expensive(step_{i - 1 if i else 0}, {i})\n"
        for i in range(400)
    )
    source = f"def pipeline(data):\n{body}    return step_399\n".encode()
    drafts, _ = chunk_code(source, "python")
    assert len(drafts) >= 3
    assert all(d.symbols == ["pipeline"] for d in drafts)
    assert drafts[0].meta["part"] == 1 and drafts[-1].meta["part"] == len(drafts)
    assert any("continues function pipeline: def pipeline(data):" in c for c in drafts[1].context)
    # Parts cover the function without gaps or overlap.
    for prev, nxt in zip(drafts, drafts[1:], strict=False):
        assert nxt.start_line == prev.end_line + 1


def test_typescript_arrow_function_and_jsdoc():
    source = b"""import { sign } from "jsonwebtoken";

/**
 * Issue a token for the user. Long enough documentation that it is not merged away.
 * It explains the claims, the expiry, and why we sign with the shared secret here.
 */
export const makeToken = async (userId: string): Promise<string> => {
  const claims = { userId, issuedAt: Date.now(), audience: "task-board", scope: "rw" };
  return sign(claims, process.env.SECRET!, { expiresIn: "15m", algorithm: "HS256" });
};
"""
    drafts, _ = chunk_code(source, "typescript")
    token = by_symbol(drafts)["makeToken"]
    assert token.kind == "function"
    assert token.content.lstrip().startswith("/**")
    assert token.start_line == 3


def test_go_method_is_qualified_by_receiver():
    source = b"""package main

// Handle serves one request. It is documented at some length so that it stands alone
// as its own chunk instead of being merged with the tiny type declaration below it.
func (s *Server) Handle(w http.ResponseWriter, r *http.Request) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.count++
	fmt.Fprintf(w, "request number %d from %s for path %s", s.count, r.RemoteAddr, r.URL.Path)
}
"""
    drafts, _ = chunk_code(source, "go")
    handle = by_symbol(drafts)["Server.Handle"]
    assert handle.kind == "method"
    # The tiny `package main` clause is merged in as context; the doc comment stays attached.
    assert "// Handle serves one request." in handle.content
    assert handle.content.index("// Handle") < handle.content.index("func (s *Server)")


def test_rust_impl_members_are_qualified():
    source = b"""pub struct Store { items: Vec<u32> }

impl Store {
    pub fn new() -> Self { Self { items: Vec::new() } }
    pub fn push(&mut self, value: u32) { self.items.push(value) }
}
"""
    drafts, _ = chunk_code(source, "rust")
    names = [n for d in drafts for n in d.symbols]
    assert "Store.new" in names and "Store.push" in names


def test_small_definitions_are_merged_with_the_largest_as_primary():
    source = b"""def a(): return 1
def b(): return 2
def c(x):
    return x + 1
"""
    drafts, _ = chunk_code(source, "python")
    assert len(drafts) == 1
    assert set(drafts[0].symbols) == {"a", "b", "c"}
    assert drafts[0].symbols[0] == "c"


def test_line_numbers_cover_the_file():
    source = b"x = 1\n\n\ndef f():\n    return x\n"
    drafts, _ = chunk_code(source, "python")
    assert drafts[0].start_line == 1
    assert drafts[-1].end_line == 5


def test_syntax_errors_do_not_crash():
    drafts, meta = chunk_code(b"def broken(:\n    return\nclass\n", "python")
    assert meta["parse_errors"] is True
    assert drafts  # still produces something searchable
