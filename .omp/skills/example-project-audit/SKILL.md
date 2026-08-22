---
name: example-project-audit
description: "EXAMPLE skill: produce a lightweight audit of a project directory (file counts by extension, presence of README/LICENSE/tests, git status if applicable). Use when you want to see a multi-step skill that combines several checks into one report, without touching this repo's real Fossil/R2 mechanics."
---

# Example: Project Audit

The third **dummy/example skill** in this skeleton — no personal
information, no secrets, no private infrastructure, and unrelated to this
repository's actual Skill Source of Truth mechanics (see
`ARCHITECTURE.md`). It exists purely to show a skill that chains several
independent checks into one coherent report.

## Procedure

Given a directory path (default: current directory):

1. **Inventory**: count files by extension (`find . -type f | sed 's/.*\.//' | sort | uniq -c | sort -rn`).
2. **Hygiene checks** — report present/missing for each:
   - `README.md` or `README`
   - `LICENSE` or `LICENSE.md`
   - a recognizable test directory/config (`tests/`, `test/`, `pytest.ini`,
     `package.json` with a `test` script, etc.)
   - `.gitignore`
3. **VCS state** (only if `.git` exists): `git status --porcelain | wc -l`
   for uncommitted-file count, `git log -1 --format=%cd` for last commit
   date.
4. **Report**: a short table — inventory, hygiene checklist, VCS summary.
   Do not make recommendations beyond what was directly observed; if a
   check doesn't apply (e.g. no `.git`), say so rather than guessing.

## Why this is the "third example"

It demonstrates composing multiple `example-file-inspector`-style checks
into a single skill with a clear report shape — the same pattern real
skills like this repository's own mechanism skills (schema validation,
publish gating) use, just without any of the private specifics.
