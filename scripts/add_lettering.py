#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path
from typing import List

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from manga_studio.project import ProjectDiscoveryError, discover_project, image_ready_reasons
from manga_studio.validation import load_json, validate_page_spec


def wrap_text(text: str, max_chars: int) -> List[str]:
    words = text.split()
    lines: List[str] = []
    current: List[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and len(candidate) > max_chars:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines or [""]


def lettering_svg(page: dict) -> str:
    snippets: List[str] = []
    snippets.append('<g id="lettering" font-family="Arial, Helvetica, sans-serif" fill="#000">')
    for index, item in enumerate(page.get("lettering", [])):
        box = item["box"]
        text = item["text"]
        max_chars = max(8, int(box["width"] / 20))
        lines = wrap_text(text, max_chars)
        font_size = min(34, max(18, int(box["height"] / max(3, len(lines) + 1))))
        line_height = int(font_size * 1.2)
        text_height = line_height * len(lines)
        text_y = box["y"] + max(font_size + 8, int((box["height"] - text_height) / 2) + font_size)
        text_x = box["x"] + int(box["width"] / 2)
        element_id = html.escape(f"letter-{index + 1}-{item['panel_id']}")

        radius = 8 if item.get("kind") == "caption" else 28
        snippets.append(
            f'<g id="{element_id}">'
            f'<rect x="{box["x"]}" y="{box["y"]}" width="{box["width"]}" height="{box["height"]}" '
            f'rx="{radius}" ry="{radius}" fill="#fff" stroke="#000" stroke-width="4"/>'
        )
        if "tail_to" in item:
            tail = item["tail_to"]
            anchor_x = box["x"] + int(box["width"] / 2)
            anchor_y = box["y"] + box["height"]
            snippets.append(
                f'<path d="M {anchor_x - 18} {anchor_y - 2} L {tail["x"]} {tail["y"]} '
                f'L {anchor_x + 18} {anchor_y - 2} Z" fill="#fff" stroke="#000" stroke-width="4"/>'
            )
        snippets.append(
            f'<text x="{text_x}" y="{text_y}" text-anchor="middle" font-size="{font_size}" '
            'font-weight="700">'
        )
        for line_index, line in enumerate(lines):
            dy = 0 if line_index == 0 else line_height
            snippets.append(f'<tspan x="{text_x}" dy="{dy}">{html.escape(line)}</tspan>')
        snippets.append("</text></g>")
    snippets.append("</g>")
    return "\n".join(snippets)


def main() -> int:
    parser = argparse.ArgumentParser(description="Add lettering from a page spec to a composed SVG page.")
    parser.add_argument("page_spec", type=Path, help="Page spec path relative to the story root or absolute.")
    parser.add_argument("--project", type=Path, help="Story directory or nested path.")
    parser.add_argument("--input", type=Path, help="Input SVG. Defaults to .manga-studio/pages/<page_id>-composed.svg.")
    parser.add_argument("--output", type=Path, help="Output SVG. Defaults to .manga-studio/lettering/<page_id>-lettered.svg.")
    args = parser.parse_args()

    try:
        context = discover_project(args.project or args.page_spec)
    except ProjectDiscoveryError as exc:
        print(f"Lettering cannot be added: {exc}")
        return 2
    project_root = context.project_root
    page_path = args.page_spec if args.page_spec.is_absolute() else project_root / args.page_spec
    page = load_json(page_path)

    gate_errors = image_ready_reasons(context)
    if context.config.get("stage_locks", {}).get("IMAGE_READY") is not True or gate_errors:
        print("Lettering cannot be added: approved production dependencies are blocked")
        for error in gate_errors or ["stage_locks.IMAGE_READY is false"]:
            print(f"- {error}")
        return 1

    errors = validate_page_spec(page_path, project_root)
    if errors:
        print(f"Lettering cannot be added: {page_path}")
        for error in errors:
            print(f"- {error}")
        return 1

    input_path = args.input or context.workspace_path(f"pages/{page['page_id']}-composed.svg")
    output_path = args.output or context.workspace_path(f"lettering/{page['page_id']}-lettered.svg")
    if not input_path.is_absolute():
        input_path = project_root / input_path
    if not output_path.is_absolute():
        output_path = project_root / output_path
    if not input_path.exists():
        print(f"Lettering cannot be added: missing composed SVG {input_path}")
        return 1

    svg = input_path.read_text(encoding="utf-8")
    if "</svg>" not in svg:
        print(f"Lettering cannot be added: input SVG has no closing </svg>: {input_path}")
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_svg = svg.replace("</svg>", lettering_svg(page) + "\n</svg>", 1)
    output_path.write_text(final_svg, encoding="utf-8")
    print(f"Added lettering: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
