#!/usr/bin/env bash
#
# setup-new-device.sh
# Otomatisasi onboarding device baru untuk my-ai-agent (OKF + Hindsight + omp).
# Jalankan dari dalam folder repo yang sudah di-clone, atau beri URL repo sebagai argumen.
#
# Usage:
#   ./setup-new-device.sh                              # jika sudah di dalam folder repo
#   ./setup-new-device.sh git@github.com:user/my-ai-agent.git   # clone dulu, lalu setup
#
set -euo pipefail

REPO_DIR_NAME="my-ai-agents"    # WAJIB konsisten di semua device
OMP_CONFIG_DIR="$HOME/.omp/agent"
OMP_CONFIG_FILE="$OMP_CONFIG_DIR/config.yml"
TOKEN_ENV_FILE="$HOME/.omp/agent/.env"   # tidak pernah di-commit ke git

log()  { printf "\033[1;36m[setup]\033[0m %s\n" "$1"; }
warn() { printf "\033[1;33m[warn]\033[0m %s\n" "$1"; }
err()  { printf "\033[1;31m[error]\033[0m %s\n" "$1" >&2; }

# ── 1. Clone repo jika diberi URL, atau pastikan sudah berada di folder yang benar ──
if [ "$#" -eq 1 ]; then
    REPO_URL="$1"
    TARGET="$HOME/$REPO_DIR_NAME"
    if [ -d "$TARGET" ]; then
        warn "Folder $TARGET sudah ada, skip clone."
    else
        log "Cloning $REPO_URL ke $TARGET (nama folder dipin agar konsisten lintas device)..."
        git clone "$REPO_URL" "$TARGET"
    fi
    cd "$TARGET"
else
    CURRENT_DIR_NAME="$(basename "$PWD")"
    if [ "$CURRENT_DIR_NAME" != "$REPO_DIR_NAME" ]; then
        warn "Nama folder saat ini ('$CURRENT_DIR_NAME') beda dari '$REPO_DIR_NAME'."
        warn "Ini bisa bikin memori Hindsight ter-fragmentasi (scoping per-project-tagged pakai nama folder)."
        read -rp "Lanjutkan tetap di folder ini? [y/N] " ans
        [[ "$ans" =~ ^[Yy]$ ]] || { err "Dibatalkan. Rename/clone ulang ke folder '$REPO_DIR_NAME'."; exit 1; }
    fi
fi

if [ ! -f "omp-config.template.yml" ]; then
    err "omp-config.template.yml tidak ditemukan di $(pwd). Jalankan script ini dari root repo."
    exit 1
fi

# ── 2. Cek dependency dasar ──
for cmd in git curl omp; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        warn "'$cmd' belum terinstall di PATH. Pastikan terpasang sebelum lanjut memakai omp."
    fi
done

if command -v tailscale >/dev/null 2>&1; then
    if ! tailscale status >/dev/null 2>&1; then
        warn "Tailscale terpasang tapi belum aktif. Jalankan: sudo tailscale up"
    fi
else
    warn "Tailscale belum terinstall. apiUrl di config perlu bisa dijangkau lewat cara lain."
fi

# ── 3. Minta token Hindsight secara aman (tidak pernah masuk git) ──
mkdir -p "$OMP_CONFIG_DIR"
if [ -f "$TOKEN_ENV_FILE" ] && grep -q "HINDSIGHT_API_TOKEN=" "$TOKEN_ENV_FILE"; then
    log "HINDSIGHT_API_TOKEN sudah ada di $TOKEN_ENV_FILE, skip input."
else
    read -rsp "Masukkan HINDSIGHT_API_TOKEN (dari password manager): " HINDSIGHT_API_TOKEN
    echo
    [ -n "$HINDSIGHT_API_TOKEN" ] || { err "Token kosong, dibatalkan."; exit 1; }
    echo "export HINDSIGHT_API_TOKEN=\"$HINDSIGHT_API_TOKEN\"" >> "$TOKEN_ENV_FILE"
    chmod 600 "$TOKEN_ENV_FILE"
    log "Token disimpan di $TOKEN_ENV_FILE (chmod 600, tidak di-commit)."
fi

