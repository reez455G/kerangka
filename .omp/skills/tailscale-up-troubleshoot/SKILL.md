---
name: tailscale-up-troubleshoot
description: "Diagnose and fix 'sudo tailscale up' failures on Linux hosts, especially 'failed to connect to local tailscaled' errors caused by the daemon service being disabled/inactive."
---

## Symptom
`sudo tailscale up` (or `tailscale status`) fails with:
```
failed to connect to local tailscaled; it doesn't appear to be running (sudo systemctl start tailscaled ?)
```

## Root cause (most common)
The `tailscaled` daemon service is `disabled`/`inactive (dead)`. The `tailscale` CLI is just a client that talks to the daemon over a local socket (`/run/tailscale/tailscaled.sock`) — if the daemon isn't running, every client command fails this way. This is NOT a network, auth, or install problem.

## Diagnosis steps
```bash
which tailscale tailscaled
sudo systemctl status tailscaled --no-pager
sudo tailscale status   # confirms the socket-connect error
```
Also sanity-check (rarely the actual blocker, but cheap to rule out):
```bash
ls -la /dev/net/tun          # tun device must exist
systemd-detect-virt          # containers may lack tun/netns permissions
```

## Fix
```bash
sudo systemctl enable --now tailscaled
```
This both starts the daemon now and persists it across reboots. Verify with `systemctl status tailscaled` (should show `active (running)`).

## Auth flow gotcha
```bash
sudo tailscale up
```
prints:
```
To authenticate, visit:
	https://login.tailscale.com/a/xxxxx
```
The process blocks, polling until the user completes login in a browser. **Do not run this under a short tool timeout** (e.g. 30s) — it will be killed with `context canceled` before the user can click through, which looks like a new failure but isn't. Instead:
1. Kick off `tailscale up` in the background (or accept it'll be backgrounded by the harness).
2. Surface the auth URL to the user and wait for them to confirm they logged in.
3. Re-check with `sudo tailscale status` (fast, no auth wait) rather than re-running `tailscale up`.

## Verification
`sudo tailscale status` should list this device with a `100.x.x.x` Tailscale IP and no longer say "Logged out". `tailscale ip -4` confirms the assigned address.
