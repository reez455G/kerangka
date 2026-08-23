#!/usr/bin/env bash
# rclone-sync-private.sh — transport layer between the local ~/private-backup/
# directory and its R2 mirror. SEPARATE from rclone-sync-skills.sh: different
# local source, different R2 prefix, different purpose.
#
#   Local:  ~/private-backup/           (secrets, Fossil DBs, archive bundles —
#                                         anything that must never live inside
#                                         a git-tracked/deletable project dir)
#   Remote: r2-my-ai-agents:${R2_PRIVATE_REMOTE_PATH}
#           (bucket "efsatu-storage", prefix "my-ai-agents/private-backup/" —
#            distinct from "my-ai-agents/omp-skills/" used for skill sync)
#
# Unlike skill sync, this is single-device-authoritative (this machine owns
# ~/private-backup/); there is no multi-device publish/validate gate. Both
# modes use `rclone sync` (true mirror, deletions propagate) since this
# directory has exactly one writer.
#
# Rationale (2026-08-23 incident): a Fossil repo DB and its working checkout
# were both deleted by `rm -rf` because the DB file lived inside a directory
# that also got deleted. Never again — private backups live outside any
# directory a project-level `rm -rf` could reach, AND get mirrored to R2 so
# local deletion alone can't cause permanent loss.
#
# Config: ~/.config/rclone/rclone.conf, remote name "r2-my-ai-agents"
# (same account-wide R2 credential used by rclone-sync-skills.sh).
set -uo pipefail   # NOT -e: rclone's own retry may print to stderr on R2's
                    # transient 501 quirk yet still exit 0 — do not abort on that.
cd "$(dirname "$0")"
[ -f .env ] && set -a && source .env && set +a

REMOTE="r2-my-ai-agents:${R2_PRIVATE_REMOTE_PATH:?R2_PRIVATE_REMOTE_PATH belum diset di .env — lihat .env.example}"
LOCAL="$HOME/private-backup"
RCLONE_CONF="$HOME/.config/rclone/rclone.conf"
MODE="${1:-}"   # pull | push, no default — must be explicit

if [ "$MODE" != "pull" ] && [ "$MODE" != "push" ]; then
    echo "[rclone-sync-private] usage: $0 pull|push (tidak ada default — harus eksplisit)" >&2
    exit 2
fi

if ! command -v rclone >/dev/null 2>&1; then
    echo "[rclone-sync-private] rclone tidak terpasang — jalankan setup-new-device.sh dulu" >&2
    exit 1
fi

if [ ! -f "$RCLONE_CONF" ] || ! grep -q "^\[r2-my-ai-agents\]" "$RCLONE_CONF" 2>/dev/null; then
    echo "[rclone-sync-private] remote r2-my-ai-agents belum dikonfigurasi di $RCLONE_CONF — jalankan setup-new-device.sh" >&2
    exit 1
fi

mkdir -p "$LOCAL" && chmod 700 "$LOCAL"

RCLONE_OPTS=(--config "$RCLONE_CONF" -q --retries 3 --low-level-retries 3 --contimeout 10s --timeout 30s)

if [ "$MODE" = "pull" ]; then
    if ! rclone sync "$REMOTE" "$LOCAL" "${RCLONE_OPTS[@]}"; then
        echo "[rclone-sync-private] pull GAGAL (R2 tidak terjangkau?)" >&2
        exit 1
    fi
    chmod -R go-rwx "$LOCAL"
    echo "[rclone-sync-private] pull OK: R2 -> $LOCAL"
    exit 0
fi

# push
if ! rclone sync "$LOCAL" "$REMOTE" "${RCLONE_OPTS[@]}"; then
    echo "[rclone-sync-private] push GAGAL — R2 TIDAK diperbarui" >&2
    exit 1
fi
echo "[rclone-sync-private] push OK: $LOCAL -> R2"
