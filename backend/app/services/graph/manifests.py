"""Dependency manifests -> declared dependencies, each with the line it was read from.

"Which project used PostgreSQL?" is answered from these, not from an LLM reading prose.
Parsers are pure (text in, facts out) and forgiving: a malformed manifest yields what could
be read, never an exception that stops the graph build.
"""

import json
import re
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import PurePosixPath

import yaml


@dataclass(frozen=True)
class Dependency:
    ecosystem: str  # pypi | npm | go | cargo | maven | gem | composer
    name: str
    spec: str  # the text as written, shown as evidence
    line: int | None = None
    dev: bool = False


@dataclass(frozen=True)
class ImageRef:
    image: str
    line: int | None
    evidence: str


@dataclass
class Manifest:
    path: str
    kind: str  # pyproject | requirements | package.json | go.mod | cargo | maven | gradle | ...
    project_name: str | None = None
    dependencies: list[Dependency] = field(default_factory=list)
    images: list[ImageRef] = field(default_factory=list)
    # Technologies implied by the manifest's mere existence (a Dockerfile means Docker).
    implies: list[str] = field(default_factory=list)


MANIFEST_NAMES = {
    "pyproject.toml": "pyproject",
    "Pipfile": "pipfile",
    "setup.py": "setup.py",
    "package.json": "package.json",
    "go.mod": "go.mod",
    "Cargo.toml": "cargo",
    "pom.xml": "maven",
    "build.gradle": "gradle",
    "build.gradle.kts": "gradle",
    "Gemfile": "gemfile",
    "composer.json": "composer",
    "Dockerfile": "dockerfile",
    "docker-compose.yml": "compose",
    "docker-compose.yaml": "compose",
    "compose.yml": "compose",
    "compose.yaml": "compose",
}
REQUIREMENTS_RE = re.compile(r"^requirements([-_.][\w.-]+)?\.(txt|in)$")


def manifest_kind(path: str) -> str | None:
    name = PurePosixPath(path).name
    if name in MANIFEST_NAMES:
        return MANIFEST_NAMES[name]
    if name.startswith("Dockerfile.") or name.endswith(".Dockerfile"):
        return "dockerfile"
    if REQUIREMENTS_RE.match(name):
        return "requirements"
    return None


def find_line(text: str, needle: str, start: int = 0) -> int | None:
    """1-based line of the first occurrence of `needle` (quoted forms first)."""
    for candidate in (f'"{needle}"', f"'{needle}'", needle):
        index = text.find(candidate, start)
        if index >= 0:
            return text.count("\n", 0, index) + 1
    return None


def _toml_key_line(text: str, key: str) -> int | None:
    """Line of `key = ...` at the start of a line: `serde` must not match `serde_json`."""
    match = re.search(rf"^\s*[\"']?{re.escape(key)}[\"']?\s*=", text, re.MULTILINE)
    return text.count("\n", 0, match.start()) + 1 if match else find_line(text, key)


def _line_text(text: str, line: int | None) -> str | None:
    if line is None:
        return None
    lines = text.splitlines()
    return lines[line - 1].strip()[:200] if 0 < line <= len(lines) else None


# --------------------------------------------------------------------------- python

PEP508_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _pep508(spec: str) -> str | None:
    match = PEP508_NAME_RE.match(spec)
    return match.group(1) if match else None


def parse_requirements(text: str, path: str) -> Manifest:
    manifest = Manifest(path, "requirements")
    dev = bool(re.search(r"dev|test|lint", PurePosixPath(path).name))
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith(("#", "-", "git+", "http:", "https:", ".", "/")):
            continue
        name = _pep508(line)
        if name:
            manifest.dependencies.append(Dependency("pypi", name, line, number, dev))
    return manifest


def _pep508_list(manifest: Manifest, text: str, specs: list, dev: bool) -> None:
    for spec in specs:
        if not isinstance(spec, str):
            continue
        name = _pep508(spec)
        if name:
            line = find_line(text, spec) or find_line(text, name)
            manifest.dependencies.append(Dependency("pypi", name, spec, line, dev))


def _poetry_table(manifest: Manifest, text: str, table: dict, dev: bool) -> None:
    for name, value in table.items():
        if name.lower() == "python":
            continue
        spec = f"{name} {value}" if isinstance(value, str) else name
        line = _toml_key_line(text, name)
        manifest.dependencies.append(Dependency("pypi", name, spec, line, dev))


