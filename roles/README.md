# Role Registry

This directory is the **Role Registry** for `my-ai-agents`. It defines *who*
operates (responsibility profiles), never *how* to do a task — that's what
`.omp/skills/` is for. See `ARCHITECTURE.md` → "Knowledge & Role Layer" for
the full model and honest scope/limitations of this layer.

## Role ≠ Skill

| | Role | Skill |
|---|---|---|
| Defines | responsibility, scope, delegation boundaries | how to perform one specific task |
| Lives in | `roles/<role_id>/ROLE.md` | `.omp/skills/<name>/SKILL.md` |
| Lifespan | stable, rarely changes | added/edited/versioned independently |
| Loaded | once, when a task is routed to it | discovered per-task, only what's relevant |

A Role has *preferred skill domains* (a hint), never a hardcoded skill list.
Loading every preferred skill for every task defeats the point — see
`src/skill_search.py` for narrowing skills to what a specific task needs.

## Registry

| role_id | Alias | Mission |
|---|---|---|
| [`leader`](leader/ROLE.md) | — | Main-session orchestrator: understand intent, recall, route, delegate, synthesize |
| [`infrastructure-automation`](infrastructure-automation/ROLE.md) | Agen Provisioning | Provision, configure, deploy, automate infrastructure |
| [`business-analyst`](business-analyst/ROLE.md) | Agen Bisnis | Turn business requirements into actionable specs |
| [`network-security`](network-security/ROLE.md) | Agen Jaringan | Network design, connectivity, security hardening |
| [`observability-secops`](observability-secops/ROLE.md) | Agen Pemantau | Monitoring, alerting, incident/security analysis |
| [`backend-api`](backend-api/ROLE.md) | Agen Integrasi | Backend services, APIs, databases, integrations |

## Routing hints (not rigid rules — Hindsight/task analysis may override)

| Trigger keywords | Route to |
|---|---|
| VM provisioning, Docker deployment, Ansible, server setup | `infrastructure-automation` |
| Business requirements, business workflow, user stories, acceptance criteria | `business-analyst` |
| Firewall, VPN, DNS, TLS, network troubleshooting | `network-security` |
| Prometheus, Grafana, alerting, incident, log analysis | `observability-secops` |
| REST API, database integration, webhook, backend service | `backend-api` |
| Multi-domain task, task decomposition, cross-role coordination | `leader` handles directly (does not route to itself) |

## Discovery (how a Leader actually picks a role — see limitations below)

```bash
python3 src/role_search.py "server provisioning"     # -> infrastructure-automation
python3 src/role_search.py "monitoring"               # -> observability-secops
python3 src/role_search.py "API"                      # -> backend-api
python3 src/role_search.py "server provisioning" --json
```

`role_search.py` ranks by keyword overlap against each `ROLE.md`'s
frontmatter (`allowed_domains`, `preferred_skill_domains`, `mission`) plus
the routing table above. It is a **local script**, not an `omp` subcommand
— see the "What this is not" note in `ARCHITECTURE.md` for why.

## Contract fields (every `ROLE.md` frontmatter)

```yaml
role_id: string, unique, kebab-case
name: string, human-readable
alias: string, optional (Indonesian display alias)
description: one-line, used by role_search.py
type: orchestrator | specialist
spawn_mode: persistent | ephemeral
mission: [string, ...]
allowed_domains: [string, ...]
preferred_skill_domains: [string, ...]
memory_filter: { role: <role_id> }
delegation_targets: [role_id, ...]
must_not_own: [string, ...]        # specialists only
```

Validate the whole registry: `python3 src/validate_roles.py`.
