#!/usr/bin/env python3
"""Skill discovery: rank .omp/skills/<name>/SKILL.md by keyword overlap
against a free-text query. Directive §26/§33/§36/§56/§57.

Two purposes:
  1. Narrow which skills a spawned agent actually needs (progressive
     disclosure: metadata first, full body only via `--inspect`).
  2. Duplicate-skill prevention: run this BEFORE creating a new skill —
     if something scores highly, extend/reuse it instead of duplicating
     (directive §33).

Reads the optional additive frontmatter fields documented in
ARCHITECTURE.md "Knowledge & Role Layer" (`domain`, `tags`, `intent`,
`scope`) when present, but works fine on skills that only have the
required `name`/`description` (src/validate_skills.py's baseline) —
these fields are 100% optional, never required.

Usage:
    python3 src/skill_search.py "cloudflare"
    python3 src/skill_search.py "cloudflare" --json
    python3 src/skill_search.py --inspect cloudflare-account-ops
"""
import json
import sys
from pathlib import Path

import frontmatter

from _search_common import fuzzy_overlap_score, tokenize


def load_skills(root: Path) -> list[tuple[str, dict, str]]:
    skills = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        skill_file = d / "SKILL.md"
        if not skill_file.is_file():
            continue
        try:
            post = frontmatter.load(skill_file)
        except Exception:
            continue
        skills.append((d.name, post.metadata, post.content))
    return skills


def score(query_tokens: set[str], meta: dict) -> int:
    haystack = " ".join(
        [
            meta.get("name", ""),
            meta.get("description", ""),
            " ".join(meta.get("tags") or []),
            meta.get("domain", "") or "",
            " ".join(meta.get("intent") or []),
            " ".join(meta.get("scope") or []),
        ]
    )
    return fuzzy_overlap_score(query_tokens, tokenize(haystack))


def main():
    root = Path(__file__).parent.parent / ".omp" / "skills"
    argv = sys.argv[1:]
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]

    if argv and argv[0] == "--inspect":
        if len(argv) < 2:
            print("Usage: skill_search.py --inspect <skill-name>", file=sys.stderr)
            sys.exit(2)
        target = argv[1]
        skill_file = root / target / "SKILL.md"
        if not skill_file.is_file():
            print(f"ERROR: {target} not found under {root}", file=sys.stderr)
            sys.exit(1)
        post = frontmatter.load(skill_file)
        if as_json:
            print(json.dumps({"name": post.get("name"), "description": post.get("description"), "metadata": post.metadata, "body": post.content}, indent=2))
        else:
            print(f"# {post.get('name')}\n{post.get('description')}\n\n{post.content}")
        return

    if not argv:
        print("Usage: skill_search.py <query> [--json] | skill_search.py --inspect <name>", file=sys.stderr)
        sys.exit(2)

    query = " ".join(argv)
    query_tokens = tokenize(query)
    skills = load_skills(root)
    ranked = sorted(((score(query_tokens, meta), name, meta) for name, meta, _ in skills), key=lambda x: -x[0])
    ranked = [(s, name, meta) for s, name, meta in ranked if s > 0]

    if as_json:
        print(json.dumps([{"name": name, "description": meta.get("description"), "score": s} for s, name, meta in ranked], indent=2))
        return

    if not ranked:
        print(f"No skill matched '{query}'. Nothing to reuse — safe to create a new one (directive §33).")
        return
    print(f"Found {len(ranked)} matching skill(s) — reuse/extend before creating a new one (directive §33):")
    for s, name, meta in ranked[:10]:
        print(f"{name:40s} score={s:<3d} {meta.get('description', '')}")


if __name__ == "__main__":
    main()
