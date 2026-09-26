"""The curated technology table: one canonical node per technology, whatever it is called.

`postgres`, `postgresql`, `PostgreSQL`, `psycopg2-binary`, `asyncpg`, `pgx` and the
`pgvector/pgvector:pg16` image all mean PostgreSQL. Getting this wrong means "which projects
use PostgreSQL?" returns part of the truth, so the table is written by hand rather than
guessed by similarity: `React` and `Preact` embed almost identically and are not the same
thing. Nothing is merged on embedding similarity, ever.

Each entry lists how the technology shows up:
  aliases  : names a person types ("postgres", "k8s"). Matched after normalisation.
  packages : `<ecosystem>:<name>` in a manifest. A trailing `*` matches a prefix
             (`npm:@langchain/*`); Go module paths also match their sub-paths and /vN.
  modules  : import names that differ from the package (`py:jose` for python-jose).
             Python imports otherwise fall back to the package name, `_` read as `-`.
  images   : Docker images (`postgres`, `pgvector/pgvector`), registry and tag stripped.
"""

import re
from dataclasses import dataclass
from functools import cache


@dataclass(frozen=True)
class Tech:
    name: str
    category: str  # language | framework | library | database | infra | auth | ai | tool
    aliases: tuple[str, ...] = ()
    packages: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()
    images: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return normalize(self.name)


def T(name: str, category: str, aliases="", packages="", modules="", images="") -> Tech:  # noqa: N802
    return Tech(
        name,
        category,
        tuple(aliases.split()),
        tuple(packages.split()),
        tuple(modules.split()),
        tuple(images.split()),
    )


