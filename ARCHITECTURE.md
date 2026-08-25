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
│  │   LOCAL RUNTIME COPY│   │                              │   │
│  │   (not canonical)   │   │                              │   │
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

Skill ownership follows **exactly one private canonical source** (Fossil) plus
**one separate public representation** (GitHub) — never two equivalent sources
feeding the same downstream artifact as if merged. `.omp/skills/` in this repo
is a **local runtime copy** (materialized on disk so OMP can discover skills
locally) — it is never itself authoritative, and it is not where a skill's
existence is decided. `private-skills.txt` in `kerangka-private` is the
classification list determining which skills stay Fossil-only vs. also exist
in the public GitHub repo.

---
## Skill Ownership: Source / Representation / Distribution / Runtime

**Updated 2026-08-24**: Fossil is now the SOLE source of truth for ALL
skills — public and private alike. GitHub is a generated mirror, not an
independent authoring location. (Prior model — public skills authored
directly in GitHub — is superseded; see `knowledge/control-plane.md`
Decision 1 for the correction history and Decision 2 for this change.)

Mandated terminology (do not deviate from these terms in this document):

| Term | Role | Is it canonical? |
|---|---|---|
| **Fossil** (`kerangka-private`) | SOLE CANONICAL SOURCE — where ALL skills (public + private) are authored, reviewed, committed, recovered | **Yes** — the only canonical source for skill content, full stop |
| **GitHub** (`kerangka` repo) | GENERATED MIRROR — public skeleton, public docs, and a read-only export of the public-subset skills | No — output of `fossil-export-skills.sh`, never hand-edited |
| **R2** (`omp-skills/` prefix) | RUNTIME DISTRIBUTION — what devices actually pull from | No — a distribution artifact, receives BOTH tiers after publish |
| **`.omp/skills/`** (this repo) | LOCAL RUNTIME COPY — materialized from Fossil, immediately before publish | No — never a source, never edit here and expect it to persist |
| **Hindsight** | LONG-TERM MEMORY — conversational/operational memory, entirely separate concern | N/A — not part of the skill/SCM chain at all |

```
                     ┌──────────────────────────┐
                     │          FOSSIL          │
                     │   SOLE CANONICAL SOURCE   │
                     │  (public + private, ALL)  │
                     │      kerangka-private      │
                     └────────────┬─────────────┘
                                  │ fossil-export-skills.sh
                                  ▼
                    .omp/skills/  ← LOCAL RUNTIME COPY, NOT canonical
                    (materialized from Fossil, this repo)
                                  │
                   ┌──────────────┴──────────────┐
                   ▼                             ▼
          validate_skills.py            git add (public subset only,
          (gate)                        per private-skills.txt exclusion)
                   │                             │
                   ▼                             ▼
          ./publish-skills.sh              git commit + push
                   │ rclone sync                 │
                   │ (PUBLISH_ALLOWED=1)          ▼
                   ▼                       ┌────────────────┐
          ┌──────────────────────┐        │    GITHUB      │
          │          R2           │        │ GENERATED      │
          │   RUNTIME DISTRIBUTION │        │ MIRROR (public │
          │  (private infra —     │        │ subset only)   │
          │   not a public surface)│        └────────────────┘
          └──────────┬─────────────┘  receives BOTH tiers; R2 is NOT a
                     │ rclone pull      public surface, just faster/less
                     │ (omp wrapper,    fragile than git-clone-per-device
                     │  pull-only)
                     ▼
       Device A / B / C  →  .omp/skills/ (LOCAL RUNTIME COPY)  →  OMP
```

**Editing workflow (applies to ALL skills now, public or private)**:
1. Edit the `SKILL.md` directly in `~/kerangka-private` (the Fossil checkout).
2. `fossil commit`.
3. From `~/kerangka`, run `./fossil-export-skills.sh` — materializes into
   `.omp/skills/`, stages + commits the public subset to git.
