#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from manga_studio.profiles import VALIDATION_PROFILES, validate_profile
from manga_studio.project import ProjectDiscoveryError, discover_project


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a portable Manga Studio story project.")
    parser.add_argument("path", nargs="?", type=Path, help="Story directory or nested path.")
    parser.add_argument("--project", type=Path, help="Explicit story directory or nested path.")
    parser.add_argument("--profile", choices=VALIDATION_PROFILES, default="story")
    args = parser.parse_args()
    try:
        context = discover_project(args.project or args.path)
    except ProjectDiscoveryError as exc:
        print(f"Project validation failed: {exc}")
        return 2
    errors = validate_profile(context, args.profile)
    if errors:
        print(f"Project validation failed ({args.profile}): {context.project_root}")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Project validation passed ({args.profile}): {context.project_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
