#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from manga_studio.profiles import VALIDATION_PROFILES, validate_profile
from manga_studio.project import (
    OPERATING_MODES,
    ProjectDiscoveryError,
    ProjectOperationError,
    VERSION_AREAS,
    create_version,
    discover_project,
    get_or_create_entity_id,
    image_ready_reasons,
    import_sources,
    initialize_project,
    inventory_sources,
    project_status,
    sha256_file,
)


def _project_argument(parser: argparse.ArgumentParser, *, init: bool = False) -> None:
    parser.add_argument("path", nargs="?", type=Path, help="Story directory or a path nested within it.")
    parser.add_argument("--project", dest="project", type=Path, help="Explicit story directory or nested project path.")
    if init:
        parser.add_argument("--mode", choices=OPERATING_MODES, default="import_existing")
        parser.add_argument("--title", help="Project title. Defaults to the story directory name.")


def _selected_path(args: argparse.Namespace) -> Path | None:
    return args.project if getattr(args, "project", None) is not None else getattr(args, "path", None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Portable Manga Studio project operations.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="Find a .manga-studio/project.json by searching upward.")
    _project_argument(discover)

    init = subparsers.add_parser("init", help="Initialize a story-local .manga-studio workspace.")
    _project_argument(init, init=True)

    inventory = subparsers.add_parser("inventory", help="Inventory source candidates without modifying them.")
    _project_argument(inventory)

    import_parser = subparsers.add_parser("import", help="Snapshot and normalize supported inventoried sources.")
    _project_argument(import_parser)

    validate = subparsers.add_parser("validate", help="Validate a story, preproduction, or production profile.")
    _project_argument(validate)
    validate.add_argument("--profile", choices=VALIDATION_PROFILES, required=True)

    status = subparsers.add_parser("status", help="Show project roots, active versions, locks, and image readiness.")
    _project_argument(status)

    hash_parser = subparsers.add_parser("hash", help="Hash a file without modifying it.")
    hash_parser.add_argument("file", type=Path)

    stable_id = subparsers.add_parser("stable-id", help="Persist or retrieve an entity ID in the story workspace.")
    stable_id.add_argument("namespace")
    stable_id.add_argument("external_key")
    stable_id.add_argument("display_name")
    stable_id.add_argument("--project", type=Path, help="Explicit story directory or nested path.")

    diff = subparsers.add_parser("diff", help="Produce a deterministic unified text diff.")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)

    version = subparsers.add_parser("version", help="Create the next non-overwriting workspace artifact version.")
    version.add_argument("source", type=Path)
    version.add_argument("--area", choices=VERSION_AREAS, required=True)
    version.add_argument("--project", type=Path, help="Explicit story directory or nested path.")

    locks = subparsers.add_parser("check-locks", help="Check stage-lock and IMAGE_READY prerequisites.")
    _project_argument(locks)

    subparsers.add_parser("doctor", help="Run toolkit installation-readiness checks.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            target = _selected_path(args) or Path.cwd()
            context, actions = initialize_project(target, mode=args.mode, title=args.title)
            print(f"Initialized Manga Studio project: {context.project_root}")
            for action in actions:
                print(f"- {action}")
            return 0

        if args.command == "hash":
            print(sha256_file(args.file.expanduser().resolve()))
            return 0

        if args.command == "diff":
            before = args.before.read_text(encoding="utf-8").splitlines(keepends=True)
            after = args.after.read_text(encoding="utf-8").splitlines(keepends=True)
            sys.stdout.writelines(difflib.unified_diff(before, after, fromfile=str(args.before), tofile=str(args.after)))
            return 0

        if args.command == "doctor":
            from doctor import run_doctor

            errors = run_doctor(SCRIPT_DIR.parent, verbose=True)
            return 1 if errors else 0

        context = discover_project(_selected_path(args))

        if args.command == "discover":
            print(json.dumps({
                "project_root": str(context.project_root),
                "workspace_root": str(context.workspace_root),
                "source_roots": [str(path) for path in context.source_roots],
                "manga_studio_install_root": str(context.install_root),
            }, indent=2))
            return 0
        if args.command == "inventory":
            result = inventory_sources(context)
            unsupported = sum(1 for item in result["files"] if item["support_status"] == "unsupported")
            print(f"Inventoried {len(result['files'])} source candidate(s); unsupported: {unsupported}")
            print(context.workspace_path("source/inventory.json"))
            return 0
        if args.command == "import":
            result = import_sources(context)
            summary = result["import_summary"]
            print(f"Imported {summary['imported']} source(s); skipped: {summary['skipped']}")
            print(context.workspace_path("source/provenance.json"))
            return 0
        if args.command == "validate":
            errors = validate_profile(context, args.profile)
            if errors:
                print(f"Validation failed ({args.profile}): {context.project_root}")
                for error in errors:
                    print(f"- {error}")
                return 1
            print(f"Validation passed ({args.profile}): {context.project_root}")
            return 0
        if args.command == "status":
            print(json.dumps(project_status(context), indent=2))
            return 0
        if args.command == "stable-id":
            print(get_or_create_entity_id(context, args.namespace, args.external_key, args.display_name))
            return 0
        if args.command == "version":
            destination = create_version(context, args.source, args.area)
            print(destination)
            return 0
        if args.command == "check-locks":
            reasons = image_ready_reasons(context)
            if reasons:
                print("IMAGE_READY prerequisites are blocked:")
                for reason in reasons:
                    print(f"- {reason}")
                return 1
            print("IMAGE_READY prerequisites pass.")
            return 0
    except (ProjectDiscoveryError, ProjectOperationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Manga Studio error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
