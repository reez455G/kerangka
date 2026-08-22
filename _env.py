#!/usr/bin/env python3
"""_env.py — shared `.env` file parser. Used by model-failover.py and
ingest-okf-to-hindsight.py so both read KEY=value lines the same way instead
of hand-rolling near-identical parsing twice."""


def parse_env_file(path) -> dict:
    """Parse a `.env`-style file (KEY=value per line, `#` comments, blank
    lines skipped) into a dict. Missing file -> empty dict."""
    env = {}
    try:
        with open(path) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return env
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env
