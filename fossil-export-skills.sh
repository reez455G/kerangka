#!/usr/bin/env bash
# fossil-export-skills.sh — Fossil is the sole source of truth for ALL
# skills (public + private), per decision 2026-08-24 (see
# knowledge/control-plane.md in the Fossil checkout). This script is the
# ONLY sanctioned path from Fossil to both downstream artifacts:
#
#   kerangka-private (Fossil checkout, ~/kerangka-private)
#     │  ALL 145 skills live here now — public and private alike.
#     │  private-skills.txt is the EXCLUSION list: names listed there are
#     │  never mirrored to GitHub. Everything else Fossil-tracked with a
#     │  SKILL.md is an export candidate.
#     │
#     ├──► materialize ALL ──► .omp/skills/ (this repo, LOCAL RUNTIME COPY)
#     │                              │
#     │                              ▼
#     │                    ./publish-skills.sh ──► R2 (both tiers, as before)
#     │
#     └──► materialize PUBLIC SUBSET ──► .omp/skills/ (same dir, git-tracked
#                                          subset only) ──► git add/commit
#                                          ──► (you) git push ──► GitHub
#
# GitHub's .omp/skills/ is now a GENERATED MIRROR. Never hand-edit a skill
# directly in the kerangka git working tree and expect it to persist — the
# next run of this script overwrites it from Fossil. Edit in Fossil, then
# re-run this script.
#
# This script does NOT push to GitHub automatically (explicit-write-path
# principle, same reasoning as R2 publish requiring PUBLISH_ALLOWED=1) — it
# stages and commits locally, then tells you to `git push` yourself.
set -euo pipefail
cd "$(dirname "$0")"

FOSSIL_CHECKOUT="${FOSSIL_CHECKOUT:-$HOME/kerangka-private}"
PRIVATE_LIST="$FOSSIL_CHECKOUT/private-skills.txt"
DEST=".omp/skills"

log()  { printf "\033[1;36m[fossil-export]\033[0m %s\n" "$1"; }
err()  { printf "\033[1;31m[fossil-export]\033[0m %s\n" "$1" >&2; }

if [ ! -d "$FOSSIL_CHECKOUT" ]; then
    err "Fossil checkout not found at $FOSSIL_CHECKOUT — set FOSSIL_CHECKOUT or open it first"
    exit 1
fi
if [ ! -f "$PRIVATE_LIST" ]; then
    err "private-skills.txt not found at $PRIVATE_LIST"
    exit 1
fi

mkdir -p "$DEST"

# ── 1. Materialize ALL Fossil-tracked skills into .omp/skills/ ────────────────
log "Materializing all Fossil-tracked skills -> $DEST ..."
total=0
for d in "$FOSSIL_CHECKOUT"/*/; do
    name="$(basename "$d")"
    [ -f "$d/SKILL.md" ] || continue
    mkdir -p "$DEST/$name"
    cp "$d/SKILL.md" "$DEST/$name/SKILL.md"
    total=$((total + 1))
done
log "Materialized $total skills (public + private union) from Fossil."

# ── 2. Determine public subset (Fossil-tracked, NOT in private-skills.txt) ────
mapfile -t PUBLIC_NAMES < <(
    for d in "$FOSSIL_CHECKOUT"/*/; do
        name="$(basename "$d")"
        [ -f "$d/SKILL.md" ] || continue
        grep -qxF "$name" "$PRIVATE_LIST" || echo "$name"
    done
)
log "Public export candidates: ${#PUBLIC_NAMES[@]} skills."

# ── 3. Stage + commit ONLY the public subset to git (GitHub mirror) ───────────
if [ "${1:-}" = "--no-git" ]; then
    log "--no-git passed: skipping git add/commit (materialization only)."
    exit 0
fi

CHANGED=0
for name in "${PUBLIC_NAMES[@]}"; do
    git add "$DEST/$name/SKILL.md" 2>/dev/null || true
done

if git diff --cached --quiet -- "$DEST"; then
    log "No public skill changes to commit — GitHub mirror already up to date."
    exit 0
fi

CHANGED_COUNT="$(git diff --cached --name-only -- "$DEST" | wc -l)"
git commit -q -m "chore: sync public skills from Fossil (fossil-export-skills.sh, ${CHANGED_COUNT} file(s) changed)"
log "Committed $CHANGED_COUNT changed file(s) to git. Run 'git push origin main' to update GitHub."
