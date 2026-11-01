# Deploying Mindgrep

One small VPS, one compose file pair, Caddy in front. No Kubernetes, no managed services:
for one user's notes and repositories this is the whole production system.

## What runs

| Service | What it does | Reachable from |
|---|---|---|
| caddy | TLS (Let's Encrypt), basic auth, reverse proxy to the frontend | the internet: 80, 443 |
| frontend | Next.js; proxies `/api/*` to the API | the compose network |
| api | FastAPI, runs migrations on start | the compose network |
| worker | ARQ: indexing, embedding, extraction, idea matching | the compose network |
| postgres | pgvector + pg_trgm; everything lives here | the compose network |
| valkey | job queue and embedding cache | the compose network |
| backup | `pg_dump` every 24 h into the `backups` volume, 14 days kept | none |
| models (optional) | the CPU model server | the compose network |

Mindgrep is single-user. Everything except `/health/live` (a bare `{"status":"ok"}` for an
uptime monitor) sits behind basic auth, so the index is never public. Writes from other
websites are refused (`Sec-Fetch-Site`), since the browser would otherwise attach your
basic-auth credentials to them. (Multi-user accounts with row-level security are deliberately
out of scope for V1; see the architecture plan's cut list.)

## First deploy

On a fresh Ubuntu VPS (2 vCPU / 4 GB is enough without the CPU model server):

```bash
# Docker Engine + compose plugin: https://docs.docker.com/engine/install/ubuntu/
git clone https://github.com/peppa234/mindgrep && cd mindgrep
cp .env.example .env
```

In `.env`:

```bash
DOMAIN=memory.example.com          # an A record pointing at this machine
BASIC_AUTH_USER=you
BASIC_AUTH_HASH='$2a$14$...'       # docker run --rm caddy:2-alpine caddy hash-password
POSTGRES_PASSWORD=<something long> # the dev default is not a password
SOURCES_DIR=/srv/brain             # what gets indexed (read-only mount)
GEMINI_API_KEY=...                 # optional: written answers
```

Then:

```bash
./infra/deploy.sh
```

It builds the images, starts everything, and waits for `/health`. Open `https://$DOMAIN`, sign
in, add sources on the Sources page.

## Models on a machine without a GPU

Pick one:

1. **Lexical only**: `EMBEDDER=none RERANKER=none`. Search, graph answers and idea matching
   by coverage all still work; paraphrase search and the reranker's similarity do not.
2. **CPU model server here**: `docker compose -f docker-compose.yml -f docker-compose.prod.yml
   --profile models up -d` and `MODEL_SERVER_URL=http://models:8001`. Needs ~4 GB of RAM more
   and indexes slowly, but embeddings are cached, so only the first index is slow.
3. **Your GPU at home**: run `.\make.ps1 models` on the desktop, join both machines to a
   private network (Tailscale is the least work), and set `MODEL_SERVER_URL` to the desktop's
   private address. Never expose the model server on a public interface.

## Updates

From the Actions tab: **Deploy → Run workflow** (any branch, tag or commit). It needs the
repository secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` and `DEPLOY_KNOWN_HOSTS`
(the output of `ssh-keyscan -H <host>`, run once from a machine you trust; the workflow
refuses any other host key), and optionally the variable `DEPLOY_PATH` (default
`~/mindgrep`). It runs `infra/deploy.sh <ref>` over SSH.
Or on the server: `./infra/deploy.sh v0.4.0`.

## Backups and restore

`backups/mindgrep-<timestamp>.dump` in the `backups` volume, one a day. Copy them off the
machine (`docker cp`, restic, rclone): a backup on the same disk is not a backup.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  pg_restore -U mindgrep -d mindgrep --clean --if-exists < mindgrep-<timestamp>.dump
```

The index itself can always be rebuilt by re-indexing the sources. What a backup protects is
what cannot be rebuilt: idea overrides, conversations, and answer feedback.
