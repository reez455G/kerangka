"""Shared tokenization/scoring for role_search.py and skill_search.py.

Exact-set token overlap misses morphological variants that matter for
routing (directive §51 requires "server provisioning" -> infrastructure-
automation, but the role text says "servers"/"provision"). Match by
prefix (min 4 chars) instead of exact equality — cheap, dependency-free,
good enough for a keyword router that always has a human/Leader in the
loop to override it.
"""
import re

STOPWORDS = {"a", "an", "the", "to", "for", "of", "and", "or", "on", "in", "with", "is", "how", "do", "we"}
MIN_PREFIX = 4


def tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9\-]+", text.lower()) if t and t not in STOPWORDS}


def _related(a: str, b: str) -> bool:
    if a == b:
        return True
    if len(a) >= MIN_PREFIX and len(b) >= MIN_PREFIX and (a.startswith(b) or b.startswith(a)):
        return True
    return False


def fuzzy_overlap_score(query_tokens: set[str], candidate_tokens: set[str]) -> int:
    return sum(1 for q in query_tokens for c in candidate_tokens if _related(q, c))
