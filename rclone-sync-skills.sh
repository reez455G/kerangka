#!/usr/bin/env bash
# rclone-sync-skills.sh — transport layer between the local .omp/skills/
# runtime tree and its R2 distribution mirror (program.md §18, supersedes §17).
#
# Authority model (program.md §18 / ARCHITECTURE.md "Skill Source of Truth"):
#   Fossil (this checkout)               = canonical for PRIVATE skills
#   my-ai-agents-public (GitHub, separate directory) = canonical for PUBLIC skills
#   R2  (<your-bucket>/.../omp-skills/, path from R2_SKILLS_REMOTE_PATH) = distribution/replication layer only,
#                                          receives BOTH tiers (R2 is private
#                                          infra, not a public surface)
#   local .omp/skills/ on OTHER devices  = disposable runtime copy
#
# This script is a dumb transport with two one-way modes — it has no opinion
# about which side is "right", authority is enforced by WHO is allowed to
# call which mode:
#
#   pull  — R2 -> local .omp/skills/. Safe for any device, any time. This is
#           what the `omp` shell wrapper runs on every session start to keep
#           runtime copies current. NEVER deletes local files it can't
#           explain (plain `rclone copy --update`, mtime-gated).
#   push  — local .omp/skills/ -> R2. This is NOT a general-purpose command.
#           It must only run as the last step of ./publish-skills.sh, AFTER
#           validate_skills.py has passed against the local runtime tree.
#           Guarded by PUBLISH_ALLOWED=1 so an unvalidated
#           `./rclone-sync-skills.sh push` run by habit fails loudly instead
#           of silently overwriting the distribution layer with unvalidated
#           content.
#
# `both` mode (pre-§17 Syncthing-replacement era) is REMOVED: treating
# push/pull as symmetric implied every device could equally publish, which
# is exactly the ambiguity §17/§18 eliminate. Devices only ever pull.
#
# Design note carried over from §16 (still applies): two one-way
# `rclone copy --update` passes, NOT `rclone bisync`. R2's S3 compatibility
# layer returns a transient "501 NotImplemented" on the first upload attempt
# of every object (known R2 quirk, not a data-integrity issue — the object is
# written correctly and rclone's built-in retry succeeds on attempt 2).
# `rclone copy` treats this as a normal retryable error and continues;
# `rclone bisync` treats it as fatal and aborts the whole sync.
#
# Config: ~/.config/rclone/rclone.conf, remote name "r2-my-ai-agents"
# (installed by setup-new-device.sh from R2_SKILLS_ACCESS_KEY_ID /
# R2_SKILLS_SECRET_ACCESS_KEY in .env — see .env.example).
set -uo pipefail   # NOT -e: rclone's own retry may print to stderr on a
                    # transient 501 yet still exit 0 — do not abort on that.
cd "$(dirname "$0")"
[ -f .env ] && set -a && source .env && set +a

REMOTE="r2-my-ai-agents:${R2_SKILLS_REMOTE_PATH:?R2_SKILLS_REMOTE_PATH belum diset di .env — lihat .env.example}"
LOCAL=".omp/skills"
RCLONE_CONF="$HOME/.config/rclone/rclone.conf"
MODE="${1:-pull}"   # pull | push

if [ "$MODE" != "pull" ] && [ "$MODE" != "push" ]; then
    echo "[rclone-sync] mode tidak dikenal: '$MODE' (hanya 'pull' atau 'push'; 'both' sudah dihapus — lihat program.md §18)" >&2
    exit 2
fi

if [ "$MODE" = "push" ] && [ "${PUBLISH_ALLOWED:-0}" != "1" ]; then
    echo "[rclone-sync] push ditolak: jangan panggil langsung. Jalankan ./publish-skills.sh" >&2
    echo "[rclone-sync] (push = canonical (Fossil/GitHub) -> R2, hanya boleh terjadi setelah validate_skills.py lolos)" >&2
    exit 3
fi

if ! command -v rclone >/dev/null 2>&1; then
    echo "[rclone-sync] rclone tidak terpasang — jalankan setup-new-device.sh dulu" >&2
    exit 0
fi

if [ ! -f "$RCLONE_CONF" ] || ! grep -q "^\[r2-my-ai-agents\]" "$RCLONE_CONF" 2>/dev/null; then
    echo "[rclone-sync] remote r2-my-ai-agents belum dikonfigurasi di $RCLONE_CONF — jalankan setup-new-device.sh" >&2
    exit 0
fi

mkdir -p "$LOCAL"

# Bounded retry/timeout: a genuinely unreachable R2 (DNS failure, network down)
# must not hang `omp` startup for minutes via rclone's own unbounded
# exponential backoff (observed empirically: default retry settings can
# exceed 90s on DNS failure alone). --retries/--low-level-retries stay >1 to
# still tolerate the transient R2 501 quirk (succeeds on attempt 2); the
# connect/overall timeouts cap worst-case wall time to well under a minute.
RCLONE_OPTS=(--update --config "$RCLONE_CONF" -q --retries 2 --low-level-retries 2 --contimeout 5s --timeout 15s)

if [ "$MODE" = "pull" ]; then
    if ! rclone copy "$REMOTE" "$LOCAL" "${RCLONE_OPTS[@]}"; then
        echo "[rclone-sync] pull gagal (R2 tidak terjangkau?) — skill lokal existing DIPERTAHANKAN, tidak dihapus" >&2
    fi
    exit 0
fi

# push (only reachable with PUBLISH_ALLOWED=1, i.e. via publish-skills.sh).
# Uses `rclone sync` (not `copy`): local .omp/skills/ has just passed
# validate_skills.py as a complete canonical snapshot, so this must be a
# true mirror — objects retired/deleted locally must also disappear from
# R2, or every device's `pull` resurrects them forever (found in practice:
# a skill deleted from .omp/skills/ came back after the next `omp` pull
# because a prior `rclone copy` push never removes anything on the remote
# side). `pull` above stays `copy --update` on purpose — it must never
# delete a device's local skills it can't explain.
if ! rclone sync "$LOCAL" "$REMOTE" "${RCLONE_OPTS[@]}" --exclude ".managed-skill-names"; then
    echo "[rclone-sync] push GAGAL — R2 TIDAK diperbarui, publish-skills.sh harus melaporkan exit non-zero" >&2
    exit 1
fi
exit 0
