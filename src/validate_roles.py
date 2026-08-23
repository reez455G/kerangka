#!/usr/bin/env python3
"""Validasi Role Registry (roles/<role_id>/ROLE.md) — directive
"OMP Knowledge Layer + Role-Based Agent Spawning" §50 acceptance test.

Terpisah dari validate_skills.py (skill != role, program.md §19) dan
validate_okf.py (OKF frontmatter beda field). Role adalah profil
tanggung jawab untuk sebuah agent, bukan prosedur — lihat roles/README.md.

Exit 1 jika ada pelanggaran kontrak.
"""
import sys
from pathlib import Path

import frontmatter

REQUIRED_ALL = ("role_id", "name", "description", "type", "spawn_mode", "mission")
REQUIRED_SPECIALIST_ONLY = ("delegation_targets", "must_not_own")
VALID_TYPES = ("orchestrator", "specialist")
VALID_SPAWN_MODES = ("persistent", "ephemeral")


def validate(root: Path) -> list[str]:
    errors = []
    if not root.is_dir():
        errors.append(f"{root} tidak ada")
        return errors
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    if not dirs:
        errors.append(f"{root} kosong — tidak ada role terdaftar")
    seen_ids = set()
    for d in dirs:
        rel = d.name
        role_file = d / "ROLE.md"
        if not role_file.is_file():
            errors.append(f"{rel}/: tidak ada ROLE.md")
            continue
        try:
            post = frontmatter.load(role_file)
        except Exception as e:
            errors.append(f"{rel}/ROLE.md: frontmatter tidak bisa diparse: {e}")
            continue

        for k in REQUIRED_ALL:
            if not post.get(k):
                errors.append(f"{rel}/ROLE.md: field wajib '{k}' kosong/tidak ada")

        role_id = post.get("role_id")
        if role_id and role_id != rel:
            errors.append(f"{rel}/ROLE.md: role_id '{role_id}' tidak cocok dengan nama direktori")
        if role_id:
            if role_id in seen_ids:
                errors.append(f"{rel}/ROLE.md: role_id '{role_id}' duplikat")
            seen_ids.add(role_id)

        rtype = post.get("type")
        if rtype and rtype not in VALID_TYPES:
            errors.append(f"{rel}/ROLE.md: type '{rtype}' tidak valid (harus {VALID_TYPES})")

        spawn_mode = post.get("spawn_mode")
        if spawn_mode and spawn_mode not in VALID_SPAWN_MODES:
            errors.append(f"{rel}/ROLE.md: spawn_mode '{spawn_mode}' tidak valid (harus {VALID_SPAWN_MODES})")

        if rtype == "specialist":
            for k in REQUIRED_SPECIALIST_ONLY:
                if not post.get(k):
                    errors.append(f"{rel}/ROLE.md: specialist wajib punya field '{k}'")
            targets = list(post.get("delegation_targets") or [])
            if role_id in targets:
                errors.append(f"{rel}/ROLE.md: delegation_targets tidak boleh memuat role_id sendiri")

        if not post.content or not post.content.strip():
            errors.append(f"{rel}/ROLE.md: body kosong")

    # leader must never appear as a delegation target of any specialist
    for d in dirs:
        role_file = d / "ROLE.md"
        if not role_file.is_file():
            continue
        try:
            post = frontmatter.load(role_file)
        except Exception:
            continue
        if "leader" in list(post.get("delegation_targets") or []):
            errors.append(f"{d.name}/ROLE.md: 'leader' tidak boleh jadi delegation_target (Leader tidak menerima routing)")

    return errors


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "roles"
    errors = validate(root)
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        sys.exit(1)
    n = len([p for p in root.iterdir() if p.is_dir()])
    print(f"OK: {n} role valid")


if __name__ == "__main__":
    main()
