#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from manga_studio.project import ProjectDiscoveryError, discover_project, image_ready_reasons
from manga_studio.validation import load_json, validate_image_job


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a ChatGPT Image Generation Job.")
    parser.add_argument("job", type=Path, help="Path to the image job JSON file.")
    parser.add_argument("--project", "--project-root", dest="project", type=Path, help="Story directory or nested path.")
    parser.add_argument("--previous-job", type=Path, help="Previous version to compare locked references against.")
    parser.add_argument(
        "--structural-only",
        action="store_true",
        help="Validate job shape without requiring referenced approved image files to exist.",
    )
    args = parser.parse_args()

    job_path = args.job.resolve()
    try:
        context = discover_project(args.project or job_path)
    except ProjectDiscoveryError as exc:
        print(f"Image job validation failed: {exc}")
        return 2
    project_root = context.project_root
    errors = validate_image_job(
        job_path,
        project_root,
        previous_job_path=args.previous_job.resolve() if args.previous_job else None,
        check_reference_existence=not args.structural_only,
    )
    try:
        job = load_json(job_path)
        if not args.structural_only and job.get("release_status") == "deferred":
            errors.append("strict release validation requires release_status to be ready, released, or completed")
        if job.get("release_status") in {"ready", "released", "completed"}:
            errors.extend(f"active image job blocked: {reason}" for reason in image_ready_reasons(context))
    except (OSError, ValueError):
        pass

    if errors:
        print(f"Image job validation failed: {job_path}")
        for error in errors:
            print(f"- {error}")
        return 1

    mode = "structural" if args.structural_only else "strict"
    print(f"Image job validation passed ({mode}): {job_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