# fmt: off
TECHNOLOGIES: list[Tech] = [
    # ------------------------------------------------------------------ languages
    T("Python", "language", "py python3"),
    T("JavaScript", "language", "js ecmascript"),
    T("TypeScript", "language", "ts"),
    T("Go", "language", "golang"),
    T("Rust", "language"),
    T("Java", "language"),
    T("Kotlin", "language"),
    T("C", "language"),
    T("C++", "language", "cpp cplusplus"),
    T("C#", "language", "csharp dotnet"),
    T("Swift", "language"),
    T("Ruby", "language"),
    T("PHP", "language"),
    T("Dart", "language"),
    T("Scala", "language"),
    T("Lua", "language"),
    T("R", "language"),
    T("Shell", "language", "bash sh zsh"),
    T("SQL", "language"),
    # ------------------------------------------------------------------ python
    T("FastAPI", "framework", "", "pypi:fastapi pypi:fastapi-slim"),
    T("Django", "framework", "", "pypi:django pypi:djangorestframework"),
    T("Flask", "framework", "", "pypi:flask"),
    T("Starlette", "framework", "", "pypi:starlette"),
    T("Pydantic", "library", "", "pypi:pydantic pypi:pydantic-settings"),
    T("SQLAlchemy", "library", "", "pypi:sqlalchemy pypi:sqlmodel"),
    T("Alembic", "tool", "", "pypi:alembic"),
    T("Celery", "library", "", "pypi:celery"),
    T("ARQ", "library", "", "pypi:arq"),
    T("Uvicorn", "tool", "", "pypi:uvicorn"),
    T("Gunicorn", "tool", "", "pypi:gunicorn"),
    T("pytest", "tool", "", "pypi:pytest"),
    T("NumPy", "library", "", "pypi:numpy"),
    T("pandas", "library", "", "pypi:pandas"),
    T("Polars", "library", "", "pypi:polars npm:nodejs-polars cargo:polars"),
    T("scikit-learn", "ai", "sklearn", "pypi:scikit-learn", "py:sklearn"),
    T("PyTorch", "ai", "torch", "pypi:torch pypi:torchvision pypi:lightning pypi:pytorch-lightning"),
    T("TensorFlow", "ai", "tf", "pypi:tensorflow pypi:tensorflow-cpu npm:@tensorflow/*"),
    T("Keras", "ai", "", "pypi:keras"),
    T("JAX", "ai", "", "pypi:jax pypi:flax"),
    T("XGBoost", "ai", "", "pypi:xgboost"),
    T("LightGBM", "ai", "", "pypi:lightgbm"),
    T("Hugging Face Transformers", "ai", "transformers huggingface hf",
      "pypi:transformers npm:@huggingface/transformers npm:@xenova/transformers"),
    T("sentence-transformers", "ai", "sbert", "pypi:sentence-transformers"),
    T("spaCy", "ai", "", "pypi:spacy"),
    T("NLTK", "ai", "", "pypi:nltk"),
    T("OpenCV", "library", "cv2", "pypi:opencv-python pypi:opencv-python-headless", "py:cv2"),
    T("Pillow", "library", "pil", "pypi:pillow", "py:PIL"),
    T("Matplotlib", "library", "", "pypi:matplotlib"),
    T("Jupyter", "tool", "ipython notebook", "pypi:jupyter pypi:jupyterlab pypi:notebook pypi:ipykernel"),
    T("Streamlit", "framework", "", "pypi:streamlit"),
    T("Gradio", "framework", "", "pypi:gradio"),
    T("Requests", "library", "", "pypi:requests"),
    T("HTTPX", "library", "", "pypi:httpx"),
    T("aiohttp", "library", "", "pypi:aiohttp"),
    T("Beautiful Soup", "library", "bs4 beautifulsoup", "pypi:beautifulsoup4 pypi:bs4", "py:bs4"),
    T("Scrapy", "framework", "", "pypi:scrapy"),
    T("Airflow", "tool", "", "pypi:apache-airflow", "py:airflow"),
    T("Prefect", "tool", "", "pypi:prefect"),
    T("Dagster", "tool", "", "pypi:dagster"),
    T("MLflow", "ai", "", "pypi:mlflow"),
    T("Ray", "ai", "", "pypi:ray"),
    T("Dask", "library", "", "pypi:dask"),
    T("tree-sitter", "library", "treesitter",
      "pypi:tree-sitter npm:tree-sitter npm:web-tree-sitter cargo:tree-sitter", "py:tree_sitter"),
    T("PyMuPDF", "library", "fitz", "pypi:pymupdf", "py:fitz py:pymupdf"),
    T("Docling", "library", "", "pypi:docling"),
    T("python-dotenv", "library", "dotenv", "pypi:python-dotenv npm:dotenv", "py:dotenv"),
    T("PyYAML", "library", "", "pypi:pyyaml", "py:yaml"),
    # ------------------------------------------------------------------ javascript / typescript
    T("React", "framework", "reactjs", "npm:react npm:react-dom"),
    T("Next.js", "framework", "next nextjs", "npm:next"),
    T("Vue", "framework", "vuejs vue.js", "npm:vue"),
    T("Nuxt", "framework", "nuxtjs", "npm:nuxt"),
    T("Svelte", "framework", "", "npm:svelte"),
    T("SvelteKit", "framework", "", "npm:@sveltejs/kit"),
    T("Angular", "framework", "angularjs", "npm:@angular/core"),
    T("Solid", "framework", "solidjs", "npm:solid-js"),
    T("Preact", "framework", "", "npm:preact"),
    T("Astro", "framework", "", "npm:astro"),
    T("Remix", "framework", "", "npm:@remix-run/react npm:@remix-run/node"),
    T("Express", "framework", "expressjs express.js", "npm:express"),
    T("NestJS", "framework", "nest", "npm:@nestjs/core"),
    T("Fastify", "framework", "", "npm:fastify"),
    T("Koa", "framework", "", "npm:koa"),
    T("Hono", "framework", "", "npm:hono"),
    T("Vite", "tool", "", "npm:vite"),
    T("Webpack", "tool", "", "npm:webpack"),
    T("Tailwind CSS", "library", "tailwind tailwindcss", "npm:tailwindcss npm:@tailwindcss/*"),
    T("shadcn/ui", "library", "shadcn", "npm:shadcn npm:shadcn-ui"),
    T("Radix UI", "library", "radix", "npm:@radix-ui/*"),
    T("Redux", "library", "", "npm:redux npm:@reduxjs/toolkit npm:react-redux"),
    T("Zustand", "library", "", "npm:zustand"),
    T("TanStack Query", "library", "react-query", "npm:@tanstack/react-query npm:react-query"),
    T("tRPC", "library", "", "npm:@trpc/server npm:@trpc/client"),
    T("Axios", "library", "", "npm:axios"),
    T("Zod", "library", "", "npm:zod"),
    T("Prisma", "library", "", "npm:prisma npm:@prisma/client"),
    T("Drizzle", "library", "drizzle-orm", "npm:drizzle-orm"),
    T("TypeORM", "library", "", "npm:typeorm"),
    T("Sequelize", "library", "", "npm:sequelize"),
    T("Mongoose", "library", "", "npm:mongoose"),
    T("Jest", "tool", "", "npm:jest"),
    T("Vitest", "tool", "", "npm:vitest"),
    T("Playwright", "tool", "", "npm:playwright npm:@playwright/test pypi:playwright pypi:pytest-playwright"),
    T("Cypress", "tool", "", "npm:cypress"),
    T("Storybook", "tool", "", "npm:storybook npm:@storybook/*"),
    T("ESLint", "tool", "", "npm:eslint"),
    T("Socket.IO", "library", "socketio socket.io",
      "npm:socket.io npm:socket.io-client pypi:python-socketio", "py:socketio"),
    T("Electron", "framework", "", "npm:electron"),
    T("React Native", "framework", "", "npm:react-native"),
    T("Expo", "framework", "", "npm:expo"),
    T("three.js", "library", "threejs three", "npm:three"),
    T("D3", "library", "d3.js d3js", "npm:d3"),
    T("Chart.js", "library", "chartjs", "npm:chart.js"),
    T("Cytoscape.js", "library", "cytoscape", "npm:cytoscape"),
    T("dnd kit", "library", "dnd-kit", "npm:@dnd-kit/*"),
    T("Node.js", "language", "node nodejs"),
    T("Deno", "language"),
    T("Bun", "language", "", "npm:bun-types npm:@types/bun"),
    # ------------------------------------------------------------------ go
    T("Gin", "framework", "", "go:github.com/gin-gonic/gin"),
    T("Echo", "framework", "", "go:github.com/labstack/echo"),
    T("Fiber", "framework", "", "go:github.com/gofiber/fiber"),
    T("chi", "framework", "", "go:github.com/go-chi/chi"),
    T("Gorilla Mux", "library", "gorilla", "go:github.com/gorilla/mux"),
    T("GORM", "library", "", "go:gorm.io/gorm"),
    T("Cobra", "library", "", "go:github.com/spf13/cobra"),
    T("testify", "tool", "", "go:github.com/stretchr/testify"),
    # ------------------------------------------------------------------ rust
    T("Tokio", "library", "", "cargo:tokio"),
    T("Axum", "framework", "", "cargo:axum"),
    T("Actix Web", "framework", "actix", "cargo:actix-web"),
    T("Rocket", "framework", "", "cargo:rocket"),
    T("Serde", "library", "", "cargo:serde cargo:serde_json"),
    T("Diesel", "library", "", "cargo:diesel"),
    T("SQLx", "library", "", "cargo:sqlx"),
    T("Reqwest", "library", "", "cargo:reqwest"),
    T("Clap", "library", "", "cargo:clap"),
    T("Bevy", "framework", "", "cargo:bevy"),
    T("WebAssembly", "tool", "wasm", "cargo:wasm-bindgen npm:wasm-pack"),
    # ------------------------------------------------------------------ jvm / ruby / php
    T("Spring Boot", "framework", "spring springboot",
      "maven:org.springframework.boot:* maven:org.springframework:*", "java:org.springframework"),
    T("Hibernate", "library", "jpa", "maven:org.hibernate:* maven:org.hibernate.orm:*",
      "java:org.hibernate java:jakarta.persistence java:javax.persistence"),
    T("JUnit", "tool", "", "maven:junit:junit maven:org.junit.jupiter:*", "java:org.junit"),
    T("Lombok", "library", "", "maven:org.projectlombok:lombok", "java:lombok"),
    T("Jackson", "library", "", "maven:com.fasterxml.jackson.core:*", "java:com.fasterxml.jackson"),
    T("Quarkus", "framework", "", "maven:io.quarkus:*", "java:io.quarkus"),
    T("Maven", "tool"),
    T("Gradle", "tool"),
    T("Ruby on Rails", "framework", "rails ror", "gem:rails"),
    T("Sinatra", "framework", "", "gem:sinatra"),
    T("RSpec", "tool", "", "gem:rspec gem:rspec-rails"),
    T("Laravel", "framework", "", "composer:laravel/framework"),
    T("Symfony", "framework", "", "composer:symfony/*"),
    # ------------------------------------------------------------------ databases
    T("PostgreSQL", "database", "postgres postgre psql pg pgsql",
      "pypi:psycopg2 pypi:psycopg2-binary pypi:psycopg pypi:psycopg-binary pypi:asyncpg pypi:pg8000 "
      "npm:pg npm:postgres npm:@neondatabase/serverless npm:@vercel/postgres "
      "go:github.com/jackc/pgx go:github.com/lib/pq go:gorm.io/driver/postgres "
      "cargo:tokio-postgres cargo:postgres maven:org.postgresql:postgresql gem:pg",
      "java:org.postgresql",
      "postgres postgis/postgis pgvector/pgvector supabase/postgres bitnami/postgresql "
      "timescale/timescaledb ankane/pgvector"),
    T("pgvector", "database", "pg_vector",
      "pypi:pgvector npm:pgvector cargo:pgvector", "", "pgvector/pgvector ankane/pgvector"),
    T("MySQL", "database", "",
      "pypi:pymysql pypi:mysqlclient pypi:mysql-connector-python pypi:aiomysql npm:mysql npm:mysql2 "
      "go:github.com/go-sql-driver/mysql maven:mysql:mysql-connector-java "
      "maven:com.mysql:mysql-connector-j gem:mysql2", "py:MySQLdb", "mysql bitnami/mysql"),
    T("MariaDB", "database", "", "pypi:mariadb npm:mariadb", "", "mariadb bitnami/mariadb"),
    T("SQLite", "database", "sqlite3",
      "pypi:aiosqlite npm:better-sqlite3 npm:sqlite3 cargo:rusqlite go:github.com/mattn/go-sqlite3 "
      "gem:sqlite3", "py:sqlite3"),
    T("MongoDB", "database", "mongo",
      "pypi:pymongo pypi:motor pypi:mongoengine pypi:beanie npm:mongodb npm:mongoose "
      "go:go.mongodb.org/mongo-driver cargo:mongodb", "", "mongo bitnami/mongodb"),
    T("Redis", "database", "",
      "pypi:redis pypi:aioredis pypi:hiredis npm:redis npm:ioredis npm:@upstash/redis "
      "go:github.com/redis/go-redis go:github.com/go-redis/redis go:github.com/gomodule/redigo "
      "cargo:redis gem:redis", "", "redis bitnami/redis redis/redis-stack"),
    T("Valkey", "database", "", "pypi:valkey npm:iovalkey", "", "valkey/valkey bitnami/valkey"),
    T("Elasticsearch", "database", "elastic es",
      "pypi:elasticsearch npm:@elastic/elasticsearch", "",
      "elasticsearch elasticsearch/elasticsearch bitnami/elasticsearch"),
    T("OpenSearch", "database", "", "pypi:opensearch-py npm:@opensearch-project/opensearch", "",
      "opensearchproject/opensearch"),
    T("Cassandra", "database", "", "pypi:cassandra-driver", "", "cassandra"),
    T("Neo4j", "database", "", "pypi:neo4j npm:neo4j-driver", "", "neo4j"),
    T("Qdrant", "database", "", "pypi:qdrant-client npm:@qdrant/js-client-rest cargo:qdrant-client",
      "", "qdrant/qdrant"),
    T("Chroma", "database", "chromadb", "pypi:chromadb npm:chromadb", "", "chromadb/chroma"),
    T("Pinecone", "database", "", "pypi:pinecone-client pypi:pinecone npm:@pinecone-database/pinecone"),
    T("Weaviate", "database", "", "pypi:weaviate-client npm:weaviate-client", "",
      "semitechnologies/weaviate"),
    T("Milvus", "database", "", "pypi:pymilvus", "", "milvusdb/milvus"),
    T("FAISS", "database", "", "pypi:faiss-cpu pypi:faiss-gpu", "py:faiss"),
    T("DuckDB", "database", "", "pypi:duckdb npm:duckdb cargo:duckdb"),
    T("ClickHouse", "database", "", "pypi:clickhouse-connect pypi:clickhouse-driver", "",
      "clickhouse/clickhouse-server"),
    T("InfluxDB", "database", "", "pypi:influxdb-client", "", "influxdb"),
    T("Supabase", "database", "", "pypi:supabase npm:@supabase/supabase-js"),
    T("Firebase", "database", "", "pypi:firebase-admin npm:firebase npm:firebase-admin"),
    # ------------------------------------------------------------------ infra & messaging
    T("Docker", "infra"),
    T("Docker Compose", "infra", "compose docker-compose"),
    T("Kubernetes", "infra", "k8s", "pypi:kubernetes"),
    T("Terraform", "infra"),
    T("RabbitMQ", "infra", "rabbit amqp", "pypi:pika pypi:aio-pika pypi:kombu npm:amqplib", "",
      "rabbitmq bitnami/rabbitmq"),
    T("Kafka", "infra", "apache-kafka",
      "pypi:kafka-python pypi:confluent-kafka pypi:aiokafka npm:kafkajs maven:org.apache.kafka:*",
      "java:org.apache.kafka", "confluentinc/cp-kafka bitnami/kafka apache/kafka"),
    T("Nginx", "infra", "", "", "", "nginx bitnami/nginx"),
    T("Caddy", "infra", "", "", "", "caddy"),
    T("Traefik", "infra", "", "", "", "traefik"),
    T("MinIO", "infra", "", "pypi:minio npm:minio", "", "minio/minio bitnami/minio"),
    T("AWS", "infra", "amazon-web-services",
      "pypi:boto3 pypi:aioboto3 npm:aws-sdk npm:@aws-sdk/*", "py:boto3"),
    T("Google Cloud", "infra", "gcp", "pypi:google-cloud-* npm:@google-cloud/*"),
    T("Azure", "infra", "", "pypi:azure-* npm:@azure/*"),
    T("Prometheus", "infra", "", "pypi:prometheus-client npm:prom-client", "", "prom/prometheus"),
    T("Grafana", "infra", "", "", "", "grafana/grafana"),
    T("Sentry", "tool", "", "pypi:sentry-sdk npm:@sentry/*"),
    T("Langfuse", "ai", "", "pypi:langfuse npm:langfuse", "", "langfuse/langfuse"),
    T("gRPC", "library", "grpc",
      "pypi:grpcio npm:@grpc/grpc-js go:google.golang.org/grpc cargo:tonic maven:io.grpc:*",
      "java:io.grpc"),
    T("Protocol Buffers", "library", "protobuf proto",
      "pypi:protobuf npm:protobufjs go:google.golang.org/protobuf cargo:prost"),
    T("GraphQL", "library", "",
      "pypi:graphene pypi:strawberry-graphql pypi:ariadne npm:graphql npm:@apollo/server "
      "npm:@apollo/client npm:apollo-server go:github.com/99designs/gqlgen"),
    T("WebSockets", "library", "websocket ws",
      "pypi:websockets npm:ws go:github.com/gorilla/websocket cargo:tokio-tungstenite"),
    T("Stripe", "tool", "", "pypi:stripe npm:stripe npm:@stripe/stripe-js"),
    # ------------------------------------------------------------------ auth & security
    T("JWT", "auth", "jsonwebtoken json-web-token jwts",
      "pypi:pyjwt pypi:python-jose pypi:jwcrypto pypi:djangorestframework-simplejwt "
      "pypi:fastapi-jwt-auth npm:jsonwebtoken npm:jose npm:jwt-decode go:github.com/golang-jwt/jwt "
      "go:github.com/dgrijalva/jwt-go cargo:jsonwebtoken maven:io.jsonwebtoken:* "
      "maven:com.auth0:java-jwt gem:jwt",
      "py:jwt py:jose java:io.jsonwebtoken"),
    T("OAuth", "auth", "oauth2 openid oidc",
      "pypi:authlib pypi:oauthlib pypi:requests-oauthlib npm:passport-oauth2 npm:openid-client "
      "go:golang.org/x/oauth2 cargo:oauth2"),
    T("Argon2", "auth", "", "pypi:argon2-cffi npm:argon2 cargo:argon2", "py:argon2"),
    T("bcrypt", "auth", "", "pypi:bcrypt npm:bcrypt npm:bcryptjs cargo:bcrypt gem:bcrypt"),
    T("Passport.js", "auth", "passport", "npm:passport"),
    T("Auth.js", "auth", "nextauth next-auth authjs", "npm:next-auth npm:@auth/*"),
    T("Clerk", "auth", "", "npm:@clerk/*"),
    T("Better Auth", "auth", "", "npm:better-auth"),
    T("Spring Security", "auth", "", "maven:org.springframework.boot:spring-boot-starter-security "
      "maven:org.springframework.security:*", "java:org.springframework.security"),
    # ------------------------------------------------------------------ AI APIs & frameworks
    T("OpenAI API", "ai", "openai", "pypi:openai npm:openai"),
    T("Anthropic API", "ai", "anthropic claude", "pypi:anthropic npm:@anthropic-ai/sdk"),
    T("Gemini API", "ai", "gemini", "pypi:google-generativeai pypi:google-genai npm:@google/generative-ai "
      "npm:@google/genai", "py:google.generativeai py:google.genai"),
    T("Groq", "ai", "", "pypi:groq npm:groq-sdk"),
    T("Ollama", "ai", "", "pypi:ollama npm:ollama", "", "ollama/ollama"),
    T("vLLM", "ai", "", "pypi:vllm", "", "vllm/vllm-openai"),
    T("LangChain", "ai", "", "pypi:langchain* npm:langchain npm:@langchain/*"),
    T("LangGraph", "ai", "", "pypi:langgraph npm:@langchain/langgraph"),
    T("LlamaIndex", "ai", "llama-index llama_index", "pypi:llama-index* npm:llamaindex", "py:llama_index"),
    T("Pydantic AI", "ai", "pydantic-ai", "pypi:pydantic-ai pypi:pydantic-ai-slim"),
    T("DSPy", "ai", "", "pypi:dspy pypi:dspy-ai"),
    T("Vercel AI SDK", "ai", "ai-sdk", "npm:ai npm:@ai-sdk/*"),
]
# fmt: on

