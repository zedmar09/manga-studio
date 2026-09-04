from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional

from .page_pipeline import (
    boxes_overlap,
    fit_lettering_text,
    panel_polygon,
    point_in_polygon,
    polygon_area,
    polygon_contains_box,
    polygon_self_intersects,
    polygons_overlap,
    source_box_to_page,
)
from .font_metrics import FontMetricError, SfntMetrics


IMAGE_JOB_REQUIRED_FIELDS = [
    "schema_version",
    "job_id",
    "job_type",
    "output_filename",
    "output_spec",
    "content_constraints",
    "required_reference_images",
    "reference_priority",
    "scene_state",
    "character_state",
    "composition",
    "safe_zone_coordinate_system",
    "dialogue_safe_zones",
    "manga_style",
    "quality_profile",
    "required_elements",
    "prohibited_elements",
    "revision_history",
    "release_status",
    "blocking_reasons",
]

IMAGE_JOB_TYPES = {
    "character_reference",
    "location_reference",
    "prop_reference",
    "storyboard_thumbnail",
    "manga_panel",
    "correction",
    "cover",
    "splash_page",
}

PANEL_PROHIBITIONS = {
    "dialogue_text",
    "captions",
    "speech_balloons",
    "sound_effect_text",
    "panel_borders",
    "page_numbers",
    "signatures",
    "watermarks",
    "color",
}

THUMBNAIL_PROHIBITIONS = {
    "final_artwork",
    "dialogue_text",
    "sound_effect_text",
    "signatures",
    "watermarks",
    "color",
}

MANGA_STYLE_FIELDS = {
    "palette",
    "linework",
    "line_weight_strategy",
    "solid_black_strategy",
    "screen_tones",
    "contrast_plan",
    "depth_plan",
    "motion_language",
    "genre",
}

PANEL_COMPOSITION_FIELDS = {
    "camera",
    "framing",
    "reading_focus",
    "event_direction",
    "background_priority",
}

EVENT_DIRECTION_FIELDS = {
    "event_type",
    "intensity",
    "importance",
    "shot_size",
    "camera_angle",
    "camera_motion",
    "action_direction",
    "emotional_beat",
    "pose_and_expression",
    "show_dont_tell_cue",
}

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
APPROVED_PREFIX = ".manga-studio/handoff/approved/"
GENERATED_PREFIX = ".manga-studio/handoff/generated/"
CORRECTIONS_PREFIX = ".manga-studio/handoff/corrections/"


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def project_path(project_root: Path, relative_path: str) -> Path:
    posix_path = PurePosixPath(relative_path)
    return project_root.joinpath(*posix_path.parts)


def validate_relative_project_path(value: Any, field_name: str) -> List[str]:
    errors: List[str] = []
    if not isinstance(value, str) or not value:
        return [f"{field_name} must be a non-empty relative path string"]

    if value.startswith("/") or value.startswith("~"):
        errors.append(f"{field_name} must be relative to the project root: {value}")
    if "\\" in value:
        errors.append(f"{field_name} must use forward slashes: {value}")
    if "//" in value:
        errors.append(f"{field_name} must not contain empty path segments: {value}")

    posix_path = PurePosixPath(value)
    if posix_path.is_absolute():
        errors.append(f"{field_name} must not be absolute: {value}")
    if any(part == ".." for part in posix_path.parts):
        errors.append(f"{field_name} must not leave the project root: {value}")

    return errors


def validate_project_path_containment(project_root: Path, value: Any, field_name: str) -> List[str]:
    path_errors = validate_relative_project_path(value, field_name)
    if path_errors or not isinstance(value, str):
        return path_errors
    try:
        resolved_root = project_root.resolve()
        resolved_path = project_path(project_root, value).resolve()
    except (OSError, RuntimeError) as exc:
        return [f"{field_name} cannot be resolved safely: {value}: {exc}"]
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        return [f"{field_name} resolves outside the project root: {value}"]
    return []


def require_fields(data: Dict[str, Any], fields: Iterable[str], prefix: str) -> List[str]:
    return [f"{prefix} is missing required field '{field}'" for field in fields if field not in data]


def validate_box(box: Any, field_name: str) -> List[str]:
    errors: List[str] = []
    if not isinstance(box, dict):
        return [f"{field_name} must be an object with x, y, width, and height"]
    for key in ["x", "y", "width", "height"]:
        if key not in box:
            errors.append(f"{field_name} is missing '{key}'")
        elif not isinstance(box[key], int) or isinstance(box[key], bool):
            errors.append(f"{field_name}.{key} must be an integer")
    if isinstance(box.get("width"), int) and not isinstance(box.get("width"), bool) and box["width"] <= 0:
        errors.append(f"{field_name}.width must be greater than zero")
    if isinstance(box.get("height"), int) and not isinstance(box.get("height"), bool) and box["height"] <= 0:
        errors.append(f"{field_name}.height must be greater than zero")
    return errors


def validate_normalized_box(box: Any, field_name: str) -> List[str]:
    errors: List[str] = []
    if not isinstance(box, dict):
        return [f"{field_name} must be an object with normalized x, y, width, and height"]
    for key in ["x", "y", "width", "height"]:
        value = box.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"{field_name}.{key} must be a number")
        elif not 0 <= value <= 1:
            errors.append(f"{field_name}.{key} must be between 0 and 1")
    if isinstance(box.get("width"), (int, float)) and box["width"] <= 0:
        errors.append(f"{field_name}.width must be greater than zero")
    if isinstance(box.get("height"), (int, float)) and box["height"] <= 0:
        errors.append(f"{field_name}.height must be greater than zero")
    if all(isinstance(box.get(key), (int, float)) for key in ["x", "y", "width", "height"]):
        if box["x"] + box["width"] > 1:
            errors.append(f"{field_name} must not extend beyond normalized width 1")
        if box["y"] + box["height"] > 1:
            errors.append(f"{field_name} must not extend beyond normalized height 1")
    return errors


def _validate_reference_image(ref: Any, index: int, project_root: Path, check_existence: bool) -> List[str]:
    errors: List[str] = []
    prefix = f"required_reference_images[{index}]"
    if not isinstance(ref, dict):
        return [f"{prefix} must be an object"]

    errors.extend(require_fields(ref, ["reference_id", "kind", "path", "locked", "usage"], prefix))

    if "reference_id" in ref and not isinstance(ref["reference_id"], str):
        errors.append(f"{prefix}.reference_id must be a string")
    if "kind" in ref and ref["kind"] not in {
        "character_reference",
        "location_reference",
        "prop_reference",
        "panel_reference",
        "storyboard_thumbnail",
    }:
        errors.append(f"{prefix}.kind has unsupported value: {ref.get('kind')}")
    if "locked" in ref and not isinstance(ref["locked"], bool):
        errors.append(f"{prefix}.locked must be true or false")
    if "usage" in ref and not isinstance(ref["usage"], str):
        errors.append(f"{prefix}.usage must be a string")

    path_value = ref.get("path")
    path_errors = validate_project_path_containment(project_root, path_value, f"{prefix}.path")
    errors.extend(path_errors)
    if not path_errors and isinstance(path_value, str):
        if not path_value.startswith(APPROVED_PREFIX):
            errors.append(
                f"{prefix}.path must point to an approved image under {APPROVED_PREFIX}: {path_value}"
            )
        if PurePosixPath(path_value).suffix.lower() not in IMAGE_SUFFIXES:
            errors.append(f"{prefix}.path must look like an image file: {path_value}")
        if check_existence and not project_path(project_root, path_value).exists():
            ref_id = ref.get("reference_id", f"index {index}")
            errors.append(f"required reference '{ref_id}' is missing at '{path_value}'")

    return errors


