"""Manifest parsers and the technology alias table: pure functions, no database."""

import pytest

from app.services.graph import technologies as tech
from app.services.graph.imports import modules_in
from app.services.graph.manifests import manifest_kind, parse_manifest


def deps(manifest):
    return [(d.ecosystem, d.name, d.line, d.dev) for d in manifest.dependencies]


def test_manifest_kind():
    assert manifest_kind("a/b/pyproject.toml") == "pyproject"
    assert manifest_kind("requirements-dev.txt") == "requirements"
    assert manifest_kind("requirements.in") == "requirements"
    assert manifest_kind("docker/Dockerfile.prod") == "dockerfile"
    assert manifest_kind("compose.yaml") == "compose"
    assert manifest_kind("README.md") is None
    assert manifest_kind("notes/requirements.md") is None


def test_pyproject_pep621_optional_and_poetry():
    text = """[project]
name = "svc"
dependencies = [
    "fastapi>=0.110",
    "sqlalchemy[asyncio]>=2.0",
]
[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.poetry.dependencies]
python = "^3.12"
redis = "^5"
"""
    m = parse_manifest("pyproject.toml", text)
    assert m.project_name == "svc"
    assert deps(m) == [
        ("pypi", "fastapi", 4, False),
        ("pypi", "sqlalchemy", 5, False),
        ("pypi", "pytest", 8, True),
        ("pypi", "redis", 12, False),
    ]


def test_requirements_skips_options_urls_and_comments():
    text = "# deps\n-r base.txt\nDjango==5.0  # web\npsycopg2-binary\ngit+https://x/y.git\n\n"
    m = parse_manifest("requirements-dev.txt", text)
    assert deps(m) == [("pypi", "Django", 3, True), ("pypi", "psycopg2-binary", 4, True)]


def test_package_json():
    text = (
        '{\n  "name": "web",\n  "dependencies": {"next": "15"},\n'
        '  "devDependencies": {"vitest": "1"}\n}'
    )
    m = parse_manifest("package.json", text)
    assert m.project_name == "web"
    assert deps(m) == [("npm", "next", 3, False), ("npm", "vitest", 4, True)]


def test_go_mod_block_and_single_line():
    text = """module github.com/me/checker

go 1.22

require github.com/gin-gonic/gin v1.9.1

require (
\tgithub.com/jackc/pgx/v5 v5.5.0
\tgolang.org/x/net v0.24.0 // indirect
)
"""
    m = parse_manifest("go.mod", text)
    assert m.project_name == "checker"
    assert deps(m) == [
        ("go", "github.com/gin-gonic/gin", 5, False),
        ("go", "github.com/jackc/pgx/v5", 8, False),
        ("go", "golang.org/x/net", 9, True),
    ]


def test_cargo_matches_keys_not_substrings():
    text = (
        '[package]\nname = "vs"\n[dependencies]\nserde_json = "1"\n'
        'serde = { version = "1" }\n[dev-dependencies]\ncriterion = "0.5"\n'
    )
    m = parse_manifest("Cargo.toml", text)
    assert deps(m) == [
        ("cargo", "serde_json", 4, False),
        ("cargo", "serde", 5, False),
        ("cargo", "criterion", 7, True),
    ]
    assert m.dependencies[1].spec == 'serde = { version = "1" }'


