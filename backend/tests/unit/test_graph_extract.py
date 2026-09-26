"""Graph extraction as a pure function of documents: project detection, naming, stacks."""

from app.services.graph.builder import DocInfo, extract


def doc(i, path, kind="code", language=None, title=None, meta=None):
    return DocInfo(i, path, kind, language, title, meta or {})


def build(documents, files, repo_roots=(), authors=None):
    return extract(7, "vault", documents, files.get, list(repo_roots), authors)


def edges(graph, type_=None):
    return {
        (graph.nodes[e.src].name, e.type, graph.nodes[e.dst].name, e.extractor)
        for e in graph.edges
        if type_ is None or e.type == type_
    }


def test_manifest_folders_become_projects_with_generic_names_qualified():
    documents = [
        doc(1, "myapp/frontend/package.json", "text", "json"),
        doc(2, "myapp/backend/pyproject.toml", "text", "toml"),
        doc(3, "myapp/backend/app/main.py", language="python"),
        doc(4, "scripts/tool.py", language="python"),
    ]
    files = {
        "myapp/frontend/package.json": '{"dependencies": {"react": "18"}}',
        "myapp/backend/pyproject.toml": '[project]\ndependencies = ["fastapi"]\n',
    }
    graph = build(documents, files)
    projects = {n.name for n in graph.nodes.values() if n.kind == "project"}
    # No manifest names; "frontend" alone says nothing, so the parent qualifies it.
    assert projects == {"myapp/frontend", "myapp/backend"}
    found = edges(graph, "uses")
    assert ("myapp/frontend", "uses", "React", "manifest") in found
    assert ("myapp/backend", "uses", "FastAPI", "manifest") in found
    assert ("myapp/backend", "uses", "Python", "language") in found
    # scripts/ sits outside every project and is not one on its own.
    assert not any(n.name == "scripts" for n in graph.nodes.values())


def test_a_git_repo_is_one_project_whatever_its_manifests():
    documents = [
        doc(1, "frontend/package.json", "text", "json"),
        doc(2, "backend/requirements.txt", "text"),
        doc(3, "backend/api.py", language="python", meta={"imports": ["import redis"]}),
    ]
    files = {
        "frontend/package.json": '{"name": "web", "dependencies": {"next": "15"}}',
        "backend/requirements.txt": "flask\n",
        "backend/api.py": "import redis\n",
    }
    graph = build(documents, files, repo_roots=[""])
    [project] = [n for n in graph.nodes.values() if n.kind == "project"]
    assert project.name == "vault"  # the source's name, not a sub-package's
    names = {graph.nodes[e.dst].name for e in graph.edges if e.type == "uses"}
    assert {"Next.js", "Flask", "Redis", "Python"} <= names
    redis = next(e for e in graph.edges if graph.nodes[e.dst].name == "Redis")
    assert (redis.extractor, redis.line, redis.confidence) == ("import", 1, 0.9)


def test_code_without_manifest_or_repo_is_one_project():
    graph = build([doc(1, "main.go", language="go")], {})
    assert [n.name for n in graph.nodes.values() if n.kind == "project"] == ["vault"]


def test_a_stray_file_does_not_add_a_language():
    documents = [doc(1, "svc/go.mod", "text")] + [
        doc(i, f"svc/pkg/f{i}.go", language="go") for i in range(2, 22)
    ]
    documents.append(doc(99, "svc/scripts/release.sh", language="shell"))
    graph = build(documents, {"svc/go.mod": "module example.com/svc\n"})
    languages = {e.evidence for e in graph.edges if e.extractor == "language"}
    assert languages == {"20 Go files"}


def test_notes_wikilinks_and_tags():
    documents = [
        doc(1, "svc/pyproject.toml", "text"),
        doc(2, "notes/design.md", "markdown", title="Design",
            meta={"links": ["svc", "Other note", "PostgreSQL", "missing"],
                  "tags": ["architecture", "postgres"]}),
        doc(3, "notes/other.md", "markdown", title="Other note"),
    ]  # fmt: skip
    files = {
        "svc/pyproject.toml": '[project]\nname = "svc"\n',
        "notes/design.md": "# Design\nUses [[svc]] and [[Other note]] on [[PostgreSQL]].\n",
    }
    found = edges(build(documents, files))
    assert ("Design", "mentions", "svc", "wikilink") in found
    assert ("Design", "links_to", "Other note", "wikilink") in found
    assert ("Design", "mentions", "PostgreSQL", "wikilink") in found
    assert ("Design", "tagged", "architecture", "tag") in found
    assert ("Design", "mentions", "PostgreSQL", "tag") in found  # #postgres is not a topic
    assert not any("missing" in edge for edge in found)


def test_local_packages_become_project_dependencies():
    documents = [doc(1, "core/package.json", "text"), doc(2, "web/package.json", "text")]
    files = {
        "core/package.json": '{"name": "core"}',
        "web/package.json": '{"name": "web", "dependencies": {"core": "workspace:*"}}',
    }
    assert ("web", "depends_on", "core", "manifest") in edges(build(documents, files))