def validate_image_job(
    job_path: Path,
    project_root: Path,
    previous_job_path: Optional[Path] = None,
    check_reference_existence: bool = True,
) -> List[str]:
    errors: List[str] = []
    project_root = project_root.resolve()

    try:
        job = load_json(job_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"failed to load image job '{job_path}': {exc}"]

    errors.extend(require_fields(job, IMAGE_JOB_REQUIRED_FIELDS, "image job"))

    job_type = job.get("job_type")
    if job_type not in IMAGE_JOB_TYPES:
        errors.append(f"job_type has unsupported value: {job_type}")

    for text_field in ["schema_version", "job_id", "output_filename"]:
        if text_field in job and not isinstance(job[text_field], str):
            errors.append(f"{text_field} must be a string")

    output_filename = job.get("output_filename")
    output_errors = validate_project_path_containment(project_root, output_filename, "output_filename")
    errors.extend(output_errors)
    if not output_errors and isinstance(output_filename, str):
        if job_type == "correction":
            if not output_filename.startswith(CORRECTIONS_PREFIX):
                errors.append(f"correction output_filename must be under {CORRECTIONS_PREFIX}")
        elif not output_filename.startswith(GENERATED_PREFIX):
            errors.append(f"output_filename must be under {GENERATED_PREFIX}")
        if PurePosixPath(output_filename).suffix.lower() not in IMAGE_SUFFIXES:
            errors.append(f"output_filename must look like an image file: {output_filename}")

    output_spec = job.get("output_spec")
    if not isinstance(output_spec, dict):
        errors.append("output_spec must be an object")
    else:
        errors.extend(require_fields(output_spec, ["format", "width", "height", "color_mode", "alpha_allowed"], "output_spec"))
        expected_suffixes = {
            "png": {".png"}, "jpeg": {".jpg", ".jpeg"}, "webp": {".webp"}, "tiff": {".tif", ".tiff"}
        }
        output_format = output_spec.get("format")
        if output_format not in expected_suffixes:
            errors.append(f"output_spec.format has unsupported value: {output_format}")
        elif isinstance(output_filename, str) and PurePosixPath(output_filename).suffix.lower() not in expected_suffixes[output_format]:
            errors.append("output_spec.format does not match output_filename extension")
        for dimension in ("width", "height"):
            value = output_spec.get(dimension)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                errors.append(f"output_spec.{dimension} must be a positive integer")
        if output_spec.get("color_mode") not in {"bilevel", "grayscale", "rgb", "rgba"}:
            errors.append(f"output_spec.color_mode has unsupported value: {output_spec.get('color_mode')}")
        if not isinstance(output_spec.get("alpha_allowed"), bool):
            errors.append("output_spec.alpha_allowed must be true or false")

    content_constraints = job.get("content_constraints")
    if not isinstance(content_constraints, dict):
        errors.append("content_constraints must be an object")
    else:
        errors.extend(require_fields(
            content_constraints,
            ["age_band", "content_rating", "content_boundaries", "sensitivity_requirements", "accessibility_goals"],
            "content_constraints",
        ))
        if not isinstance(content_constraints.get("age_band"), str) or not content_constraints.get("age_band", "").strip():
            errors.append("content_constraints.age_band must be a non-empty string")
        if content_constraints.get("content_rating") not in {
            "all_ages", "teen", "older_teen", "mature", "unrated_pending_review"
        }:
            errors.append("content_constraints.content_rating has an unsupported value")
        for field, allow_empty in (("content_boundaries", False), ("sensitivity_requirements", True), ("accessibility_goals", False)):
            values = content_constraints.get(field)
            if (
                not isinstance(values, list)
                or (not allow_empty and not values)
                or not all(isinstance(item, str) and item.strip() for item in values)
            ):
                qualifier = "an array" if allow_empty else "a non-empty array"
                errors.append(f"content_constraints.{field} must be {qualifier} of non-empty strings")

    references = job.get("required_reference_images")
    if not isinstance(references, list):
        errors.append("required_reference_images must be an array")
        references = []
    else:
        seen_refs = set()
        for index, ref in enumerate(references):
            errors.extend(_validate_reference_image(ref, index, project_root, check_reference_existence))
            if isinstance(ref, dict) and isinstance(ref.get("reference_id"), str):
                ref_id = ref["reference_id"]
                if ref_id in seen_refs:
                    errors.append(f"duplicate reference_id in required_reference_images: {ref_id}")
                seen_refs.add(ref_id)

    dependencies = job.get("deferred_reference_dependencies", [])
    dependency_ids: List[str] = []
    if not isinstance(dependencies, list):
        errors.append("deferred_reference_dependencies must be an array")
        dependencies = []
    for index, dependency in enumerate(dependencies):
        prefix = f"deferred_reference_dependencies[{index}]"
        if not isinstance(dependency, dict):
            errors.append(f"{prefix} must be an object")
            continue
        errors.extend(require_fields(dependency, ["reference_id", "source_job_id", "kind", "usage"], prefix))
        reference_id = dependency.get("reference_id")
        if not isinstance(reference_id, str) or not reference_id:
            errors.append(f"{prefix}.reference_id must be a non-empty string")
        else:
            if reference_id in dependency_ids:
                errors.append(f"duplicate deferred reference_id: {reference_id}")
            dependency_ids.append(reference_id)
        if not isinstance(dependency.get("source_job_id"), str) or not dependency.get("source_job_id"):
            errors.append(f"{prefix}.source_job_id must be a non-empty string")
        if dependency.get("kind") not in {
            "character_reference", "location_reference", "prop_reference", "panel_reference", "storyboard_thumbnail"
        }:
            errors.append(f"{prefix}.kind has unsupported value: {dependency.get('kind')}")
        if not isinstance(dependency.get("usage"), str):
            errors.append(f"{prefix}.usage must be a string")

    priority = job.get("reference_priority")
    if not isinstance(priority, list) or not all(isinstance(item, str) for item in priority):
        errors.append("reference_priority must be an array of reference_id strings")
        priority = []

    ref_ids = [ref["reference_id"] for ref in references if isinstance(ref, dict) and isinstance(ref.get("reference_id"), str)]
    priority_ids = [*ref_ids, *dependency_ids]
    if priority_ids or priority:
        if len(priority) != len(set(priority)):
            errors.append("reference_priority must not repeat reference IDs")
        missing_priority = sorted(set(priority_ids) - set(priority))
        extra_priority = sorted(set(priority) - set(priority_ids))
        if missing_priority:
            errors.append(f"reference_priority is missing required references: {', '.join(missing_priority)}")
        if extra_priority:
            errors.append(f"reference_priority names unknown references: {', '.join(extra_priority)}")
    duplicate_sources = sorted(set(ref_ids) & set(dependency_ids))
    if duplicate_sources:
        errors.append(
            "reference IDs cannot be both resolved and deferred: " + ", ".join(duplicate_sources)
        )

    release_status = job.get("release_status")

    for object_field in ["scene_state", "character_state", "composition", "manga_style"]:
        if object_field in job and not isinstance(job[object_field], dict):
            errors.append(f"{object_field} must be an object")

    if job.get("safe_zone_coordinate_system") != "source_normalized":
        errors.append("safe_zone_coordinate_system must be source_normalized")

    manga_style = job.get("manga_style")
    if isinstance(manga_style, dict):
        missing_style = sorted(MANGA_STYLE_FIELDS - set(manga_style))
        if missing_style:
            errors.append(f"manga_style is missing required production fields: {', '.join(missing_style)}")
        for field in MANGA_STYLE_FIELDS - {"palette"}:
            if field in manga_style and (not isinstance(manga_style[field], str) or not manga_style[field].strip()):
                errors.append(f"manga_style.{field} must be a non-empty string")
        if manga_style.get("palette") not in {"black-and-white", "grayscale", "color"}:
            errors.append(f"manga_style.palette has unsupported value: {manga_style.get('palette')}")
        if job_type in {"manga_panel", "storyboard_thumbnail"} and manga_style.get("palette") != "black-and-white":
            errors.append(f"{job_type} manga_style.palette must be black-and-white")
        if job_type in {"manga_panel", "storyboard_thumbnail"} and isinstance(output_spec, dict):
            if output_spec.get("color_mode") not in {"bilevel", "grayscale"}:
                errors.append(f"{job_type} output_spec.color_mode must be bilevel or grayscale")

    quality_profile = job.get("quality_profile")
    if not isinstance(quality_profile, dict):
        errors.append("quality_profile must be an object")
    else:
        errors.extend(require_fields(
            quality_profile,
            ["tier", "goals", "variation_policy", "continuity_strictness", "detail_budget", "self_check_required"],
            "quality_profile",
        ))
        if quality_profile.get("tier") not in {"standard", "high"}:
            errors.append(f"quality_profile.tier has unsupported value: {quality_profile.get('tier')}")
        if release_status in {"ready", "released", "completed"} and quality_profile.get("tier") != "high":
            errors.append("active image jobs must use quality_profile.tier 'high'")
        if release_status in {"ready", "released", "completed"} and quality_profile.get("detail_budget") != "high":
            errors.append("active image jobs must use quality_profile.detail_budget 'high'")
        if release_status in {"ready", "released", "completed"} and quality_profile.get("self_check_required") is not True:
            errors.append("active image jobs must require the quality self-check")
        goals = quality_profile.get("goals")
        if not isinstance(goals, list) or not goals or not all(isinstance(item, str) for item in goals):
            errors.append("quality_profile.goals must be a non-empty array of strings")
        if quality_profile.get("variation_policy") not in {"event_driven", "reference_driven", "layout_driven"}:
            errors.append("quality_profile.variation_policy must be event_driven, reference_driven, or layout_driven")
        if quality_profile.get("continuity_strictness") != "locked":
            errors.append("quality_profile.continuity_strictness must be locked")
        if quality_profile.get("detail_budget") not in {"standard", "high"}:
            errors.append("quality_profile.detail_budget must be standard or high")
        if not isinstance(quality_profile.get("self_check_required"), bool):
            errors.append("quality_profile.self_check_required must be true or false")
        if job_type == "manga_panel" and quality_profile.get("variation_policy") != "event_driven":
            errors.append("manga_panel quality_profile.variation_policy must be event_driven")
        if job_type in {"character_reference", "location_reference", "prop_reference"} and quality_profile.get("variation_policy") != "reference_driven":
            errors.append(f"{job_type} quality_profile.variation_policy must be reference_driven")
        if job_type == "storyboard_thumbnail" and quality_profile.get("variation_policy") != "layout_driven":
            errors.append("storyboard_thumbnail quality_profile.variation_policy must be layout_driven")

    for array_field in ["dialogue_safe_zones", "required_elements", "prohibited_elements"]:
        if array_field in job and not isinstance(job[array_field], list):
            errors.append(f"{array_field} must be an array")
        elif array_field in {"required_elements", "prohibited_elements"} and not all(
            isinstance(item, str) and item.strip() for item in job.get(array_field, [])
        ):
            errors.append(f"{array_field} must contain only non-empty strings")

    safe_zones = job.get("dialogue_safe_zones")
    if isinstance(safe_zones, list):
        for index, box in enumerate(safe_zones):
            errors.extend(validate_normalized_box(box, f"dialogue_safe_zones[{index}]"))

    composition = job.get("composition")
    if isinstance(composition, dict):
        if job_type == "manga_panel":
            missing_composition = sorted(PANEL_COMPOSITION_FIELDS - set(composition))
            if missing_composition:
                errors.append(f"manga_panel composition is missing: {', '.join(missing_composition)}")
            event_direction = composition.get("event_direction")
            if not isinstance(event_direction, dict):
                errors.append("manga_panel composition.event_direction must be an object")
            else:
                missing_direction = sorted(EVENT_DIRECTION_FIELDS - set(event_direction))
                if missing_direction:
                    errors.append(f"manga_panel event_direction is missing: {', '.join(missing_direction)}")
            if composition.get("background_priority") not in {"minimal", "supporting", "story_critical"}:
                errors.append("manga_panel composition.background_priority has an unsupported value")
        elif job_type == "character_reference":
            required = {"sheet_layout", "views", "expressions", "proportion_guide", "continuity_focus", "background"}
            missing = sorted(required - set(composition))
            if missing:
                errors.append(f"character_reference composition is missing: {', '.join(missing)}")
            if not isinstance(composition.get("views"), list) or len(composition.get("views", [])) < 3:
                errors.append("character_reference composition.views must contain at least three views")
            if not isinstance(composition.get("expressions"), list) or len(composition.get("expressions", [])) < 4:
                errors.append("character_reference composition.expressions must contain at least four expressions")
        elif job_type == "location_reference":
            required = {"sheet_layout", "views", "spatial_map", "scale_cues", "continuity_landmarks", "lighting_states"}
            missing = sorted(required - set(composition))
            if missing:
                errors.append(f"location_reference composition is missing: {', '.join(missing)}")
            if not isinstance(composition.get("views"), list) or len(composition.get("views", [])) < 3:
                errors.append("location_reference composition.views must contain at least three views")
        elif job_type == "prop_reference":
            required = {"sheet_layout", "views", "scale_reference", "functional_states", "continuity_markers", "background"}
            missing = sorted(required - set(composition))
            if missing:
                errors.append(f"prop_reference composition is missing: {', '.join(missing)}")
            if not isinstance(composition.get("views"), list) or len(composition.get("views", [])) < 3:
                errors.append("prop_reference composition.views must contain at least three views")
        elif job_type == "storyboard_thumbnail":
            required = {"reading_sequence", "panel_blocks", "balloon_placeholders", "visual_focus", "roughness"}
            missing = sorted(required - set(composition))
            if missing:
                errors.append(f"storyboard_thumbnail composition is missing: {', '.join(missing)}")
            if composition.get("roughness") != "planning_thumbnail_not_final_art":
                errors.append("storyboard_thumbnail must remain a planning thumbnail, not final artwork")

    if release_status not in {"deferred", "ready", "released", "completed", "superseded"}:
        errors.append(f"release_status has unsupported value: {release_status}")
    blocking_reasons = job.get("blocking_reasons")
    if not isinstance(blocking_reasons, list) or not all(isinstance(item, str) for item in blocking_reasons):
        errors.append("blocking_reasons must be an array of strings")
    elif release_status == "deferred" and not blocking_reasons:
        errors.append("deferred image jobs must include at least one blocking reason")
    elif release_status in {"ready", "released", "completed"} and blocking_reasons:
        errors.append(f"{release_status} image jobs must not include blocking reasons")
    if release_status == "deferred":
        for ref in references:
            if isinstance(ref, dict) and isinstance(ref.get("path"), str):
                if not project_path(project_root, ref["path"]).is_file():
                    errors.append(
                        "deferred jobs must use deferred_reference_dependencies instead of "
                        f"inventing a missing reference path: {ref['path']}"
                    )
    elif dependencies:
        errors.append("active image jobs must resolve deferred_reference_dependencies into required_reference_images")

    if job_type == "manga_panel":
        if release_status == "deferred" and not references and not dependencies:
            errors.append("deferred manga_panel jobs must name at least one reference job dependency")
        elif release_status != "deferred" and not references:
            errors.append("manga_panel jobs must name at least one approved reference image")
        prohibited = set(job.get("prohibited_elements", []))
        missing = sorted(PANEL_PROHIBITIONS - prohibited)
        if missing:
            errors.append(f"manga_panel prohibited_elements is missing: {', '.join(missing)}")
    if job_type == "storyboard_thumbnail":
        prohibited = set(job.get("prohibited_elements", []))
        missing = sorted(THUMBNAIL_PROHIBITIONS - prohibited)
        if missing:
            errors.append(f"storyboard_thumbnail prohibited_elements is missing: {', '.join(missing)}")

    revisions = job.get("revision_history")
    if not isinstance(revisions, list) or not revisions:
        errors.append("revision_history must be a non-empty array")
        revisions = []
    else:
        seen_versions = set()
        numeric_versions: List[int] = []
        for index, revision in enumerate(revisions):
            prefix = f"revision_history[{index}]"
            if not isinstance(revision, dict):
                errors.append(f"{prefix} must be an object")
                continue
            errors.extend(require_fields(revision, ["version", "output_filename", "notes"], prefix))
            version = revision.get("version")
            if isinstance(version, str):
                if version in seen_versions:
                    errors.append(f"duplicate revision version: {version}")
                seen_versions.add(version)
                match = re.fullmatch(r"v([0-9]{3})", version)
                if match is None:
                    errors.append(f"{prefix}.version must use v### format")
                else:
                    numeric_versions.append(int(match.group(1)))
            else:
                errors.append(f"{prefix}.version must be a string")
            if "output_filename" in revision:
                errors.extend(validate_project_path_containment(
                    project_root, revision["output_filename"], f"{prefix}.output_filename"
                ))
            if "notes" in revision and not isinstance(revision["notes"], str):
                errors.append(f"{prefix}.notes must be a string")

        if numeric_versions and numeric_versions != sorted(numeric_versions):
            errors.append("revision_history versions must be in ascending order")

        if isinstance(output_filename, str) and revisions:
            latest_output = revisions[-1].get("output_filename") if isinstance(revisions[-1], dict) else None
            if latest_output != output_filename:
                errors.append("latest revision output_filename must match job output_filename")
            previous_outputs = [
                revision.get("output_filename")
                for revision in revisions[:-1]
                if isinstance(revision, dict)
            ]
            if output_filename in previous_outputs:
                errors.append("corrections and revisions must create a new output_filename instead of overwriting")
            job_version = re.search(r"-v([0-9]{3})$", str(job.get("job_id", "")))
            latest_version = revisions[-1].get("version") if isinstance(revisions[-1], dict) else None
            if job_version is not None and latest_version != f"v{job_version.group(1)}":
                errors.append("latest revision version must match the version suffix in job_id")

    if job_type == "correction":
        if not isinstance(job.get("revision_of_job_id"), str):
            errors.append("correction jobs must include revision_of_job_id")
        elif job.get("revision_of_job_id") == job.get("job_id"):
            errors.append("correction revision_of_job_id must identify an earlier job")
        correction = job.get("correction_requirements")
        if not isinstance(correction, dict):
            errors.append("correction jobs must include correction_requirements")
        else:
            errors.extend(require_fields(
                correction,
                ["source_review_id", "requested_changes", "preserve_elements"],
                "correction_requirements",
            ))
            if not isinstance(correction.get("source_review_id"), str) or not correction.get("source_review_id"):
                errors.append("correction_requirements.source_review_id must be a non-empty string")
            for key in ("requested_changes", "preserve_elements"):
                values = correction.get(key)
                if not isinstance(values, list) or not values or not all(isinstance(item, str) for item in values):
                    errors.append(f"correction_requirements.{key} must be a non-empty array of strings")
        latest_revision = revisions[-1] if revisions and isinstance(revisions[-1], dict) else {}
        superseded = latest_revision.get("supersedes_output_filename")
        if not superseded:
            errors.append("correction latest revision must include supersedes_output_filename")
        elif superseded == output_filename:
            errors.append("correction output_filename must differ from supersedes_output_filename")

    if previous_job_path is not None:
        errors.extend(_validate_locked_references(job, previous_job_path))

    return errors


