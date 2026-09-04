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
from manga_studio.page_pipeline import next_version_path
from manga_studio.print_preflight import preflight_project
from manga_studio.project import ProjectDiscoveryError, discover_project, sha256_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight page geometry against a physical print profile.")
    parser.add_argument("path", nargs="?", type=Path, help="Story directory or nested path.")
    parser.add_argument("--project", type=Path, help="Explicit story directory or nested path.")
    parser.add_argument("--output", type=Path, help="New project-relative print-preflight review JSON.")
    args = parser.parse_args()
    try:
        context = discover_project(args.project or args.path)
        errors, findings, summary = preflight_project(context)
        findings = [
            *({"severity": "error", "code": "print_preflight", "message": message} for message in errors),
            *findings,
        ]
        output_path = args.output or next_version_path(
            context.workspace_path("production/preflight"), "print-preflight", ".json"
        )
        if not output_path.is_absolute():
            output_path = context.project_path(output_path.as_posix())
        output_path = output_path.resolve()
        try:
            output_relative = output_path.relative_to(context.project_root.resolve()).as_posix()
        except ValueError as exc:
            raise ValueError("print-preflight output must stay inside the project") from exc
        if (
            not output_relative.startswith(".manga-studio/production/preflight/")
            or output_path.suffix.lower() != ".json"
        ):
            raise ValueError(
                "print-preflight output must be a JSON file under .manga-studio/production/preflight/"
            )
        if output_path.exists():
            raise ValueError(f"refusing to overwrite existing output: {output_path}")
        match = re.search(r"-v([0-9]{3})$", output_path.stem)
        version = match.group(1) if match else "001"
        review = {
            "schema_version": "1.0.0",
            "review_id": f"print-preflight-v{version}",
            "project_id": context.config["project_id"],
            "review_type": "print_preflight",
            "target": ".manga-studio/project.json",
            "target_sha256": sha256_file(context.project_file),
            "target_hashes": [
                {
                    "relative_path": path.relative_to(context.project_root).as_posix(),
                    "sha256": sha256_file(path),
                }
                for path in [
                    context.project_file,
                    *(
                        path for path in sorted(context.workspace_path("pages").glob("*.json"))
                        if not path.name.startswith("._")
                    ),
                ]
            ],
            "status": "blocked" if errors else "review_ready",
            "automated": True,
            "approval_required": True,
            "metric_scope": "technical_preflight",
            "findings": findings,
        }
        schema_errors = validate_instance(review, context.install_root / "schemas" / "review.schema.json")
        if schema_errors:
            raise ValueError("generated preflight review failed schema validation: " + "; ".join(schema_errors))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(review, handle, indent=2, ensure_ascii=True)
            handle.write("\n")
        print(f"Print preflight: {output_path}")
        print(json.dumps({"status": review["status"], "summary": summary}, indent=2))
        return 1 if errors else 0
    except (ProjectDiscoveryError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Print preflight failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
