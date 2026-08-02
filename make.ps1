<#
    Windows task runner for MemoryOS.

    There is no `make` on this machine, so this script is the everyday entry point.
    The Makefile alongside it holds the same tasks for CI and WSL.

    Usage:  .\make.ps1 <task>
    Tasks:  up | down | restart | build | logs | health | docs | ps | psql | valkey | test | fmt | clean
#>
param(
    [Parameter(Position = 0)]
    [string]$Task = "help"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Require-Env {
    if (-not (Test-Path ".env")) {
        Write-Host "No .env found — creating one from .env.example" -ForegroundColor Yellow
        Copy-Item ".env.example" ".env"
    }
}

switch ($Task) {
    "up" {
        Require-Env
        docker compose up -d --build
        Write-Host "`nStack is starting. Check it with: .\make.ps1 health" -ForegroundColor Cyan
    }
    "down" { docker compose down }
    "restart" { docker compose restart }
    "build" { Require-Env; docker compose build }
    "logs" { docker compose logs -f --tail 100 }
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
    "test" { docker compose exec api pytest }
    "fmt" { docker compose exec api sh -c "ruff format . && ruff check --fix ." }
    "clean" {
        Write-Host "This deletes the Postgres and Valkey volumes. Everything indexed is lost." -ForegroundColor Yellow
        $answer = Read-Host "Type 'yes' to continue"
        if ($answer -eq "yes") { docker compose down -v } else { Write-Host "Cancelled." }
    }
    default {
        Write-Host "Usage: .\make.ps1 <task>`n"
        Write-Host "  up       build and start the stack"
        Write-Host "  down     stop the stack (keeps data)"
        Write-Host "  restart  restart containers"
        Write-Host "  build    rebuild images"
        Write-Host "  logs     follow logs"
        Write-Host "  ps       container status"
        Write-Host "  health   GET /health and print the result"
        Write-Host "  docs     open Swagger UI in the browser"
        Write-Host "  psql     open a psql shell"
        Write-Host "  valkey   open a valkey-cli shell"
        Write-Host "  test     run the backend test suite"
        Write-Host "  fmt      format and autofix with ruff"
        Write-Host "  clean    stop the stack AND delete all data volumes"
    }
}
