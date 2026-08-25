# my-ai-agents

Konfigurasi + basis pengetahuan statis untuk **OMP (Oh My Pi)**, dengan **tiga lapis memori/state**: pengetahuan statis (OKF + native skills), memori dinamis (Hindsight), dan state terstruktur agent (Cloudflare Control Plane).

```
┌────────────────────────────────────────────────────────────────────┐
│                          my-ai-agents                              │
│                                                                    │
│   📚 .omp/skills/         💭 Hindsight          ☁️  Cloudflare      │
│   Git-tracked source      Memori Percakapan     Control Plane      │
│   (authoritative)                                                  │
│   ─ auto-scanned omp      ─ retain()            ─ gateway Worker   │
│   ─ 1 SKILL.md/folder     ─ recall()            ─ D1: run/event/   │
│   ─ prioritas 100         ─ reflect()             artifact state   │
│   ─ publish -> R2 (dist.)                        ─ R2: artifact     │
│                                                    biner (agent    │
│   knowledge/ (OKF,                                tulis langsung) │
│   append-only archive,                          ─ registry/        │
│   git)                                            resources.json  │
└────────────────────────────────────────────────────────────────────┘
```

## Arsitektur

| Komponen | Fungsi | Sifat |
|---|---|---|
| **`.omp/skills/`** | Skill/rules siap pakai — auto-discovered native oleh `omp` | **LOCAL RUNTIME COPY, bukan sumber kanonik.** Fossil (`kerangka-private`) adalah **satu-satunya sumber kanonik** untuk SEMUA skill (public+private) sejak 2026-08-24 — GitHub `kerangka` sekarang generated mirror (`./fossil-export-skills.sh`), bukan lokasi edit langsung. Didistribusikan ke device lain via **Cloudflare R2 + rclone** (`./publish-skills.sh` untuk publish, pull-only otomatis lewat wrapper `omp` — tidak pernah push otomatis), prioritas provider tertinggi (100) |
| **OKF** (`knowledge/`) | Arsip sumber pengetahuan statis — rules, skills, kebijakan | Append-only, versioned di git |
| **Hindsight** (Docker/remote) | Memori dinamis — percakapan, keputusan, konteks | Semantik, auto-learn via LLM, native ke `omp` (`recall`/`retain`/`reflect`) |
| **Cloudflare Control Plane** | State terstruktur agent — run/event/artifact tracking, resource registry | Worker `my-ai-agents-gateway` + D1 `my-ai-agents-db`; artifact biner di R2 `<R2_BUCKET_NAME>` (agent tulis langsung, bukan lewat gateway) |
| **Role Registry** (`roles/`) | Profil tanggung jawab agent (Leader + 5 spesialis) untuk delegasi berbasis peran | Statis, git-tracked. Bukan skill — lihat `roles/README.md` untuk perbedaan Role vs Skill |

Eksekusi LLM dan orkestrasi ditangani native oleh runtime `omp` — tidak ada lagi agen Python custom di repo ini. Detail arsitektur Cloudflare lengkap (diagram, API, keputusan desain): lihat `ARCHITECTURE.md` dan skill `cloudflare-account-ops`.

### Role & Skill discovery (Leader orchestration)

```bash
# Pilih role berdasarkan task (routing, directive "Role-Based Agent Spawning")
python3 src/role_search.py "server provisioning"     # -> infrastructure-automation
python3 src/role_search.py "monitoring"               # -> observability-secops

# Cek skill yang relevan/sudah ada SEBELUM bikin skill baru (cegah duplikat)
python3 src/skill_search.py "cloudflare"
python3 src/skill_search.py --inspect cloudflare-account-ops

# Validasi registry role
python3 src/validate_roles.py
```

Detail lengkap model Leader → recall → role → spawn → hasil ringkas →
retain: `ARCHITECTURE.md` § "Knowledge & Role Layer", `program.md` §19.

## Struktur Direktori

