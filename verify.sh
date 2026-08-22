#!/bin/bash
set -e
cd "$(dirname "$0")"

[ -f .env ] || { echo "❌ .env tidak ada — copy .env.example dan isi dulu"; exit 1; }
set -a; source .env; set +a
URL="${HINDSIGHT_API_URL:-http://localhost:8890}"
BANK="$HINDSIGHT_BANK_ID"

echo "=== 1. Hindsight Runtime ==="
case "$URL" in
  *localhost*|*127.0.0.1*)
    docker compose ps ;;
  *)
    echo "  Mode B (remote: $URL) — skip cek docker lokal" ;;
esac
echo

echo "=== 2. Health Check ==="
curl -sf -H "Authorization: Bearer $HINDSIGHT_API_TOKEN" "$URL/health" \
  && echo " ✅ Hindsight healthy" || echo " ❌ Hindsight not responding"
echo

echo "=== 3. Validasi Kontrak OKF ==="
.venv/bin/python src/validate_okf.py
echo

echo "=== 4. .env NOT tracked by git ==="
if git rev-parse --git-dir > /dev/null 2>&1; then
    git status --porcelain .env 2>/dev/null | grep -q '.env' && echo "  ⚠️  .env visible to git" || echo "  ✅ .env not tracked"
else
    echo "  (no git repo yet — skip)"
fi
echo

echo "=== 5. Control Plane UI ==="
case "$URL" in
  *localhost*|*127.0.0.1*) echo "  Buka http://localhost:9999 untuk cek bank '$BANK'" ;;
  *) echo "  Dashboard ada di server Hindsight (port 9999) — cek bank '$BANK'" ;;
esac
echo
echo "=== Done ==="
