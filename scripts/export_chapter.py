#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from manga_studio.profiles import validate_profile
from manga_studio.project import ProjectDiscoveryError, discover_project
from manga_studio.validation import load_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Export approved lettered Manga Studio pages.")
    parser.add_argument("path", nargs="?", type=Path, help="Story directory or nested path.")
    parser.add_argument("--project", type=Path, help="Explicit story directory or nested path.")
    parser.add_argument("--chapter-id", help="Optional chapter grouping; projects need not have chapters.")
    parser.add_argument("--output-dir", type=Path, help="Output directory under the story or an absolute path.")
    args = parser.parse_args()

    try:
        context = discover_project(args.project or args.path)
    except ProjectDiscoveryError as exc:
        print(f"Export failed: {exc}")
        return 2
    errors = validate_profile(context, "production")
    if errors:
        print(f"Export failed: production validation is blocked for {context.project_root}")
        for error in errors:
            print(f"- {error}")
        return 1

    package_name = args.chapter_id or context.config["project_id"]
    output_dir = args.output_dir or context.workspace_path(f"exports/{package_name}")
    if not output_dir.is_absolute():
        output_dir = context.project_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    exported_pages = []
    for page_path in sorted(context.workspace_path("pages").glob("*.json")):
        page = load_json(page_path)
        page_id = page["page_id"]
        source = context.workspace_path(f"lettering/{page_id}-lettered.svg")
        destination = output_dir / f"{page_id}.svg"
        shutil.copy2(source, destination)
        exported_pages.append(destination.name)

    manifest = {
        "schema_version": context.config["schema_version"],
        "project_id": context.config["project_id"],
        "chapter_id": args.chapter_id,
        "format": "svg",
        "pages": exported_pages,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Exported page package: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
