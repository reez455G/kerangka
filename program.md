# My-AI-Agents Program

## Purpose

`my-ai-agents` adalah knowledge and orchestration layer untuk OMP.

Sistem menggabungkan:

- Skills
- Knowledge
- Hindsight memory
- Role-based agents
- Private source control
- Skill distribution

Tujuan utamanya adalah membuat agent dapat menggunakan kembali pengetahuan
dan pengalaman sebelumnya tanpa memasukkan seluruh repository atau history
ke context setiap session.

---

## 1. Session Startup

Ketika `omp` dijalankan:

```text
Device
  │
  ▼
pull skills from R2
  │
  ▼
.omp/skills/
  │
  ▼
OMP
```

Device hanya melakukan pull.

Tidak ada push skill otomatis ketika session selesai.

## 2. Leader

Leader adalah agent pada main session.

Leader bertanggung jawab untuk:

- memahami request,
- melakukan recall jika diperlukan,
- mencari skill yang relevan,
- menentukan specialist jika diperlukan,
- melakukan delegation,
- menggabungkan hasil,
- menyimpan lesson yang berguna ke Hindsight.

Leader tidak perlu melakukan delegation untuk pekerjaan sederhana.

## 3. Role-Based Agents

Gunakan specialist ketika pekerjaan membutuhkan domain tertentu.

Available roles:

- Infrastructure & Automation Engineer
- Business Analyst
- Network & Security Administrator
- Observability & SecOps Analyst
- Backend & API Developer

Flow:

```text
Leader
  │
  ▼
Role discovery
  │
  ▼
Specialist
  │
  ▼
Result
  │
  ▼
Leader
```

Role menentukan tanggung jawab.

Skill menentukan instruksi/capability.

Role dan Skill bukan hal yang sama.

## 4. Skill Usage

Sebelum membuat skill baru:

- cari skill yang sudah ada,
- baca skill yang relevan,
- gunakan atau perbaiki skill tersebut jika memungkinkan.

Buat skill baru hanya jika workflow atau pengetahuan tersebut cukup
reusable untuk pekerjaan berikutnya.

Jangan membuat duplikasi skill.

## 5. Skill Lifecycle

Skill private:

```text
create/update
     │
     ▼
Fossil
     │
     ▼
validate
     │
     ▼
publish
     │
     ▼
R2
```

R2 hanya digunakan untuk distribusi.

`.omp/skills/` pada device adalah runtime copy — bukan sumber kanonik.

## 6. Public Skills

Skill yang aman dan generic dapat dipublikasikan.

Flow (proses manual, bukan automated pipeline — tidak ada tool
`fossil export --public` atau sejenisnya):

```text
Private canonical source
        │
        ▼
generalize / redact (manual)
        │
        ▼
GitHub public repository
```

Catatan: mayoritas skill publik saat ini diedit langsung sebagai konten
publik di repo GitHub (`kerangka`) — tidak semuanya berasal dari redaksi
skill privat. Flow di atas berlaku untuk kasus ketika sebuah skill privat
memang punya padanan publik yang perlu dibuat.

Jangan memindahkan data pribadi, credential, konfigurasi private, atau
informasi internal ke repository public.

Public skill boleh menjelaskan mekanisme my-ai-agents secara detail selama
isinya tidak mengandung data private.

## 7. Hindsight Memory

Gunakan Hindsight untuk menyimpan informasi yang berguna lintas session.

Simpan terutama:

- keputusan,
- solusi,
- lesson learned,
- workflow yang berhasil,
- failure dan resolusinya,
- referensi ke skill/knowledge yang relevan.

Jangan menyimpan seluruh transcript atau seluruh isi skill tanpa kebutuhan.

## 8. Memory Metadata

Memory yang berkaitan dengan workflow sebaiknya menggunakan metadata ringan.

Contoh:

```text
[role:infrastructure-automation]
[project:my-ai-agents]
[workflow:cloudflare-deployment]
[skill:cloudflare-account-ops]
```

Metadata digunakan untuk membantu recall menemukan memory yang relevan
dengan cepat dan mengurangi context yang tidak diperlukan.

## 9. Knowledge vs Skill vs Memory

Gunakan aturan berikut:

- **Skill** → bagaimana melakukan sesuatu
- **Knowledge** → informasi authoritative tentang sesuatu
- **Hindsight** → apa yang pernah terjadi / dipelajari
- **Role** → siapa yang paling tepat mengerjakan sesuatu

Jangan memasukkan informasi yang sama ke semua layer tanpa alasan.

## 10. Token Efficiency

Target utama knowledge layer adalah mengurangi penggunaan token.

Gunakan:

```text
User request
     │
     ▼
Recall relevant memory
     │
     ▼
Find relevant role
     │
     ▼
Find relevant skill
     │
     ▼
Load minimum required context
     │
     ▼
Execute
     │
     ▼
Retain useful result
```

