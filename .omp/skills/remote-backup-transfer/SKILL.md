---
name: remote-backup-transfer
description: "Prosedur arsip, transfer (scp), dan ekstraksi remote menggunakan SSH password."
---

# Prosedur Backup & Transfer ke Server Remote

Gunakan prosedur ini untuk mengarsipkan direktori, mentransfer ke server remote, dan mengekstraknya:

1. **Buat Arsip (dengan pengecualian file yang berubah cepat):**
   ```bash
   tar -czf backup.tar.gz --exclude='./tmp' --exclude='./galaxy_cache' .
   ```

2. **Transfer & Ekstraksi Remote:**
   ```bash
   sshpass -p 'PASSWORD' scp backup.tar.gz user@remote:/path/ke/tujuan/ && \
   sshpass -p 'PASSWORD' ssh user@remote "tar -xzf /path/ke/tujuan/backup.tar.gz -C /path/ke/tujuan/"
   ```
   
*Catatan: Pastikan sshpass terinstal di mesin lokal.*
