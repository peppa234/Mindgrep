#!/usr/bin/env bash
# Deploy (or update) MemoryOS on the VPS, from the repository checkout there:
#
#   ./infra/deploy.sh            pull main, rebuild, restart, wait until healthy
#   ./infra/deploy.sh <ref>      deploy a tag or commit instead
#
# The GitHub Actions deploy workflow runs this over SSH. Migrations run on api start.
set -euo pipefail

cd "$(dirname "$0")/.."
REF="${1:-main}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

if [ ! -f .env ]; then
    echo "deploy: no .env here; copy .env.example and fill in DOMAIN and BASIC_AUTH_*" >&2
    exit 1
fi
if grep -Eq '^POSTGRES_PASSWORD=(memoryos)?[[:space:]]*$' .env; then
    echo "deploy: POSTGRES_PASSWORD is empty or the dev default; set a long random one in .env" >&2
    exit 1
fi

git fetch --quiet --tags origin
git checkout --quiet "$REF"
if git symbolic-ref -q HEAD >/dev/null; then
    git pull --quiet --ff-only origin "$REF"
fi
echo "deploy: $(git log -1 --format='%h %s')"

"${COMPOSE[@]}" build --pull
"${COMPOSE[@]}" up -d --remove-orphans

# Healthy means the API answers and Postgres has its extensions: /health checks both.
for _ in $(seq 1 60); do
    if "${COMPOSE[@]}" exec -T api python -c \
        "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=5).status == 200 else 1)" \
        2>/dev/null; then
        echo "deploy: healthy"
        docker image prune -f >/dev/null
        exit 0
    fi
    sleep 2
done
echo "deploy: the api did not become healthy in 2 minutes" >&2
"${COMPOSE[@]}" logs --tail 60 api >&2
exit 1
