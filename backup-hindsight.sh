#!/usr/bin/env bash
# backup-hindsight.sh — hot backup of Hindsight embedded Postgres to R2.
#
# Architecture (directive §19-21):
#   Hindsight container (pg 18.1.0, socket /tmp/.s.PGSQL.5432)
#     ↓  pg_dump (plain SQL, no stop required — hot consistent snapshot)
#   /tmp/hindsight-YYYYMMDD-HHMMSS.sql.gz
#     ↓  rclone copy → R2:efsatu-storage/my-ai-agents/hindsight-backups/
#   Cleanup: keep last N local copies
#
# Restore procedure:
#   1. docker stop hindsight
#   2. docker exec hindsight psql -U hindsight -d postgres -c "DROP DATABASE hindsight;"
#   3. docker exec hindsight psql -U hindsight -d postgres -c "CREATE DATABASE hindsight;"
#   4. gunzip -c <backup>.sql.gz | docker exec -i hindsight \
#        /home/hindsight/.pg0/installation/18.1.0/bin/psql \
#        -U hindsight -d hindsight -p 5432
#   5. docker start hindsight
#
# This is SEPARATE from skill publishing (directive §21):
#   Skill backup:  Fossil → R2:efsatu-storage/my-ai-agents/omp-skills/
#   Memory backup: Hindsight → R2:efsatu-storage/my-ai-agents/hindsight-backups/
#
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && source .env && set +a

CONTAINER="hindsight"
RCLONE_CONF="$HOME/.config/rclone/rclone.conf"
REMOTE_PREFIX="${R2_HINDSIGHT_REMOTE_PATH:-efsatu-storage/my-ai-agents/hindsight-backups}"
LOCAL_BACKUP_DIR="${HINDSIGHT_BACKUP_DIR:-/tmp/hindsight-backups}"
KEEP_LOCAL=3           # keep last 3 local compressed dumps
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
DUMP_FILE="$LOCAL_BACKUP_DIR/hindsight-${TIMESTAMP}.sql.gz"

log()  { printf "\033[1;36m[backup-hindsight]\033[0m %s\n" "$1"; }
err()  { printf "\033[1;31m[backup-hindsight]\033[0m %s\n" "$1" >&2; }

# ── 1. Pre-flight ──────────────────────────────────────────────────────────────
if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
    err "Container '$CONTAINER' not found. Is Hindsight running?"
    exit 1
fi

if ! command -v rclone >/dev/null 2>&1; then
    err "rclone not installed — cannot upload to R2"
    exit 1
fi

if [ ! -f "$RCLONE_CONF" ] || ! grep -q "^\[r2-my-ai-agents\]" "$RCLONE_CONF" 2>/dev/null; then
    err "rclone remote r2-my-ai-agents not configured — run setup-new-device.sh"
    exit 1
fi

mkdir -p "$LOCAL_BACKUP_DIR"

# ── 2. Hot pg_dump via PGPASSWORD ──────────────────────────────────────────────
log "Starting hot pg_dump of Hindsight (container: $CONTAINER)..."
if ! docker exec -e PGPASSWORD=hindsight "$CONTAINER" \
        /home/hindsight/.pg0/installation/18.1.0/bin/pg_dump \
        -U hindsight -d hindsight -p 5432 --format=plain \
        2>/dev/null | gzip > "$DUMP_FILE"; then
    err "pg_dump failed — backup NOT created"
    rm -f "$DUMP_FILE"
    exit 1
fi

DUMP_SIZE="$(du -sh "$DUMP_FILE" | cut -f1)"
log "Dump complete: $DUMP_FILE ($DUMP_SIZE)"

# ── 3. Upload to R2 ────────────────────────────────────────────────────────────
RCLONE_OPTS=(--config "$RCLONE_CONF" -q --retries 3 --low-level-retries 3 --contimeout 10s --timeout 60s)
log "Uploading to R2: r2-my-ai-agents:${REMOTE_PREFIX}/"
if ! rclone copy "$DUMP_FILE" "r2-my-ai-agents:${REMOTE_PREFIX}/" "${RCLONE_OPTS[@]}"; then
    err "R2 upload failed — local backup retained at $DUMP_FILE"
    exit 1
fi
log "Upload OK: $(basename "$DUMP_FILE") → R2:${REMOTE_PREFIX}/"

# ── 4. Prune old local backups ─────────────────────────────────────────────────
KEPT=$(ls -t "$LOCAL_BACKUP_DIR"/hindsight-*.sql.gz 2>/dev/null | wc -l)
if [ "$KEPT" -gt "$KEEP_LOCAL" ]; then
    ls -t "$LOCAL_BACKUP_DIR"/hindsight-*.sql.gz | tail -n +"$((KEEP_LOCAL+1))" | xargs rm -f
    log "Pruned old local backups (kept $KEEP_LOCAL)"
fi

# ── 5. Verify R2 listing ───────────────────────────────────────────────────────
log "R2 backup listing (recent 5):"
rclone ls "r2-my-ai-agents:${REMOTE_PREFIX}/" "${RCLONE_OPTS[@]}" 2>/dev/null | sort -k2 | tail -5

log "Backup complete. Restore procedure documented in script header."