# shellcheck disable=SC1090
source "$TOKEN_ENV_FILE"

if grep -q "HINDSIGHT_API_URL=" "$TOKEN_ENV_FILE"; then
    log "HINDSIGHT_API_URL sudah ada di $TOKEN_ENV_FILE, skip input."
else
    read -rp "Masukkan HINDSIGHT_API_URL [https://hindsight.<yourdomain>.tld]: " HINDSIGHT_API_URL
    HINDSIGHT_API_URL="${HINDSIGHT_API_URL:-http://localhost:8000}"
    echo "export HINDSIGHT_API_URL=\"$HINDSIGHT_API_URL\"" >> "$TOKEN_ENV_FILE"
fi
# shellcheck disable=SC1090
source "$TOKEN_ENV_FILE"
export HINDSIGHT_API_URL HINDSIGHT_API_TOKEN

# ── 3b. Pilih bank memori omp: lanjut bank existing atau fresh ──
if grep -q "HINDSIGHT_BANK_ID=" "$TOKEN_ENV_FILE"; then
    log "HINDSIGHT_BANK_ID sudah ada di $TOKEN_ENV_FILE, skip input."
else
    log "Mengambil daftar bank dari $HINDSIGHT_API_URL ..."
    BANKS_JSON="$(curl -fsS -H "Authorization: Bearer $HINDSIGHT_API_TOKEN" "$HINDSIGHT_API_URL/v1/default/banks" 2>/dev/null || true)"
    if [ -n "$BANKS_JSON" ]; then
        echo "Bank existing di server (pilih salah satu untuk LANJUT memori lama):"
        printf '%s' "$BANKS_JSON" | python3 -c '
import json, sys
for b in json.load(sys.stdin).get("banks", []):
    print("  - %s (%s facts, terakhir %s)" % (b["bank_id"], b.get("fact_count", 0), (b.get("updated_at") or "?")[:10]))
' || printf '%s\n' "$BANKS_JSON"
    else
        warn "Tidak bisa ambil daftar bank dari server — ketik manual."
    fi
    read -rp "Bank ID omp (nama existing = LANJUT, nama baru = FRESH; bank dibuat otomatis saat write pertama) [my-ai-agent]: " HINDSIGHT_BANK_ID
    HINDSIGHT_BANK_ID="${HINDSIGHT_BANK_ID:-my-ai-agent}"
    echo "export HINDSIGHT_BANK_ID=\"$HINDSIGHT_BANK_ID\"" >> "$TOKEN_ENV_FILE"
fi
# shellcheck disable=SC1090
source "$TOKEN_ENV_FILE"
export HINDSIGHT_BANK_ID

# ── 4. Terapkan config template ──
log "Menerapkan omp-config.template.yml -> $OMP_CONFIG_FILE"
RENDERED="$(envsubst < omp-config.template.yml)"
if [ ! -f "$OMP_CONFIG_FILE" ]; then
    printf '%s\n' "$RENDERED" > "$OMP_CONFIG_FILE"
elif ! grep -q '^hindsight:' "$OMP_CONFIG_FILE"; then
    printf '\n%s\n' "$RENDERED" >> "$OMP_CONFIG_FILE"
else
    warn "config.yml sudah punya blok 'hindsight:' — tidak diubah. Config hasil render:"
    printf '%s\n' "$RENDERED"
fi

if [ ! -d .venv ]; then
    log "Membuat venv + install dependencies..."
    python3 -m venv .venv 2>/dev/null || {
        python3 -m venv --without-pip .venv
        curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
        .venv/bin/python /tmp/get-pip.py -q
    }
    .venv/bin/pip install -q -r requirements.txt
fi
if [ ! -f .env ]; then
    log "Membuat .env dari .env.example..."
    cp .env.example .env
    sed -i "s|^HINDSIGHT_API_URL=.*|HINDSIGHT_API_URL=$HINDSIGHT_API_URL|; s|^HINDSIGHT_API_TOKEN=.*|HINDSIGHT_API_TOKEN=$HINDSIGHT_API_TOKEN|" .env
fi