def _validate_locked_references(current_job: Dict[str, Any], previous_job_path: Path) -> List[str]:
    errors: List[str] = []
    try:
        previous_job = load_json(previous_job_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"failed to load previous job '{previous_job_path}': {exc}"]

    previous_refs = {
        ref.get("reference_id"): ref
        for ref in previous_job.get("required_reference_images", [])
        if isinstance(ref, dict) and isinstance(ref.get("reference_id"), str)
    }
    current_refs = {
        ref.get("reference_id"): ref
        for ref in current_job.get("required_reference_images", [])
        if isinstance(ref, dict) and isinstance(ref.get("reference_id"), str)
    }

    for ref_id, previous_ref in previous_refs.items():
        if not previous_ref.get("locked"):
            continue
        current_ref = current_refs.get(ref_id)
        if current_ref is None:
            errors.append(f"locked reference '{ref_id}' was removed")
            continue
        if current_ref.get("path") != previous_ref.get("path"):
            errors.append(
                "locked reference "
                f"'{ref_id}' changed from '{previous_ref.get('path')}' to '{current_ref.get('path')}'"
            )
        if current_ref.get("locked") is not True:
            errors.append(f"locked reference '{ref_id}' must remain locked")

    return errors


def validate_page_spec(page_path: Path, project_root: Path) -> List[str]:
    errors: List[str] = []
    try:
        page = load_json(page_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"failed to load page spec '{page_path}': {exc}"]

    required = [
        "schema_version",
        "page_id",
        "page_number",
        "status",
        "reading_order",
        "reading_sequence",
        "page_size",
        "page_intent",
        "layout",
        "panels",
        "lettering_style",
        "lettering",
    ]
    errors.extend(require_fields(page, required, "page spec"))

    page_size = page.get("page_size", {})
    page_width: Optional[int] = None
    page_height: Optional[int] = None
    if isinstance(page_size, dict):
        for key in ["width", "height"]:
            if (
                not isinstance(page_size.get(key), int)
                or isinstance(page_size.get(key), bool)
                or page_size.get(key) <= 0
            ):
                errors.append(f"page_size.{key} must be a positive integer")
        if isinstance(page_size.get("width"), int) and not isinstance(page_size.get("width"), bool) and page_size["width"] > 0:
            page_width = page_size["width"]
        if isinstance(page_size.get("height"), int) and not isinstance(page_size.get("height"), bool) and page_size["height"] > 0:
            page_height = page_size["height"]
    else:
        errors.append("page_size must be an object")

    layout = page.get("layout")
    global_safe_area: Dict[str, Any] | None = None
    if not isinstance(layout, dict):
        errors.append("layout must be an object")
    else:
        candidate_safe_area = layout.get("safe_area")
        if candidate_safe_area is None:
            errors.append("layout.safe_area is required")
        else:
            safe_area_errors = validate_box(candidate_safe_area, "layout.safe_area")
            errors.extend(safe_area_errors)
            if not safe_area_errors and page_width is not None and page_height is not None:
                if (
                    candidate_safe_area["x"] < 0
                    or candidate_safe_area["y"] < 0
                    or candidate_safe_area["x"] + candidate_safe_area["width"] > page_width
                    or candidate_safe_area["y"] + candidate_safe_area["height"] > page_height
                ):
                    errors.append("layout.safe_area must stay inside the page")
                else:
                    global_safe_area = candidate_safe_area

    lettering_style = page.get("lettering_style")
    if not isinstance(lettering_style, dict):
        errors.append("lettering_style must be an object")
    else:
        font_file = lettering_style.get("font_file")
        if lettering_style.get("embed_font") and not isinstance(font_file, str):
            errors.append("lettering_style.embed_font requires font_file")
        if isinstance(font_file, str):
            font_errors = validate_project_path_containment(project_root, font_file, "lettering_style.font_file")
            errors.extend(font_errors)
            if not font_errors:
                font_path = project_path(project_root, font_file)
                if font_path.suffix.lower() not in {".ttf", ".otf"}:
                    errors.append("lettering_style.font_file must be a TTF or OTF file")
                elif not font_path.is_file():
                    errors.append(f"lettering_style.font_file does not exist: {font_file}")
                else:
                    try:
                        SfntMetrics(font_path)
                    except (OSError, FontMetricError) as exc:
                        errors.append(f"lettering_style.font_file cannot provide usable metrics: {exc}")

    panels = page.get("panels")
    if not isinstance(panels, list) or not panels:
        errors.append("panels must be a non-empty array")
        panels = []

    panel_ids = set()
    panel_records: List[Dict[str, Any]] = []
    for index, panel in enumerate(panels):
        prefix = f"panels[{index}]"
        if not isinstance(panel, dict):
            errors.append(f"{prefix} must be an object")
            continue
        errors.extend(require_fields(panel, ["panel_id", "source_job_id", "frame", "art_path"], prefix))
        panel_id = panel.get("panel_id")
        if isinstance(panel_id, str):
            if panel_id in panel_ids:
                errors.append(f"duplicate panel_id: {panel_id}")
            panel_ids.add(panel_id)
        frame = panel.get("frame")
        frame_errors = validate_box(frame, f"{prefix}.frame")
        errors.extend(frame_errors)
        polygon = []
        if not frame_errors and isinstance(frame, dict):
            if not panel.get("bleed") and page_width is not None and page_height is not None:
                if (
                    frame["x"] < 0
                    or frame["y"] < 0
                    or frame["x"] + frame["width"] > page_width
                    or frame["y"] + frame["height"] > page_height
                ):
                    errors.append(f"{prefix}.frame must stay inside the page unless bleed is true")

            clip_polygon = panel.get("clip_polygon")
            if clip_polygon is not None:
                if not isinstance(clip_polygon, list) or len(clip_polygon) < 3:
                    errors.append(f"{prefix}.clip_polygon must contain at least three points")
                else:
                    valid_points = True
                    point_values = []
                    for point_index, point in enumerate(clip_polygon):
                        point_prefix = f"{prefix}.clip_polygon[{point_index}]"
                        if not isinstance(point, dict):
                            errors.append(f"{point_prefix} must be an object with x and y")
                            valid_points = False
                            continue
                        if (
                            not isinstance(point.get("x"), int)
                            or isinstance(point.get("x"), bool)
                            or not isinstance(point.get("y"), int)
                            or isinstance(point.get("y"), bool)
                        ):
                            errors.append(f"{point_prefix}.x and .y must be integers")
                            valid_points = False
                            continue
                        point_values.append((float(point["x"]), float(point["y"])))
                    if valid_points:
                        polygon = point_values
                        if len(set(polygon)) < 3 or polygon_area(polygon) <= 0:
                            errors.append(f"{prefix}.clip_polygon must define a non-zero area")
                        if polygon_self_intersects(polygon):
                            errors.append(f"{prefix}.clip_polygon must not self-intersect")
                        for x, y in polygon:
                            if not (
                                frame["x"] <= x <= frame["x"] + frame["width"]
                                and frame["y"] <= y <= frame["y"] + frame["height"]
                            ):
                                errors.append(f"{prefix}.clip_polygon must stay inside its frame")
                                break
                            if (
                                not panel.get("bleed")
                                and page_width is not None
                                and page_height is not None
                                and not (0 <= x <= page_width and 0 <= y <= page_height)
                            ):
                                errors.append(f"{prefix}.clip_polygon must stay inside the page unless bleed is true")
                                break
            if not polygon:
                polygon = panel_polygon(panel)

        source_canvas = panel.get("source_canvas")
        source_canvas_valid = isinstance(source_canvas, dict)
        if not source_canvas_valid:
            errors.append(f"{prefix}.source_canvas must be an object")
        else:
            for key in ("width", "height"):
                if not isinstance(source_canvas.get(key), int) or isinstance(source_canvas.get(key), bool) or source_canvas[key] <= 0:
                    errors.append(f"{prefix}.source_canvas.{key} must be a positive integer")
                    source_canvas_valid = False
        if panel.get("safe_zone_coordinate_system") != "source_normalized":
            errors.append(f"{prefix}.safe_zone_coordinate_system must be source_normalized")

        safe_zones = panel.get("dialogue_safe_zones")
        if not isinstance(safe_zones, list):
            errors.append(f"{prefix}.dialogue_safe_zones must be an array")
            safe_zones = []
        projected_safe_zones: List[Dict[str, float]] = []
        for safe_index, safe_zone in enumerate(safe_zones):
            safe_prefix = f"{prefix}.dialogue_safe_zones[{safe_index}]"
            safe_errors = validate_normalized_box(safe_zone, safe_prefix)
            errors.extend(safe_errors)
            if not safe_errors and polygon and source_canvas_valid:
                projected = source_box_to_page(panel, safe_zone)
                projected_safe_zones.append(projected)
                if not polygon_contains_box(polygon, projected):
                    errors.append(
                        f"{safe_prefix} is cropped or leaves the panel after source-image fit/focus placement"
                    )

        event = panel.get("event")
        if event is not None and not isinstance(event, dict):
            errors.append(f"{prefix}.event must be an object")
        elif isinstance(event, dict) and not isinstance(event.get("show_dont_tell_cue"), str):
            errors.append(f"{prefix}.event.show_dont_tell_cue must be a string")

        art_path = panel.get("art_path")
        if art_path is None:
            if page.get("status") in {"ready_for_composition", "composed", "lettered", "exported"}:
                errors.append(f"{prefix}.art_path is required when page status is {page.get('status')}")
        else:
            path_errors = validate_project_path_containment(project_root, art_path, f"{prefix}.art_path")
            errors.extend(path_errors)
            if not path_errors:
                if not art_path.startswith(APPROVED_PREFIX):
                    errors.append(f"{prefix}.art_path must point under {APPROVED_PREFIX}")
                elif not project_path(project_root, art_path).exists():
                    errors.append(f"{prefix}.art_path does not exist: {art_path}")
        if polygon:
            panel_records.append({
                "panel": panel,
                "polygon": polygon,
                "prefix": prefix,
                "projected_safe_zones": projected_safe_zones,
            })

    reading_sequence = page.get("reading_sequence")
    if reading_sequence is None:
        errors.append("reading_sequence is required")
    else:
        if not isinstance(reading_sequence, list) or not all(isinstance(item, str) for item in reading_sequence):
            errors.append("reading_sequence must be an array of panel_id strings")
        else:
            if len(reading_sequence) != len(set(reading_sequence)):
                errors.append("reading_sequence must not repeat panel IDs")
            missing = sorted(panel_ids - set(reading_sequence))
            extra = sorted(set(reading_sequence) - panel_ids)
            if missing:
                errors.append(f"reading_sequence is missing panels: {', '.join(missing)}")
            if extra:
                errors.append(f"reading_sequence names unknown panels: {', '.join(extra)}")

    allow_page_overlap = bool(page.get("layout", {}).get("allow_panel_overlap")) if isinstance(page.get("layout", {}), dict) else False
    for index, first in enumerate(panel_records):
        for second in panel_records[index + 1:]:
            if not polygons_overlap(first["polygon"], second["polygon"]):
                continue
            first_panel = first["panel"]
            second_panel = second["panel"]
            if not (allow_page_overlap or first_panel.get("allow_overlap") or second_panel.get("allow_overlap")):
                errors.append(
                    f"panels '{first_panel.get('panel_id')}' and '{second_panel.get('panel_id')}' overlap without permission"
                )
            if first_panel.get("z_index", 0) == second_panel.get("z_index", 0):
                errors.append(
                    f"overlapping panels '{first_panel.get('panel_id')}' and '{second_panel.get('panel_id')}' need distinct z_index values"
                )

    lettering = page.get("lettering")
    if not isinstance(lettering, list):
        errors.append("lettering must be an array")
        lettering = []
    lettering_records: List[Dict[str, Any]] = []
    lettering_ids = set()
    reading_orders = []
    panels_by_id = {
        record["panel"].get("panel_id"): record
        for record in panel_records
        if isinstance(record["panel"].get("panel_id"), str)
    }
    for index, item in enumerate(lettering):
        prefix = f"lettering[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        errors.extend(require_fields(item, ["panel_id", "kind", "text", "box"], prefix))
        panel_id = item.get("panel_id")
        if panel_id not in panel_ids:
            errors.append(f"{prefix}.panel_id does not match a panel: {panel_id}")
        lettering_id = item.get("lettering_id")
        if lettering_id is not None:
            if not isinstance(lettering_id, str) or not lettering_id:
                errors.append(f"{prefix}.lettering_id must be a non-empty string")
            elif lettering_id in lettering_ids:
                errors.append(f"duplicate lettering_id: {lettering_id}")
            else:
                lettering_ids.add(lettering_id)
        reading_order = item.get("reading_order")
        if reading_order is not None:
            if not isinstance(reading_order, int) or isinstance(reading_order, bool) or reading_order <= 0:
                errors.append(f"{prefix}.reading_order must be a positive integer")
            else:
                reading_orders.append(reading_order)
        if not isinstance(item.get("text"), str) or not item.get("text", "").strip():
            errors.append(f"{prefix}.text must be a non-empty string")

        box = item.get("box")
        box_errors = validate_box(box, f"{prefix}.box")
        errors.extend(box_errors)
        if not box_errors and isinstance(box, dict):
            if page_width is not None and page_height is not None and (
                box["x"] < 0
                or box["y"] < 0
                or box["x"] + box["width"] > page_width
                or box["y"] + box["height"] > page_height
            ):
                errors.append(f"{prefix}.box must stay inside the page")
            panel_record = panels_by_id.get(panel_id)
            if panel_record and not item.get("allow_cross_panel"):
                if not polygon_contains_box(panel_record["polygon"], box):
                    errors.append(f"{prefix}.box must stay inside panel '{panel_id}'")
                safe_zones = panel_record.get("projected_safe_zones", [])
                if item.get("kind") != "sfx" and not item.get("allow_outside_safe_zone"):
                    if safe_zones and not any(
                        isinstance(zone, dict) and all(
                            isinstance(zone.get(key), (int, float))
                            for key in ("x", "y", "width", "height")
                        ) and all(
                            zone["x"] <= x <= zone["x"] + zone["width"]
                            and zone["y"] <= y <= zone["y"] + zone["height"]
                            for x, y in [
                                (box["x"], box["y"]),
                                (box["x"] + box["width"], box["y"] + box["height"]),
                            ]
                        )
                        for zone in safe_zones
                    ):
                        errors.append(f"{prefix}.box must stay inside a dialogue-safe zone")
            if (
                global_safe_area
                and item.get("kind") != "sfx"
                and not item.get("allow_outside_safe_zone")
                and not (
                    global_safe_area["x"] <= box["x"]
                    and global_safe_area["y"] <= box["y"]
                    and box["x"] + box["width"] <= global_safe_area["x"] + global_safe_area["width"]
                    and box["y"] + box["height"] <= global_safe_area["y"] + global_safe_area["height"]
                )
            ):
                errors.append(f"{prefix}.box must stay inside layout.safe_area")
            if isinstance(item.get("text"), str) and item.get("text", "").strip():
                if not fit_lettering_text(item, page.get("lettering_style", {}), project_root)["fits"]:
                    errors.append(f"{prefix}.text does not fit its box at the minimum font size")
            lettering_records.append({"item": item, "box": box, "prefix": prefix})

        tail = item.get("tail_to")
        if tail is not None:
            if (
                not isinstance(tail, dict)
                or not isinstance(tail.get("x"), int)
                or isinstance(tail.get("x"), bool)
                or not isinstance(tail.get("y"), int)
                or isinstance(tail.get("y"), bool)
            ):
                errors.append(f"{prefix}.tail_to must contain integer x and y")
            else:
                panel_record = panels_by_id.get(panel_id)
                if panel_record and not point_in_polygon((float(tail["x"]), float(tail["y"])), panel_record["polygon"]):
                    errors.append(f"{prefix}.tail_to must point inside panel '{panel_id}'")

        if item.get("kind") == "sfx":
            sound = item.get("sound")
            if not isinstance(sound, dict):
                errors.append(f"{prefix}.sound is required for sfx lettering")
            else:
                errors.extend(require_fields(sound, ["source", "meaning", "intensity"], f"{prefix}.sound"))

    if reading_orders and len(reading_orders) != len(lettering):
        errors.append("when one lettering item has reading_order, every lettering item must have reading_order")
    if len(reading_orders) != len(set(reading_orders)):
        errors.append("lettering reading_order values must be unique")

    for index, first in enumerate(lettering_records):
        for second in lettering_records[index + 1:]:
            if first["item"].get("panel_id") != second["item"].get("panel_id"):
                continue
            if boxes_overlap(first["box"], second["box"]) and not (
                first["item"].get("allow_overlap") or second["item"].get("allow_overlap")
            ):
                errors.append(
                    f"{first['prefix']} and {second['prefix']} overlap without permission"
                )

    return errors


