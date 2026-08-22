---
name: cli-tool-skill-authoring
description: "Write a SKILL.md that lets any CLI agent correctly discover and operate an existing command-line tool. Use when asked to \"add a skill for X tool\", \"make this CLI agent-operable\", or document a binary/script for future agent sessions."
---

## Goal

Produce a SKILL.md that a *different* agent, with zero prior context on the tool, can read once and then use the tool correctly and safely.

## Structure that works

1. **Frontmatter** — `name` (kebab-case, matches the tool) and `description` (one line, front-load *when to use it*, not what it is — this is what discovery matches against).
2. **One-paragraph mental model** — what the tool actually does and its one core design decision (e.g. "picks the clipboard mechanism automatically", "never touches disk"). Not a feature list.
3. **"Before using it" preflight** — how to confirm the tool is installed/available and how to self-diagnose common environment issues (a `--check`/`--doctor`/`--version` equivalent), plus the install command if it's missing.
4. **Core usage** — the 2-4 invocation shapes that cover 90% of real use, as runnable examples, not a syntax diagram.
5. **Agent-relevant flags table** — NOT the full `--help` dump. Only flags an agent would actually need to reach for, each with *when* to use it, not just what it does. Omit flags aimed at interactive humans (like custom color themes).
6. **Exit codes / failure modes** — especially non-obvious ones (e.g. "exit 3 means refused-not-failed, here's the real fix"). Agents need to branch on these programmatically.
7. **The one sharp edge** — every real tool has exactly one thing that silently does the wrong thing if you don't know about it (a size limit that truncates silently, a flag that only works in one mode, a default that changes based on environment). Give it its own section, not a buried bullet.
8. **Composability recipes** — if the tool is meant to be piped/combined with standard tools (sed/awk/grep/tail, jq, xargs), show 3-5 concrete one-liners rather than describing the pattern abstractly.
9. **How to verify it worked** — don't let the agent trust a bare `exit 0`. State what to actually check (re-read the output, run a paired read-back command, grep a log) to confirm the side effect really happened.

## Non-negotiable process

- **Every operational claim MUST be grounded in the tool's actual source or an actual command run before it goes in the doc.** Do not write "X will warn about Y" from memory or plausible inference — grep the source for where that warning would be emitted, or run the command and paste the real output. A plausible-sounding but false claim in an agent-facing skill doc causes silent downstream failures, because the next agent will trust it and act on it without re-verifying.
- Keep the flags table to what's actually needed; a full `--help` dump duplicates `--help` and gives the reading agent nothing extra.
- If the tool has an environment-variable equivalent for common flags, list it — agents scripting non-interactively often prefer env vars.
- Link back to full docs/README at the end rather than duplicating everything.
