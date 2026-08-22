---
name: fix-bashrc-compatibility
description: "Memperbaiki error 'shopt: command not found' di .bashrc saat di-source oleh shell non-bash."
---

Untuk menghindari error "command not found: shopt" saat file .bashrc di-source oleh shell non-bash (zsh/dash), bungkus perintah bash-spesifik dalam:

```bash
if [ -n "$BASH_VERSION" ]; then
    # Perintah bash-spesifik (shopt, dll)
fi
```