def validate_creative_brief(brief_path: Path, project_id: str) -> List[str]:
    try:
        brief = load_json(brief_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"failed to load creative brief '{brief_path}': {exc}"]
    errors: List[str] = []
    if brief.get("project_id") != project_id:
        errors.append("creative brief project_id does not match project.json")
    target = brief.get("target_length")
    if isinstance(target, dict):
        minimum = target.get("minimum")
        maximum = target.get("maximum")
        if isinstance(minimum, int) and isinstance(maximum, int) and minimum > maximum:
            errors.append("creative brief target_length.minimum must not exceed maximum")
    originality = brief.get("originality")
    if isinstance(originality, dict):
        if not originality.get("differentiators"):
            errors.append("creative brief must state at least one differentiator")
        if not originality.get("prohibited_derivation"):
            errors.append("creative brief must state prohibited derivation boundaries")
    return errors


def validate_success_plan(plan_path: Path, project_id: str, project_root: Path) -> List[str]:
    try:
        plan = load_json(plan_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"failed to load success plan '{plan_path}': {exc}"]
    errors: List[str] = []
    if plan.get("project_id") != project_id:
        errors.append("success plan project_id does not match project.json")

    brief_rel = plan.get("creative_brief_path")
    path_errors = validate_project_path_containment(
        project_root, brief_rel, "success plan creative_brief_path"
    )
    errors.extend(path_errors)
    if isinstance(brief_rel, str) and not brief_rel.startswith(".manga-studio/story/briefs/"):
        errors.append("success plan creative_brief_path must be under .manga-studio/story/briefs/")
    if isinstance(brief_rel, str) and not path_errors:
        brief_path = (project_root / brief_rel).resolve()
        if not brief_path.is_file():
            errors.append(f"success plan creative brief is missing: {brief_rel}")
        else:
            current_hash = hashlib.sha256(brief_path.read_bytes()).hexdigest()
            if current_hash != plan.get("creative_brief_sha256"):
                errors.append(f"success plan creative brief checksum changed: {brief_rel}")

    audience = plan.get("audience_and_positioning")
    basis = plan.get("basis")
    research_sources = basis.get("research_sources", []) if isinstance(basis, dict) else []
    source_kinds: Dict[str, str] = {}
    for index, source in enumerate(research_sources if isinstance(research_sources, list) else []):
        if not isinstance(source, dict):
            continue
        source_id = source.get("source_id")
        if isinstance(source_id, str):
            if source_id in source_kinds:
                errors.append(f"success plan research source_id is duplicated: {source_id}")
            source_kinds[source_id] = source.get("kind")
        if source.get("kind") in {"market_research", "platform_documentation", "analytics", "legal_advice"} and not source.get("accessed_on"):
            errors.append(f"success plan basis.research_sources[{index}] requires accessed_on")

    hypotheses = audience.get("market_hypotheses", []) if isinstance(audience, dict) else []
    expected_kinds = {
        "user_provided": {"user_input"},
        "researched": {"market_research", "platform_documentation"},
        "feedback_supported": {"reader_feedback"},
        "analytics_supported": {"analytics"},
    }
    for index, hypothesis in enumerate(hypotheses if isinstance(hypotheses, list) else []):
        if not isinstance(hypothesis, dict):
            continue
        status = hypothesis.get("evidence_status")
        source_ids = hypothesis.get("evidence_source_ids", [])
        if not isinstance(source_ids, list):
            source_ids = []
        if status in expected_kinds and not source_ids:
            errors.append(
                f"success plan market_hypotheses[{index}] with evidence_status {status} requires evidence_source_ids"
            )
        for source_id in source_ids:
            if source_id not in source_kinds:
                errors.append(
                    f"success plan market_hypotheses[{index}] references unknown research source: {source_id}"
                )
            elif status in expected_kinds and source_kinds[source_id] not in expected_kinds[status]:
                errors.append(
                    f"success plan market_hypotheses[{index}] evidence source kind does not match {status}: {source_id}"
                )

    publishing = plan.get("publishing_strategy")
    if isinstance(publishing, dict):
        if publishing.get("status") == "planned" and not publishing.get("target_channels"):
            errors.append("success plan publishing_strategy.status planned requires target_channels")
        image_deliverables = {"thumbnail", "cover", "promo_strip", "character_sheet", "key_image"}
        deliverables = publishing.get("discoverability_deliverables", [])
        if not isinstance(deliverables, list):
            deliverables = []
        for index, deliverable in enumerate(deliverables):
            if not isinstance(deliverable, dict):
                continue
            kind = deliverable.get("deliverable")
            owner = deliverable.get("owner")
            job_rel = deliverable.get("image_job_path")
            prefix = f"success plan discoverability_deliverables[{index}]"
            if kind in image_deliverables and owner != "chatgpt_image_generation":
                errors.append(f"{prefix} visual deliverable must be owned by chatgpt_image_generation")
            if kind == "trailer" and owner not in {"external_media_tool", "human"}:
                errors.append(f"{prefix} trailer must have an external media or human owner")
            if kind in image_deliverables and deliverable.get("status") in {"ready", "completed"}:
                job_errors = validate_project_path_containment(
                    project_root, job_rel, f"{prefix}.image_job_path"
                )
                errors.extend(job_errors)
                if isinstance(job_rel, str) and not (
                    job_rel.startswith(".manga-studio/handoff/pending/")
                    or job_rel.startswith(".manga-studio/handoff/corrections/")
                ):
                    errors.append(f"{prefix}.image_job_path must be under a handoff job directory")
                if isinstance(job_rel, str) and not job_errors and not (project_root / job_rel).is_file():
                    errors.append(f"{prefix}.image_job_path does not exist: {job_rel}")
            elif kind not in image_deliverables and job_rel is not None:
                errors.append(f"{prefix}.image_job_path is only valid for a visual image deliverable")

    measurement = plan.get("measurement_and_iteration")
    metrics = measurement.get("primary_metrics", []) if isinstance(measurement, dict) else []
    if isinstance(metrics, list):
        names = [item.get("name") for item in metrics if isinstance(item, dict)]
        if len(names) != len(set(names)):
            errors.append("success plan primary metric names must be unique")
        metric_names = {name for name in names if isinstance(name, str)}
    else:
        metric_names = set()
    observations = measurement.get("observations", []) if isinstance(measurement, dict) else []
    observation_ids: set[str] = set()
    for index, observation in enumerate(observations if isinstance(observations, list) else []):
        if not isinstance(observation, dict):
            continue
        observation_id = observation.get("observation_id")
        if isinstance(observation_id, str):
            if observation_id in observation_ids:
                errors.append(f"success plan observation_id is duplicated: {observation_id}")
            observation_ids.add(observation_id)
        metric_name = observation.get("metric_name")
        if metric_name not in metric_names:
            errors.append(
                f"success plan observations[{index}] references unknown primary metric: {metric_name}"
            )
        evidence_ids = observation.get("evidence_source_ids", [])
        if isinstance(evidence_ids, list):
            for source_id in evidence_ids:
                if source_id not in source_kinds:
                    errors.append(
                        f"success plan observations[{index}] references unknown evidence source: {source_id}"
                    )
    return errors


