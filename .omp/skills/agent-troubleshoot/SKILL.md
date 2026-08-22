---
name: agent-troubleshoot
description: "Diagnose agent session failures like database locks, tool timeouts, or missing system dependencies."
---

# Agent Troubleshooting Recipe

If an agent session appears to hang, returns timeout errors, or crashes with 'database is locked', follow this sequence:

1. **Check System Health**: Run `journalctl` for the specific time frame to identify process-level failures (timeout, connection refused).
2. **Verify Dependencies**: If `search_files` fails, verify if `rg` (ripgrep) or `find` are installed on the host. 
3. **Database Contention**: If 'database is locked' appears, terminate stale browser processes or stuck tool-executor threads that might be holding the DB lock.
4. **Network/API**: If API connection errors occur, check provider health or network connectivity (e.g., curl to the inference API endpoint).

Always prioritize these checks over re-running the failing task.
