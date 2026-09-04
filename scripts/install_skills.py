#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


NAMESPACE_MARKER = "namespace: manga-studio"


def load_manifest(install_root: Path) -> Dict[str, Any]:
    path = install_root / "manifests" / "manga-skills.json"
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    skills = manifest.get("skills")
    if not isinstance(skills, list):
        raise ValueError("manifest skills must be an array")
    names = [item.get("name") for item in skills if isinstance(item, dict)]
    if len(names) != len(skills) or not all(isinstance(name, str) and name for name in names):
        raise ValueError("every manifest skill must have a non-empty name")
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"duplicate Manga Studio skill names: {', '.join(duplicates)}")
    if len(names) != 17:
        raise ValueError(f"manifest must list exactly 17 Manga Studio skills; found {len(names)}")
    return manifest


def verify_skill(source: Path, expected_name: str, expected_version: str) -> List[str]:
    errors: List[str] = []
    skill_file = source / "SKILL.md"
    if not skill_file.is_file():
        return [f"missing SKILL.md: {skill_file}"]
    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        errors.append(f"invalid frontmatter start: {skill_file}")
    if f"name: {expected_name}\n" not in text:
        errors.append(f"frontmatter name does not match manifest: {skill_file}")
    if NAMESPACE_MARKER not in text:
        errors.append(f"missing Manga Studio namespace marker: {skill_file}")
    if f"version: {expected_version}" not in text and f'version: "{expected_version}"' not in text:
        errors.append(f"frontmatter version does not match manifest: {skill_file}")
    if "description:" not in text:
        errors.append(f"missing description: {skill_file}")
    return errors


def is_managed_manga_skill(destination: Path) -> bool:
    skill_file = destination / "SKILL.md"
    if destination.is_symlink():
        try:
            skill_file = destination.resolve() / "SKILL.md"
        except OSError:
            return False
    return skill_file.is_file() and NAMESPACE_MARKER in skill_file.read_text(encoding="utf-8")


def plan_install(install_root: Path, destination_root: Path, mode: str) -> Tuple[List[Dict[str, str]], List[str]]:
    manifest = load_manifest(install_root)
    plan: List[Dict[str, str]] = []
    errors: List[str] = []
    for item in manifest["skills"]:
        name = item["name"]
        version = item["version"]
        source = install_root / "skills-src" / name
        destination = destination_root / name
        errors.extend(verify_skill(source, name, version))
        if destination.exists() or destination.is_symlink():
            if is_managed_manga_skill(destination):
                action = "replace"
            else:
                action = "reject"
                errors.append(f"refusing to overwrite existing non-Manga skill: {destination}")
        else:
            action = "create"
        plan.append({
            "action": action,
            "name": name,
            "source": str(source),
            "destination": str(destination),
            "mode": mode,
        })
    return plan, errors


def execute_install(plan: List[Dict[str, str]], destination_root: Path, mode: str) -> Path | None:
    replacements = [item for item in plan if item["action"] == "replace"]
    backup_root: Path | None = None
    if replacements:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_root = destination_root / ".manga-studio-backups" / timestamp
        backup_root.mkdir(parents=True, exist_ok=False)
    destination_root.mkdir(parents=True, exist_ok=True)
    for item in plan:
        if item["action"] == "reject":
            continue
        source = Path(item["source"])
        destination = Path(item["destination"])
        if item["action"] == "replace":
            assert backup_root is not None
            shutil.move(str(destination), str(backup_root / item["name"]))
        if mode == "symlink":
            destination.symlink_to(source, target_is_directory=True)
        else:
            shutil.copytree(source, destination)
    registry = {
        "schema_version": "1.0.0",
        "namespace": "manga-studio",
        "mode": mode,
        "install_root": str(destination_root),
        "skills": [item["name"] for item in plan if item["action"] != "reject"],
        "backup_root": str(backup_root) if backup_root else None,
    }
    registry_path = destination_root / ".manga-studio-install.json"
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return backup_root


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install only manifest-listed Manga Studio skills.")
    parser.add_argument("--scope", choices=["user"], required=True)
    parser.add_argument("--mode", choices=["symlink", "copy"], required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--destination-root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    install_root = Path(__file__).resolve().parents[1]
    destination_root = args.destination_root or Path.home() / ".agents" / "skills"
    destination_root = destination_root.expanduser().resolve()
    plan, errors = plan_install(install_root, destination_root, args.mode)
    print(f"Manga Studio skill installation plan ({'dry-run' if args.dry_run else 'apply'}):")
    for item in plan:
        print(f"- {item['action'].upper()}: {item['destination']} <- {item['source']} [{item['mode']}]")
    if errors:
        print("Installation plan rejected:")
        for error in errors:
            print(f"- {error}")
        return 1
    if args.dry_run:
        print("Dry run complete; no files were changed.")
        return 0
    backup_root = execute_install(plan, destination_root, args.mode)
    print(f"Installed {len(plan)} Manga Studio skills under {destination_root}")
    if backup_root:
        print(f"Rollback backup: {backup_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