def validate_nemu(nemu_path: Path, project_id: str) -> List[str]:
    try:
        nemu = load_json(nemu_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"failed to load nemu '{nemu_path}': {exc}"]
    errors: List[str] = []
    if nemu.get("project_id") != project_id:
        errors.append("nemu project_id does not match project.json")
    if nemu.get("representation") != "structured_geometry_only":
        errors.append("nemu must remain structured geometry and must not contain Codex-generated artwork")
    pages = nemu.get("pages")
    if not isinstance(pages, list) or not pages:
        return [*errors, "nemu pages must be a non-empty array"]
    page_ids = set()
    for page_index, page in enumerate(pages):
        prefix = f"nemu.pages[{page_index}]"
        if not isinstance(page, dict):
            errors.append(f"{prefix} must be an object")
            continue
        page_id = page.get("page_id")
        if page_id in page_ids:
            errors.append(f"duplicate nemu page_id: {page_id}")
        page_ids.add(page_id)
        panels = page.get("panels")
        if not isinstance(panels, list) or not panels:
            errors.append(f"{prefix}.panels must be a non-empty array")
            panels = []
        panel_ids = set()
        for panel_index, panel in enumerate(panels):
            panel_prefix = f"{prefix}.panels[{panel_index}]"
            if not isinstance(panel, dict):
                errors.append(f"{panel_prefix} must be an object")
                continue
            panel_id = panel.get("panel_id")
            if panel_id in panel_ids:
                errors.append(f"{prefix} repeats panel_id {panel_id}")
            panel_ids.add(panel_id)
            errors.extend(validate_normalized_box(panel.get("frame"), f"{panel_prefix}.frame"))
        sequence = page.get("reading_sequence")
        if isinstance(sequence, list):
            missing = panel_ids - set(sequence)
            extra = set(sequence) - panel_ids
            if missing:
                errors.append(f"{prefix}.reading_sequence is missing panels: {', '.join(sorted(missing))}")
            if extra:
                errors.append(f"{prefix}.reading_sequence names unknown panels: {', '.join(sorted(extra))}")
        lettering = page.get("lettering_plan")
        if isinstance(lettering, list):
            orders = []
            for item_index, item in enumerate(lettering):
                item_prefix = f"{prefix}.lettering_plan[{item_index}]"
                if not isinstance(item, dict):
                    continue
                if item.get("panel_id") not in panel_ids:
                    errors.append(f"{item_prefix}.panel_id does not match a nemu panel")
                errors.extend(validate_normalized_box(item.get("zone"), f"{item_prefix}.zone"))
                if isinstance(item.get("reading_order"), int):
                    orders.append(item["reading_order"])
            if len(orders) != len(set(orders)):
                errors.append(f"{prefix}.lettering_plan reading_order values must be unique")
    checklist = nemu.get("review_checklist")
    if isinstance(checklist, dict) and nemu.get("status") == "approved":
        incomplete = sorted(key for key, value in checklist.items() if value is not True)
        if incomplete:
            errors.append(f"approved nemu has incomplete review checks: {', '.join(incomplete)}")
    return errors


