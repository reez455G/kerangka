#!/usr/bin/env python3
"""Validasi kontrak OKF (program.md §2 & §5). Exit 1 jika ada pelanggaran."""
import sys
from pathlib import Path

import frontmatter

# Pra-kontrak, §5.1 melarang edit frontmatter existing → dikecualikan dari source/imported_at
GRANDFATHERED = {"panduan_layanan.md", "skema_database.md"}
REQUIRED = ("id", "title", "tags")
REQUIRED_FULL = ("source", "imported_at")


def validate(root: Path) -> list[str]:
    errors = []
    files = sorted(root.rglob("*.md"))
    index_path = root / "index.md"
    index_text = index_path.read_text() if index_path.exists() else ""
    if not index_text:
        errors.append(f"{root}/index.md tidak ada atau kosong")
    seen_ids = {}
    for f in files:
        rel = f.relative_to(root).as_posix()
        try:
            post = frontmatter.load(f)
        except Exception as e:
            errors.append(f"{rel}: frontmatter tidak bisa diparse: {e}")
            continue
        if rel == "index.md":
            continue  # index = meta, cukup bisa diparse
        for k in REQUIRED:
            if not post.get(k):
                errors.append(f"{rel}: field wajib '{k}' kosong/tidak ada")
        if f.name not in GRANDFATHERED:
            for k in REQUIRED_FULL:
                if not post.get(k):
                    errors.append(f"{rel}: field wajib '{k}' kosong/tidak ada (file baru wajib lengkap)")
        fid = post.get("id")
        if fid:
            if fid in seen_ids:
                errors.append(f"{rel}: id '{fid}' duplikat dengan {seen_ids[fid]}")
            seen_ids[fid] = rel
        if f.name not in index_text:
            errors.append(f"{rel}: tidak terdaftar di index.md (kontrak §5.5)")
    return errors


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "knowledge"
    errors = validate(root)
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        sys.exit(1)
    print(f"OK: {len(list(root.rglob('*.md')))} file valid")


if __name__ == "__main__":
    main()