# Languages the router labels documents with -> the technology they are.
LANGUAGE_TECH = {
    "python": "Python", "javascript": "JavaScript", "typescript": "TypeScript",
    "tsx": "TypeScript", "go": "Go", "rust": "Rust", "java": "Java", "kotlin": "Kotlin",
    "c": "C", "cpp": "C++", "csharp": "C#", "swift": "Swift", "ruby": "Ruby", "php": "PHP",
    "dart": "Dart", "scala": "Scala", "lua": "Lua", "r": "R", "shell": "Shell", "sql": "SQL",
}  # fmt: skip

_NON_KEY = re.compile(r"[\s\-_.'\"/()]+")


def normalize(name: str) -> str:
    """Case, spaces and punctuation are noise in a technology name; `+` and `#` are not
    (C, C++ and C# are three languages)."""
    return _NON_KEY.sub("", name.lower())


def normalize_package(ecosystem: str, name: str) -> str:
    name = name.strip()
    if ecosystem == "pypi":
        return re.sub(r"[-_.]+", "-", name.lower())  # PEP 503
    if ecosystem in ("npm", "cargo", "gem", "composer"):
        return name.lower()
    return name  # go module paths and maven coordinates are case-sensitive


@dataclass(frozen=True)
class _Index:
    by_name: dict[str, Tech]
    exact: dict[str, list[Tech]]  # "npm:react" -> [React]
    prefixes: list[tuple[str, Tech]]  # ("npm:@langchain/", LangChain), longest first
    modules: dict[str, list[Tech]]  # "py:jose" -> [JWT]
    images: dict[str, list[Tech]]


