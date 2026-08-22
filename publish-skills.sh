#!/usr/bin/env bash
# publish-skills.sh — the ONLY sanctioned path from canonical sources to R2.
# program.md §18 (GitHub Skeleton + Fossil Canonical Migration; supersedes §17).
#
# Two canonical sources feed the SAME local .omp/skills/ runtime tree in
# THIS directory (both are needed locally for OMP to work day-to-day):
#
#   Fossil (this checkout)      = canonical for PRIVATE skills/knowledge
#   my-ai-agents-public (GitHub)= canonical for PUBLIC skills/docs/scripts
#          │                             │
#          └──────────────┬──────────────┘
#                          ▼
#              .omp/skills/ (local, this directory — union of both)
#                          │
#                          ▼
#              validate_skills.py   ── FAIL ──► stop, R2 untouched, exit 1
#                          │ PASS
#                          ▼
#              write .omp/skills/MANIFEST.json (fossil revision + skill list)
#                          │
#                          ▼
#              rclone push (PUBLISH_ALLOWED=1 ./rclone-sync-skills.sh push)
#                          │
#                          ▼
#              R2: <your-bucket>/<your-project>/omp-skills/ (private infra —
#              receives BOTH public and private skills; R2 is distribution
#              only, not a public surface, directive §22)
#
# This does NOT commit to Fossil or push/commit to the public GitHub repo —
# those are separate, explicit, manual acts (directive §14: an agent
# modifying a private skill must `fossil commit` itself; §11 for GitHub).
# Publishing to R2 only requires that whatever is currently sitting in
# .omp/skills/ passes validation — it does not require every file to be
# already committed anywhere, though uncommitted PRIVATE changes are flagged
# in the manifest via the fossil dirty-check below.
set -uo pipefail
cd "$(dirname "$0")"

fail() { echo "[publish-skills] FAIL: $*" >&2; exit 1; }

SKILLS_DIR=".omp/skills"

# 1. Regenerate .omp/skills/ from managed-skills/ + knowledge/ embedded-class
#    so publish always reflects the latest of both, not a stale snapshot.
echo "[publish-skills] Regenerasi $SKILLS_DIR dari managed-skills/ + knowledge/ ..."
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
FOSSIL_REV="unknown"
FOSSIL_DIRTY=""
if command -v fossil >/dev/null 2>&1 && fossil info >/dev/null 2>&1; then
    FOSSIL_REV="$(fossil info | awk '/^checkout:/{print $2}')"
    fossil changes 2>/dev/null | grep -q . && FOSSIL_DIRTY=" (uncommitted private changes present)"
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
