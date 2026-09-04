from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional


IMAGE_JOB_REQUIRED_FIELDS = [
    "schema_version",
    "job_id",
    "job_type",
    "output_filename",
    "required_reference_images",
    "reference_priority",
    "scene_state",
    "character_state",
    "composition",
    "dialogue_safe_zones",
    "manga_style",
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


def require_fields(data: Dict[str, Any], fields: Iterable[str], prefix: str) -> List[str]:
    return [f"{prefix} is missing required field '{field}'" for field in fields if field not in data]


def validate_box(box: Any, field_name: str) -> List[str]:
    errors: List[str] = []
    if not isinstance(box, dict):
        return [f"{field_name} must be an object with x, y, width, and height"]
    for key in ["x", "y", "width", "height"]:
        if key not in box:
            errors.append(f"{field_name} is missing '{key}'")
        elif not isinstance(box[key], int):
            errors.append(f"{field_name}.{key} must be an integer")
    if isinstance(box.get("width"), int) and box["width"] <= 0:
        errors.append(f"{field_name}.width must be greater than zero")
    if isinstance(box.get("height"), int) and box["height"] <= 0:
        errors.append(f"{field_name}.height must be greater than zero")
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
    }:
        errors.append(f"{prefix}.kind has unsupported value: {ref.get('kind')}")
    if "locked" in ref and not isinstance(ref["locked"], bool):
        errors.append(f"{prefix}.locked must be true or false")
    if "usage" in ref and not isinstance(ref["usage"], str):
        errors.append(f"{prefix}.usage must be a string")

    path_value = ref.get("path")
    path_errors = validate_relative_project_path(path_value, f"{prefix}.path")
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
    output_errors = validate_relative_project_path(output_filename, "output_filename")
    errors.extend(output_errors)
    if not output_errors and isinstance(output_filename, str):
        if job_type == "correction":
            if not output_filename.startswith(CORRECTIONS_PREFIX):
                errors.append(f"correction output_filename must be under {CORRECTIONS_PREFIX}")
        elif not output_filename.startswith(GENERATED_PREFIX):
            errors.append(f"output_filename must be under {GENERATED_PREFIX}")
        if PurePosixPath(output_filename).suffix.lower() not in IMAGE_SUFFIXES:
            errors.append(f"output_filename must look like an image file: {output_filename}")

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
            "character_reference", "location_reference", "prop_reference", "panel_reference"
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
        missing_priority = sorted(set(priority_ids) - set(priority))
        extra_priority = sorted(set(priority) - set(priority_ids))
        if missing_priority:
            errors.append(f"reference_priority is missing required references: {', '.join(missing_priority)}")
        if extra_priority:
            errors.append(f"reference_priority names unknown references: {', '.join(extra_priority)}")

    for object_field in ["scene_state", "character_state", "composition", "manga_style"]:
        if object_field in job and not isinstance(job[object_field], dict):
            errors.append(f"{object_field} must be an object")

    for array_field in ["dialogue_safe_zones", "required_elements", "prohibited_elements"]:
        if array_field in job and not isinstance(job[array_field], list):
            errors.append(f"{array_field} must be an array")

    safe_zones = job.get("dialogue_safe_zones")
    if isinstance(safe_zones, list):
        for index, box in enumerate(safe_zones):
            errors.extend(validate_box(box, f"dialogue_safe_zones[{index}]"))

    release_status = job.get("release_status")
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

    revisions = job.get("revision_history")
    if not isinstance(revisions, list) or not revisions:
        errors.append("revision_history must be a non-empty array")
        revisions = []
    else:
        seen_versions = set()
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
            else:
                errors.append(f"{prefix}.version must be a string")
            if "output_filename" in revision:
                errors.extend(validate_relative_project_path(revision["output_filename"], f"{prefix}.output_filename"))
            if "notes" in revision and not isinstance(revision["notes"], str):
                errors.append(f"{prefix}.notes must be a string")

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

    if job_type == "correction":
        if not isinstance(job.get("revision_of_job_id"), str):
            errors.append("correction jobs must include revision_of_job_id")
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
        "page_size",
        "panels",
        "lettering",
    ]
    errors.extend(require_fields(page, required, "page spec"))

    page_size = page.get("page_size", {})
    if isinstance(page_size, dict):
        for key in ["width", "height"]:
            if not isinstance(page_size.get(key), int) or page_size.get(key) <= 0:
                errors.append(f"page_size.{key} must be a positive integer")
    else:
        errors.append("page_size must be an object")

    panels = page.get("panels")
    if not isinstance(panels, list) or not panels:
        errors.append("panels must be a non-empty array")
        panels = []

    panel_ids = set()
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
        errors.extend(validate_box(panel.get("frame"), f"{prefix}.frame"))
        art_path = panel.get("art_path")
        if art_path is None:
            if page.get("status") in {"ready_for_composition", "composed", "lettered", "exported"}:
                errors.append(f"{prefix}.art_path is required when page status is {page.get('status')}")
        else:
            path_errors = validate_relative_project_path(art_path, f"{prefix}.art_path")
            errors.extend(path_errors)
            if not path_errors:
                if not art_path.startswith(APPROVED_PREFIX):
                    errors.append(f"{prefix}.art_path must point under {APPROVED_PREFIX}")
                elif not project_path(project_root, art_path).exists():
                    errors.append(f"{prefix}.art_path does not exist: {art_path}")

    lettering = page.get("lettering")
    if not isinstance(lettering, list):
        errors.append("lettering must be an array")
        lettering = []
    for index, item in enumerate(lettering):
        prefix = f"lettering[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        errors.extend(require_fields(item, ["panel_id", "kind", "text", "box"], prefix))
        if item.get("panel_id") not in panel_ids:
            errors.append(f"{prefix}.panel_id does not match a panel: {item.get('panel_id')}")
        errors.extend(validate_box(item.get("box"), f"{prefix}.box"))

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
