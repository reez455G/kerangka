---
name: fork-cherry-pick-upstream-subtree
description: "Use when a local repo is a heavily-diverged fork of a public upstream GitHub repo and the user wants to pull a specific feature/subdirectory (e.g. an analysis dashboard, a config module) from upstream into the fork without merging the whole history. Also covers the tsconfig/build-isolation gotcha when grafting a frontend (React/Vite) subproject into a backend (Bun/Node) repo, and how to verify in a memory-constrained sandbox."
---

## When to use
Local repo has diverged significantly from a public upstream (different `git remote origin`, often no shared history reachable by a simple merge). The user wants one or two concrete features grafted in, not a full merge/rebase.

## Procedure

1. **Add a read-only upstream remote** (don't touch `origin`):
   ```bash
   git remote add upstream git@github.com:<owner>/<repo>.git
   git fetch upstream master
   ```

2. **Pull only the specific path(s) needed**, not the whole tree:
   ```bash
   git checkout upstream/master -- path/to/subdir
   git reset   # unstage so it can be reviewed like any other change
   ```

3. **Before grafting code that changes shared type surfaces** (e.g. adding an enum value like a new asset/market/tenant), grep the whole repo for the type's usages and check whether cheaper, already-generic code paths already cover the new case — don't blindly copy a sibling implementation that was heavily hand-tuned for a specific case (e.g. per-asset trading strategy parameters). Duplicating tuned/live parameters under a new name and presenting them as validated is dishonest and risky; prefer wiring the new case into the existing generic path and documenting the gap.

4. **If the grafted subtree is a different toolchain/runtime than the host repo** (e.g. a Vite+React frontend copied into a Bun/Node backend repo), check whether the host's root `tsconfig.json` (or equivalent build config) has an `include`/`exclude` that already isolates the subtree. If not, the root's non-DOM `lib` config will explode into dozens of `Cannot find name 'document'/'window'` style errors the moment root typecheck runs — even if the subtree's OWN `tsconfig.json` is completely fine in isolation. Fix: add the subtree directory to the root config's `exclude`. Verify by running the subtree's own check *and* the root's check separately; both must pass clean.

5. **Verifying a frontend subtree in a resource-constrained sandbox:** a full production bundle (`vite build`) can OOM under memory pressure (swap-heavy sandboxes) even for a small app — this is a resource artifact, not a code bug. Prefer this cheaper verification ladder instead of retrying the full build with a bigger heap:
   - `tsc -b --noEmit` inside the subtree (catches real type errors, near-instant).
   - Start the dev server (`vite`/equivalent) in the background, then `curl -s -o /dev/null -w "%{http_code}"` the local port and inspect the first bytes of the response body to confirm it actually serves the app shell — not just that the process is "ready" per a log-line match (log-ready and port-ready can race).
   - Only attempt a full production build if the user specifically needs the built artifact.

6. **Report clearly what was intentionally NOT ported.** If cherry-picking exposed a latent bug that also exists upstream (e.g. upstream's own root tsconfig has the same gap but nobody noticed because their CI never runs the affected script), say so — it's a genuine finding, not a local-only mistake.

## Pitfalls this avoids
- Merging the grafted subtree's config into the host's typecheck scope silently (breaks `bun run check`/`tsc -b` with dozens of unrelated-looking DOM errors).
- Fabricating "supported" functionality (new asset/tenant/feature) by copying another entity's tuned live parameters and renaming them, without any real validation for the new case.
- Treating an OOM'd production build as a code failure and thrashing retries instead of using a lighter verification method.
- Treating environment-blocked network calls (proxy/TLS interception, no egress) as evidence a feature doesn't exist or is broken — try to verify via web_search or note it as unverifiable and flag the prerequisite explicitly instead of guessing.