# ── 4b. Pasang git hooks + import skill ke managed-skills lokal (aman diulang) ──
log "Memasang git hooks (core.hooksPath -> githooks/) agar 'git pull' otomatis meng-import skill baru..."
git config core.hooksPath githooks
chmod +x githooks/post-merge githooks/post-checkout import-learned-skills.sh sync-skills.sh sync-okf-skills.py publish-skills.sh rclone-sync-skills.sh src/validate_skills.py 2>/dev/null || true
log "Import awal skill repo -> ~/.omp/agent/managed-skills (skill lokal yang sudah ada tidak akan ditimpa)..."
./import-learned-skills.sh

# ── 5. Auto-load token env di shell rc (opsional, sekali saja) ──
SHELL_RC="$HOME/.bashrc"
[ -n "${ZSH_VERSION:-}" ] && SHELL_RC="$HOME/.zshrc"
SOURCE_LINE="[ -f \"$TOKEN_ENV_FILE\" ] && source \"$TOKEN_ENV_FILE\""
if ! grep -qF "$TOKEN_ENV_FILE" "$SHELL_RC" 2>/dev/null; then
    echo "$SOURCE_LINE" >> "$SHELL_RC"
    log "Menambahkan auto-load token ke $SHELL_RC"
fi

# ── 5b. Fungsi wrapper 'omp' (auto pull skill terbaru dari R2 saat mulai sesi — program.md §17) ──
# Bukan alias sederhana lagi — perlu fungsi shell supaya bisa jalankan pull
# sebelum omp, tanpa perlu Syncthing sebagai daemon terpisah. TIDAK push di
# akhir sesi: publish (Git -> R2) adalah operasi eksplisit lewat
# ./publish-skills.sh, bukan efek samping otomatis tiap keluar sesi.
OMP_BIN="$(type -P omp || echo "$HOME/.bun/bin/omp")"
OMP_FUNCTION="omp() {
    (cd \"$PWD\" && ./rclone-sync-skills.sh pull)
    \"$OMP_BIN\" \"\$@\"
}"
# Bersihkan definisi 'omp' lama (alias ATAU function, versi manapun) sebelum menulis yang baru.
python3 - "$SHELL_RC" <<'PYEOF'
import re, sys
path = sys.argv[1]
try:
    with open(path) as f:
        content = f.read()
except FileNotFoundError:
    content = ""
# Hapus alias omp= satu baris lama
content = re.sub(r'^alias omp=.*\n?', '', content, flags=re.MULTILINE)
# Hapus definisi function omp() { ... } lama (multi-baris, non-greedy sampai '}' penutup di awal baris)
content = re.sub(r'^omp\(\) \{.*?\n\}\n?', '', content, flags=re.MULTILINE | re.DOTALL)
with open(path, "w") as f:
    f.write(content)
PYEOF
echo "$OMP_FUNCTION" >> "$SHELL_RC"
log "Fungsi 'omp' (dengan auto pull/push skill via R2) dipasang di $SHELL_RC"

ALIAS_SYNC="alias omp-sync=\"cd $PWD && git pull origin main && git push origin main\""
if grep -qF "alias omp-sync=" "$SHELL_RC" 2>/dev/null; then
    if grep -qF "$ALIAS_SYNC" "$SHELL_RC" 2>/dev/null; then
        log "Alias 'omp-sync' sudah terpasang dan up-to-date di $SHELL_RC"
    else
        grep -v "alias omp-sync=" "$SHELL_RC" > "$SHELL_RC.tmp" || true
        mv "$SHELL_RC.tmp" "$SHELL_RC"
        echo "$ALIAS_SYNC" >> "$SHELL_RC"
        log "Alias 'omp-sync' berhasil diperbarui di $SHELL_RC"
    fi
else
    echo "$ALIAS_SYNC" >> "$SHELL_RC"
    log "Menambahkan alias 'omp-sync' (manual pull+push untuk knowledge/, src/, program.md) ke $SHELL_RC"
fi

# ── 5c. Setup rclone untuk .omp/skills/ (transport R2 <-> device, program.md §17) ──
if ! command -v rclone >/dev/null 2>&1; then
    if command -v apt >/dev/null 2>&1; then
        log "rclone belum terinstall. Menginstall (butuh sudo)..."
        sudo apt update && sudo apt install -y rclone
    else
        warn "rclone belum terinstall dan package manager selain apt terdeteksi — install manual: https://rclone.org/downloads/"
    fi