def parse_pyproject(text: str, path: str) -> Manifest:
    manifest = Manifest(path, "pyproject")
    data = tomllib.loads(text)
    project = data.get("project") or {}
    poetry = (data.get("tool") or {}).get("poetry") or {}
    manifest.project_name = project.get("name") or poetry.get("name")
    _pep508_list(manifest, text, project.get("dependencies") or [], False)
    for group in (project.get("optional-dependencies") or {}).values():
        _pep508_list(manifest, text, group or [], True)
    for group in (data.get("dependency-groups") or {}).values():  # PEP 735
        _pep508_list(manifest, text, group or [], True)
    _poetry_table(manifest, text, poetry.get("dependencies") or {}, False)
    _poetry_table(manifest, text, poetry.get("dev-dependencies") or {}, True)
    for group in (poetry.get("group") or {}).values():
        _poetry_table(manifest, text, (group or {}).get("dependencies") or {}, True)
    return manifest


def parse_pipfile(text: str, path: str) -> Manifest:
    manifest = Manifest(path, "pipfile")
    data = tomllib.loads(text)
    _poetry_table(manifest, text, data.get("packages") or {}, False)
    _poetry_table(manifest, text, data.get("dev-packages") or {}, True)
    return manifest


SETUP_REQUIRES_RE = re.compile(r"install_requires\s*=\s*\[(.*?)\]", re.DOTALL)


def parse_setup_py(text: str, path: str) -> Manifest:
    """Never executed: only a literal `install_requires=[...]` list is read."""
    manifest = Manifest(path, "setup.py")
    match = SETUP_REQUIRES_RE.search(text)
    if match:
        specs = re.findall(r"""["']([^"']+)["']""", match.group(1))
        _pep508_list(manifest, text, specs, False)
    name = re.search(r"""\bname\s*=\s*["']([^"']+)["']""", text)
    manifest.project_name = name.group(1) if name else None
    return manifest


# --------------------------------------------------------------------------- javascript


def parse_package_json(text: str, path: str) -> Manifest:
    manifest = Manifest(path, "package.json")
    data = json.loads(text)
    if not isinstance(data, dict):
        return manifest
    manifest.project_name = data.get("name") if isinstance(data.get("name"), str) else None
    for table, dev in (
        ("dependencies", False),
        ("peerDependencies", False),
        ("optionalDependencies", False),
        ("devDependencies", True),
    ):
        for name, version in (data.get(table) or {}).items():
            manifest.dependencies.append(
                Dependency("npm", name, f'"{name}": "{version}"', find_line(text, name), dev)
            )
    return manifest


def parse_composer(text: str, path: str) -> Manifest:
    manifest = Manifest(path, "composer")
    data = json.loads(text)
    if not isinstance(data, dict):
        return manifest
    manifest.project_name = data.get("name")
    for table, dev in (("require", False), ("require-dev", True)):
        for name, version in (data.get(table) or {}).items():
            if name == "php" or name.startswith("ext-"):
                continue
            manifest.dependencies.append(
                Dependency("composer", name, f'"{name}": "{version}"', find_line(text, name), dev)
            )
    return manifest


# --------------------------------------------------------------------------- go, rust, ruby

GO_REQUIRE_RE = re.compile(r"^\s*(?:require\s+)?([\w.~/-]+\.[\w.~/-]+)\s+(v[\w.+-]+)(.*)$")


def parse_go_mod(text: str, path: str) -> Manifest:
    manifest = Manifest(path, "go.mod")
    in_block = False
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("//", 1)[0].strip()
        comment = raw.split("//", 1)[1] if "//" in raw else ""
        if line.startswith("module "):
            manifest.project_name = line.split()[1].rsplit("/", 1)[-1]
        elif line.startswith("require ("):
            in_block = True
        elif in_block and line == ")":
            in_block = False
        elif in_block or line.startswith("require "):
            match = GO_REQUIRE_RE.match(line)
            if match:
                manifest.dependencies.append(
                    Dependency(
                        "go",
                        match.group(1),
                        f"{match.group(1)} {match.group(2)}",
                        number,
                        dev="indirect" in comment,
                    )
                )
    return manifest


def parse_cargo(text: str, path: str) -> Manifest:
    manifest = Manifest(path, "cargo")
    data = tomllib.loads(text)
    manifest.project_name = (data.get("package") or {}).get("name")
    tables = [
        (data.get("dependencies") or {}, False),
        (data.get("dev-dependencies") or {}, True),
        (data.get("build-dependencies") or {}, True),
        (((data.get("workspace") or {}).get("dependencies")) or {}, False),
    ]
    for table, dev in tables:
        for name, value in table.items():
            version = value if isinstance(value, str) else (value or {}).get("version", "")
            crate = (value.get("package") if isinstance(value, dict) else None) or name
            line = _toml_key_line(text, name)
            spec = _line_text(text, line) or f'{name} = "{version}"'
            manifest.dependencies.append(Dependency("cargo", crate, spec, line, dev))
    return manifest


GEM_RE = re.compile(r"""^\s*gem\s+["']([\w.-]+)["']""")


