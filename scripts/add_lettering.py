#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from manga_studio.page_pipeline import (
    latest_version_path,
    lettering_svg,
    next_version_path,
    wrap_text,
)
from manga_studio.approvals import validate_locks
from manga_studio.json_schema import validate_json_file
from manga_studio.profiles import validate_approved_panel_artwork, validate_print_production_readiness
from manga_studio.project import ProjectDiscoveryError, discover_project, image_ready_reasons
from manga_studio.validation import load_json, validate_page_spec


def _managed_path(path: Path, project_root: Path, prefix: str, suffix: str, label: str) -> Path:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(project_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside the project") from exc
    if not relative.startswith(prefix) or resolved.suffix.lower() != suffix:
        raise ValueError(f"{label} must be a {suffix} file under {prefix}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add professional vector lettering and structured SFX to a composed manga SVG."
    )
    parser.add_argument("page_spec", type=Path, help="Page spec path relative to the story root or absolute.")
    parser.add_argument("--project", type=Path, help="Story directory or nested path.")
    parser.add_argument(
        "--input",
        type=Path,
        help="Composed SVG. Defaults to the latest .manga-studio/pages/<page_id>-composed-v###.svg.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="New output SVG. Defaults to the next .manga-studio/lettering/<page_id>-lettered-v###.svg.",
    )
    args = parser.parse_args()

    try:
        context = discover_project(args.project or args.page_spec)
    except ProjectDiscoveryError as exc:
        print(f"Lettering cannot be added: {exc}")
        return 2
    project_root = context.project_root
    page_path = args.page_spec if args.page_spec.is_absolute() else project_root / args.page_spec
    try:
        page_path = _managed_path(
            page_path, project_root, ".manga-studio/pages/", ".json", "page specification"
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Lettering cannot be added: {exc}")
        return 2
    try:
        page = load_json(page_path)
    except (OSError, ValueError) as exc:
        print(f"Lettering cannot be added: failed to load {page_path}: {exc}")
        return 2

    gate_errors = [*validate_locks(context), *image_ready_reasons(context)]
    if context.config.get("stage_locks", {}).get("IMAGE_READY") is not True or gate_errors:
        print("Lettering cannot be added: approved production dependencies are blocked")
        for error in gate_errors or ["stage_locks.IMAGE_READY is false"]:
            print(f"- {error}")
        return 1

    errors = [
        f"schema: {message}"
        for message in validate_json_file(
            page_path, context.install_root / "schemas" / "page.schema.json"
        )
    ]
    errors.extend(validate_page_spec(page_path, project_root))
    errors.extend(validate_approved_panel_artwork(context, page))
    errors.extend(validate_print_production_readiness(context))
    if errors:
        print(f"Lettering cannot be added: {page_path}")
        for error in errors:
            print(f"- {error}")
        return 1

    input_path = args.input
    if input_path is None:
        input_path = latest_version_path(
            context.workspace_path("pages"), f"{page['page_id']}-composed", ".svg"
        )
        if input_path is None:
            legacy = context.workspace_path(f"pages/{page['page_id']}-composed.svg")
            input_path = legacy if legacy.is_file() else None
    elif not input_path.is_absolute():
        input_path = project_root / input_path
    if input_path is not None:
        try:
            input_path = _managed_path(
                input_path, project_root, ".manga-studio/pages/", ".svg", "composed input"
            )
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"Lettering cannot be added: {exc}")
            return 2
    if input_path is None or not input_path.exists():
        print(f"Lettering cannot be added: no composed SVG exists for {page['page_id']}")
        return 1

    output_path = args.output
    if output_path is None:
        output_path = next_version_path(
            context.workspace_path("lettering"), f"{page['page_id']}-lettered", ".svg"
        )
    elif not output_path.is_absolute():
        output_path = project_root / output_path
    try:
        output_path = _managed_path(
            output_path, project_root, ".manga-studio/lettering/", ".svg", "lettered output"
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Lettering cannot be added: {exc}")
        return 2
    if output_path.exists():
        print(f"Lettering cannot be added: refusing to overwrite existing output {output_path}")
        return 1

    svg = input_path.read_text(encoding="utf-8")
    if "</svg>" not in svg:
        print(f"Lettering cannot be added: input SVG has no closing </svg>: {input_path}")
        return 1
    if 'id="lettering"' in svg:
        print(f"Lettering cannot be added: input SVG already contains a lettering layer: {input_path}")
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_svg = svg.replace("</svg>", lettering_svg(page, project_root) + "\n</svg>", 1)
    with output_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(final_svg)
    print(f"Added versioned vector lettering: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