4. `git push origin main` — updates the GitHub mirror (manual, explicit,
   same reasoning as R2's `PUBLISH_ALLOWED` gate: no silent auto-push).
5. `./publish-skills.sh` — validates, publishes everything (both tiers) to R2.

**Classification**: `private-skills.txt` (in the Fossil checkout) is an
**exclusion list** — every Fossil-tracked skill with a `SKILL.md` is a
public-mirror candidate by default; listing a name there is what keeps it
out of the GitHub mirror. Getting this list wrong leaks private content
publicly, so `fossil-export-skills.sh` is the only script permitted to
decide the public/private split — do not hand-roll a second classifier.

Rules:
- **Fossil is the only authoritative source for ALL skills, public and private.** Modify any skill by editing it in the `kerangka-private` Fossil checkout, then `fossil commit` — never edit the R2 copy, the GitHub mirror, or a device's local runtime copy and expect it to persist as canonical.
- **GitHub is a generated mirror, never a source.** `.omp/skills/` in the `kerangka` git working tree is regenerated by `fossil-export-skills.sh` on every run. A hand-edit made directly to a file under `.omp/skills/` in the `kerangka` git checkout will be silently overwritten the next time the export script runs — it is not a bug, it is the point.
- **`.omp/skills/` is a local runtime copy, never a source.** Same rule applies on every device: pulled content from R2 is disposable and re-derived from Fossil, never edited in place and expected to persist.
- **R2 is distribution, not collaboration, and not a public surface.** It receives BOTH tiers (R2 is private infrastructure the user's own devices pull from — being distributed via R2 doesn't make a skill public). Multiple devices independently pushing to it would recreate the ambiguity this model eliminates.
- **rclone is transport only.** It has no opinion about authority — `rclone-sync-skills.sh pull` is safe for any device at any time; `rclone-sync-skills.sh push` is gated (`PUBLISH_ALLOWED=1`) and only ever invoked by `./publish-skills.sh`. Push uses `rclone sync` (not `copy`) so skills retired locally actually disappear from R2 instead of accumulating forever.
- **Publishing to R2 is explicit.** `./publish-skills.sh` runs `fossil-export-skills.sh --no-git` (materialize only, skip the GitHub-mirror commit step), bridges in anything from `managed-skills/` + `knowledge/` embedded-class not yet committed to Fossil, runs `src/validate_skills.py` as a hard gate over the full local set, writes `.omp/skills/MANIFEST.json`, then pushes to R2. Validation failure = zero R2 change, non-zero exit.
- **Publishing to GitHub is a separate explicit act.** `./fossil-export-skills.sh` (without `--no-git`) stages and commits the public subset locally; you still run `git push` yourself. This mirrors R2's explicit-write-path philosophy — no silent auto-push on session activity.
- **Fossil autosync is OFF** — no automatic commit/push, matching the same "no silent auto-publish on session start" lesson that motivated moving away from git-autopull/push in the first place.
- **Normal `omp` startup only pulls.** The wrapper never pushes local state to R2, never commits to Fossil, never commits/pushes to the GitHub mirror as a session side effect. (Verified 2026-08-24: `omp()` in `~/.zshrc` contains no push call.)
- **Failed pulls never destroy local skills.** `rclone copy --update` only overwrites when the remote is newer; an unreachable R2 leaves existing local skills untouched.
- **Do not edit R2 or the GitHub mirror directly.** Neither is authoritative for either tier.
- **Hindsight is not part of this chain.** Memory (recall/retain/reflect/learn) is a completely separate system — see "Memory Flow" below. Hindsight never synchronizes skills, and skills are never stored inside Hindsight beyond compact metadata references.

## What Is `program.md`? (APPEND-ONLY, mechanically enforced)

`program.md` (repo root) is the operating-model contract — "how should the
agent work" — rewritten from scratch 2026-08-24 after the original was lost
in the `rm -rf` incident. As of 2026-08-25 it is **append-only**, same
contract as `knowledge/`:

- **NEVER** modify existing text in `program.md`.
- **NEVER** delete `program.md`.
- **ONLY** append new sections at the end. To correct something already
  written, append a new dated note explaining the correction — do not
  touch the original text.

This is enforced **mechanically**, not just by convention:
`githooks/pre-commit` (active via `git config core.hooksPath githooks`)
rejects any commit that shrinks `program.md` or changes any of its existing
bytes — only a commit whose new content is a strict superset (old content
as an exact byte-for-byte prefix, plus new content appended) is accepted.
See `program.md` §20 for the full contract text and rationale.

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

## What Is Memory? (LONG-TERM MEMORY — separate from Skill/SCM chain)

Hindsight provides semantic long-term memory via `retain()`, `recall()`, `reflect()` OMP native tools.

- **Bank**: `my-ai-agent` (canonical, same across all devices)
- **URL**: `hindsight.<YOUR_ZONE_DOMAIN>` (via Cloudflare Tunnel `home-lab`) or `localhost:8890` (Mode A)
- **Auth**: `HINDSIGHT_API_TOKEN` (in `.env`, gitignored)
- **LLM backend**: `meta/llama-3.1-70b-instruct` via NVIDIA — use non-reasoning instruct models only
- **Persistence**: embedded Postgres 18.1.0 inside the `hindsight` Docker container, data on the `my-ai-agent_hindsight-data` Docker volume (`unless-stopped` restart policy)

Memory is NOT stored in D1 or KV. D1 stores structured metadata; Hindsight stores semantic content.

**Memory Flow** (independent of the Skill/SCM flow above — these never merge):

```
OMP
 │
 ├── recall() / reflect()   ← read
 └── retain() / learn()     ← write
          │
          ▼
      Hindsight
  (embedded Postgres, Docker volume)
          │
          │ explicit backup (NOT automatic, NOT session-triggered)
          ▼
  ./backup-hindsight.sh
  (hot `pg_dump --format=plain`, gzip)
          │
          ▼
   R2:hindsight-backups/    ← MEMORY BACKUP
   (separate R2 prefix from omp-skills/ — different concern, different lifecycle)
```

**Why `pg_dump` is safe for a hot backup**: Hindsight's embedded database is
standard PostgreSQL 18.1.0 (confirmed via `instance.json` inside the
container). `pg_dump` is PostgreSQL's own supported logical-backup tool and
is explicitly documented as safe to run against a live, writing database —
it takes an MVCC snapshot, not a raw file copy. This is NOT "raw copying the
internal database" (which would risk corruption); it is the standard
supported export mechanism for this database engine. Verified empirically:
`docker restart hindsight` → fact count identical before/after (12,706 facts,
2026-08-24), confirming persistence independent of the backup process.

Restore procedure is documented in `backup-hindsight.sh`'s header comment.

**Hindsight is never part of the skill/SCM chain.** It does not synchronize
skills between devices, does not read from or write to Fossil/GitHub/R2's
`omp-skills/` prefix, and full `SKILL.md` bodies are not stored inside it —
only compact `retain()`/`learn()` summaries and metadata tags
(`[role:...] [project:...] [workflow:...] [skill:...] [status:...]`) are, so
recall stays a cheap index into the skill/role system rather than a second
copy of it.

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
| Agent skills | `.omp/skills/` (Fossil-private + GitHub-public sources; R2 via rclone = distribution) | OMP native provider |
| Static knowledge | `knowledge/` (private entries Fossil-tracked; public entries Git-tracked in kerangka) | OMP native provider |
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
| `publish-skills.sh` | Validate + publish local `.omp/skills/` (Fossil-private + Git-public union) → R2 (the only sanctioned canonical→R2 path) |
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
├── program.md               ← operating-model contract, APPEND-ONLY (mechanically enforced — see below)
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
├── .omp/skills/                ← runtime tree; PRIVATE skills Fossil-tracked here, PUBLIC skills Git-tracked in the separate kerangka repo; distributed via R2/rclone (see "Skill Source of Truth")
│
├── roles/                      ← Role Registry (program.md §19, "Knowledge & Role Layer" below)
│   ├── README.md                   ← index, routing table, Role vs Skill
│   ├── leader/ROLE.md
│   ├── infrastructure-automation/ROLE.md
│   ├── business-analyst/ROLE.md
│   ├── network-security/ROLE.md
│   ├── observability-secops/ROLE.md
│   └── backend-api/ROLE.md
│
├── src/
│   ├── validate_skills.py      ← skill contract gate (publish-skills.sh)
│   ├── validate_okf.py         ← knowledge/ OKF contract gate
│   ├── validate_roles.py       ← role contract gate
│   ├── role_search.py          ← keyword role discovery (routing)
│   ├── skill_search.py         ← keyword skill discovery (duplicate prevention, progressive disclosure)
│   └── _search_common.py       ← shared fuzzy matcher for the two search scripts
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

---

## Knowledge & Role Layer (2026-08-23)

This section documents the role-based orchestration model added on top of
the existing Skill/Hindsight/Fossil/GitHub/R2 architecture. Full design
rationale and honest scope/limitations: `program.md` §19. Durable
decision record: `knowledge/control-plane.md` Decision 15.

### Concepts

| Term | Meaning |
|---|---|
| **Skill** | Stable, reusable **procedure** — how to do one task. `.omp/skills/<name>/SKILL.md`. |
| **Memory** | Reusable **experience/outcome** from a past task. Lives in Hindsight, written via `retain`. |
| **Hindsight** | The recall engine over Memory. Not a second skill repository — see "Non-negotiable separation" below. |
| **Role** | A responsibility profile for an agent — mission, scope, delegation boundaries. `roles/<role_id>/ROLE.md`. **Role ≠ Skill**: a role names *preferred skill domains*, it never bundles the skills themselves. |
| **Agent** | A runtime worker operating under a Role. In this repo, "spawning an agent" means invoking the OMP session's own `task` tool with a role's `ROLE.md` folded into the spawn prompt — see "Leader spawn mechanics." |
| **Workflow** | A coordinated unit of work, usually spanning multiple roles. |
| **Project** | Higher-level context containing workflows (e.g. `my-ai-agents`, `meridian`). |
| **Leader** | The main OMP session itself. Orchestrates: recall → route → spawn → synthesize → retain. `roles/leader/ROLE.md`. Never spawned, never a delegation target. |
| **KnowledgeContext** | The minimal envelope handed to a spawned agent: task + project + role + up to 3 memory summaries + up to 3 skill IDs + constraints. See "Spawn context" below. |

### Non-negotiable separation (unchanged by this layer)

- Hindsight stores **metadata, summaries, experiences, decisions,
  outcomes, recall hints** — never full `SKILL.md` bodies, never raw
  conversation transcripts.
- Canonical skill/knowledge ownership is unchanged: PUBLIC → GitHub
  (`kerangka`), PRIVATE → Fossil (`~/kerangka/my-ai-agents.fossil` —
  colocated inside the public repo checkout, gitignored; see
  `kerangka/.gitignore`).
  R2 remains distribution-only for both tiers. This layer adds a registry
  and discovery scripts on top; it does not touch the publish pipeline.
- A Role is metadata about responsibility, not a second place skill
  bodies get copied into.

### Agent hierarchy

```
                         USER
                           |
                           v
                  +-----------------+
                  |      LEADER      |   (this OMP session)
                  +--------+---------+
                           |
                     task analysis
                           |
                    Hindsight recall  (recall/reflect, query composed
                           |           from task+project+workflow terms)
                     role_search.py   (roles/README.md routing table
                           |           is the fallback/manual path)
                     spawn via `task` tool, ROLE.md + KnowledgeContext
              +------------+------------+------------+------------+
              v            v            v            v            v
     infrastructure-  business-   network-    observability-  backend-
     automation       analyst     security    secops          api
              |            |            |            |            |
              +------------+------------+------------+------------+
                           |
                    compact structured result
                           |
                           v
                         LEADER
                           |
                       synthesis
                           |
                           v
                       retain() outcome (tagged, see "Memory tagging")
                           |
                           v
                          USER
```

### Leader spawn mechanics — what "spawn a role" actually means here

There is no `omp agent spawn <role> <task>` command (see "What this layer
is NOT" below). In practice the Leader:

1. `python3 src/role_search.py "<task keywords>"` (or the routing table in
   `roles/README.md`) picks a `role_id`.
2. `python3 src/skill_search.py "<task keywords>"` narrows to at most 3
   relevant skill names — never the role's entire `preferred_skill_domains`
   list.
3. `recall("<role_id> <project> <task keywords>")` pulls at most 3 relevant
   prior memory summaries.
4. The Leader invokes the `task` tool with:
   - `task`: the concrete assignment, plus the selected role's `ROLE.md`
     body pasted in as the agent's operating charter (mission,
     responsibilities, must-delegate list).
   - `context`: the 3-or-fewer memory summaries, the 3-or-fewer skill
     IDs/names, and any explicit constraints — this is the
     KnowledgeContext envelope. Nothing else from the conversation is
     forwarded.
   - `agent`: `"task"` (general-purpose) unless a more specific built-in
     agent type fits the work better (e.g. `"scout"` for read-only
     investigation, `"reviewer"` for review-only work).
5. The spawned agent returns a compact result; the Leader does not forward
   its full transcript to the user.
6. If the result is durable/reusable knowledge, the Leader calls `retain()`
   using the tagging convention below.

Default token budget (tune with real usage, not guessed): max 3 memories,
max 3 skills, max ~600 tokens of memory-summary text per spawn.

### Spawn context (KnowledgeContext) — worked example

```
Role: Infrastructure & Automation Engineer (roles/infrastructure-automation/ROLE.md)
Task: Deploy Prometheus node exporter to server X.
Project: monitoring
Relevant memory: Previous deployment succeeded using Ansible (retain id …).
Relevant skills: prometheus-disk-full-diagnosis, sar-24h-resource-check
Constraint: existing monitoring network must remain unchanged.
```

### Memory tagging convention

The real `retain` tool takes only `content` + `context` strings — there is
no structured `role_id`/`project_id`/`workflow_id` field in the underlying
API. To keep role-aware recall possible without inventing a schema
Hindsight doesn't have, prefix `content` with a tag line:

```
[role:infrastructure-automation][project:my-ai-agents][workflow:prometheus-deployment][outcome:success]
Skills used: ansible, prometheus, linux-monitoring.
Result: Exporter installed and verified on server X.
```

`recall()` queries then include the same tag tokens as search terms
(e.g. `recall("role:infrastructure-automation prometheus deployment")`).
This is best-effort lexical filtering, not a guaranteed structured filter
— documented honestly rather than claiming a capability the tool doesn't
have.

### Memory write policy

Write memory only for durable/reusable knowledge: architecture decisions,
successful complex workflows, failure+resolution pairs, reusable
procedures, gotchas, role hand-offs, project milestones. Do not retain
greetings, ephemeral debugging chatter, obvious commands, or redundant
context (directive "Memory write policy").

### Skill metadata — optional additive fields

`src/validate_skills.py` still only requires `name`/`description`
(unchanged, and it must stay that way — 126 existing skills depend on
it). New skills MAY additionally declare, for better `skill_search.py`
ranking:

```yaml
---
name: cloudflare-account-ops
description: Safely inspect and manage Cloudflare infrastructure.
domain: infrastructure       # optional, single primary domain
tags: [cloudflare, workers, d1, r2]   # optional
intent: [inspect, deploy, troubleshoot, cleanup]   # optional
scope: [account, worker, database, storage]        # optional
---
```

These fields are never required and existing skills are not retroactively
edited to add them — annotate incrementally, only when it actually helps
discovery for a skill that's hard to find by name/description alone.

### What this layer is NOT (documented limitation, not a silent gap)

- **Not new `omp` CLI verbs.** `omp` (`@oh-my-pi/pi-coding-agent`) is an
  external binary. It has a plugin system (`omp plugin install/list/...`)
  for providers/tools, but no confirmed mechanism to register new
  top-level verbs like `omp role list` or `omp agent spawn`. Building
  that would mean patching a third-party package — a materially
  different, much larger undertaking than this repo's scope. What's
  built instead: `src/role_search.py` / `src/skill_search.py` /
  `src/validate_roles.py`, runnable today, doing the equivalent
  discovery/validation work as local scripts.
- **Not Herdr-based spawning.** Herdr (https://herdr.dev) is a terminal
  pane/workspace multiplexer for long-running, human-visible agent
  sessions — not an RPC-style "spawn worker, get compact result,
  terminate" system. Its own agent guide's rule is explicit: if the
  guide/API doesn't support a requested behavior, document the
  limitation and implement the closest supported architecture rather
  than inventing one. The closest supported architecture already exists
  in this OMP session as the native `task`/`hub` tools, which is what
  "Leader spawn mechanics" above uses. Herdr remains available as an
  escalation path when a task genuinely needs a persistent, human-watched
  pane (e.g. a long infra job the operator wants to observe live) — it is
  not the default mechanism for ephemeral role-scoped spawns.

### Design principles (condensed)

Don't remember everything — remember what's useful. Don't load every
skill — load what's relevant to the current task. Don't create a skill
if one already exists (`skill_search.py` first). Don't duplicate skill
bodies into memory. Don't spawn an agent for trivial work. Don't load a
role's entire skill list into a child agent. Memory and delegation are
optimization layers — Hindsight being unavailable, or no specialist role
fitting, must never block the Leader from doing the work itself.