```
my-ai-agents/
├── program.md                    # Operating-model contract, APPEND-ONLY — mekanis via githooks/pre-commit
├── ARCHITECTURE.md                # Referensi arsitektur lengkap (termasuk Cloudflare Control Plane)
├── docker-compose.yml            # Hindsight server
├── requirements.txt              # Python dependencies (validate_okf.py saja)
├── .env.example                  # Template environment variables
├── omp-config.template.yml       # Template config untuk device baru
├── setup-new-device.sh           # Onboarding script device baru
├── sync-skills.sh                # regenerasi .omp/skills/ dari managed-skills lokal + knowledge/ (tidak menyentuh R2)
├── verify.sh                     # Checklist verifikasi
│
├── src/
│   └── validate_okf.py           # Validator kontrak OKF (knowledge/*.md)
│
├── cloudflare/
│   ├── my-ai-agents-gateway/     # Source Worker Control Plane (TypeScript)
│   │   ├── wrangler.toml         # Binding: D1 saja (KV/R2 sengaja tidak dibind)
│   │   └── src/index.ts          # API: /v1/runs, /v1/runs/:id/events, /v1/artifacts, /v1/resources
│   └── schema/                   # Migrasi D1 bernomor urut (001_initial.sql, dst.)
│
├── registry/
│   └── resources.json            # Inventori otoritatif semua resource Cloudflare — cek sebelum provisioning
│
├── publish-skills.sh              # satu-satunya jalur sah Git -> R2: validate_skills.py (gate) -> tulis MANIFEST.json -> rclone push
├── rclone-sync-skills.sh          # transport R2 <-> device: pull (device manapun) / push (hanya dipanggil publish-skills.sh)
├── .omp/skills/                   # skill native, Git-tracked (sumber otoritatif) — lihat "Skill Source of Truth" di ARCHITECTURE.md
│
└── knowledge/                    # OKF Knowledge Base — arsip sumber (append-only!)
    ├── index.md                  # Indeks semua knowledge
    ├── panduan_layanan.md        # Domain: kebijakan layanan
    ├── skema_database.md         # Domain: referensi teknis
    ├── control-plane.md          # Keputusan desain Cloudflare Control Plane
    ├── agent-rules/              # konvensi dari berbagai project
    └── skills/                   # skill library
```

## `program.md` — Append-Only

`program.md` (kontrak operating-model) tidak boleh diubah atau dihapus
setelah ditulis — hanya boleh ditambah di akhir. Ini ditegakkan **mekanis**
lewat `githooks/pre-commit` (aktifkan dengan `git config core.hooksPath
githooks`, sudah otomatis di-set `setup-new-device.sh`): commit apapun yang
mengubah atau memperpendek isi `program.md` akan **ditolak**. Kalau perlu
koreksi terhadap isi yang sudah ada, append catatan baru bertanggal — jangan
sentuh teks aslinya. Detail lengkap: `program.md` §20.

## Deploy

Ada **2 metode deploy** — pilih salah satu sesuai kebutuhan:

```
┌─────────────────────────────────────────────────────────────┐
│                     METODE DEPLOY                           │
│                                                             │
│   Mode A: Self-Hosted (Lokal)     Mode B: Existing Server   │
│   ┌─────────────────────┐        ┌─────────────────────┐   │
│   │  Device ini         │        │  Device ini         │   │
│   │  ├── agent.py       │        │  ├── agent.py       │   │
│   │  ├── knowledge/     │        │  ├── knowledge/     │   │
│   │  └── Hindsight 🐳   │        │  └── .env (remote)  │   │
│   │      localhost:8890  │        │                     │   │
│   └─────────────────────┘        └────────┬────────────┘   │
│                                           │                │
│                                    ┌──────▼──────────┐     │
│                                    │ Server Existing  │     │
│                                    │ Hindsight 🐳     │     │
│                                    │ host:8890        │     │
│                                    └─────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

### Mode A: Self-Hosted (Hindsight Lokal)

Hindsight jalan di device yang sama sebagai Docker container. Cocok untuk:
- Laptop/PC utama yang selalu on (server 24/7)
- Development & testing
- Tidak tergantung koneksi internet untuk memori

#### 1. Clone & Setup

```bash
git clone git@github.com:<your-github-username>/my-ai-agents.git
cd my-ai-agents
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

#### 2. Environment Variables

```bash
cp .env.example .env
nano .env
```

Isi semua variable:

