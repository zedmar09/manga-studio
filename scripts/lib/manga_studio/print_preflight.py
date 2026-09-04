from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .project import ProjectContext
from .validation import load_json


def _inches(value: float, unit: str) -> float:
    return value if unit == "in" else value / 25.4


def _pixels(value: float, unit: str, dpi: int) -> int:
    return round(_inches(value, unit) * dpi)


def _page_side(config: Dict[str, Any], page_number: int) -> str:
    profile = config["target_manga_format"]["print_profile"]
    configured = profile["page_side"]
    if configured != "auto":
        return configured
    right_to_left = config.get("reading_direction") == "right-to-left"
    if right_to_left:
        return "left" if page_number % 2 else "right"
    return "right" if page_number % 2 else "left"


def expected_print_canvas(profile: Dict[str, Any]) -> Tuple[int, int]:
    unit = profile["unit"]
    dpi = profile["dpi"]
    bleed = profile["bleed"]
    width = profile["trim_width"] + bleed["left"] + bleed["right"]
    height = profile["trim_height"] + bleed["top"] + bleed["bottom"]
    return _pixels(width, unit, dpi), _pixels(height, unit, dpi)


def preflight_project(context: ProjectContext) -> Tuple[List[str], List[Dict[str, str]], Dict[str, Any]]:
    errors: List[str] = []
    findings: List[Dict[str, str]] = []
    target = context.config.get("target_manga_format", {})
    intent = target.get("output_intent", "screen")
    profile = target.get("print_profile")
    if intent not in {"print", "both"}:
        return ["target_manga_format.output_intent must be print or both"], findings, {}
    if not isinstance(profile, dict):
        return ["target_manga_format.print_profile is required"], findings, {}

    required = {
        "name", "unit", "dpi", "trim_width", "trim_height", "bleed", "safe_margin",
        "binding", "inner_gutter", "page_side", "export_format", "crop_marks", "color_profile",
    }
    missing = sorted(required - set(profile))
    if missing:
        return ["print_profile is missing: " + ", ".join(missing)], findings, {}
    if profile.get("unit") not in {"mm", "in"}:
        errors.append("print_profile.unit must be mm or in")
    if (
        not isinstance(profile.get("dpi"), int)
        or isinstance(profile.get("dpi"), bool)
        or not 72 <= profile["dpi"] <= 2400
    ):
        errors.append("print_profile.dpi must be an integer from 72 through 2400")
    for group in ("bleed", "safe_margin"):
        value = profile.get(group)
        if not isinstance(value, dict):
            errors.append(f"print_profile.{group} must be an edge-measurement object")
            continue
        for edge in ("top", "right", "bottom", "left"):
            measurement = value.get(edge)
            if not isinstance(measurement, (int, float)) or isinstance(measurement, bool) or measurement < 0:
                errors.append(f"print_profile.{group}.{edge} must be a non-negative number")
    for key in ("trim_width", "trim_height"):
        if (
            not isinstance(profile.get(key), (int, float))
            or isinstance(profile.get(key), bool)
            or profile[key] <= 0
        ):
            errors.append(f"print_profile.{key} must be greater than zero")
    inner_gutter = profile.get("inner_gutter")
    if not isinstance(inner_gutter, (int, float)) or isinstance(inner_gutter, bool) or inner_gutter < 0:
        errors.append("print_profile.inner_gutter must be a non-negative number")
    if profile.get("binding") not in {"none", "perfect", "saddle_stitch", "case_bound", "digital"}:
        errors.append("print_profile.binding has an unsupported value")
    if profile.get("page_side") not in {"auto", "left", "right", "single"}:
        errors.append("print_profile.page_side has an unsupported value")
    if profile.get("export_format") not in {"pdf", "png", "tiff"}:
        errors.append("print_profile.export_format has an unsupported value")
    if not isinstance(profile.get("crop_marks"), bool):
        errors.append("print_profile.crop_marks must be true or false")
    if not isinstance(profile.get("color_profile"), str) or not profile["color_profile"].strip():
        errors.append("print_profile.color_profile must be a non-empty string")
    if errors:
        return errors, findings, {}

    expected_width, expected_height = expected_print_canvas(profile)
    summary = {
        "profile": profile["name"],
        "expected_canvas_px": {"width": expected_width, "height": expected_height},
        "dpi": profile["dpi"],
        "export_format": profile["export_format"],
        "color_profile": profile["color_profile"],
    }
    if target.get("page_width_px") != expected_width or target.get("page_height_px") != expected_height:
        errors.append(
            "target_manga_format pixel dimensions do not equal trim plus bleed at the configured DPI "
            f"({expected_width}x{expected_height}px required)"
        )

    page_paths = [
        path for path in sorted(context.workspace_path("pages").glob("*.json"))
        if not path.name.startswith("._")
    ]
    if not page_paths:
        errors.append("print preflight requires at least one page specification")
    for page_path in page_paths:
        try:
            page = load_json(page_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"failed to load print page specification {page_path.name}: {exc}")
            continue
        page_id = page.get("page_id", page_path.stem)
        size = page.get("page_size", {})
        if size.get("width") != expected_width or size.get("height") != expected_height:
            errors.append(f"{page_id}: page_size must be {expected_width}x{expected_height}px")
            continue
        safe_area = page.get("layout", {}).get("safe_area")
        if not isinstance(safe_area, dict):
            errors.append(f"{page_id}: layout.safe_area is required for print")
            continue
        if not all(
            isinstance(safe_area.get(key), (int, float)) and not isinstance(safe_area.get(key), bool)
            for key in ("x", "y", "width", "height")
        ):
            errors.append(f"{page_id}: layout.safe_area values must be numeric")
            continue
        page_number = page.get("page_number")
        if (
            not isinstance(page_number, int)
            or isinstance(page_number, bool)
            or page_number < 1
        ):
            errors.append(f"{page_id}: page_number must be a positive integer")
            continue
        side = _page_side(context.config, page_number)
        unit = profile["unit"]
        dpi = profile["dpi"]
        bleed = profile["bleed"]
        safe = profile["safe_margin"]
        required_left = _pixels(bleed["left"] + safe["left"], unit, dpi)
        required_right = _pixels(bleed["right"] + safe["right"], unit, dpi)
        if side == "right":
            required_left += _pixels(profile["inner_gutter"], unit, dpi)
        elif side == "left":
            required_right += _pixels(profile["inner_gutter"], unit, dpi)
        actual_right = expected_width - safe_area.get("x", 0) - safe_area.get("width", 0)
        actual_bottom = expected_height - safe_area.get("y", 0) - safe_area.get("height", 0)
        requirements = {
            "left": (safe_area.get("x", 0), required_left),
            "right": (actual_right, required_right),
            "top": (safe_area.get("y", 0), _pixels(bleed["top"] + safe["top"], unit, dpi)),
            "bottom": (actual_bottom, _pixels(bleed["bottom"] + safe["bottom"], unit, dpi)),
        }
        for edge, (actual, required_value) in requirements.items():
            if not isinstance(actual, (int, float)) or actual < required_value:
                errors.append(
                    f"{page_id}: {edge} safe area provides {actual}px; at least {required_value}px is required"
                )
        findings.append({
            "severity": "info",
            "code": "page_side_resolved",
            "message": f"{page_id} is preflighted as a {side} page for binding-gutter calculations.",
        })
    if profile.get("export_format") != "pdf":
        findings.append({
            "severity": "warning",
            "code": "non_pdf_print_export",
            "message": "The configured print export is not PDF; confirm the printer accepts the selected raster format.",
        })
    if profile.get("crop_marks") is False:
        findings.append({
            "severity": "info",
            "code": "crop_marks_disabled",
            "message": "Crop marks are disabled by the selected print profile.",
        })
    return errors, findings, summary
