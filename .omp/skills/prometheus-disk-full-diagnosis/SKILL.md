---
name: prometheus-disk-full-diagnosis
description: "Use when a Linux host running Prometheus (often paired with Grafana) reports high disk usage via df -h, or when Prometheus/Grafana dashboards show stale/missing metrics — diagnoses whether /var/lib/prometheus TSDB is the disk hog, whether retention is honored, and whether Prometheus has crashed from ENOSPC. Also covers recovering diagnostic visibility on a host that becomes SSH-exec-unresponsive during WAL replay after the fix."
---

## Diagnosis

1. `df -h /` — confirm the filesystem is actually near-full.
2. `du -x -h --max-depth=1 /var/lib 2>/dev/null | sort -rh` — find the hog. `/var/lib/prometheus` at tens of GB is the usual suspect. Avoid a blind `du -x /` at max-depth=1 on the whole root fs — on a loaded/slow-disk host this reliably hangs past a 300–600s command timeout; go straight to `/var/lib` once `df` confirms `/`.
3. Confirm retention is actually configured and honored:
   - `systemctl cat prometheus | grep -i retention` (or check `/etc/systemd/system/prometheus.service` ExecStart flags) for `--storage.tsdb.retention.time=Nd`.
   - `ls -lt --time-style=long-iso /var/lib/prometheus | grep '^d'` — block directory names are ULIDs; their mtimes give the true oldest/newest data. If oldest block mtime ≈ now − N days, retention is working as configured (not a leak) — the size is just genuine data volume, and the real question becomes "is N days too much for the available disk."
4. Check whether Prometheus actually crashed from the fullness (this is the common, urgent case — a full disk doesn't just grow slowly, it eventually panics the process):
   ```
   systemctl status prometheus --no-pager
   journalctl -u prometheus --no-pager -n 60 | grep -B30 'exited, code=exited'
   ```
   Look for `panic: write /var/lib/prometheus/chunks_head/...: no space left on device`. Prometheus does NOT auto-restart after this (systemd marks the unit `failed`) — metrics collection is silently dead until someone restarts it. Always check `systemctl status prometheus` even if the user only asked about disk space; a full disk here is often not just a capacity warning but an active outage.

## Remediation

1. Free space by deleting the oldest TSDB block dir(s) (the ULID directories under `/var/lib/prometheus`, oldest by mtime) — this is equivalent to what retention-based compaction would have done anyway. Do NOT touch `wal/` or `chunks_head/` (live state).
2. If asked to change retention, edit the `--storage.tsdb.retention.time=` flag in `/etc/systemd/system/prometheus.service`, then `systemctl daemon-reload`.
3. `systemctl restart prometheus`.
4. Verify: `systemctl status prometheus` shows `active (running)`, and `curl -s -o /dev/null -w '%{http_code}' http://localhost:9090/-/healthy` returns `200`.

## Known gotcha: SSH exec sessions hang during WAL replay

After restarting Prometheus following an ENOSPC crash, it must replay its WAL (can be several GB) before it starts listening on :9090. This is CPU/IO-heavy and can spike host load average to 10+ on small VMs. Symptom: every *new* `ssh host "cmd"` invocation from the agent times out (30–60s+) even though `ping` succeeds and a previously-open `ssh://` read-based connection keeps working fine (SFTP-style reads are cheaper than a full new interactive session/PTY).

Don't fight this by retrying with more `-o` flags — just downgrade to a lightweight diagnostic channel that doesn't need a new exec session:
- `read ssh://user@host:port/proc/loadavg` — track load coming down.
- `read ssh://user@host:port/proc/<pid>/status` — find the Prometheus PID (search for `Name:\tprometheus`), watch `VmRSS`/thread count grow as replay progresses. (`/proc/<pid>/cmdline` is null-byte separated and gets rejected as "binary" by the ssh:// text reader — use `/status` or `/proc/<pid>/cmdline` via a real ssh tool instead, not the ssh:// read path.)
- `read ssh://user@host:port/proc/net/tcp`, `grep :2382` (hex for port 9090) to check whether Prometheus has started listening yet, without needing `ss`/`netstat` over exec.

Once load drops and the listening port appears, a plain `ssh -p <port> user@host "cmd"` (no extra `-o ConnectTimeout=...` wrapper, no `timeout N` prefix) tends to succeed again — those extra layers were not the cause of the hang, host load was.