def test_pom_and_gradle():
    pom = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <artifactId>inv</artifactId>
  <dependencies>
    <dependency><groupId>org.postgresql</groupId><artifactId>postgresql</artifactId></dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>"""
    m = parse_manifest("pom.xml", pom)
    assert m.project_name == "inv" and "Maven" in m.implies
    assert [(d.name, d.dev) for d in m.dependencies] == [
        ("org.postgresql:postgresql", False),
        ("org.junit.jupiter:junit-jupiter", True),
    ]
    gradle = (
        "plugins { id 'org.springframework.boot' version '3.2' }\n"
        "dependencies {\n"
        "    implementation 'org.springframework.boot:spring-boot-starter-web'\n"
        '    testImplementation("org.junit.jupiter:junit-jupiter:5.10")\n'
        "}\n"
    )
    m = parse_manifest("build.gradle.kts", gradle)
    assert [(d.name, d.line, d.dev) for d in m.dependencies] == [
        ("org.springframework.boot:spring-boot-starter-web", 3, False),
        ("org.junit.jupiter:junit-jupiter", 4, True),
    ]
    assert "Kotlin" in m.implies


def test_dockerfile_skips_build_stages_and_compose_reads_images():
    dockerfile = "FROM node:22 AS build\nRUN npm ci\nFROM build AS test\nFROM nginx:alpine\n"
    m = parse_manifest("Dockerfile", dockerfile)
    assert [(i.image, i.line) for i in m.images] == [("node:22", 1), ("nginx:alpine", 4)]
    compose = (
        "services:\n  db:\n    image: pgvector/pgvector:pg16\n"
        "  api:\n    build: .\n  cache:\n    image: ${CACHE_IMAGE}\n"
    )
    m = parse_manifest("docker-compose.yml", compose)
    assert [(i.image, i.line) for i in m.images] == [("pgvector/pgvector:pg16", 3)]
    assert m.implies == ["Docker", "Docker Compose"]


@pytest.mark.parametrize(
    "path,text",
    [
        ("pyproject.toml", "[project\nname="),
        ("package.json", "{not json"),
        ("pom.xml", "<project><unclosed>"),
        ("docker-compose.yml", "services: [::"),
    ],
)
def test_malformed_manifests_never_raise(path, text):
    m = parse_manifest(path, text)
    assert m is not None and m.dependencies == []


def test_alias_table_resolves_every_spelling():
    for name in ("postgres", "PostgreSQL", "psql", "pgsql"):
        assert tech.by_name(name).name == "PostgreSQL"
    assert tech.by_name("next.js").name == tech.by_name("NextJS").name == "Next.js"
    assert tech.by_name("C++").name == "C++" and tech.by_name("c#").name == "C#"
    assert tech.by_name("Preact").name == "Preact" != tech.by_name("React").name
    assert tech.by_name("no-such-thing") is None


def test_packages_modules_and_images_resolve():
    names = lambda techs: [t.name for t in techs]  # noqa: E731
    assert names(tech.by_package("pypi", "psycopg2_binary")) == ["PostgreSQL"]
    assert names(tech.by_package("pypi", "Python-Jose")) == ["JWT"]
    assert names(tech.by_package("go", "github.com/jackc/pgx/v5")) == ["PostgreSQL"]
    assert names(tech.by_package("npm", "@langchain/core")) == ["LangChain"]
    assert names(tech.by_package("npm", "left-pad")) == []
    assert names(tech.by_module("python", "jose.jwt")) == ["JWT"]
    assert names(tech.by_module("python", "sqlalchemy.ext.asyncio")) == ["SQLAlchemy"]
    assert names(tech.by_module("typescript", "./local")) == []
    assert names(tech.by_module("tsx", "@tanstack/react-query")) == ["TanStack Query"]
    assert names(tech.by_module("rust", "actix_web::web")) == ["Actix Web"]
    assert names(tech.by_module("java", "org.springframework.security.core.User")) == [
        "Spring Security"
    ]
    assert tech.image_name("docker.io/library/postgres:16-alpine") == "postgres"
    assert tech.image_name("ghcr.io/org/app:1.2@sha256:abc") == "org/app"
    assert names(tech.by_image("valkey/valkey:8-alpine")) == ["Valkey"]


def test_import_statements_to_modules():
    assert modules_in("from jose import jwt", "python") == ["jose"]
    assert modules_in("from . import models", "python") == []
    assert modules_in("import os, redis.asyncio as redis", "python") == ["os", "redis.asyncio"]
    assert modules_in('import { create } from "zustand";', "typescript") == ["zustand"]
    assert modules_in("import './styles.css'", "javascript") == []
    assert modules_in("const x = require('express')", "javascript") == ["express"]
    assert modules_in("use serde::{Deserialize, Serialize};", "rust") == ["serde"]
    assert modules_in("import static org.junit.Assert.assertEquals;", "java") == [
        "org.junit.Assert.assertEquals"
    ]
