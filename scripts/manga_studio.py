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
from manga_studio.approvals import clear_lock, invalidate_stale_approvals, record_approval, set_lock, validate_approval, validate_locks
from manga_studio.diagnostics import publish_diagnostic_report
from manga_studio.migration import migrate_project
from manga_studio.project import (
    OPERATING_MODES,
    ProjectDiscoveryError,
    ProjectOperationError,
    STAGE_GATES,
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
from manga_studio.revisions import apply_change_set
from manga_studio.structure import show_structure, structure_sources, validate_source_maps


def _project_argument(parser: argparse.ArgumentParser, *, init: bool = False) -> None:
    parser.add_argument("path", nargs="?", type=Path, help="Story directory or a path nested within it.")
    parser.add_argument("--project", dest="project", type=Path, help="Explicit story directory or nested project path.")
    if init:
        parser.add_argument("--mode", choices=OPERATING_MODES, default="import_existing")
        parser.add_argument("--title", help="Project title. Defaults to the story directory name.")


def _selected_path(args: argparse.Namespace) -> Path | None:
    return args.project if getattr(args, "project", None) is not None else getattr(args, "path", None)


def _project_input(context, value: Path) -> Path:
    return value.expanduser().resolve() if value.is_absolute() else context.project_path(value.as_posix())


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

    migrate = subparsers.add_parser("migrate", help="Migrate a v2 story workspace to schema v3 without changing sources.")
    _project_argument(migrate)

    structure = subparsers.add_parser("structure", help="Create immutable structural source maps.")
    _project_argument(structure)

    validate_map = subparsers.add_parser("validate-source-map", help="Validate source-map checksums, ranges, and IDs.")
    _project_argument(validate_map)

    show = subparsers.add_parser("show-structure", help="Print the active structure index.")
    _project_argument(show)

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

    for command, decision in (("approve", "approved"), ("reject", "rejected")):
        approval = subparsers.add_parser(command, help=f"Record an explicit {decision} artifact decision.")
        approval.add_argument("target", type=Path)
        approval.add_argument("--artifact-type", required=True)
        approval.add_argument("--target-version", required=True)
        approval.add_argument("--actor", required=True)
        approval.add_argument("--notes", default="")
        approval.add_argument("--supersedes")
        approval.add_argument("--project", type=Path)

    approval_validation = subparsers.add_parser("validate-approval", help="Validate an approval target and checksum.")
    approval_validation.add_argument("approval", type=Path)
    approval_validation.add_argument("--project", type=Path)

    set_lock_parser = subparsers.add_parser("set-lock", help="Set a stage lock using valid prerequisite approvals.")
    set_lock_parser.add_argument("gate", choices=STAGE_GATES)
    set_lock_parser.add_argument("--approval", action="append", type=Path, default=[])
    set_lock_parser.add_argument("--actor", required=True)
    set_lock_parser.add_argument("--notes", default="")
    set_lock_parser.add_argument("--project", type=Path)

    clear_lock_parser = subparsers.add_parser("clear-lock", help="Clear a stage lock while preserving lock history.")
    clear_lock_parser.add_argument("gate", choices=STAGE_GATES)
    clear_lock_parser.add_argument("--actor", required=True)
    clear_lock_parser.add_argument("--notes", default="")
    clear_lock_parser.add_argument("--project", type=Path)

    validate_locks_parser = subparsers.add_parser("validate-locks", help="Validate active lock records and approvals.")
    _project_argument(validate_locks_parser)

    apply_parser = subparsers.add_parser("apply-change-set", help="Apply an approved change set as a new manuscript version.")
    apply_parser.add_argument("change_set", type=Path)
    apply_parser.add_argument("--actor", required=True)
    apply_parser.add_argument("--project", type=Path)

    diagnose_parser = subparsers.add_parser("diagnose", help="Validate and publish a structured diagnostic draft.")
    diagnose_parser.add_argument("draft", type=Path)
    diagnose_parser.add_argument("--markdown", action="store_true")
    diagnose_parser.add_argument("--project", type=Path)

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
            for blocked in summary.get("blocked", []):
                print(f"- BLOCKED {blocked['relative_path']}: {blocked['reason']}")
            print(context.workspace_path("source/provenance.json"))
            return 0
        if args.command == "migrate":
            for action in migrate_project(context):
                print(f"- {action}")
            return 0
        if args.command == "structure":
            result = structure_sources(context)
            review_count = sum(item["structure_status"] == "review_required" for item in result["documents"])
            print(f"Structured {len(result['documents'])} document(s); review required: {review_count}")
            print(context.workspace_path("source/structure.json"))
            return 1 if review_count else 0
        if args.command == "validate-source-map":
            errors = validate_source_maps(context)
            if errors:
                print("Source-map validation failed:")
                for error in errors:
                    print(f"- {error}")
                return 1
            print("Source-map validation passed.")
            return 0
        if args.command == "show-structure":
            print(json.dumps(show_structure(context), indent=2))
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
        if args.command in {"approve", "reject"}:
            approval_path = record_approval(
                context,
                _project_input(context, args.target),
                artifact_type=args.artifact_type,
                target_version=args.target_version,
                actor=args.actor,
                decision="approved" if args.command == "approve" else "rejected",
                notes=args.notes,
                supersedes_approval_id=args.supersedes,
            )
            print(approval_path)
            return 0
        if args.command == "validate-approval":
            invalidate_stale_approvals(context)
            errors = validate_approval(context, _project_input(context, args.approval))
            if errors:
                print("Approval validation failed:")
                for error in errors:
                    print(f"- {error}")
                return 1
            print("Approval validation passed.")
            return 0
        if args.command == "set-lock":
            path = set_lock(
                context,
                args.gate,
                approval_paths=[_project_input(context, item) for item in args.approval],
                actor=args.actor,
                notes=args.notes,
            )
            print(path)
            return 0
        if args.command == "clear-lock":
            print(clear_lock(context, args.gate, actor=args.actor, notes=args.notes))
            return 0
        if args.command == "validate-locks":
            errors = validate_locks(context)
            if errors:
                print("Stage-lock validation failed:")
                for error in errors:
                    print(f"- {error}")
                return 1
            print("Stage-lock validation passed.")
            return 0
        if args.command == "apply-change-set":
            print(json.dumps(apply_change_set(
                context,
                _project_input(context, args.change_set),
                actor=args.actor,
            ), indent=2))
            return 0
        if args.command == "diagnose":
            print(json.dumps(publish_diagnostic_report(
                context,
                _project_input(context, args.draft),
                markdown_companion=args.markdown,
            ), indent=2))
            return 0
    except (ProjectDiscoveryError, ProjectOperationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Manga Studio error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