@cache
def _index() -> _Index:
    by_name: dict[str, Tech] = {}
    exact: dict[str, list[Tech]] = {}
    prefixes: list[tuple[str, Tech]] = []
    modules: dict[str, list[Tech]] = {}
    images: dict[str, list[Tech]] = {}
    for tech in TECHNOLOGIES:
        for alias in (tech.name, *tech.aliases):
            key = normalize(alias)
            if key in by_name and by_name[key] is not tech:
                raise ValueError(
                    f"alias {alias!r} is claimed by {by_name[key].name} and {tech.name}"
                )
            by_name[key] = tech
        for package in tech.packages:
            ecosystem, _, name = package.partition(":")
            if name.endswith("*"):
                prefixes.append((f"{ecosystem}:{normalize_package(ecosystem, name[:-1])}", tech))
            else:
                exact.setdefault(f"{ecosystem}:{normalize_package(ecosystem, name)}", []).append(
                    tech
                )
        for module in tech.modules:
            modules.setdefault(module, []).append(tech)
        for image in tech.images:
            images.setdefault(image, []).append(tech)
    prefixes.sort(key=lambda p: -len(p[0]))
    return _Index(by_name, exact, prefixes, modules, images)


def by_name(name: str) -> Tech | None:
    return _index().by_name.get(normalize(name))


