# Same tasks as make.ps1, for CI and WSL. On Windows use: .\make.ps1 <task>
.PHONY: help up down restart build logs ps health docs psql valkey test fmt clean

help:
	@echo "up       build and start the stack"
	@echo "down     stop the stack (keeps data)"
	@echo "restart  restart containers"
	@echo "build    rebuild images"
	@echo "logs     follow logs"
	@echo "ps       container status"
	@echo "health   GET /health and print the result"
	@echo "docs     print the Swagger UI URL"
	@echo "psql     open a psql shell"
	@echo "valkey   open a valkey-cli shell"
	@echo "test     run the backend test suite"
	@echo "fmt      format and autofix with ruff"
	@echo "clean    stop the stack AND delete all data volumes"

.env:
	cp .env.example .env

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

test:
	docker compose exec api pytest

fmt:
	docker compose exec api sh -c "ruff format . && ruff check --fix ."

clean:
	docker compose down -v
