---
name: verify-before-deleting-dead-code
description: "Use before deleting anything labeled 'dead code', 'unused binding', or 'zero callers' — including claims from a prior audit or subagent — to avoid breaking live functionality on a false premise."
---

## Why

Instructions (or prior audit reports, including your own subagent scouts) sometimes assert something is "dead" or "unused" based on a shallow or literal grep. Deleting on that assumption can break live functionality — the opposite of a cleanup. Naive greps miss:

- String-concatenated calls: `api('GET', 'foo.php?id=' + id + '&mode=1')` won't match a literal-string search for `mode=1` if the grep pattern assumed a quoted literal.
- Attributes/keys consumed by a compiler or runtime elsewhere in the codebase (e.g. template-engine hint attributes read by a separate loader script), not by the file that defines them.
- Identifiers produced via object shorthand or spread (`{ a, b, ...rest }`) rather than explicit `key: value`, which simple regex key-extraction misses.

## Procedure before deleting anything called "dead"

1. **Grep the consumer, not just the definer.** If X is a template attribute/hint, grep the file that *parses* the template (the runtime/compiler), not just the file that declares X.
2. **Grep loosely, then confirm tightly.** Search for the bare identifier/string across the whole relevant surface (not one exact literal pattern) to catch string-concatenated or shorthand usages.
3. **Cross-reference systematically for template bindings.** Extract every `{{ identifier }}` (or equivalent) used in a template, and extract every place identifiers are *produced* (object literal keys, shorthand properties, spreads, class fields) in the logic that renders it. Diff the two sets — don't trust a first-pass regex; re-check any "orphan" hit by hand, since spread/shorthand syntax produces false positives constantly.
4. **Never trust a prior audit's "zero callers" claim at face value**, even your own from earlier in the same session — re-verify with a fresh, broader search before acting on it, especially before an irreversible-feeling delete.
5. **If truly dead after verification, delete freely** — the point isn't to avoid deleting, it's to avoid deleting live code on a false premise. Report what you verified and how.

## Output when you push back

If a delete request is based on a false "dead" premise: do the safe part of the request, decline only the unverified part, and show the exact grep/cross-reference evidence for why it's live — not just an assertion.
