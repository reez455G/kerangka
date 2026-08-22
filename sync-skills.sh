#!/usr/bin/env bash
# sync-skills.sh — regenerates the local .omp/skills/ runtime tree (both
# PUBLIC and PRIVATE skills together — this directory is where OMP actually
# runs, program.md §18) from its two upstream sources:
#   1. ~/.omp/agent/managed-skills/* -> .omp/skills/  (manage_skill output)
#   2. knowledge/{skills,agent-rules}/*.md -> .omp/skills/ for embedded-class
#      sources only (sync-okf-skills.py; bare-class sources are never touched)
#   3. knowledge/**/*.md -> Hindsight bank (ingest-okf-to-hindsight.py), so
#      recall()/reflect() surface OKF content, not just the native skill
#      provider (program.md §12); best-effort, never blocks the rest.
#
# Ownership after program.md §18 (GitHub Skeleton + Fossil Canonical
# Migration): this script does NOT decide public vs private. It just keeps
# every locally-known skill present here so OMP works. Once regenerated:
#   - PRIVATE skills (see private-skills.txt) must be `fossil add`ed +
#     `fossil commit`ed here if new or changed — Fossil is their canonical
#     source now, not this directory by itself.
#   - PUBLIC skills belong in the separate my-ai-agents-public checkout
#     (GitHub-tracked); copy new/changed ones there via
#     build-public-skeleton.sh, then commit+push in that directory.
#
# This script only regenerates files on disk. It does NOT commit anywhere,
# and does NOT publish to R2 — that is ./publish-skills.sh's job (validation
# gate + rclone push). Run this after every manage_skill create/update, or
# after editing knowledge/, then classify+commit new content appropriately.
set -euo pipefail
cd "$(dirname "$0")"
SRC="$HOME/.omp/agent/managed-skills"
DEST=".omp/skills"
[ -d "$SRC" ] || { echo "Tidak ada managed-skills di $SRC"; exit 0; }
mkdir -p "$DEST"
MANIFEST="$DEST/.managed-skill-names"
: > "$MANIFEST.tmp"
for d in "$SRC"/*/; do
    name="$(basename "$d")"
    [ -f "$d/SKILL.md" ] || continue
    mkdir -p "$DEST/$name"
    cp "$d/SKILL.md" "$DEST/$name/SKILL.md"
    echo "$name" >> "$MANIFEST.tmp"
    echo "synced: $name"
done
sort -u "$MANIFEST.tmp" > "$MANIFEST" && rm -f "$MANIFEST.tmp"

echo "--- knowledge/ -> .omp/skills/ (embedded-class only) ---"
./.venv/bin/python sync-okf-skills.py || echo "WARN: sync-okf-skills.py gagal, lanjut tanpa embedded-class sync (agar manifest tetap ter-commit)"

echo "--- knowledge/ -> Hindsight (recall/reflect visibility, program.md §12) ---"
.venv/bin/python ingest-okf-to-hindsight.py || echo "WARN: OKF->Hindsight ingestion gagal (Hindsight down?), lanjut tanpa ini"