fi

if command -v rclone >/dev/null 2>&1; then
    RCLONE_CONF="$HOME/.config/rclone/rclone.conf"
    mkdir -p "$(dirname "$RCLONE_CONF")"
    if grep -q "^\[r2-my-ai-agents\]" "$RCLONE_CONF" 2>/dev/null; then
        log "Remote rclone 'r2-my-ai-agents' sudah terpasang."
    else
        echo
        log "Setup remote rclone untuk pull .omp/skills/ dari Cloudflare R2 (distribusi; Git tetap sumber otoritatif)."
        if grep -q "R2_SKILLS_ACCESS_KEY_ID=" "$TOKEN_ENV_FILE" 2>/dev/null; then
            log "Kredensial R2 ditemukan di $TOKEN_ENV_FILE."
        else
            echo "Kredensial R2 (S3-compatible) — minta ke operator, atau lihat program.md §17 untuk cara membuatnya."
            read -rp "R2 Access Key ID: " R2_AK
            read -rsp "R2 Secret Access Key: " R2_SK; echo
            read -rp "R2 S3 Endpoint (https://<account_id>.r2.cloudflarestorage.com): " R2_EP
            {
                echo "R2_SKILLS_ACCESS_KEY_ID=$R2_AK"
                echo "R2_SKILLS_SECRET_ACCESS_KEY=$R2_SK"
                echo "R2_SKILLS_ENDPOINT=$R2_EP"
            } >> "$TOKEN_ENV_FILE"
        fi
        # shellcheck disable=SC1090
        source "$TOKEN_ENV_FILE"
        cat >> "$RCLONE_CONF" <<EOF

[r2-my-ai-agents]
type = s3
provider = Cloudflare
access_key_id = ${R2_SKILLS_ACCESS_KEY_ID:-}
secret_access_key = ${R2_SKILLS_SECRET_ACCESS_KEY:-}
endpoint = ${R2_SKILLS_ENDPOINT:-}
acl = private
no_check_bucket = true
EOF
        log "Remote rclone 'r2-my-ai-agents' ditulis ke $RCLONE_CONF"
    fi

    chmod +x rclone-sync-skills.sh publish-skills.sh 2>/dev/null || true
    log "Menjalankan sync awal (.omp/skills/ <- R2)..."
    ./rclone-sync-skills.sh pull || warn "Sync awal gagal — cek kredensial R2 di atas, atau coba manual: ./rclone-sync-skills.sh pull"
else
    warn "rclone tidak terinstall — .omp/skills/ tidak akan tersinkron otomatis ke/dari device ini. Install manual lalu ikuti README."
fi

# ── 6. Test konektivitas ke Hindsight server ──
HINDSIGHT_URL="$(grep -oP '(?<=apiUrl: ).*' "$OMP_CONFIG_FILE" | head -1)"
if [ -n "$HINDSIGHT_URL" ]; then
    log "Cek koneksi ke $HINDSIGHT_URL/health ..."
    if curl -fsS -H "Authorization: Bearer $HINDSIGHT_API_TOKEN" "${HINDSIGHT_URL}/health" >/dev/null 2>&1; then
        log "✅ Hindsight server terjangkau dan sehat."
    else
        warn "Tidak bisa reach $HINDSIGHT_URL/health — cek Tailscale aktif & server hidup di laptop 24/7."
    fi
else
    warn "Tidak bisa parse apiUrl dari config. Cek isi $OMP_CONFIG_FILE secara manual."
fi

echo
log "Setup selesai. Jalankan 'omp' di dalam folder repo untuk mulai sesi (mental model & histori akan auto-recall)."
log "Skill di .omp/skills/ otomatis pull dari R2 sebelum tiap sesi (tidak push otomatis — publish ke R2 sekarang eksplisit lewat ./publish-skills.sh setelah edit di Git)."
log "Ingat: 'omp-sync' untuk pull/push manual knowledge/, src/, program.md (git, bukan R2). Skill = edit di Git working tree .omp/skills/, lalu ./publish-skills.sh."
