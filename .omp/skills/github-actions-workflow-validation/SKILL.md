---
name: github-actions-workflow-validation
description: "Validate and debug GitHub Actions workflow YAML before pushing, especially conditional publish/release jobs gated on optional secrets. Use when authoring or editing .github/workflows/*.yml, when a workflow run shows a weird name (the file path itself) with zero jobs, or when gating a job/step on whether a secret is configured."
---

# GitHub Actions workflow validation

## The `secrets`-in-`if:` trap

`secrets` cannot be referenced in a job-level (or any pre-run-evaluated) `if:`
expression:

```yaml
# BROKEN -- rejects the whole workflow file at parse time
jobs:
  publish:
    if: ${{ secrets.CARGO_REGISTRY_TOKEN != '' }}
```

GitHub responds with "Unrecognized named-value: secrets" and refuses to parse
the *entire* file. In the Actions UI this shows up as a run named after the
file path itself (e.g. `.github/workflows/release.yml`) instead of the
workflow's declared `name:`, with **zero jobs** and `conclusion: failure` --
that combination (weird run name + 0 jobs) is the diagnostic tell that it's a
parse failure, not a job failure. `GET /repos/{owner}/{repo}/actions/runs/{id}/jobs`
returns `{"total_count": 0, "jobs": []}` for these runs.

**Fix:** map the secret to a job-level `env:`, then gate an individual
**step's** `if:` on that env var instead of gating the whole job:

```yaml
jobs:
  publish:
    runs-on: ubuntu-latest
    env:
      CARGO_REGISTRY_TOKEN: ${{ secrets.CARGO_REGISTRY_TOKEN }}
    steps:
      - uses: actions/checkout@v4       # always runs, cheap
      - run: cargo publish --locked
        if: ${{ env.CARGO_REGISTRY_TOKEN != '' }}   # only this step is gated
```

This lets the job legitimately report `success` (with the gated step showing
`skipped`) when the secret isn't configured yet, instead of failing the
release or silently refusing to parse.

## Validate with `actionlint`, not just PyYAML

`import yaml; yaml.safe_load(open(f))` only catches generic YAML syntax
errors. It happily parses `if: ${{ secrets.X != '' }}` because that's valid
YAML -- it just isn't valid *GitHub Actions*. Use
[actionlint](https://github.com/rhysd/actionlint) instead, which knows
GitHub's actual expression-scoping and schema rules:

```sh
curl -fsSL -o /tmp/al.tar.gz https://github.com/rhysd/actionlint/releases/download/v1.7.7/actionlint_1.7.7_linux_amd64.tar.gz
tar -xzf /tmp/al.tar.gz -C /tmp actionlint
/tmp/actionlint .github/workflows/*.yml
```

Run this before every push that touches a workflow file. Note: actionlint's
runner-label list can lag behind GitHub's actual offerings (e.g. it may not
yet know about `macos-15-intel`) -- a flagged unknown label is worth a quick
cross-check against an actually-successful run using that label before
assuming it's a real error.

## Asset glob gotchas

When collecting release assets for checksumming, remember filenames may use
either a hyphen or a dot after a common prefix (`clipf-x86_64-...tar.gz` vs
`clipf.bash`/`clipf.zsh`). `sha256sum clipf-*` silently excludes the dotted
ones. Use the broader `clipf*` glob (verify it doesn't accidentally catch the
SHA256SUMS file itself, which it won't since that name doesn't start with the
prefix) -- and after any release, actually download the published assets and
cross-check them against SHA256SUMS end to end rather than trusting the
workflow logic by inspection.
