---
name: compare-fork-vs-upstream-github
description: "Use when asked to compare a local repo against its upstream/original GitHub source (e.g. \"bandingkan dengan repo ini: github.com/...\", \"how does this differ from upstream\", \"compare our fork to the original\") to find concrete kelebihan/kekurangan without cloning the remote repo."
---

## When to use
User gives a GitHub URL and asks how the current local repo compares to it (fork vs upstream, "what did we add/lose", pros/cons of each side).

## Key capability
The `read` tool auto-resolves plain `https://github.com/...` URLs to specialized GitHub methods — no cloning, no `gh` CLI needed:
- `read https://github.com/<owner>/<repo>` → repo overview (README, top-level file tree, stars/forks/language)
- `read https://github.com/<owner>/<repo>/tree/<branch>/<subdir>` → directory listing for that subdir (use this to defeat "N files elided" truncation on large trees — drill into `utils/`, `engine/`, etc. individually)
- `read https://github.com/<owner>/<repo>/blob/<branch>/<path>` or the raw.githubusercontent.com URL → fetches raw file content (works even via the `blob` URL, tool resolves to `github-raw`)
- `read https://github.com/<owner>/<repo>/commits/<branch>` → commit history (proves last-updated recency / maintenance activity)

## Workflow
1. Fetch the upstream repo root overview first — compare README/package.json name/description against the local repo's own README/package.json to confirm fork lineage (often the local repo's README/docs are literal copies).
2. Fetch upstream's key manifest/config files (package.json, main registry/index files like a strategy or plugin registry) raw, and diff mentally against the local equivalents you already read this session.
3. If the initial tree listing shows "…N more files elided", re-fetch specific subdirectories via `/tree/<branch>/<subdir>` rather than trying to get the full tree in one call.
4. For git-hygiene claims about the LOCAL repo (e.g. "are these files actually committed?"), verify with `git ls-files`, `git status --porcelain`, `git log -1`, `git remote -v` — don't assume from a plain directory listing, since gitignored working-tree clutter looks identical to tracked bloat until checked.
5. Build one comparison table with rows = concrete dimensions (feature count, telemetry, tests, config surface, docs freshness, git hygiene, popularity/maintenance) rather than a vague prose summary — this is what actually answers "kelebihan dan kekurangan masing-masing".

## Pitfall
Don't rely solely on the truncated `tree` listing for file counts/structure claims — it silently elides files past a limit. Always drill into subdirectories that matter for the comparison.
