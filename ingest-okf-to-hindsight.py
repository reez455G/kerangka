#!/usr/bin/env python3
"""ingest-okf-to-hindsight.py — mirror knowledge/**/*.md (OKF, program.md §2/§5)
into Hindsight as retrievable memory, so recall()/reflect() surface OKF content
alongside dynamic memory in one query instead of only via omp's native skill
provider (which is cwd-scoped to this repo and only loads full SKILL.md bodies,
not fact-level semantic search).

Idempotent: knowledge/ is append-only (program.md §5 forbids editing existing
files), so a file's content never changes once ingested. Each OKF file becomes
one Hindsight document keyed by document_id=f"okf:{frontmatter id}"; a file is
skipped if that document_id already exists in the bank. New files (or files
added after this script last ran) get ingested; nothing is ever re-ingested or
overwritten.

Run manually, or via sync-skills.sh (auto-runs after manage_skill/knowledge
changes). Requires HINDSIGHT_API_URL/HINDSIGHT_API_TOKEN/HINDSIGHT_BANK_ID in
.env (same as verify.sh). Retains synchronously (waits for completion) so a
re-run immediately after always sees the just-ingested documents and never
double-submits — safe to invoke repeatedly. Uses python-frontmatter (already
a requirements.txt dependency via validate_okf.py) and the shared _env.py
parser (also used by model-failover.py).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import frontmatter

from _env import parse_env_file

REPO = Path(__file__).parent
KNOWLEDGE = REPO / "knowledge"


def api_call(url, token, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", "curl/8.0.0")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def existing_okf_document_ids(base_url, bank_id, token):
    """Best-effort scan of already-ingested okf: document_ids (paginated)."""
    ids = set()
    offset = 0
    limit = 100
    while True:
        url = f"{base_url}/v1/default/banks/{bank_id}/documents?limit={limit}&offset={offset}"
        try:
            data = api_call(url, token)
        except Exception as e:
            print(f"WARN: could not list existing documents: {e}", file=sys.stderr)
            return ids
        items = data.get("items") or data.get("documents") or []
        for item in items:
            doc_id = item.get("id") or (item.get("retain_params") or {}).get("document_id")
            if doc_id and doc_id.startswith("okf:"):
                ids.add(doc_id)
        if len(items) < limit:
            break
        offset += limit
    return ids


def main():
    env = parse_env_file(REPO / ".env")
    base_url = os.environ.get("HINDSIGHT_API_URL", env.get("HINDSIGHT_API_URL", "http://localhost:8890"))
    token = os.environ.get("HINDSIGHT_API_TOKEN", env.get("HINDSIGHT_API_TOKEN"))
    bank_id = os.environ.get("HINDSIGHT_BANK_ID", env.get("HINDSIGHT_BANK_ID", "my-ai-agent"))
    if not token:
        print("ERROR: HINDSIGHT_API_TOKEN not set (check .env)", file=sys.stderr)
        return 1

    known = existing_okf_document_ids(base_url, bank_id, token)
    print(f"Already ingested: {len(known)} okf documents")

    files = sorted(KNOWLEDGE.rglob("*.md"))
    to_ingest = []
    for f in files:
        if f.name == "index.md":
            continue
        try:
            post = frontmatter.load(f)
        except Exception as e:
            print(f"SKIP {f.relative_to(KNOWLEDGE)}: frontmatter parse error: {e}", file=sys.stderr)
            continue
        okf_id = post.get("id")
        if not okf_id:
            print(f"SKIP {f.relative_to(KNOWLEDGE)}: no OKF id", file=sys.stderr)
            continue
        doc_id = f"okf:{okf_id}"
        if doc_id in known:
            continue
        body = post.content.strip()
        if not body:
            print(f"SKIP {f.relative_to(KNOWLEDGE)}: empty body after frontmatter", file=sys.stderr)
            continue
        tags = ["source:okf", "project:my-ai-agents"]
        for t in (post.get("tags") or []):
            tags.append(f"okf-tag:{t}")
        to_ingest.append({
            "content": body,
            "context": post.get("title") or okf_id,
            "document_id": doc_id,
            "timestamp": "unset",  # static reference material, not a dated event
            "tags": tags,
        })

    if not to_ingest:
        print("Nothing new to ingest.")
        return 0

    print(f"Ingesting {len(to_ingest)} new OKF document(s) in chunks of 2 synchronously to avoid Cloudflare timeouts...")
    url = f"{base_url}/v1/default/banks/{bank_id}/memories"
    chunk_size = 2
    for i in range(0, len(to_ingest), chunk_size):
        if i > 0:
            print("  Sleeping 3s to avoid LLM rate limits...")
            time.sleep(3)
        chunk = to_ingest[i:i + chunk_size]
        chunk_ids = [d["document_id"] for d in chunk]
        print(f"  -> Ingesting chunk: {chunk_ids}")
        req = urllib.request.Request(
            url,
            data=json.dumps({"items": chunk, "async": False}).encode(),
            method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "curl/8.0.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                result = json.loads(resp.read())
                print(f"     ✅ Done: {json.dumps(result)[:150]}...")
        except urllib.error.HTTPError as e:
            print(f"ERROR: ingest failed for chunk {chunk_ids}: {e.code} {e.read().decode()}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
