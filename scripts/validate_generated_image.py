#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from manga_studio.image_intake import ImageInspectionError, compare_to_job, inspect_image
from manga_studio.json_schema import validate_instance
from manga_studio.page_pipeline import next_version_path
from manga_studio.project import ProjectDiscoveryError, discover_project, sha256_file
from manga_studio.validation import load_json, validate_image_job


def _inside_project(path: Path, project_root: Path, label: str) -> tuple[Path, str]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(project_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside the project: {resolved}") from exc
    return resolved, relative


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an externally generated image without editing or approving it."
    )
    parser.add_argument("job", type=Path, help="Source image-job JSON under handoff/pending.")
    parser.add_argument("image", type=Path, help="Generated image at the job's exact output_filename.")
    parser.add_argument("--project", type=Path, help="Story directory or nested path.")
    parser.add_argument("--output", type=Path, help="New project-relative intake JSON destination.")
    args = parser.parse_args()

    try:
        context = discover_project(args.project or args.job)
        job_path = args.job if args.job.is_absolute() else context.project_path(args.job.as_posix())
        image_path = args.image if args.image.is_absolute() else context.project_path(args.image.as_posix())
        job_path, job_relative = _inside_project(job_path, context.project_root, "image job")
        image_path, image_relative = _inside_project(image_path, context.project_root, "generated image")
        if not job_relative.startswith(".manga-studio/handoff/pending/"):
            raise ValueError("image job must be under .manga-studio/handoff/pending/")
        job = load_json(job_path)
        errors = [
            f"schema: {message}"
            for message in validate_instance(
                job, context.install_root / "schemas" / "image-job.schema.json"
            )
        ]
        errors.extend(validate_image_job(job_path, context.project_root, check_reference_existence=True))
        if job.get("release_status") not in {"ready", "released", "completed"}:
            errors.append(
                "generated images can be accepted only for ready, released, or completed jobs; "
                f"found {job.get('release_status')!r}"
            )
        if image_relative != job.get("output_filename"):
            errors.append(
                "generated image path must exactly match image-job output_filename; "
                f"expected {job.get('output_filename')!r}, found {image_relative!r}"
            )
        if errors:
            print("Generated image intake failed before file inspection:")
            for error in errors:
                print(f"- {error}")
            return 1

        file_info = inspect_image(image_path)
        file_info["sha256"] = sha256_file(image_path)
        expected_spec = job["output_spec"]
        findings = compare_to_job(file_info, job)
        status = "blocked" if any(item["severity"] == "error" for item in findings) else (
            "review_required" if findings else "technical_valid"
        )
        output_path = args.output
        if output_path is None:
            output_path = next_version_path(
                context.workspace_path("continuity/intake"), f"{job['job_id']}-intake", ".json"
            )
        elif not output_path.is_absolute():
            output_path = context.project_path(output_path.as_posix())
        output_path, _ = _inside_project(output_path, context.project_root, "intake output")
        try:
            intake_relative = output_path.relative_to(context.project_root.resolve()).as_posix()
        except ValueError as exc:
            raise ValueError("intake output must stay inside the project") from exc
        if not intake_relative.startswith(".manga-studio/continuity/intake/") or output_path.suffix != ".json":
            raise ValueError("intake output must be a JSON file under .manga-studio/continuity/intake/")
        if output_path.exists():
            raise ValueError(f"refusing to overwrite existing intake record: {output_path}")
        version_match = re.search(r"-v([0-9]{3})$", output_path.stem)
        version = version_match.group(1) if version_match else "001"
        record = {
            "schema_version": "1.0.0",
            "intake_id": f"{job['job_id']}-intake-v{version}",
            "project_id": context.config["project_id"],
            "job_id": job["job_id"],
            "job_path": job_relative,
            "job_sha256": sha256_file(job_path),
            "image_path": image_relative,
            "captured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "file": file_info,
            "expected": {
                "output_filename": job["output_filename"],
                "format": expected_spec["format"],
                "width": expected_spec["width"],
                "height": expected_spec["height"],
                "color_mode": expected_spec["color_mode"],
                "alpha_allowed": expected_spec["alpha_allowed"],
                "palette": job["manga_style"]["palette"],
            },
            "status": status,
            "findings": findings,
            "approval_required": True,
        }
        schema_errors = validate_instance(
            record, context.install_root / "schemas" / "generated-image.schema.json"
        )
        if schema_errors:
            raise ValueError("generated intake record failed schema validation: " + "; ".join(schema_errors))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(record, handle, indent=2, ensure_ascii=True)
            handle.write("\n")
        print(f"Generated image intake: {output_path}")
        print(f"Technical status: {status}; human visual approval is still required.")
        return 1 if status == "blocked" else 0
    except (ProjectDiscoveryError, ImageInspectionError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Generated image intake failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
