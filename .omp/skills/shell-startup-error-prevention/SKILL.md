---
name: shell-startup-error-prevention
description: "Prevent shell startup errors by appending '|| true' to potentially failing commands in .bashrc."
---

When a command in .bashrc or another shell startup script might be missing, failing, or only applicable in specific interactive contexts, append '|| true' to the command. This ensures the script continues execution even if the command returns a non-zero exit status, preventing annoying error messages on shell startup.
