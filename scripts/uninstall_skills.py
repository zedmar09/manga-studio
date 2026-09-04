#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import List

from install_skills import is_managed_manga_skill, load_manifest


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Uninstall only managed Manga Studio skills.")
    parser.add_argument("--scope", choices=["user"], required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--destination-root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    install_root = Path(__file__).resolve().parents[1]
    manifest = load_manifest(install_root)
    destination_root = (args.destination_root or Path.home() / ".agents" / "skills").expanduser().resolve()
    targets = []
    errors = []
    for item in manifest["skills"]:
        destination = destination_root / item["name"]
        if not destination.exists() and not destination.is_symlink():
            print(f"- PRESERVE: {destination} (not installed)")
        elif is_managed_manga_skill(destination):
            targets.append(destination)
            print(f"- REMOVE: {destination}")
        else:
            errors.append(f"refusing to remove non-Manga skill: {destination}")
            print(f"- REJECT: {destination}")
    if errors:
        for error in errors:
            print(error)
        return 1
    if args.dry_run:
        print("Dry run complete; no files were changed.")
        return 0
    for target in targets:
        if target.is_symlink():
            target.unlink()
        else:
            shutil.rmtree(target)
    registry = destination_root / ".manga-studio-install.json"
    if registry.exists():
        data = json.loads(registry.read_text(encoding="utf-8"))
        if data.get("namespace") == "manga-studio":
            registry.unlink()
    print(f"Removed {len(targets)} Manga Studio skill(s). Story workspaces were not touched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
