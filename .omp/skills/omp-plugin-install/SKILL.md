---
name: omp-plugin-install
description: "Install, list, discover, and manage omp (Oh My Pi) plugins via omp plugin CLI commands"
---

# omp Plugin Management

## Current State
- Plugins stored in `~/.omp/plugins/node_modules/` (raw TypeScript, loaded by Bun at runtime — no build step)
- Plugin registry: `~/.omp/plugins/omp-plugins.lock.json`
- Plugin package manifest: `~/.omp/plugins/package.json`

## Install

### From npm
```bash
omp plugin install <@scope/package-name>
# or with npm prefix:
omp plugin install npm:<@scope/package-name>
```

### From local path (dev/link)
```bash
omp plugin link <path-to-plugin-dir>
```

### Interactive via marketplace TUI (inside omp session)
```
/marketplace
```

### Add a marketplace source first
```bash
omp plugin marketplace add <source>
```

## Useful Commands

| Action | Command |
|---|---|
| List installed | `omp plugin list` |
| Discover available | `omp plugin discover` |
| Doctor (check & fix) | `omp plugin doctor --fix` |
| Uninstall | `omp plugin uninstall <name>` |
| Enable/disable feature | `omp plugin enable --<feature>=<value>` / `omp plugin disable --<feature>=<value>` |
| Set config | `omp plugin config --set key=value` |
| Upgrade | `omp plugin upgrade <name>` |
| Project-only scope | add `--scope project` |
| Preview (no changes) | add `--dry-run` |
| Force install | add `--force` |
| JSON output | add `--json` |

## Key Notes

1. **Never use `npm install` directly** — plugin won't register in omp config. Always use `omp plugin install`.
2. **Raw TS, no build step** — editing `.ts` files in `~/.omp/plugins/node_modules/<pkg>/src/` takes effect on next omp start.
3. **Startup can be slow (30-90s)** at `loadExtensions` phase while plugins fetch model lists from API. Use `PI_DEBUG_STARTUP=1` for streaming phase markers.
4. **Plugin lock file** (`omp-plugins.lock.json`) tracks: version, enabled state, enabledFeatures, and settings per plugin.
5. **Auth broker daemon** — if a provider plugin's auth seems stale, kill the broker: `pkill -f __omp_worker_daemon_broker`.
