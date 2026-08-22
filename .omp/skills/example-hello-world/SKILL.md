---
name: example-hello-world
description: "EXAMPLE skill demonstrating the minimum shape of a my-ai-agents native skill (frontmatter + body). Use when you want to see the simplest possible skill before writing your own."
---

# Example: Hello World

This is a **dummy/example skill** shipped with the public my-ai-agents
skeleton so a fresh clone demonstrates the skill system without exposing any
personal skills. It contains no personal information, no secrets, and no
private infrastructure.

## What a skill is

A skill is a `SKILL.md` file under `.omp/skills/<name>/` with two parts:

1. **Frontmatter** (the `---`-delimited block above) — exactly two required
   fields:
   - `name`: must match the directory name
   - `description`: written so an agent can decide, from the description
     alone, whether this skill is relevant to the current task. Front-load
     the trigger conditions ("Use when...").
2. **Body** — the actual instructions, in Markdown. Keep it procedural and
   specific; this is what the agent reads once it decides the skill applies.

## Minimal example

```
"Say hello" → an agent with this skill loaded would respond: "Hello, world!"
```

That's it — no code, no external tool required. See
`example-file-inspector` for a skill that actually does something, and
`example-project-audit` for one that combines multiple steps.
