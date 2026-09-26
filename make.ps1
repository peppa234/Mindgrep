<#
    Windows task runner for MemoryOS.

    There is no `make` on this machine, so this script is the everyday entry point.
    The Makefile alongside it holds the same tasks for CI and WSL.

    Usage:  .\make.ps1 <task> [args]
    Run with no task to list them all.
#>
param(
    [Parameter(Position = 0)]
    [string]$Task = "help",
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Require-Env {
    if (-not (Test-Path ".env")) {
        Write-Host "No .env found — creating one from .env.example" -ForegroundColor Yellow
        Copy-Item ".env.example" ".env"
    }
    if (-not (Test-Path "data/sources")) { New-Item -ItemType Directory -Force "data/sources" | Out-Null }
}

# Runs the eval harness inside the api container, where the database and model server are.
function Invoke-Eval([string[]]$EvalArgs) {
    docker compose exec api python -m eval.runners.retrieval_eval @EvalArgs
}

$ModelsVenv = "backend/.venv-models"

switch ($Task) {
    "up" {
        Require-Env
        docker compose up -d --build
        Write-Host "`nStack is starting. Check it with: .\make.ps1 health" -ForegroundColor Cyan
        Write-Host "Frontend: http://localhost:3000   API docs: http://localhost:8000/docs" -ForegroundColor Cyan
        Write-Host "Models are not in the stack: start them with .\make.ps1 models (GPU, separate window)" -ForegroundColor Cyan
    }
    "down" { docker compose down }
    "restart" { docker compose restart }
    "build" { Require-Env; docker compose build }
    "logs" { docker compose logs -f --tail 100 @Rest }
    "ps" { docker compose ps }
    "health" {
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 15
            Write-Host "HTTP $($r.StatusCode)" -ForegroundColor Green
            $r.Content
        }
        catch {
            Write-Host "Health check failed: $_" -ForegroundColor Red
            docker compose logs api --tail 40
            exit 1
        }
    }
    "docs" {
        Start-Process "http://localhost:8000/docs"
        Write-Host "Opened Swagger UI at http://localhost:8000/docs" -ForegroundColor Cyan
    }
    "psql" { docker compose exec postgres psql -U memoryos -d memoryos }
    "valkey" { docker compose exec valkey valkey-cli }
    "migrate" { docker compose exec api alembic upgrade head }
    "test" { docker compose exec api pytest @Rest }
    "fmt" { docker compose exec api sh -c "ruff format . eval && ruff check --fix . eval" }
    "lint" { docker compose exec api sh -c "ruff check . eval && ruff format --check . eval" }

    "models" {
        # The embedding + reranking server, on the host GPU. Docker Desktop on Windows cannot
        # reach a laptop GPU reliably; the containers call this over host.docker.internal.
        if (-not (Test-Path "$ModelsVenv/Scripts/python.exe")) {
            Write-Host "First run: creating $ModelsVenv with CUDA PyTorch (~3 GB download)..." -ForegroundColor Yellow
            $env:UV_HTTP_TIMEOUT = "600"
            uv venv --python 3.12 $ModelsVenv
            uv pip install --python $ModelsVenv torch --index-url https://download.pytorch.org/whl/cu128
            uv pip install --python $ModelsVenv -r backend/requirements-models.txt
        }
        Write-Host "Model server on http://localhost:8001 (first start downloads ~2.5 GB of weights)" -ForegroundColor Cyan
        Push-Location backend
        try { & ".venv-models/Scripts/python.exe" -m uvicorn app.modelserver.main:app --host 0.0.0.0 --port 8001 }
        finally { Pop-Location }
    }

    "eval" { Invoke-Eval (@("--modes", "lexical,vector,hybrid,rerank") + $Rest) }
    "eval-personal" {
        if (-not (Test-Path "eval/golden/personal.yaml")) {
            Write-Host "Create eval/golden/personal.yaml first (copy personal.example.yaml)." -ForegroundColor Red
            exit 1
        }
        Invoke-Eval (@("--golden", "eval/golden/personal.yaml", "--no-index") + $Rest)
    }
    "eval-baseline" {
        # Regenerates the CI baseline exactly as CI computes it: hashing embedder, no reranker,
        # on a fresh throwaway database so no dev data can leak into the numbers.
        docker compose exec postgres psql -U memoryos -d postgres -qc "DROP DATABASE IF EXISTS memoryos_ci" -c "CREATE DATABASE memoryos_ci"
        docker compose exec -e DATABASE_URL=postgresql+asyncpg://memoryos:memoryos@postgres:5432/memoryos_ci `
            -e EMBEDDER=hash -e RERANKER=none api sh -c `
            "alembic upgrade head && python -m eval.runners.retrieval_eval --modes lexical,vector,hybrid --name baseline-ci"
        docker compose exec postgres psql -U memoryos -d postgres -qc "DROP DATABASE memoryos_ci"
    }
    "eval-graph" { docker compose exec api python -m eval.runners.graph_eval --out eval/reports @Rest }
    "eval-chat" { docker compose exec api python -m eval.runners.chat_eval @Rest }
    "extract" {
        if (-not $Rest) { Write-Host 'Usage: .\make.ps1 extract <source id>' -ForegroundColor Red; exit 1 }
        $r = Invoke-WebRequest -Method Post -Uri "http://localhost:8000/api/v1/sources/$($Rest[0])/extract" -UseBasicParsing
        $r.Content
    }
    "label" {
        if (-not $Rest) { Write-Host 'Usage: .\make.ps1 label "your query"' -ForegroundColor Red; exit 1 }
        docker compose exec api python -m eval.runners.label ($Rest -join " ")
    }

    "clean" {
        Write-Host "This deletes the Postgres and Valkey volumes. Everything indexed is lost." -ForegroundColor Yellow
        $answer = Read-Host "Type 'yes' to continue"
        if ($answer -eq "yes") { docker compose down -v } else { Write-Host "Cancelled." }
    }
    default {
        Write-Host "Usage: .\make.ps1 <task> [args]`n"
        Write-Host "  Stack"
        Write-Host "    up             build and start the stack (postgres, valkey, api, worker, frontend)"
        Write-Host "    models         start the embedding/rerank model server on the host GPU"
        Write-Host "    down           stop the stack (keeps data)"
        Write-Host "    restart        restart containers"
        Write-Host "    build          rebuild images"
        Write-Host "    logs [svc]     follow logs, e.g. .\make.ps1 logs worker"
        Write-Host "    ps             container status"
        Write-Host "    health         GET /health and print the result"
        Write-Host "    docs           open Swagger UI in the browser"
        Write-Host "  Data"
        Write-Host "    psql           open a psql shell"
        Write-Host "    valkey         open a valkey-cli shell"
        Write-Host "    migrate        apply database migrations"
        Write-Host "    clean          stop the stack AND delete all data volumes"
        Write-Host "  Quality"
        Write-Host "    test [args]    run the backend test suite"
        Write-Host "    lint / fmt     check / fix formatting with ruff"
        Write-Host "    eval           fixture benchmark, every search mode -> eval/reports/"
        Write-Host "    eval-personal  your benchmark (eval/golden/personal.yaml)"
        Write-Host "    eval-baseline  regenerate the CI baseline"
        Write-Host "    eval-graph     knowledge-graph precision/recall and chat routing"
        Write-Host "    eval-chat      end-to-end chat: abstention and citations (needs real models)"
        Write-Host "    extract <id>   LLM concept extraction over a source's notes and READMEs"
        Write-Host '    label "query"  candidates with ready-to-paste golden labels'
    }
}