def validate_project(project_root: Path, strict_image_jobs: bool = False) -> List[str]:
    errors: List[str] = []
    project_root = project_root.resolve()
    workspace_root = project_root / ".manga-studio"
    project_file = workspace_root / "project.json"

    try:
        project = load_json(project_file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"failed to load project '{project_file}': {exc}"]

    required = [
        "schema_version",
        "project_id",
        "title",
        "source_language",
        "output_language",
        "project_type",
        "genre",
        "source_roots",
        "source_inclusion_patterns",
        "source_exclusion_patterns",
        "chapter_detection_strategy",
        "existing_structure_preservation",
        "revision_mode",
        "author_voice_preservation",
        "reading_direction",
        "target_manga_format",
        "workflow_phase",
        "stage_locks",
        "image_generation_enabled",
        "active_manuscript_version",
        "active_canon_version",
        "active_storyboard_version",
    ]
    errors.extend(require_fields(project, required, "project"))

    for key in ("source_roots", "source_inclusion_patterns", "source_exclusion_patterns"):
        values = project.get(key)
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            errors.append(f"{key} must be an array of strings")
    for index, source_root in enumerate(project.get("source_roots", [])):
        errors.extend(validate_relative_project_path(source_root, f"source_roots[{index}]"))

    pages_dir = workspace_root / "pages"
    if pages_dir.is_dir():
        for page_path in sorted(pages_dir.glob("*.json")):
            if not page_path.name.startswith("._"):
                errors.extend(
                    f"{page_path.relative_to(project_root)}: {message}"
                    for message in validate_page_spec(page_path, project_root)
                )

    pending_dir = workspace_root / "handoff" / "pending"
    job_ids = set()
    if pending_dir.is_dir():
        for job_path in sorted(pending_dir.glob("*.json")):
            if job_path.name.startswith("._"):
                continue
            try:
                job = load_json(job_path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"failed to load pending job '{job_path}': {exc}")
                continue
            job_id = job.get("job_id")
            if isinstance(job_id, str):
                if job_id in job_ids:
                    errors.append(f"duplicate image job_id in pending handoff: {job_id}")
                job_ids.add(job_id)
            errors.extend(
                f"{job_path.relative_to(project_root)}: {message}"
                for message in validate_image_job(
                    job_path,
                    project_root,
                    check_reference_existence=strict_image_jobs,
                )
            )
    else:
        errors.append(f"handoff pending directory does not exist: {pending_dir}")

    return errors
