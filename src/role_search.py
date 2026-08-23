#!/usr/bin/env python3
"""Role discovery: rank roles/<role_id>/ROLE.md by keyword overlap against
a free-text query. Directive "Role-Based Agent Spawning" §36/§51.

This is a local script, NOT an `omp role search` subcommand — `omp` is an
external binary with no confirmed mechanism to register new top-level
verbs (program.md §19). It is the closest supported architecture to what
the directive describes, per the "document the limitation, implement the
closest supported architecture" rule.

Usage:
    python3 src/role_search.py "server provisioning"
    python3 src/role_search.py "monitoring" --json
"""
import json
import sys
from pathlib import Path

import frontmatter

from _search_common import fuzzy_overlap_score, tokenize


def load_roles(root: Path) -> list[dict]:
    roles = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        role_file = d / "ROLE.md"
        if not role_file.is_file():
            continue
        try:
            post = frontmatter.load(role_file)
        except Exception:
            continue
        roles.append(post.metadata)
    return roles


def score(query_tokens: set[str], role: dict) -> int:
    haystack = " ".join(
        [
            role.get("name", ""),
            role.get("description", ""),
            " ".join(role.get("allowed_domains") or []),
            " ".join(role.get("preferred_skill_domains") or []),
            " ".join(role.get("mission") or []),
        ]
    )
    return fuzzy_overlap_score(query_tokens, tokenize(haystack))


def main():
    args = [a for a in sys.argv[1:] if a != "--json"]
    as_json = "--json" in sys.argv[1:]
    if not args:
        print("Usage: role_search.py <query> [--json]", file=sys.stderr)
        sys.exit(2)
    query = " ".join(args)
    root = Path(__file__).parent.parent / "roles"
    roles = load_roles(root)
    query_tokens = tokenize(query)

    ranked = sorted(
        ((score(query_tokens, r), r) for r in roles if r.get("type") != "orchestrator"),
        key=lambda x: -x[0],
    )
    ranked = [(s, r) for s, r in ranked if s > 0]

    if as_json:
        print(json.dumps([{"role_id": r["role_id"], "name": r.get("name"), "description": r.get("description"), "score": s} for s, r in ranked], indent=2))
        return

    if not ranked:
        print(f"No role matched '{query}'. Try roles/README.md routing table, or the Leader handles it directly.")
        return
    for s, r in ranked:
        print(f"{r['role_id']:28s} score={s:<3d} {r.get('description', '')}")


if __name__ == "__main__":
    main()