| Variable | Contoh | Keterangan |
|---|---|---|
| `HINDSIGHT_API_LLM_PROVIDER` | `openai` | Provider LLM (openai, anthropic, ollama, gemini, dll) |
| `HINDSIGHT_API_LLM_API_KEY` | `nvapi-xxx` | API key provider |
| `HINDSIGHT_API_LLM_BASE_URL` | `https://integrate.api.nvidia.com/v1` | Endpoint LLM |
| `HINDSIGHT_API_LLM_MODEL` | `deepseek-ai/deepseek-v4-pro` | Model yang dipakai |
| `HINDSIGHT_API_WORKER_ID` | `hindsight-prod` | Worker identity |
| `HINDSIGHT_API_URL` | `http://localhost:8890` | URL Hindsight dari host |
| `HINDSIGHT_API_TOKEN` | `openssl rand -hex 32` | Token autentikasi |

#### 3. Jalankan Hindsight

```bash
docker compose up -d

# Tunggu ~3-10 menit untuk startup (tergantung hardware)
# Monitor:
watch -n 10 'curl -sf http://localhost:8890/health && echo OK || echo waiting...'
```

#### 4. Verifikasi

```bash
curl http://localhost:8890/health
bash verify.sh
```

---

### Mode B: Hindsight Existing (Remote Server)

Hindsight sudah jalan di server lain (laptop utama, VPS, dll). Device ini hanya perlu connect. Cocok untuk:
- Device tambahan (laptop kedua, PC kantor)
- Shared memory antar device
- Tidak perlu Docker di device ini

Ada **2 cara koneksi** ke server existing:

#### Opsi B1: Via Tailscale (Recommended)

Koneksi peer-to-peer terenkripsi tanpa expose port ke internet. Paling aman.

```
┌──────────────┐    Tailscale    ┌──────────────────┐
│ Device Baru  │◄──────────────►│ Server Hindsight  │
│              │   WireGuard     │ :8890 (API)       │
│ .env:        │   encrypted     │ :9999 (Dashboard) │
│ HINDSIGHT_   │                 │                   │
│ API_URL=     │                 │ 100.x.x.x        │
│ http://100.  │                 │ atau              │
│ x.x.x:8890  │                 │ hostname.tail...  │
└──────────────┘                 └──────────────────┘
```

**Di server (sekali saja):**

```bash
# Install & login Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up

# Catat hostname/IP
tailscale status   # → contoh: 100.64.0.1 atau laptop-server
```

**Di device baru:**

```bash
# Install & login Tailscale (akun yang sama)
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up

# Setup .env
cp .env.example .env
nano .env
```

```env
HINDSIGHT_API_URL=http://100.64.0.1:8890          # IP Tailscale server
# atau
HINDSIGHT_API_URL=http://laptop-server.tail1234.ts.net:8890
HINDSIGHT_API_TOKEN=(sama dengan token di server)
```

```bash
# Test
curl -sf http://100.64.0.1:8890/health && echo "OK"
```

**Kelebihan Tailscale:**
- Peer-to-peer (tidak lewat server pihak ketiga)
- Port tidak exposed ke internet
- Otomatis WireGuard encryption
- Bisa akses dashboard `:9999` langsung

---

#### Opsi B2: Via Cloudflare Tunnel

Expose Hindsight via Cloudflare tanpa buka port di router. Bisa diakses dari mana saja.

```
┌──────────────┐                ┌───────────┐              ┌──────────────────┐
│ Device Baru  │◄─── HTTPS ───►│ Cloudflare │◄── Tunnel ──│ Server Hindsight │
│              │                │ CDN/Proxy  │              │ cloudflared      │
│ .env:        │                │            │              │ :8890 (API)      │
│ HINDSIGHT_   │                └───────────┘              └──────────────────┘
│ API_URL=     │
│ https://     │
│ hindsight.   │
│ domain.com   │
└──────────────┘
```

**Di server:**

```bash
# Install cloudflared
curl -fsSL https://pkg.cloudflare.com/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

# Login & buat tunnel
cloudflared tunnel login
cloudflared tunnel create hindsight

# Config tunnel → file ~/.cloudflared/config.yml
```

```yaml
# ~/.cloudflared/config.yml
tunnel: <TUNNEL_ID>
credentials-file: ~/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: hindsight.domain.com     # ganti dengan domain kamu
    service: http://localhost:8890
  - hostname: hindsight-ui.domain.com  # opsional: dashboard
    service: http://localhost:9999
  - service: http_status:404
```

```bash
# Jalankan tunnel
cloudflared tunnel route dns hindsight hindsight.domain.com
cloudflared tunnel run hindsight

# Atau sebagai service (auto-start)
sudo cloudflared service install
```

