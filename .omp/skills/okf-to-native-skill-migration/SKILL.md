---
name: okf-to-native-skill-migration
description: "Migrate an OKF-wrapped knowledge corpus (markdown files with an outer id/title/tags/source/imported_at frontmatter block, git-tracked under a knowledge/ directory) into native provider/skills/name/SKILL.md discovery format. Use when a custom knowledge-loader script (like knowledge_okf.py) is deleted or deprecated and the underlying .md content needs to become consumable again by a native skill-discovery mechanism (e.g. OMP's .omp/skills/, Claude Code's skills/, etc)."
---

## When this applies

A repo has a `knowledge/` (or similarly named) directory of markdown files, each wrapped in an OKF-style outer frontmatter block:

```
---
id: skill-foo
title: "Foo"
tags: [skill, ...]
source: ~/original/path/SKILL.md
imported_at: 2026-07-07
---
<body>
```

Some of these files were originally real `SKILL.md` files (imported from another skills repo) and therefore have a SECOND, embedded frontmatter block immediately after the OKF wrapper closes:

```
---
id: skill-foo
...
---
---
name: foo
description: ...
---
# Foo
...
```

Others (agent-rules / CLAUDE.md / AGENTS.md imports, manual profile docs) never had a native frontmatter and go straight from the OKF wrapper into a `# Heading`.

## Procedure

1. **Classify every file first, do not assume by counting `---` occurrences.** Body content can contain incidental horizontal rules (`---`) that inflate a naive dash-count. Instead, walk lines: find where the OKF wrapper closes (second `---`), skip up to one blank line, and check whether the NEXT line is exactly `---`. If yes -> embedded native frontmatter present ("EMBEDDED"). If no -> bare body ("BARE").
2. **EMBEDDED files: pure mechanical strip.** Take everything from that second `---` onward (native frontmatter + body, byte-for-byte) and write it directly to `<skills-root>/<name>/SKILL.md`, where `<name>` is the `name:` field already present in the embedded frontmatter. Do this with a small Python script over all files at once — do not hand-edit each one, and do not paraphrase/rewrite the content.
3. **BARE files: need synthesized frontmatter.** Read the full file, then author a `name:` (kebase-case, derived from the OKF `id` minus its prefix like `skill-`/`agent-rules-`) and a `description:` (one sentence, third person, ending in explicit "Use when..." trigger conditions) by hand. Preserve the original body verbatim underneath — do not summarize or trim large reference docs (a 400+ line engineering manual should migrate at full length, not be condensed).
4. **Verify byte-parity on EMBEDDED files** with `diff` (or equivalent) against a naive re-read after writing, and grep the destination tree for the expected file count before declaring done.
5. **Smoke test discovery**, not just file existence: spawn a fresh headless session in the target repo's cwd and ask it to list its discovered skill/tool catalog, then grep for the specific new names. A file existing on disk does not prove the discovery mechanism actually picked it up (config gates, cwd-walk-up rules, etc. can silently exclude it).
6. **Do not delete the source `knowledge/`-style archive** unless explicitly asked — treat the migration as adding a consumable copy, not a move. If the source has its own append-only/validation contract, leave that contract's enforcement script untouched and re-run it after the migration to confirm the archive is still internally consistent.
7. **Document the gap**: unlike a managed-skill-style sync script, this migration is a one-time snapshot. If the source archive can still grow (new files appended), explicitly note in the project's contract doc that there is no automated sync for it yet, so it doesn't silently drift out of sync with the native skills copy.
