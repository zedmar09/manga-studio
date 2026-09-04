#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from manga_studio.page_pipeline import next_version_path, panel_polygon, polygon_svg_points
from manga_studio.approvals import validate_locks
from manga_studio.json_schema import validate_json_file
from manga_studio.profiles import validate_approved_panel_artwork, validate_print_production_readiness
from manga_studio.project import ProjectDiscoveryError, discover_project, image_ready_reasons
from manga_studio.validation import load_json, project_path, validate_page_spec


def svg_image_href(output_path: Path, image_path: Path) -> str:
    return os.path.relpath(image_path, output_path.parent).replace(os.sep, "/")


def _managed_path(path: Path, project_root: Path, prefix: str, suffix: str, label: str) -> Path:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(project_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside the project") from exc
    if not relative.startswith(prefix) or resolved.suffix.lower() != suffix:
        raise ValueError(f"{label} must be a {suffix} file under {prefix}")
    return resolved


def _focus_alignment(panel: Dict[str, Any]) -> str:
    focus = panel.get("focus", {})
    x = focus.get("x", 0.5) if isinstance(focus, dict) else 0.5
    y = focus.get("y", 0.5) if isinstance(focus, dict) else 0.5
    horizontal = "xMin" if x < 0.34 else "xMax" if x > 0.66 else "xMid"
    vertical = "YMin" if y < 0.34 else "YMax" if y > 0.66 else "YMid"
    return horizontal + vertical


def compose_svg(page: Dict[str, Any], project_root: Path, output_path: Path) -> str:
    width = page["page_size"]["width"]
    height = page["page_size"]["height"]
    layout = page.get("layout", {}) if isinstance(page.get("layout"), dict) else {}
    background = html.escape(str(layout.get("background", "#fff")))
    indexed_panels = list(enumerate(page["panels"]))
    indexed_panels.sort(key=lambda entry: (entry[1].get("z_index", 0), entry[0]))

    lines: List[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect x="0" y="0" width="100%" height="100%" fill="{background}"/>',
        "<defs>",
    ]

    for _, panel in indexed_panels:
        panel_id = html.escape(panel["panel_id"])
        points = polygon_svg_points(panel_polygon(panel))
        lines.append(f'<clipPath id="clip-{panel_id}"><polygon points="{points}"/></clipPath>')
    lines.append("</defs>")

    default_border = {"visible": True, "color": "#000", "width": 6, "line_join": "miter"}
    if isinstance(layout.get("default_border"), dict):
        default_border.update(layout["default_border"])

    for _, panel in indexed_panels:
        frame = panel["frame"]
        panel_id = html.escape(panel["panel_id"])
        image_path = project_path(project_root, panel["art_path"]).resolve()
        href = html.escape(svg_image_href(output_path, image_path))
        fit = "meet" if panel.get("fit") == "contain" else "slice"
        preserve = f"{_focus_alignment(panel)} {fit}"
        points = polygon_svg_points(panel_polygon(panel))
        summary = html.escape(panel.get("summary", ""))
        lines.extend([
            f'<g id="panel-{panel_id}" data-panel-id="{panel_id}" data-z-index="{panel.get("z_index", 0)}">',
            f"<title>{summary}</title>",
            f'<image href="{href}" x="{frame["x"]}" y="{frame["y"]}" width="{frame["width"]}" '
            f'height="{frame["height"]}" preserveAspectRatio="{preserve}" clip-path="url(#clip-{panel_id})"/>',
        ])
        border = dict(default_border)
        if isinstance(panel.get("border"), dict):
            border.update(panel["border"])
        if border.get("visible") and border.get("width", 0) > 0:
            lines.append(
                f'<polygon points="{points}" fill="none" stroke="{html.escape(str(border["color"]))}" '
                f'stroke-width="{int(border["width"])}" stroke-linejoin="{html.escape(str(border["line_join"]))}" '
                'vector-effect="non-scaling-stroke"/>'
            )
        lines.append("</g>")

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compose approved manga panel images into a versioned, unlettered SVG page."
    )
    parser.add_argument("page_spec", type=Path, help="Page spec path relative to the story root or absolute.")
    parser.add_argument("--project", type=Path, help="Story directory or nested path.")
    parser.add_argument(
        "--output",
        type=Path,
        help="New output SVG path. Defaults to the next .manga-studio/pages/<page_id>-composed-v###.svg.",
    )
    args = parser.parse_args()

    try:
        context = discover_project(args.project or args.page_spec)
    except ProjectDiscoveryError as exc:
        print(f"Page cannot be composed: {exc}")
        return 2
    project_root = context.project_root
    page_path = args.page_spec if args.page_spec.is_absolute() else project_root / args.page_spec
    try:
        page_path = _managed_path(
            page_path, project_root, ".manga-studio/pages/", ".json", "page specification"
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Page cannot be composed: {exc}")
        return 2
    try:
        page = load_json(page_path)
    except (OSError, ValueError) as exc:
        print(f"Page cannot be composed: failed to load {page_path}: {exc}")
        return 2

    gate_errors = [*validate_locks(context), *image_ready_reasons(context)]
    if context.config.get("stage_locks", {}).get("IMAGE_READY") is not True or gate_errors:
        print("Page cannot be composed: IMAGE_READY production gate is blocked")
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
        print(f"Page cannot be composed: {page_path}")
        for error in errors:
            print(f"- {error}")
        return 1

    output_path = args.output
    if output_path is None:
        output_path = next_version_path(
            context.workspace_path("pages"), f"{page['page_id']}-composed", ".svg"
        )
    elif not output_path.is_absolute():
        output_path = project_root / output_path
    try:
        output_path = _managed_path(
            output_path, project_root, ".manga-studio/pages/", ".svg", "composed output"
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Page cannot be composed: {exc}")
        return 2
    if output_path.exists():
        print(f"Page cannot be composed: refusing to overwrite existing output {output_path}")
        return 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(compose_svg(page, project_root, output_path))
    print(f"Composed versioned unlettered page: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