**Di device baru:**

```env
HINDSIGHT_API_URL=https://hindsight.domain.com
HINDSIGHT_API_TOKEN=(sama dengan token di server)
```

```bash
# Test — cloudflared tidak perlu diinstall di client
curl -sf https://hindsight.domain.com/health && echo "OK"
```

**Kelebihan Cloudflare Tunnel:**
- Tidak perlu buka port di router/firewall
- HTTPS otomatis (SSL by Cloudflare)
- Bisa diakses dari internet (dengan auth)
- Tidak perlu install apapun di client

**Pertimbangan:**
- Traffic lewat Cloudflare (bukan peer-to-peer)
- Perlu domain yang di-manage di Cloudflare
- Tambahkan Cloudflare Access jika ingin extra auth layer

---

#### Perbandingan Opsi Koneksi

| | Tailscale | Cloudflare Tunnel |
|---|---|---|
| Install di client | ✅ Perlu | ❌ Tidak perlu |
| Enkripsi | WireGuard (P2P) | HTTPS (via Cloudflare) |
| Akses dari internet | ❌ Hanya Tailscale network | ✅ Dari mana saja |
| Perlu domain | ❌ | ✅ |
| Buka port di router | ❌ | ❌ |
| Latensi | Rendah (P2P) | Sedang (via CDN) |
| Dashboard `:9999` | Langsung akses | Perlu hostname tambahan |
| Cocok untuk | Tim kecil / personal | Public API / multi-lokasi |

#### Docker Tidak Diperlukan di Client

Di Mode B (kedua opsi), `docker-compose.yml` tidak perlu dijalankan di device client. Cukup `.env` yang mengarah ke server existing.

---

### Perbandingan Mode

| | Mode A: Self-Hosted | Mode B: Existing |
|---|---|---|
| Docker di device ini | ✅ Wajib | ❌ Tidak perlu |
| LLM API key di `.env` | ✅ Wajib | ❌ Tidak perlu |
| Perlu koneksi ke server | ❌ Lokal | ✅ Via Tailscale/VPN/LAN |
| Startup time | ~3-10 menit | Instan |
| Memori disimpan di | Device ini | Server |
| Dashboard (port 9999) | `localhost:9999` | `<server>:9999` |
| Cocok untuk | Server utama | Device tambahan |

---

### Setup via Script (kedua mode)

```bash
bash setup-new-device.sh
```

Script akan mendeteksi mode berdasarkan `omp-config.template.yml` dan memandu setup.

## Cara Pakai Skill/OKF

### Pakai skill yang sudah ada

Skill di `.omp/skills/<name>/SKILL.md` otomatis di-scan native oleh `omp` (prioritas tertinggi, 100) begitu `omp` dijalankan dari dalam repo ini atau subdirektorinya — tidak perlu import Python apa pun. Cukup jalankan `omp` dan minta sesuatu yang relevan; skill yang cocok otomatis dimuat ke context.

### Tambah skill/knowledge baru

1. Edit di lokasi yang benar tergantung klasifikasi (program.md §18): skill PRIVATE → `.omp/skills/<nama-skill>/SKILL.md` di Fossil checkout ini, lalu `fossil commit`; skill PUBLIC → di working tree repo `kerangka` (Git-tracked terpisah), lalu copy ke sini + `git commit`/`push` di sana. Cek `private-skills.txt` untuk daftar klasifikasi saat ini. Jangan pernah edit salinan R2, jangan edit salinan lokal di device lain dan menganggapnya kanonik.
2. Kalau skill juga perlu jadi arsip OKF (dicari via tag, audit trail git blame): drop juga file `.md` ke `knowledge/skills/` atau `knowledge/agent-rules/` dengan frontmatter OKF, lalu daftarkan di `knowledge/index.md` (kontrak append-only, `program.md` §5). Opsional — banyak skill hanya perlu ada di `.omp/skills/`.
3. `./publish-skills.sh` — regenerasi `.omp/skills/` dari managed-skills/knowledge, validasi (`src/validate_skills.py`, wajib lolos), tulis `MANIFEST.json`, lalu push ke R2. Device lain menerimanya lewat `rclone pull` otomatis (wrapper `omp`) di sesi berikutnya.
4. `git commit`/`git push` kapan pun kamu mau riwayat Git ikut bergerak — terpisah dari langkah 3, tidak otomatis.

