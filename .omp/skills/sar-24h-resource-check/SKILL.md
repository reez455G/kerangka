---
name: sar-24h-resource-check
description: "Use when asked to check CPU, RAM, or disk I/O usage over the last N hours (e.g. \"cek cpu & ram & disk i/o 24 jam terakhir\") on a Linux host with sysstat installed — pulls historical stats from sar logs instead of only a live snapshot, and flags reboots/data gaps."
---

## Goal
Answer "check CPU/RAM/disk I/O for the last N hours" with real historical data, not just a live `top`/`free` snapshot.

## Procedure

1. **Confirm sysstat is collecting data:**
   ```bash
   which sar mpstat iostat vmstat
   systemctl status sysstat
   ls -la /var/log/sysstat/   # Debian/Ubuntu path; RHEL uses /var/log/sa/
   ```
   Files are named `saDD` (per-day binary stats, DD = day of month). If today's DD hasn't rolled over yet for the full window, you need **yesterday's file + today's file**.

2. **Pull the exact time window across two files** (e.g. last 24h ending now = yesterday from `now`'s time-of-day onward, plus all of today):
   ```bash
   sar -f /var/log/sysstat/saYY -u -s HH:MM:SS   # CPU, from a start time to midnight
   sar -f /var/log/sysstat/saDD -u               # CPU, today so far
   sar -f /var/log/sysstat/saYY -r -s HH:MM:SS   # RAM
   sar -f /var/log/sysstat/saDD -r
   sar -f /var/log/sysstat/saYY -b -s HH:MM:SS   # disk I/O (tps, bread/s, bwrtn/s)
   sar -f /var/log/sysstat/saDD -b
   ```
   `-u` = CPU (%user/%system/%iowait/%idle), `-r` = memory (%memused, kbcommit, swap), `-b` = disk I/O summary. Use `-d` for per-device breakdown if needed.

3. **Always check for `LINUX RESTART` markers in the sar output** — sar inserts these inline when the system rebooted. A reboot mid-window means:
   - Historical data before the marker in that boot's counters resets.
   - Multiple restarts in a short window (e.g. 3 in 24h, or two within minutes of each other) is anomalous and worth flagging to the user explicitly — don't just report averages and move on.
   - Cross-check with `last reboot -F` and `journalctl --list-boots` to get exact reboot timestamps and correlate with any error logs.

4. **Also check for silent data gaps** (no sar entries for a multi-hour span with no RESTART marker, or a RESTART followed by a large gap before next entry) — this usually means the machine was suspended/powered off, not that data collection failed. State the gap explicitly rather than silently averaging around it.

5. **Cap off with a live snapshot** for "right now" context, since sar's most recent interval may be minutes stale:
   ```bash
   free -h; df -h /; iostat -xz 1 1; cat /proc/loadavg
   ps aux --sort=-%cpu | head -6; ps aux --sort=-%mem | head -6
   ```
   `iostat -xz` gives `%util`, `r_await`, `w_await` per device — useful for spotting disk contention that plain tps/throughput numbers hide.

6. **Report format**: a small table per metric (CPU/RAM/disk) with time-window averages, called-out anomalies (reboots, gaps, iowait/await spikes) up front, and the live snapshot at the bottom for "right now" grounding. Don't just dump raw `sar` output — summarize.

## Gotchas
- `sar` binary log files are locale/version-sensitive; if `sar -f <file>` errors with a format mismatch, the sysstat version that wrote it differs from the one reading it — fall back to whatever `sadf -d` or `sar -f file 2>&1 | head` reveals.
- Systems with `sysstat.service` present but log files sparse or missing for the window mean historical data doesn't exist — say so plainly instead of extrapolating from a live snapshot.
