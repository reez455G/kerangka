# my-ai-agents — Architecture Reference

> **For AI agents and engineers entering this repository.**
> Read this before touching any code, script, or Cloudflare resource.

---

## What Is This Repository?

`my-ai-agents` is an **AI Agent Control Plane** — a git-tracked configuration and knowledge base that defines how AI agents (running via OMP) store skills, access memory, track their work, and interact with infrastructure.

It does NOT contain agent logic or LLM code. It is the **operational substrate** agents run on.

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────┐
│                      my-ai-agents                              │
│                                                                │
│  ┌─────────────────────┐   ┌──────────────────────────────┐   │
│  │   .omp/skills/      │   │   knowledge/ (OKF archive)   │   │
│  │   Native skill      │   │   Append-only, git-tracked   │   │
│  │   discovery         │   │   policies/rules/skills      │   │
│  │   R2 sync (rclone)  │   │                              │   │
│  └─────────────────────┘   └──────────────────────────────┘   │
│                                                                │
│  ┌─────────────────────┐   ┌──────────────────────────────┐   │
│  │   Hindsight         │   │   my-ai-agents-gateway       │   │
│  │   (Docker/remote)   │   │   (Cloudflare Worker)        │   │
│  │   Semantic memory   │   │   Agent Control Plane API    │   │
│  │   retain/recall/    │   │                              │   │
│  │   reflect           │   └──────┬───────────────────────┘   │
│  └─────────────────────┘          │                            │
│                              ┌────┴──────────────────────┐    │
│                              │  D1: my-ai-agents-db      │    │
│                              │  R2: <R2_BUCKET_NAME>        │    │
│                              │  KV: CACHE                 │    │
│                              └───────────────────────────┘    │
└────────────────────────────────────────────────────────────────┘
```

---

## Layer Responsibilities

| Layer | Component | Responsibility | What NOT to Store Here |
|---|---|---|---|
| **Skill runtime** | `.omp/skills/` | Executable agent skills, auto-discovered by OMP | Binary data, secrets |
| **Knowledge archive** | `knowledge/` | Static facts, policies, agent-rules — append-only | Dynamic state, conversation history |
| **Semantic memory** | Hindsight | Long-term conversational memory, cross-device recall | Structured metadata, large files |
| **Structured state** | D1 `my-ai-agents-db` | Agent runs, events, artifact metadata, resource registry | Binary files, semantic memory |
| **Config/cache** | KV `CACHE` | Available for future agent config/flags (prefix `mai:`); not currently bound to gateway | Long-term data, large content |
| **Artifacts** | R2 `<R2_BUCKET_NAME>` | Binary files, reports, exports — agents write directly (prefix `my-ai-agents/`); gateway stores metadata only | Structured metadata (use D1) |
| **API gateway** | Worker `my-ai-agents-gateway` | HTTP API for D1 CRUD: runs, events, artifacts, resources. D1-only; no R2/KV binding | Business logic, LLM calls |
| **Private access** | Tunnel `home-lab` | Hindsight API via `hindsight.<YOUR_ZONE_DOMAIN>` | Direct public exposure |

---

## What Is an Agent?

An agent is an OMP session — a single run of `omp` that uses skills from `.omp/skills/` and memory from Hindsight. Agents interact with the control plane via:

1. **Native OMP tools**: `retain()`, `recall()`, `reflect()` → Hindsight
2. **Gateway API**: `POST /v1/runs`, `POST /v1/events` → D1 (structured tracking)
3. **Skills**: read from `.omp/skills/`, sourced from `knowledge/` + `manage_skill` outputs

---

## What Is a Skill?

A skill is a `SKILL.md` file under `.omp/skills/<name>/`. OMP auto-discovers it when running inside this repo. Skills define repeatable procedures and operational behavior.

Sources:
- **Embedded-class**: `knowledge/skills/*.md` → auto-synced by `sync-okf-skills.py`
- **Bare-class**: authored directly in `.omp/skills/<name>/SKILL.md`
- **Managed**: created by OMP `manage_skill` tool → `~/.omp/agent/managed-skills/` → synced by `sync-skills.sh`

Skills are authored directly in this Git repository (`.omp/skills/<name>/SKILL.md` is Git-tracked — see "Skill Source of Truth & Distribution" below) and distributed to other devices via Cloudflare R2 + rclone, not via `git pull`. The `omp` shell function auto-pulls from R2 before each session (pull-only, no auto-push). See `program.md` §17 for the full model and §16 for migration history from Syncthing.

---
## Skill Source of Truth & Distribution

```
┌──────────────────┐
│       Git        │
│ AUTHORITATIVE    │
│ SKILL SOURCE     │  .omp/skills/<name>/SKILL.md, Git-tracked
└────────┬─────────┘
         │ validate_skills.py (gate)
         ▼
    ./publish-skills.sh
         │ rclone push (PUBLISH_ALLOWED=1 only)
         ▼
┌──────────────────┐
│       R2         │
│  DISTRIBUTION    │  <R2_BUCKET_NAME>/my-ai-agents/omp-skills/
│     LAYER        │
└────────┬─────────┘
         │ rclone pull (omp wrapper, every session start)
         ▼
  Device A / B / C  →  local .omp/skills/  →  OMP runtime (disposable copy)
```

Rules (program.md §17):
- **Git is the only authoritative skill source.** Create/modify/rename/delete a skill by editing `.omp/skills/<name>/SKILL.md` in this repo's Git working tree — never edit the R2 copy, never treat a local runtime copy on another device as canonical.
- **R2 is distribution, not collaboration.** It is a one-way mirror of what Git published; multiple devices independently pushing to it would recreate the ambiguity this model eliminates.
- **rclone is transport only.** It has no opinion about authority — `rclone-sync-skills.sh pull` is safe for any device at any time; `rclone-sync-skills.sh push` is gated (`PUBLISH_ALLOWED=1`) and only ever invoked by `./publish-skills.sh`.
- **Publishing is explicit.** `./publish-skills.sh` regenerates `.omp/skills/` from its upstream sources (managed-skills, `knowledge/`), runs `src/validate_skills.py` as a hard gate, writes `.omp/skills/MANIFEST.json` (git revision, timestamp, skill count/list — no secrets), then pushes to R2. Validation failure = zero R2 change, non-zero exit.
- **Normal `omp` startup only pulls.** The wrapper never pushes local state to R2 as a session side effect.
- **Failed pulls never destroy local skills.** `rclone copy --update` only overwrites when the remote is newer; an unreachable R2 leaves existing local skills untouched.
- **Do not edit R2 directly.** Do not treat a local device copy as authoritative.


## What Is Knowledge?

`knowledge/` is the append-only OKF archive. Every file has OKF frontmatter:

```markdown
---
id: unique-id
title: Descriptive Title
tags: [skill, docker, deploy]
source: /path/to/original
imported_at: YYYY-MM-DD
---
```

Rules (from `program.md`):
- **NEVER** modify existing files in `knowledge/`
- **NEVER** delete files from `knowledge/`
- **ONLY** append: new files, or new lines at the end of existing files
- Every new file MUST be registered in `knowledge/index.md`

---

## What Is Memory?

Hindsight provides semantic long-term memory via `retain()`, `recall()`, `reflect()` OMP native tools.

- **Bank**: `my-ai-agent` (canonical, same across all devices)
- **URL**: `hindsight.<YOUR_ZONE_DOMAIN>` (via Cloudflare Tunnel `home-lab`) or `localhost:8890` (Mode A)
- **Auth**: `HINDSIGHT_API_TOKEN` (in `.env`, gitignored)
- **LLM backend**: `meta/llama-3.1-70b-instruct` via NVIDIA — use non-reasoning instruct models only

Memory is NOT stored in D1 or KV. D1 stores structured metadata; Hindsight stores semantic content.

---

## What Is the Cloudflare Control Plane?

The Cloudflare layer provides durable infrastructure for agent work:

```
my-ai-agents-gateway (Worker)
    URL: https://my-ai-agents-gateway.<CF_ACCOUNT_SUBDOMAIN>.workers.dev
    Auth: Authorization: Bearer $MAI_GATEWAY_TOKEN
    Binding: D1 only (no R2/KV bound — gateway is metadata-only)
    │
    └── D1: my-ai-agents-db (<D1_DATABASE_UUID>)
            tables: resources, agent_runs, agent_events, artifacts

Agents write binary artifacts directly to R2 <R2_BUCKET_NAME> (not through this Worker).
KV CACHE available account-wide; not bound to gateway until a config use case exists.
```

**Gateway API**:
| Method | Path | Purpose | Idempotency |
|---|---|---|---|
| GET | `/health` | Liveness, no auth | — |
| GET | `/v1/resources` | List active resources | — |
| POST | `/v1/resources` | Register/upsert resource | UPSERT on (name, type, env) |
| POST | `/v1/runs` | Create agent run | Pass `idempotency_key` to deduplicate |
| GET | `/v1/runs/:id` | Get run status | — |
| PATCH | `/v1/runs/:id` | Update run (COALESCE — won't clear existing result) | Safe to re-call |
| GET | `/v1/runs/:id/events` | List events for a run | — |
| POST | `/v1/runs/:id/events` | Append a run event | Append-only |
| GET | `/v1/artifacts` | List artifacts (?run_id=, ?agent_id=) | — |
| POST | `/v1/artifacts` | Register artifact metadata | Append-only |
| GET | `/v1/artifacts/:id` | Get artifact metadata | — |
| POST | `/v1/digest/run` | Manually trigger the daily digest (same logic as Cron Trigger) | Not idempotent — creates a new run each call |

---

## Where Is State Stored?

| State type | Storage | Access |
|---|---|---|
| Agent skills | `.omp/skills/` (Git-tracked source; R2 via rclone = distribution) | OMP native provider |
| Static knowledge | `knowledge/` (git) | OMP native provider |
| Semantic memory | Hindsight | `retain`/`recall`/`reflect` OMP tools |
| Agent run records | D1 `agent_runs` | Gateway API `POST /v1/runs` |
| Run timeline | D1 `agent_events` | Gateway API `POST /v1/runs/:id/events` |
| Artifact metadata | D1 `artifacts` | Gateway API `POST /v1/artifacts` |
| Binary artifacts | R2 `<R2_BUCKET_NAME>` | R2 API / wrangler |
| Config/flags | KV `CACHE` | Available; not yet used by gateway. Add `mai:{key}` entries when concrete need exists |

---

## Where Are Artifacts Stored?

Binary artifacts (reports, screenshots, exports, logs) go to R2 `<R2_BUCKET_NAME>`.

Key convention:
```
my-ai-agents/agent-runs/{environment}/{agent-id}/{run-id}/{filename}
```

Artifact metadata (size, content-type, R2 key) goes to D1 `artifacts` table, registered via `POST /v1/artifacts`.

---

## How Are Async Jobs Handled?

Currently: not yet needed. If an async workload is identified, Cloudflare Queues will be introduced. The pattern will be:

```
Agent → Queue → Worker Consumer → D1 / R2 / Hindsight
```

Do NOT introduce Queues speculatively. Add them only when a concrete async use case exists.

---

## How Are Durable Workflows Handled?

Currently: not yet needed. Cloudflare Workflows will be introduced only when a multi-step durable execution pattern (e.g. discovery → fetch → analyze → persist → notify) is required.

---

## How Are Scheduled Jobs Handled?

**Implemented (2026-08-22):** `my-ai-agents-gateway` has one Cloudflare Cron Trigger:

| Schedule | Job | What it does |
|---|---|---|
| `0 17 * * *` (17:00 UTC = 00:00 WIB) | Daily activity digest | Fetches the last 24h of Hindsight memory across every device/project sharing bank `my-ai-agent`, groups by `project:`/`brain:` tags, synthesizes prose via Hindsight's own `reflect()` (reuses its already-configured LLM — no new AI infra), retains the digest back into Hindsight (`tags: [daily-digest, date:YYYY-MM-DD]`), writes a readable copy to R2 (`my-ai-agents/digests/{date}.md`), and registers the artifact in D1. Tracked as a normal `agent_runs` row (`agent_id: daily-digest-cron`, `trigger: cron`). |

Manual trigger for testing (bypasses the schedule): `POST /v1/digest/run` (same auth as other `/v1/*` routes).

**Known limitation:** the digest document retained back into Hindsight has been observed with `memory_unit_count: 0` — Hindsight's fact-extraction LLM does not reliably extract discrete facts from an already-synthesized meta-summary, so the digest does not reliably surface via `recall()`/`reflect()` on subsequent queries. The R2 markdown copy + D1 artifact metadata are the durable, verified-reliable read path; the Hindsight retain is best-effort enrichment, not guaranteed.

No other scheduled jobs exist. Additional Cron Triggers (health checks, artifact cleanup) will be added only when a concrete need arises.

---

## How Are Private Services Accessed?

Via Cloudflare Tunnel `home-lab` (token-based, active):
- `hindsight.<YOUR_ZONE_DOMAIN>` → Hindsight API on private server port 8890
- Tunnel ingress is configured in Zero Trust Dashboard, NOT in `/etc/cloudflared/config.yml`

Service-to-service auth: `CF_ACCESS_CLIENT_ID` + `CF_ACCESS_CLIENT_SECRET` (in `.env`, gitignored).

---

## How Are Resources Discovered?

Before creating any Cloudflare resource:
1. Check `registry/resources.json` for existing inventory
2. Run the discovery commands in `cloudflare-account-ops` skill (§4 Discovery Policy)
3. Proceed only if no existing resource serves the purpose

---

## How Are Resources Provisioned?

Follow the agent lifecycle:
```
DISCOVER → CHECK EXISTS → PLAN → CREATE IF REQUIRED → VERIFY → REGISTER
```

All provisioning MUST be idempotent (safe to re-run). SQL uses `CREATE TABLE IF NOT EXISTS`. Workers use `wrangler deploy` (upsert). Resources check existence before creating.

After provisioning, update `registry/resources.json`.

---

## How Are Resources Cleaned Up?

1. Discover the resource in live account + `registry/resources.json`
2. Verify `owner: my-ai-agents`
3. Verify environment and check for dependents
4. Warn about irreversible data loss
5. Require explicit human confirmation for production
6. Set `"status": "retired"` in `registry/resources.json` after decommission

**NEVER** delete based on naming patterns alone.

---

## How Are Secrets Handled?

| Secret | Location | NEVER in |
|---|---|---|
| `CLOUDFLARE_API_TOKEN` | `.env` (gitignored) in the relevant Worker's source dir | git, logs, API responses |
| `HINDSIGHT_API_TOKEN` | `.env` (gitignored), `~/.omp/agent/.env` | git |
| `MAI_GATEWAY_TOKEN` | `.env` (gitignored), Worker Secret | git, wrangler.toml |
| `CF_ACCESS_CLIENT_ID/SECRET` | `.env` (gitignored) | git |

Worker secrets set via `wrangler secret put`, never in `wrangler.toml`.

---

## How Are DNS Changes Handled?

The `CLOUDFLARE_API_TOKEN` has NO `dns_records` permission. DNS changes are a privileged operation.

Agent workflow when DNS is needed:
1. Agent detects DNS change requirement
2. Agent produces explicit DNS record specification (name, type, value, TTL)
3. Human performs change via Cloudflare Dashboard → DNS
4. OR: operator uses a separate DNS-scoped token

Agents MUST NOT retry DNS APIs or treat DNS failure as a generic token error.

---

## Agent Lifecycle for Infrastructure Operations

```
DISCOVER   ← check registry/resources.json + live account
    ↓
PLAN       ← determine what must change and why
    ↓
VALIDATE   ← confirm idempotency, no duplicate names, no broken deps
    ↓
EXECUTE    ← apply changes; set secrets via wrangler secret put
    ↓
VERIFY     ← hit /health, test a real endpoint, confirm D1 row created
    ↓
REGISTER   ← update registry/resources.json
    ↓
OBSERVE    ← check gateway /health, D1 counts, R2 objects
    ↓
CLEANUP    ← remove stale resources (with human confirmation)
```

---

## Observability

Answer these questions at any time:
| Question | Where |
|---|---|
| Is the gateway alive? | `GET /health` |
| What runs are active? | D1 `agent_runs WHERE status='running'` via gateway |
| Which agent owns it? | D1 `agent_runs.agent_id` |
| When did it last run? | D1 `agent_runs.started_at` |
| Did it fail? | D1 `agent_runs.status='failed'` + `error` column |
| Where is the result? | D1 `artifacts.object_key` → R2 |
| What resources exist? | `registry/resources.json` + `GET /v1/resources` |

---

## Deploy / Onboarding Reference

| Script | Purpose |
|---|---|
| `setup-new-device.sh` | Onboard a new device (OMP config, Hindsight creds, rclone R2 skill pull) |
| `publish-skills.sh` | Validate + publish Git `.omp/skills/` → R2 (the only sanctioned Git→R2 path) |
| `sync-skills.sh` | Regenerate `.omp/skills/` from managed-skills + knowledge/ (does not touch R2) |
| `sync-okf-skills.py` | knowledge/ embedded-class → `.omp/skills/` |
| `import-learned-skills.sh` | `.omp/skills/` → `~/.omp/agent/managed-skills/` (fill gaps) |
| `verify.sh` | Verify Hindsight connectivity + OKF contract validity |
| `ingest-okf-to-hindsight.py` | OKF archive → Hindsight (semantic search of knowledge/) |

Cloudflare worker: `cd cloudflare/my-ai-agents-gateway && npx wrangler deploy`
D1 migration: `npx wrangler d1 execute my-ai-agents-db --file=cloudflare/schema/001_initial.sql --remote`

---

## Environment Variables Required

See `.env.example` for full list. Key variables:

| Variable | Purpose |
|---|---|
| `HINDSIGHT_API_URL` | Hindsight endpoint |
| `HINDSIGHT_API_TOKEN` | Hindsight auth token |
| `HINDSIGHT_BANK_ID` | Memory bank (`my-ai-agent`) |
| `MAI_GATEWAY_URL` | Gateway Worker URL |
| `MAI_GATEWAY_TOKEN` | Gateway API auth token |
| `CF_ACCESS_CLIENT_ID` | Cloudflare Access service token |
| `CF_ACCESS_CLIENT_SECRET` | Cloudflare Access service secret |

---

## File Map

```
my-ai-agents/
├── ARCHITECTURE.md          ← this file
├── program.md               ← OKF+memory architecture contract (append-only)
├── README.md                ← quickstart
├── docker-compose.yml       ← Hindsight (Mode A: local)
├── .env.example             ← env variable template
├── omp-config.template.yml  ← OMP config template for new devices
│
├── cloudflare/
│   ├── my-ai-agents-gateway/   ← Agent Control Plane Worker source
│   │   ├── wrangler.toml
│   │   ├── src/index.ts
│   │   ├── package.json
│   │   └── tsconfig.json
│   └── schema/
│       └── 001_initial.sql     ← D1 schema migration
│       └── 002_idempotency.sql ← idempotency_key column + partial unique index
│
├── registry/
│   └── resources.json          ← Authoritative resource inventory
│
├── knowledge/                  ← OKF archive (append-only, git-tracked)
│   ├── index.md
│   ├── skills/                 ← 27 skill backups
│   └── agent-rules/            ← 7 agent-rules backups
│
├── .omp/skills/                ← Git-tracked authoritative skill source; distributed via R2/rclone (see "Skill Source of Truth")
│
├── orchestrator/               ← Multi-agent orchestration scripts
├── research/                   ← Experimental code (fastapi_crud, minidb, etc.)
├── site/                       ← Static personal site
│
├── setup-new-device.sh
├── publish-skills.sh
├── rclone-sync-skills.sh
├── sync-skills.sh
├── sync-okf-skills.py
├── import-learned-skills.sh
├── verify.sh
└── ingest-okf-to-hindsight.py
```
