#!/usr/bin/env bash
# publish-skills.sh — the ONLY sanctioned path from canonical sources to R2.
#
# Fossil is the SOLE source of truth for ALL skills (public + private), per
# decision 2026-08-24 (knowledge/control-plane.md, Fossil checkout). GitHub's
# .omp/skills/ is a generated mirror of the public subset — never edited by
# hand. See fossil-export-skills.sh for the Fossil -> .omp/skills/ -> GitHub
# mirror path; this script handles Fossil -> .omp/skills/ -> R2 instead.
#
#   Fossil (kerangka-private, ALL 145 skills)
#          │
#          ▼ fossil-export-skills.sh --no-git (materialize only, no git commit)
#          ▼
#   .omp/skills/ (local, this directory — LOCAL RUNTIME COPY, not canonical)
#          │
#          ▼ sync-skills.sh (bridge: managed-skills/ not yet in Fossil +
#          │  knowledge/ embedded-class docs — supplementary, not primary)
#          ▼
#   validate_skills.py   ── FAIL ──► stop, R2 untouched, exit 1
#          │ PASS
#          ▼
#   write .omp/skills/MANIFEST.json (fossil revision + skill list)
#          │
#          ▼
#   rclone push (PUBLISH_ALLOWED=1 ./rclone-sync-skills.sh push)
#          │
#          ▼
#   R2: <your-bucket>/<your-project>/omp-skills/ (private infra — receives
#   BOTH public and private skills; R2 is distribution only, not a public
#   surface)
#
# This does NOT commit to Fossil, and does NOT push to GitHub — those are
# separate, explicit acts (fossil commit for skill edits; fossil-export-
# skills.sh + git push for the GitHub mirror). Publishing to R2 only
# requires that whatever is currently sitting in .omp/skills/ passes
# validation.
set -uo pipefail
cd "$(dirname "$0")"

fail() { echo "[publish-skills] FAIL: $*" >&2; exit 1; }

SKILLS_DIR=".omp/skills"

# 1. Materialize .omp/skills/ from Fossil (primary, authoritative for ALL
#    skills), then bridge in anything from managed-skills/ + knowledge/
#    embedded-class not yet committed to Fossil.
echo "[publish-skills] Materializing $SKILLS_DIR dari Fossil (sumber utama) ..."
./fossil-export-skills.sh --no-git || fail "fossil-export-skills.sh gagal — perbaiki sebelum publish"
echo "[publish-skills] Bridging managed-skills/ + knowledge/ embedded-class (skill baru belum di-commit ke Fossil) ..."
./sync-skills.sh || fail "sync-skills.sh gagal — perbaiki sebelum publish"

# 2. Validate every skill in the local runtime tree (both public and private
#    together). This is the mandatory publish gate — no bypass flag exists
#    on purpose.
echo "[publish-skills] Validasi $SKILLS_DIR ..."
if ! .venv/bin/python src/validate_skills.py "$SKILLS_DIR"; then
    fail "validasi skill gagal — R2 TIDAK diubah. Perbaiki isi $SKILLS_DIR lalu ulangi."
fi

# 3. Manifest: record both canonical sources' state so R2 content is
#    traceable back to exactly what produced it (troubleshooting aid only —
#    never the source of truth itself, never holds secrets).
FOSSIL_CHECKOUT="${FOSSIL_CHECKOUT:-$HOME/kerangka-private}"
FOSSIL_REV="unknown"
FOSSIL_DIRTY=""
if command -v fossil >/dev/null 2>&1 && fossil info --repository "$FOSSIL_CHECKOUT" >/dev/null 2>&1; then
    FOSSIL_REV="$(cd "$FOSSIL_CHECKOUT" && fossil info | awk '/^checkout:/{print $2}')"
    (cd "$FOSSIL_CHECKOUT" && fossil changes 2>/dev/null | grep -q .) && FOSSIL_DIRTY=" (uncommitted skill changes present)"
fi
PUBLIC_REPO_REV="not-configured"
if [ -n "${PUBLIC_SKELETON_DIR:-}" ] && git -C "$PUBLIC_SKELETON_DIR" rev-parse HEAD >/dev/null 2>&1; then
    PUBLIC_REPO_REV="$(git -C "$PUBLIC_SKELETON_DIR" rev-parse HEAD)"
fi
PUBLISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
SKILL_NAMES="$(find "$SKILLS_DIR" -mindepth 1 -maxdepth 1 -type d -printf '"%f",' | sed 's/,$//')"
SKILL_COUNT="$(find "$SKILLS_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)"
cat > "$SKILLS_DIR/MANIFEST.json" <<EOF
{
  "source_vcs": "fossil+github",
  "repository": "my-ai-agents",
  "fossil_revision": "${FOSSIL_REV}${FOSSIL_DIRTY}",
  "public_repo_revision": "${PUBLIC_REPO_REV}",
  "published_at": "${PUBLISHED_AT}",
  "skill_count": ${SKILL_COUNT},
  "skills": [${SKILL_NAMES}]
}
EOF
echo "[publish-skills] Manifest ditulis: fossil_revision=${FOSSIL_REV}${FOSSIL_DIRTY}, skill_count=${SKILL_COUNT}"

# 4. Publish: local .omp/skills/ -> R2. Only this script may set
#    PUBLISH_ALLOWED=1; rclone-sync-skills.sh refuses push otherwise.
echo "[publish-skills] Push ke R2 (path dari R2_SKILLS_REMOTE_PATH) ..."
if ! PUBLISH_ALLOWED=1 ./rclone-sync-skills.sh push; then
    fail "rclone push gagal — R2 mungkin sebagian/tidak diperbarui, cek konektivitas/kredensial"
fi

echo "[publish-skills] OK: ${SKILL_COUNT} skill dipublish (fossil_revision=${FOSSIL_REV}${FOSSIL_DIRTY}) ke R2."
