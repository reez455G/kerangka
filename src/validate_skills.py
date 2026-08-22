#!/usr/bin/env python3
"""Validasi skill native (.omp/skills/<name>/SKILL.md) sebelum publish ke R2
(program.md §17). Terpisah dari validate_okf.py (yang memvalidasi kontrak
OKF di knowledge/) karena format frontmatter beda: skill native pakai
`name`/`description`, bukan `id`/`title`/`tags`/`source`/`imported_at`.

Exit 1 jika ada pelanggaran — dipakai sebagai gate wajib oleh publish-skills.sh
sebelum apapun dikirim ke R2. Publish TIDAK BOLEH lanjut jika script ini gagal.
"""
import sys
from pathlib import Path

import frontmatter

REQUIRED = ("name", "description")


def validate(root: Path) -> list[str]:
    errors = []
    if not root.is_dir():
        errors.append(f"{root} tidak ada")
        return errors
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    if not dirs:
        errors.append(f"{root} kosong — tidak ada skill untuk dipublish")
    for d in dirs:
        rel = d.name
        skill_file = d / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"{rel}/: tidak ada SKILL.md")
            continue
        try:
            post = frontmatter.load(skill_file)
        except Exception as e:
            errors.append(f"{rel}/SKILL.md: frontmatter tidak bisa diparse: {e}")
            continue
        for k in REQUIRED:
            if not post.get(k):
                errors.append(f"{rel}/SKILL.md: field wajib '{k}' kosong/tidak ada")
        if not post.content or not post.content.strip():
            errors.append(f"{rel}/SKILL.md: body kosong")
    return errors


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / ".omp" / "skills"
    errors = validate(root)
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        sys.exit(1)
    n = len([p for p in root.iterdir() if p.is_dir()])
    print(f"OK: {n} skill valid")


if __name__ == "__main__":
    main()