## Skill Source of Truth: Fossil (private) / GitHub (public) → R2 → rclone

`.omp/skills/` sekarang **split sumber otoritatif** berdasarkan klasifikasi (program.md §18, membalik §17's single-Git-source model — lihat Decision 14 di `knowledge/control-plane.md`):

- **PRIVATE** skills (personal/project-internal, infra-fingerprinting — lihat `private-skills.txt`): sumber otoritatif adalah **Fossil** (`~/kerangka/my-ai-agents.fossil` — file repo-nya colocated di dalam checkout `kerangka`, tapi gitignored, lihat `kerangka/.gitignore`; checkout kerja Fossil tetap di repo ini). Edit, lalu `fossil commit`.
- **PUBLIC** skills (generik, aman dibagi): sumber otoritatif adalah repo Git **terpisah** `kerangka`. Edit di sana, commit, push, lalu copy hasilnya ke `.omp/skills/` di repo ini sebelum publish.

`<R2_SKILLS_REMOTE_PATH>` di R2 adalah **mirror distribusi untuk KEDUA tier** — jangan pernah tulis ke sana secara langsung, dan jangan anggap salinan lokal di device lain sebagai kanonik. R2 sendiri adalah infra privat (bukan permukaan publik) — didistribusikannya sebuah skill lewat R2 tidak membuatnya publik.

### Cara kerja

```
Fossil (private)         kerangka (Git, public)
     │                            │
     └──────────┬─────────────────┘
                ▼
     .omp/skills/ lokal (union kedua tier, repo ini)
                │
validate_skills.py (gate) ──FAIL──► stop, R2 tidak berubah
                │ PASS
                ▼
./publish-skills.sh ──► rclone sync (PUBLISH_ALLOWED=1) ──► R2 (<R2_SKILLS_REMOTE_PATH>)
                                                                  │
                                          ┌───────────────────────┼───────────────────────┐
                                          ▼                       ▼                       ▼
                                     Device A                Device B                Device C
                                (rclone pull, tiap        (rclone pull)           (rclone pull, baru,
                                 sesi `omp` mulai)                                  cukup 1 config)
```

Push sekarang pakai `rclone sync` (bukan `copy`) — skill yang dihapus lokal juga hilang dari R2, tidak menumpuk selamanya (ditemukan dalam praktik: skill lama yang sudah dihapus sempat "hidup lagi" karena `copy` lama tidak pernah menghapus apa pun di sisi remote).

Fungsi `omp` (dipasang otomatis oleh `setup-new-device.sh`) membungkus binary omp asli — **pull-only**, TIDAK push, TIDAK fossil commit, TIDAK git commit/push:
```bash
omp() {
    (cd ~/my-ai-agents && ./rclone-sync-skills.sh pull)   # tarik update sebelum sesi
    /path/ke/bin/omp "$@"
}
```
Publish (Fossil/GitHub → R2) selalu manual/eksplisit lewat `./publish-skills.sh` — tidak pernah berjalan sebagai efek samping sesi `omp`. Fossil autosync juga OFF secara eksplisit (`fossil setting autosync off`).

### Setup device baru (sekali per device, tidak perlu pairing)

`setup-new-device.sh` sudah meng-cover ini otomatis. Manual (kalau perlu):

```bash
sudo apt install -y rclone
mkdir -p ~/.config/rclone
cat >> ~/.config/rclone/rclone.conf <<EOF

[r2-my-ai-agents]
type = s3
provider = Cloudflare
access_key_id = <R2_SKILLS_ACCESS_KEY_ID dari operator>
secret_access_key = <R2_SKILLS_SECRET_ACCESS_KEY dari operator>
endpoint = <R2_SKILLS_ENDPOINT dari operator>
acl = private
no_check_bucket = true
EOF

cd ~/my-ai-agents
./rclone-sync-skills.sh pull
```

**Kredensial R2**: minta ke operator yang punya akses Dashboard Cloudflare (R2 API token permanen S3-compatible **hanya bisa dibuat via Dashboard**, bukan REST API — lihat `program.md` §16.2 untuk detail). Untuk skill PUBLIC: `git clone` repo `kerangka`. Untuk skill PRIVATE, `setup-new-device.sh` punya langkah **opsional** setup Fossil client (skip kalau device cuma mau konsumsi skill, sudah cukup dari langkah R2 di atas) — dua kasus:
- **Sudah punya Fossil server jalan** (mis. `fossil server` di home-lab): tinggal `fossil clone <url> ~/kerangka/my-ai-agents.fossil` lalu `fossil open --keep`, script akan tanya URL-nya langsung.
- **Belum ada server, cuma file `.fossil` lokal di device utama**: salin manual (`scp`, bukan lewat R2/git — ini private) lalu `fossil open ~/kerangka/my-ai-agents.fossil --keep`.

### Gotcha R2 yang perlu diketahui

R2 mengembalikan `501 NotImplemented` transien pada percobaan upload pertama tiap objek (bug kompatibilitas S3 di sisi R2, bukan bug kita) — data tetap benar tertulis, rclone retry otomatis dan berhasil di percobaan ke-2. **Karena itu skrip pakai opsi retry rclone bawaan, BUKAN `rclone bisync`** — `bisync` menganggap error ini fatal dan abort seluruh sync. Pull pakai `copy --update` (mtime-gated, tidak pernah menghapus lokal); push pakai `sync` (mirror penuh dari state lokal yang baru lolos validasi).

### Kalau device kamu masih pakai model lama

Model `both`/bidirectional-push per-device (§16), Syncthing (§13), dan single-Git-source (§17) sudah tidak dipakai. Jalankan ulang `bash setup-new-device.sh` untuk memasang fungsi `omp` versi pull-only terbaru.


## Cara Pakai Hindsight

Hindsight dipakai native oleh `omp` lewat tool bawaan `recall`/`retain`/`reflect`/`learn` — tidak ada API Python custom lagi. Konfigurasi ada di `~/.omp/agent/config.yml` (`hindsight.apiUrl`, `hindsight.bankId`, dst., lihat `omp-config.template.yml`).

## Cara Pakai Cloudflare Control Plane

Sejak 2026-08-22, agent yang butuh **state terstruktur** (run/event/artifact tracking, bukan sekadar percakapan) punya lapisan Cloudflare tambahan di atas OKF + Hindsight.

### Kredensial

```env
# di .env — lihat .env.example
MAI_GATEWAY_URL=https://my-ai-agents-gateway.<CF_ACCOUNT_SUBDOMAIN>.workers.dev
MAI_GATEWAY_TOKEN=<Worker Secret GATEWAY_TOKEN, minta ke operator>
```

### Alur pemakaian dasar (siklus hidup run)

```bash
H="Authorization: Bearer $MAI_GATEWAY_TOKEN"
BASE="$MAI_GATEWAY_URL"

# 1. Buat run (idempotency_key opsional — aman di-retry)
RUN=$(curl -sf -X POST "$BASE/v1/runs" -H "$H" -H "Content-Type: application/json" \
  -d '{"agent_id":"nama-agent","trigger":"manual","idempotency_key":"unik-per-tugas"}')

# 2. Catat event penting sepanjang eksekusi
curl -sf -X POST "$BASE/v1/runs/$RUN_ID/events" -H "$H" -H "Content-Type: application/json" \
  -d '{"agent_id":"nama-agent","event_type":"started","data":{}}'

# 3. Artifact biner ditulis LANGSUNG ke R2 (bukan lewat gateway)
wrangler r2 object put "<R2_BUCKET_NAME>/my-ai-agents/agent-runs/production/nama-agent/$RUN_ID/report.json" \
  --file=./report.json --content-type=application/json --remote

# 4. Daftarkan metadata artifact (object_key WAJIB prefix "my-ai-agents/")
curl -sf -X POST "$BASE/v1/artifacts" -H "$H" -H "Content-Type: application/json" \
  -d "{\"run_id\":\"$RUN_ID\",\"type\":\"report\",\"object_key\":\"my-ai-agents/agent-runs/production/nama-agent/$RUN_ID/report.json\"}"

# 5. Tutup run
curl -sf -X PATCH "$BASE/v1/runs/$RUN_ID" -H "$H" -H "Content-Type: application/json" \
  -d '{"status":"completed","result":"ringkasan hasil"}'
```

### Ringkasan Aktivitas Harian (Cron Trigger)

`my-ai-agents-gateway` punya Cron Trigger (`0 17 * * *`, 00:00 WIB) yang tiap hari otomatis:
1. Ambil semua memori Hindsight yang ditulis dalam 24 jam terakhir — lintas **semua device/project** yang terhubung ke bank `my-ai-agent` (bukan cuma repo ini)
2. Kelompokkan per tag `project:`/`brain:`
3. Sintesis ringkasan narasi via `reflect()` Hindsight sendiri
4. Simpan ke R2 (`<R2_BUCKET_NAME>/my-ai-agents/digests/{date}.md`), daftarkan di D1, dan retain balik ke Hindsight (best-effort)

**Trigger manual** (tanpa nunggu jadwal, untuk testing):
```bash
curl -X POST "$MAI_GATEWAY_URL/v1/digest/run" -H "Authorization: Bearer $MAI_GATEWAY_TOKEN"
```

**Baca digest hari ini:**
```bash
wrangler r2 object get "<R2_BUCKET_NAME>/my-ai-agents/digests/$(date -u +%Y-%m-%d).md" --file=digest.md --remote
```

> Catatan: digest yang di-retain ke Hindsight kadang tidak menghasilkan fakta baru yang bisa di-`recall()` (Hindsight kadang tidak mengekstrak fakta dari teks yang sudah berupa ringkasan). File R2 + metadata D1 adalah jalur baca yang paling andal — lihat `program.md §15.3`.

### Aturan wajib sebelum menyentuh Cloudflare

1. **Selalu cek `registry/resources.json` dulu** sebelum membuat resource baru — mencegah duplikasi Worker/D1/KV/R2.
2. **Jangan pernah pakai `CLOUDFLARE_API_TOKEN`** untuk operasi Control Plane sehari-hari — itu token account-level untuk provisioning, bukan untuk agent biasa. Gateway punya token sendiri (`GATEWAY_TOKEN`).
3. **DNS tetap manual** — token yang ada sengaja tidak punya izin `dns_records`. Jangan retry DNS API mengira token rusak.
4. Detail penuh kebijakan (naming convention, environment, cleanup, security): baca skill `cloudflare-account-ops`.

## Kontrak Append-Only

Didefinisikan di `program.md`:

- **DILARANG** mengubah atau menghapus file di `knowledge/`
- **HANYA BOLEH** menambah file baru + entry di `index.md`
- Setiap file wajib punya frontmatter OKF (id, title, tags, source, imported_at)
- Menjaga integritas knowledge base sebagai single source of truth

## Onboarding Device Baru

```bash
# Clone repo
git clone git@github.com:<your-github-username>/my-ai-agents.git
cd my-ai-agents

# Jalankan setup
bash setup-new-device.sh
```

Script akan: clone repo → minta token & URL → pilih bank memori omp (lanjut bank existing atau fresh) → apply omp config (non-destruktif) → setup venv + `.env` → test konektivitas.

Script ini **juga** meng-handle `.omp/skills/` — menginstall rclone, setup remote R2, dan jalankan sync awal (lihat "Sinkronisasi `.omp/skills/` via Cloudflare R2" di atas untuk detail kredensial).

## Port & Infra

| Service | Port | Keterangan |
|---|---|---|
| Hindsight API | `8890` | Host port (mapped ke container 8888) |
| Control Plane UI | `9999` | Dashboard visual memori bank |
| Cloudflare Gateway | — (edge, tanpa port lokal) | `https://my-ai-agents-gateway.<CF_ACCOUNT_SUBDOMAIN>.workers.dev` — state agent terstruktur |

## Backup & Restore

```bash
# Backup volume Hindsight
docker run --rm -v my-ai-agents_hindsight-data:/data -v $(pwd):/backup alpine \
  tar czf /backup/hindsight-backup-$(date +%F).tar.gz /data

# Restore
docker run --rm -v my-ai-agents_hindsight-data:/data -v $(pwd):/backup alpine \
  tar xzf /backup/hindsight-backup-YYYY-MM-DD.tar.gz -C /

# Knowledge base
# Sudah di git — clone ulang = restore otomatis
```

## Token Rotation

Jika `HINDSIGHT_API_TOKEN` bocor:

```bash
cd ~/my-ai-agents
NEW_TOKEN=$(openssl rand -hex 32)
sed -i "s/^HINDSIGHT_API_TOKEN=.*/HINDSIGHT_API_TOKEN=$NEW_TOKEN/" .env
docker compose down && docker compose up -d
```
