#!/bin/sh
# Nightly logical backup of the MemoryOS database, KEEP_DAYS days kept.
#
#   backup.sh            one backup now (docker compose ... run --rm backup backup.sh)
#   backup.sh --loop     the `backup` service: one now, then one every 24 hours
#
# Restore into an empty database:
#   docker compose ... exec -T postgres pg_restore -U memoryos -d memoryos --clean --if-exists \
#     < backups/memoryos-<date>.dump
# The index can always be rebuilt from the sources; the backup is for what cannot: your
# idea overrides, conversations and feedback.
set -eu

KEEP_DAYS="${KEEP_DAYS:-14}"
DIR=/backups

backup() {
    stamp=$(date -u +%Y-%m-%dT%H%M%SZ)
    target="$DIR/memoryos-$stamp.dump"
    pg_dump --format=custom --no-owner --file="$target.partial"
    mv "$target.partial" "$target"
    echo "backup: wrote $target ($(du -h "$target" | cut -f1))"
    find "$DIR" -name 'memoryos-*.dump' -mtime +"$KEEP_DAYS" -print -delete
}

if [ "${1:-}" = "--loop" ]; then
    while true; do
        if backup; then
            sleep 86400
        else
            echo "backup: failed, retrying in an hour" >&2
            sleep 3600
        fi
    done
else
    backup
fi
