#!/usr/bin/env bash
# import-learned-skills.sh — copy .omp/skills/* into ~/.omp/agent/managed-skills/
# so previously-learned (manage_skill) skills are also available globally
# (any cwd/repo), since the `omp-managed` provider scans managed-skills/
# unconditionally (program.md §11.4).
#
# Scope: ONLY names listed in .omp/skills/.managed-skill-names (written by
# sync-skills.sh from the managed-skills export direction). The other ~34
# entries in .omp/skills/ are repo/domain-specific knowledge migrated from
# knowledge/ (program.md §10/§11) — importing those globally would leak
# project-specific skill descriptions into every unrelated omp session on
# this device, so they are deliberately left native-provider-scoped
# (.omp/skills/ only loads when cwd is inside this repo).
#
# Policy: only fill genuine gaps. A missing local entry is imported. A local
# entry whose content differs from the repo copy is NEVER auto-overwritten —
# mtime is not a reliable "which is newer" signal here (git checkout resets
# mtimes to checkout time, not commit time), so any content divergence is
# reported for manual review instead of guessed at.
#
# Called by: setup-new-device.sh (initial import) and githooks/post-merge +
# githooks/post-checkout (keep-in-sync on every `git pull`).
set -euo pipefail
cd "$(dirname "$0")"
SRC=".omp/skills"
DEST="$HOME/.omp/agent/managed-skills"
MANIFEST="$SRC/.managed-skill-names"
[ -d "$SRC" ] || { echo "Tidak ada $SRC di repo ini"; exit 0; }
[ -f "$MANIFEST" ] || { echo "Tidak ada $MANIFEST — belum pernah sync-skills.sh dijalankan, tidak ada yang diimpor."; exit 0; }
mkdir -p "$DEST"

imported=0
diverged=0
while IFS= read -r name; do
    [ -n "$name" ] || continue
    src_file="$SRC/$name/SKILL.md"
    [ -f "$src_file" ] || continue
    dest_file="$DEST/$name/SKILL.md"
    if [ ! -f "$dest_file" ]; then
        mkdir -p "$DEST/$name"
        cp "$src_file" "$dest_file"
        echo "imported: $name (baru)"
        imported=$((imported + 1))
    elif ! cmp -s "$src_file" "$dest_file"; then
        echo "diverged: $name (isi lokal beda dari repo — dibiarkan, cek manual jika perlu selaraskan)"
        diverged=$((diverged + 1))
    fi
done < "$MANIFEST"
echo "Selesai. Imported: $imported, diverged (dibiarkan): $diverged"