def get(name: str) -> Tech:
    tech = by_name(name)
    if tech is None:
        raise KeyError(name)
    return tech


def by_package(ecosystem: str, name: str) -> list[Tech]:
    index = _index()
    key = f"{ecosystem}:{normalize_package(ecosystem, name)}"
    found = list(index.exact.get(key, []))
    if ecosystem == "go":
        # github.com/jackc/pgx/v5 and github.com/labstack/echo/v4/middleware are still pgx/echo.
        parts = key.split("/")
        for end in range(len(parts) - 1, 0, -1):
            found += index.exact.get("/".join(parts[:end]), [])
    for prefix, tech in index.prefixes:
        if key.startswith(prefix):
            found.append(tech)
    return list(dict.fromkeys(found))


def by_module(language: str, module: str) -> list[Tech]:
    """Resolve an import to technologies. `module` is the import target as written."""
    index = _index()
    if language == "python":
        parts = module.split(".")
        for end in range(len(parts), 0, -1):  # google.generativeai before google
            hit = index.modules.get("py:" + ".".join(parts[:end]))
            if hit:
                return hit
        return by_package("pypi", parts[0].replace("_", "-"))
    if language in ("javascript", "typescript", "tsx"):
        if module.startswith((".", "/", "~", "@/", "#")) or module.startswith("node:"):
            return []
        parts = module.split("/")
        package = "/".join(parts[:2]) if module.startswith("@") else parts[0]
        return by_package("npm", package)
    if language == "go":
        return by_package("go", module)
    if language == "rust":
        crate = module.split("::")[0]
        if crate in ("crate", "self", "super", "std", "core", "alloc"):
            return []
        return by_package("cargo", crate.replace("_", "-")) or by_package("cargo", crate)
    if language == "java":
        parts = module.split(".")
        for end in range(len(parts), 1, -1):
            hit = index.modules.get("java:" + ".".join(parts[:end]))
            if hit:
                return hit
    return []


def image_name(reference: str) -> str:
    """`docker.io/library/postgres:16-alpine@sha256:..` -> `postgres`."""
    ref = reference.strip().split("@", 1)[0]
    parts = ref.split("/")
    if len(parts) > 1 and ("." in parts[0] or ":" in parts[0] or parts[0] == "localhost"):
        parts = parts[1:]  # a registry host
    if parts and parts[0] == "library":
        parts = parts[1:]
    name = "/".join(parts)
    if ":" in name.rsplit("/", 1)[-1]:
        name = name.rsplit(":", 1)[0]
    return name.lower()


def by_image(reference: str) -> list[Tech]:
    return list(_index().images.get(image_name(reference), []))


def language_tech(language: str | None) -> Tech | None:
    name = LANGUAGE_TECH.get(language or "")
    return get(name) if name else None
