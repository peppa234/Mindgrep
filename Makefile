# Same tasks as make.ps1, for CI, WSL, Linux and macOS. On Windows use: .\make.ps1 <task>
.PHONY: help up down restart build logs ps health docs psql valkey migrate test fmt lint \
        models eval eval-personal eval-baseline eval-graph eval-chat eval-ideas \n        refresh-ideas extract label clean deploy

MODELS_VENV := backend/.venv-models
DC_EVAL := docker compose exec api python -m eval.runners.retrieval_eval

help:
	@echo "up             build and start the stack"
	@echo "models         start the model server on this machine (CUDA if available)"
	@echo "down           stop the stack (keeps data)"
	@echo "restart        restart containers"
	@echo "build          rebuild images"
	@echo "logs           follow logs"
	@echo "ps             container status"
	@echo "health         GET /health and print the result"
	@echo "docs           print the Swagger UI URL"
	@echo "psql           open a psql shell"
	@echo "valkey         open a valkey-cli shell"
	@echo "migrate        apply database migrations"
	@echo "test           run the backend test suite"
	@echo "fmt / lint     fix / check formatting with ruff"
	@echo "eval           fixture benchmark, every search mode"
	@echo "eval-personal  your benchmark (eval/golden/personal.yaml)"
	@echo "eval-baseline  regenerate the CI baseline"
	@echo "eval-graph     knowledge-graph precision/recall and chat routing"
	@echo "eval-chat      end-to-end chat: abstention and citations (needs real models)"
	@echo "eval-ideas     idea <-> implementation gap: detection, matching, thresholds"
	@echo "refresh-ideas  re-match every idea against every project"
	@echo "extract ID=... LLM concept extraction over a source's notes and READMEs"
	@echo "label Q=...    candidates with ready-to-paste golden labels"
	@echo "clean          stop the stack AND delete all data volumes"
	@echo "deploy         on the VPS: build and start the production stack (docs/deploy.md)"

.env:
	cp .env.example .env
	mkdir -p data/sources

up: .env
	docker compose up -d --build

down:
	docker compose down

restart:
	docker compose restart

build: .env
	docker compose build

logs:
	docker compose logs -f --tail 100

ps:
	docker compose ps

health:
	curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8000/health
	curl -sS http://localhost:8000/health

docs:
	@echo "Swagger UI: http://localhost:8000/docs"

psql:
	docker compose exec postgres psql -U memoryos -d memoryos

valkey:
	docker compose exec valkey valkey-cli

migrate:
	docker compose exec api alembic upgrade head

test:
	docker compose exec api pytest

fmt:
	docker compose exec api sh -c "ruff format . eval && ruff check --fix . eval"

lint:
	docker compose exec api sh -c "ruff check . eval && ruff format --check . eval"

$(MODELS_VENV)/bin/python:
	uv venv --python 3.12 $(MODELS_VENV)
	uv pip install --python $(MODELS_VENV) torch
	uv pip install --python $(MODELS_VENV) -r backend/requirements-models.txt

models: $(MODELS_VENV)/bin/python
	cd backend && .venv-models/bin/python -m uvicorn app.modelserver.main:app --host 0.0.0.0 --port 8001

eval:
	$(DC_EVAL) --modes lexical,vector,hybrid,rerank

eval-personal:
	$(DC_EVAL) --golden eval/golden/personal.yaml --no-index

eval-baseline:
	docker compose exec postgres psql -U memoryos -d postgres -qc "DROP DATABASE IF EXISTS memoryos_ci" -c "CREATE DATABASE memoryos_ci"
	docker compose exec -e DATABASE_URL=postgresql+asyncpg://memoryos:memoryos@postgres:5432/memoryos_ci \
		-e EMBEDDER=hash -e RERANKER=none api sh -c \
		"alembic upgrade head && python -m eval.runners.retrieval_eval --modes lexical,vector,hybrid --name baseline-ci"
	docker compose exec postgres psql -U memoryos -d postgres -qc "DROP DATABASE memoryos_ci"

eval-graph:
	docker compose exec api python -m eval.runners.graph_eval --out eval/reports

eval-chat:
	docker compose exec api python -m eval.runners.chat_eval

eval-ideas:
	docker compose exec api python -m eval.runners.idea_eval --out eval/reports

refresh-ideas:
	curl -sS -X POST http://localhost:8000/api/v1/ideas/refresh

extract:
	curl -sS -X POST http://localhost:8000/api/v1/sources/$(ID)/extract

label:
	docker compose exec api python -m eval.runners.label "$(Q)"

clean:
	docker compose down -v

deploy:
	./infra/deploy.sh
