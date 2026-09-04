#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from manga_studio.json_schema import validate_instance
from manga_studio.page_pipeline import next_version_path, page_quality_review
from manga_studio.project import ProjectDiscoveryError, discover_project
from manga_studio.validation import load_json, validate_page_spec


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a deterministic page-quality review without approving or editing artwork."
    )
    parser.add_argument("page_spec", type=Path, help="Page spec path relative to the story root or absolute.")
    parser.add_argument("--project", type=Path, help="Story directory or nested path.")
    parser.add_argument(
        "--output",
        type=Path,
        help="New review JSON path. Defaults to the next .manga-studio/continuity/<page_id>-quality-review-v###.json.",
    )
    args = parser.parse_args()

    try:
        context = discover_project(args.project or args.page_spec)
    except ProjectDiscoveryError as exc:
        print(f"Page review failed: {exc}")
        return 2

    page_path = args.page_spec if args.page_spec.is_absolute() else context.project_path(args.page_spec.as_posix())
    try:
        page_path = page_path.resolve()
        relative_target = page_path.relative_to(context.project_root.resolve()).as_posix()
    except (OSError, RuntimeError, ValueError):
        print(f"Page review failed: page spec must stay inside the project: {page_path}")
        return 2
    try:
        page = load_json(page_path)
    except (OSError, ValueError) as exc:
        print(f"Page review failed: failed to load {page_path}: {exc}")
        return 2
    page_id = page.get("page_id")
    if not isinstance(page_id, str) or re.fullmatch(r"[a-z0-9][a-z0-9-]*", page_id) is None:
        print("Page review failed: page_id must be a lowercase stable ID")
        return 2

    validation_errors = [
        f"schema: {message}"
        for message in validate_instance(page, context.install_root / "schemas" / "page.schema.json")
    ]
    validation_errors.extend(validate_page_spec(page_path, context.project_root))

    output_path = args.output
    if output_path is None:
        output_path = next_version_path(
            context.workspace_path("continuity"), f"{page_id}-quality-review", ".json"
        )
    elif not output_path.is_absolute():
        output_path = context.project_path(output_path.as_posix())
    try:
        output_path = output_path.resolve()
        output_relative = output_path.relative_to(context.project_root.resolve()).as_posix()
    except (OSError, RuntimeError, ValueError):
        print(f"Page review failed: output must stay inside the project: {output_path}")
        return 2
    if not output_relative.startswith(".manga-studio/continuity/") or output_path.suffix.lower() != ".json":
        print("Page review failed: output must be a JSON file under .manga-studio/continuity/")
        return 2
    if output_path.exists():
        print(f"Page review failed: refusing to overwrite existing output {output_path}")
        return 1

    version_match = re.search(r"-v([0-9]{3})$", output_path.stem)
    version = version_match.group(1) if version_match else "001"
    review = page_quality_review(
        page,
        project_id=context.config["project_id"],
        target=relative_target,
        review_id=f"{page_id}-quality-v{version}",
        validation_errors=validation_errors,
        project_root=context.project_root,
    )
    review_schema_errors = validate_instance(
        review, context.install_root / "schemas" / "review.schema.json"
    )
    if review_schema_errors:
        print("Page review failed: generated report did not satisfy review.schema.json")
        for error in review_schema_errors:
            print(f"- {error}")
        return 2

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(review, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    print(f"Page quality review: {output_path}")
    print(json.dumps({"status": review["status"], "metrics": review["metrics"]}, indent=2))
    return 1 if review["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