def parse_gemfile(text: str, path: str) -> Manifest:
    manifest = Manifest(path, "gemfile")
    for number, raw in enumerate(text.splitlines(), start=1):
        match = GEM_RE.match(raw)
        if match:
            manifest.dependencies.append(Dependency("gem", match.group(1), raw.strip(), number))
    return manifest


# --------------------------------------------------------------------------- jvm


def parse_pom(text: str, path: str) -> Manifest:
    manifest = Manifest(path, "maven", implies=["Maven", "Java"])
    # The stdlib parser's expat (>= 2.4) caps entity amplification, and manifests are
    # size-capped by the walker before they get here.
    root = ET.fromstring(text)
    ns = root.tag[: root.tag.index("}") + 1] if root.tag.startswith("{") else ""
    artifact = root.find(f"{ns}artifactId")
    manifest.project_name = (
        artifact.text.strip() if artifact is not None and artifact.text else None
    )
    parent = root.find(f"{ns}parent")
    candidates = list(root.iter(f"{ns}dependency"))
    if parent is not None:
        candidates.append(parent)
    for dep in candidates:
        group = (dep.findtext(f"{ns}groupId") or "").strip()
        artifact_id = (dep.findtext(f"{ns}artifactId") or "").strip()
        if not group or not artifact_id:
            continue
        scope = (dep.findtext(f"{ns}scope") or "").strip()
        manifest.dependencies.append(
            Dependency(
                "maven",
                f"{group}:{artifact_id}",
                f"{group}:{artifact_id}",
                find_line(text, f"<artifactId>{artifact_id}</artifactId>"),
                dev=scope == "test",
            )
        )
    return manifest


GRADLE_RE = re.compile(
    r"""^\s*(\w+)\s*\(?\s*["']([\w.-]+):([\w.-]+)(?::[^"']*)?["']""", re.MULTILINE
)


def parse_gradle(text: str, path: str) -> Manifest:
    manifest = Manifest(path, "gradle", implies=["Gradle"])
    if path.endswith(".kts"):
        manifest.implies.append("Kotlin")
    for match in GRADLE_RE.finditer(text):
        configuration, group, artifact = match.groups()
        if configuration in ("id", "version", "group"):
            continue
        manifest.dependencies.append(
            Dependency(
                "maven",
                f"{group}:{artifact}",
                match.group(0).strip(),
                text.count("\n", 0, match.start()) + 1,
                dev=configuration.startswith("test"),
            )
        )
    return manifest


# --------------------------------------------------------------------------- containers

FROM_RE = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)", re.IGNORECASE)


def parse_dockerfile(text: str, path: str) -> Manifest:
    manifest = Manifest(path, "dockerfile", implies=["Docker"])
    stages: set[str] = set()
    for number, raw in enumerate(text.splitlines(), start=1):
        match = FROM_RE.match(raw)
        if not match:
            continue
        image = match.group(1)
        alias = re.search(r"\bAS\s+(\S+)", raw, re.IGNORECASE)
        if image.lower() not in stages and image.lower() != "scratch" and "$" not in image:
            manifest.images.append(ImageRef(image, number, raw.strip()))
        if alias:
            stages.add(alias.group(1).lower())
    return manifest


def parse_compose(text: str, path: str) -> Manifest:
    manifest = Manifest(path, "compose", implies=["Docker", "Docker Compose"])
    data = yaml.safe_load(text)
    services = (data or {}).get("services") if isinstance(data, dict) else None
    if not isinstance(services, dict):
        return manifest
    for service in services.values():
        # Services with `build:` instead of `image:` are covered by their own Dockerfile.
        image = service.get("image") if isinstance(service, dict) else None
        if isinstance(image, str) and "$" not in image:
            line = find_line(text, image)
            manifest.images.append(ImageRef(image, line, _line_text(text, line) or image))
    return manifest


PARSERS = {
    "pyproject": parse_pyproject,
    "requirements": parse_requirements,
    "pipfile": parse_pipfile,
    "setup.py": parse_setup_py,
    "package.json": parse_package_json,
    "composer": parse_composer,
    "go.mod": parse_go_mod,
    "cargo": parse_cargo,
    "gemfile": parse_gemfile,
    "maven": parse_pom,
    "gradle": parse_gradle,
    "dockerfile": parse_dockerfile,
    "compose": parse_compose,
}


def parse_manifest(path: str, text: str) -> Manifest | None:
    """Parse one manifest; None if `path` is not a manifest. Never raises on bad content."""
    kind = manifest_kind(path)
    if kind is None:
        return None
    try:
        return PARSERS[kind](text, path)
    except (ValueError, TypeError, AttributeError, KeyError, ET.ParseError, yaml.YAMLError):
        # tomllib.TOMLDecodeError and json.JSONDecodeError are ValueErrors.
        return Manifest(path, kind)
