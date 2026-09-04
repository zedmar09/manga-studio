#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from install_skills import rollback_install


def main() -> int:
    parser = argparse.ArgumentParser(description="Rollback the current Manga Studio user-scope installation transaction.")
    parser.add_argument("--scope", choices=["user"], required=True)
    parser.add_argument("--destination-root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--backup-root", type=Path)
    args = parser.parse_args()
    destination = (args.destination_root or Path.home() / ".agents" / "skills").expanduser().resolve()
    restored = rollback_install(destination, args.backup_root)
    print(f"Rolled back Manga Studio installation using {restored}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