Jangan:

```text
User request
     │
     ▼
Load entire knowledge repository
     │
     ▼
Load every skill
     │
     ▼
Load entire history
```

## 11. Memory Retention

Tidak semua hasil session perlu disimpan.

Retain jika hasil:

- reusable,
- merupakan keputusan penting,
- menyelesaikan masalah yang mungkin muncul lagi,
- menghasilkan workflow baru,
- memperbaiki skill,
- memberikan lesson yang berguna.

Jangan retain informasi sementara atau percakapan yang tidak memiliki
nilai untuk session berikutnya.

## 12. Backup

Skill distribution dan Hindsight backup adalah dua hal berbeda.

Skill:

```text
Fossil → R2 → devices
```

Memory:

```text
Hindsight → backup → R2
```

Backup memory tidak boleh dianggap sebagai bagian dari skill distribution.

## 13. Maintenance

Secara berkala:

- validasi skill,
- cek duplicate skill,
- cek broken skill,
- cek role registry,
- cek R2 distribution,
- cek backup Hindsight,
- cek repository public tidak membocorkan private data.

Jangan melakukan cleanup otomatis terhadap data private tanpa konfirmasi.

## 14. Change Policy

Untuk perubahan besar:

```text
inspect
  │
  ▼
understand existing architecture
  │
  ▼
make smallest useful change
  │
  ▼
validate
  │
  ▼
document important decision
```

Jangan membuat abstraction atau infrastructure baru jika existing mechanism
sudah cukup.

Prioritaskan sistem yang:

- mudah dipahami,
- mudah dipulihkan,
- mudah digunakan agent,
- mudah digunakan manusia,
- minim maintenance.

## 15. Agent Working Rule

Sebelum mengerjakan task:

1. Apakah ada memory yang relevan?
2. Apakah ada skill yang relevan?
3. Apakah ada knowledge authoritative?
4. Apakah perlu specialist?
5. Apa context minimum yang dibutuhkan?

Setelah selesai:

1. Apa hasil penting?
2. Apakah ada lesson reusable?
3. Apakah skill perlu dibuat/diperbaiki?
4. Apakah memory perlu disimpan?

## 16. Simple Decision Tree

```text
Butuh melakukan sesuatu?
        │
        ▼
    Cari Skill
        │
        ├── ada → gunakan
        │
        └── tidak ada
              │
              ▼
         buat jika reusable


Butuh pengalaman sebelumnya?
        │
        ▼
      recall()


Butuh specialist?
        │
        ▼
    pilih Role


Selesai?
        │
        ▼
retain lesson jika reusable
```

## 17. Canonical Architecture

```text
                    ┌───────────────┐
                    │    Fossil     │
                    │    PRIVATE    │
                    │   CANONICAL   │
                    └───────┬───────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
       Public extraction             validate/publish
              │                           │
              ▼                           ▼
          GitHub                         R2
                                          │
                                       pull
                                          │
                                          ▼
                                      Devices
                                          │
                                          ▼
                                         OMP
                                          │
                                          ▼
                                       Leader
                                      /   │   \
                                  Recall Role Skill
                                      \   │   /
                                        task
                                          │
                                          ▼
                                     Specialist
                                          │
                                          ▼
                                       Result
                                          │
                                          ▼
                                      Hindsight
```

## 18. Core Principle

Sistem harus tetap sederhana:

- Fossil = private source
- GitHub = public source
- R2 = distribution
- OMP = runtime
- Role = responsibility
- Skill = procedure
- Knowledge = authoritative information
- Hindsight = experience/memory

Jika sebuah desain baru tidak membuat salah satu dari hal tersebut lebih
jelas atau lebih mudah digunakan, jangan tambahkan layer tersebut.

---

## 19. Hubungan dengan Dokumen Lain

`program.md` ini ditulis ulang dari nol (2026-08-24), bukan pemulihan
`program.md` lama. Evolusi historis sebelumnya (migrasi Syncthing→rclone,
migrasi Git→Fossil, berbagai patch dan keputusan interim) sudah menjadi
history operasional, bukan lagi bagian dari operating model saat ini.

Keputusan historis penting tetap dipertahankan secara terpisah, append-only,
di `knowledge/control-plane.md` (Fossil, private) — bukan diulang di sini.

Pembagian tanggung jawab dokumen:

```text
knowledge/control-plane.md
    = "sistem kita seperti apa, dan kenapa" (decision log, append-only)

program.md
    = "agent harus bekerja bagaimana" (operating model, dokumen ini)

skills/
    = "cara melakukan pekerjaan tertentu" (how-to, per-task)

knowledge/
    = "informasi authoritative" (fakta statis, append-only)

Hindsight
    = "apa yang pernah kita pelajari" (memory, dinamis)
```
