# Docker notes

## Multi-stage builds

Build in a fat image, copy only the artefact into a slim one. For Python, install
dependencies in their own layer *before* copying the source, so editing code does not
reinstall everything.

## Healthchecks and depends_on

`depends_on` alone only waits for the container to *start*. To wait until Postgres accepts
connections, give it a healthcheck (`pg_isready`) and use `condition: service_healthy`.

## Cleaning up

`docker system prune -a --volumes` frees everything unused, including named volumes. Careful:
that includes your local database.
