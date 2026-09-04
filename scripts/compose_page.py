#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from manga_studio.project import ProjectDiscoveryError, discover_project, image_ready_reasons
from manga_studio.validation import APPROVED_PREFIX, load_json, project_path, validate_page_spec


def svg_image_href(output_path: Path, image_path: Path) -> str:
    return os.path.relpath(image_path, output_path.parent).replace(os.sep, "/")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compose approved manga panel images into an unlettered SVG page.")
    parser.add_argument("page_spec", type=Path, help="Page spec path relative to the story root or absolute.")
    parser.add_argument("--project", type=Path, help="Story directory or nested path.")
    parser.add_argument("--output", type=Path, help="Output SVG path. Defaults to .manga-studio/pages/<page_id>-composed.svg.")
    args = parser.parse_args()

    try:
        context = discover_project(args.project or args.page_spec)
    except ProjectDiscoveryError as exc:
        print(f"Page cannot be composed: {exc}")
        return 2
    project_root = context.project_root
    page_path = args.page_spec if args.page_spec.is_absolute() else project_root / args.page_spec
    page = load_json(page_path)

    gate_errors = image_ready_reasons(context)
    if context.config.get("stage_locks", {}).get("IMAGE_READY") is not True or gate_errors:
        print("Page cannot be composed: IMAGE_READY production gate is blocked")
        for error in gate_errors or ["stage_locks.IMAGE_READY is false"]:
            print(f"- {error}")
        return 1

    errors = validate_page_spec(page_path, project_root)
    if errors:
        print(f"Page cannot be composed: {page_path}")
        for error in errors:
            print(f"- {error}")
        return 1

    for panel in page["panels"]:
        art_path = panel["art_path"]
        if not art_path:
            print(f"Page cannot be composed: panel '{panel['panel_id']}' has no approved art_path")
            return 1
        if not art_path.startswith(APPROVED_PREFIX):
            print(f"Page cannot be composed: panel '{panel['panel_id']}' does not use an approved image: {art_path}")
            return 1

    output_path = args.output
    if output_path is None:
        output_path = context.workspace_path(f"pages/{page['page_id']}-composed.svg")
    elif not output_path.is_absolute():
        output_path = project_root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    width = page["page_size"]["width"]
    height = page["page_size"]["height"]
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect x="0" y="0" width="100%" height="100%" fill="#fff"/>',
        "<defs>",
    ]

    for panel in page["panels"]:
        frame = panel["frame"]
        panel_id = html.escape(panel["panel_id"])
        lines.append(
            f'<clipPath id="clip-{panel_id}"><rect x="{frame["x"]}" y="{frame["y"]}" '
            f'width="{frame["width"]}" height="{frame["height"]}"/></clipPath>'
        )

    lines.append("</defs>")

    for panel in page["panels"]:
        frame = panel["frame"]
        panel_id = html.escape(panel["panel_id"])
        image_path = project_path(project_root, panel["art_path"]).resolve()
        href = html.escape(svg_image_href(output_path, image_path))
        lines.append(
            f'<image href="{href}" x="{frame["x"]}" y="{frame["y"]}" width="{frame["width"]}" '
            f'height="{frame["height"]}" preserveAspectRatio="xMidYMid slice" clip-path="url(#clip-{panel_id})"/>'
        )
        lines.append(
            f'<rect x="{frame["x"]}" y="{frame["y"]}" width="{frame["width"]}" '
            f'height="{frame["height"]}" fill="none" stroke="#000" stroke-width="6"/>'
        )

    lines.append("</svg>")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Composed unlettered page: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
