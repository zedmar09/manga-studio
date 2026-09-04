from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .json_schema import validate_json_file
from .project import (
    INVENTORY_FILE,
    PROJECT_FILE,
    SCHEMA_VERSION,
    STAGE_GATES,
    WORKSPACE_DIRECTORIES,
    ProjectContext,
    image_ready_reasons,
    provenance_errors,
)
from .validation import (
    APPROVED_PREFIX,
    load_json,
    require_fields,
    validate_image_job,
    validate_page_spec,
    validate_relative_project_path,
)


VALIDATION_PROFILES = ("story", "preproduction", "production")


PROJECT_REQUIRED_FIELDS = (
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
    "operating_mode",
    "stage_locks",
    "image_generation_enabled",
    "active_manuscript_version",
    "active_canon_version",
    "active_storyboard_version",
)


def _schema_errors(instance: Path, schema: Path, project_root: Path) -> List[str]:
    if not instance.is_file():
        return []
    try:
        return [
            f"{instance.relative_to(project_root)}: {message}"
            for message in validate_json_file(instance, schema)
        ]
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return [f"schema validation failed for {instance}: {exc}"]


def _validate_story_schemas(context: ProjectContext) -> List[str]:
    schemas = context.install_root / "schemas"
    cases = [
        (context.project_file, schemas / "project.schema.json"),
        (context.workspace_path("source/inventory.json"), schemas / "source-inventory.schema.json"),
        (context.workspace_path("source/provenance.json"), schemas / "provenance.schema.json"),
        (context.workspace_path("source/id-map.json"), schemas / "stable-id-map.schema.json"),
        (context.workspace_path("continuity/state.json"), schemas / "continuity-state.schema.json"),
    ]
    for directory, schema_name in (
        ("canon/characters", "character.schema.json"),
        ("canon/locations", "location.schema.json"),
        ("canon/props", "prop.schema.json"),
    ):
        cases.extend(
            (path, schemas / schema_name)
            for path in sorted(context.workspace_path(directory).glob("*.json"))
        )
    errors: List[str] = []
    for instance, schema in cases:
        errors.extend(_schema_errors(instance, schema, context.project_root))
    return errors


def _validate_project_config(context: ProjectContext) -> List[str]:
    config = context.config
    errors = require_fields(config, PROJECT_REQUIRED_FIELDS, "project")
    if config.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"project.schema_version must be {SCHEMA_VERSION}; found {config.get('schema_version')}"
        )
    if not isinstance(config.get("project_id"), str) or not config.get("project_id"):
        errors.append("project_id must be a non-empty string")
    for key in ("genre", "source_roots", "source_inclusion_patterns", "source_exclusion_patterns"):
        value = config.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            errors.append(f"{key} must be an array of strings")
    for index, path in enumerate(config.get("source_roots", [])):
        errors.extend(validate_relative_project_path(path, f"source_roots[{index}]"))
        if isinstance(path, str) and not validate_relative_project_path(path, f"source_roots[{index}]"):
            resolved = (context.project_root / path).resolve()
            try:
                resolved.relative_to(context.project_root)
            except ValueError:
                errors.append(f"source_roots[{index}] resolves outside project_root: {path}")
    for key in ("chapter_detection_strategy", "existing_structure_preservation", "author_voice_preservation", "target_manga_format"):
        if not isinstance(config.get(key), dict):
            errors.append(f"{key} must be an object")
    if not isinstance(config.get("image_generation_enabled"), bool):
        errors.append("image_generation_enabled must be true or false")

    locks = config.get("stage_locks")
    if not isinstance(locks, dict):
        errors.append("stage_locks must be an object")
    else:
        missing = [gate for gate in STAGE_GATES if gate not in locks]
        extra = sorted(set(locks) - set(STAGE_GATES))
        if missing:
            errors.append(f"stage_locks is missing: {', '.join(missing)}")
        if extra:
            errors.append(f"stage_locks contains unknown gates: {', '.join(extra)}")
        for gate in STAGE_GATES:
            if gate in locks and not isinstance(locks[gate], bool):
                errors.append(f"stage_locks.{gate} must be true or false")

    for field in ("active_manuscript_version", "active_canon_version", "active_storyboard_version"):
        value = config.get(field)
        if value is not None:
            path_errors = validate_relative_project_path(value, field)
            errors.extend(path_errors)
            if not path_errors and not context.project_path(value).exists():
                errors.append(f"{field} does not exist: {value}")

    if locks and locks.get("IMAGE_READY"):
        reasons = image_ready_reasons(context)
        if reasons:
            errors.append("IMAGE_READY is true but its prerequisites fail: " + "; ".join(reasons))
    if locks and locks.get("STORY_LOCKED"):
        for prerequisite in ("SOURCE_LOCKED", "CANON_APPROVED", "MANUSCRIPT_APPROVED"):
            if not locks.get(prerequisite):
                errors.append(f"STORY_LOCKED requires {prerequisite}")
    if locks and locks.get("STORYBOARD_LOCKED") and not locks.get("STORYBOARD_APPROVED"):
        errors.append("STORYBOARD_LOCKED requires STORYBOARD_APPROVED")
    return errors


def _validate_workspace(context: ProjectContext) -> List[str]:
    errors: List[str] = []
    if context.project_file != context.workspace_root / PROJECT_FILE:
        errors.append("project.json must live directly under .manga-studio")
    for relative in WORKSPACE_DIRECTORIES:
        if not context.workspace_path(relative).is_dir():
            errors.append(f"required workspace directory is missing: .manga-studio/{relative}/")
    return errors


def _validate_inventory(context: ProjectContext) -> List[str]:
    path = context.workspace_path(INVENTORY_FILE)
    if not path.exists():
        if context.config.get("stage_locks", {}).get("SOURCE_LOCKED"):
            return ["SOURCE_LOCKED requires .manga-studio/source/inventory.json"]
        return []
    try:
        inventory = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"failed to load source inventory: {exc}"]
    errors = require_fields(inventory, ["schema_version", "project_id", "project_root", "source_roots", "files"], "source inventory")
    if inventory.get("project_id") != context.config.get("project_id"):
        errors.append("source inventory project_id does not match project.json")
    if inventory.get("project_root") != ".":
        errors.append("source inventory project_root must be '.' and must not store an absolute path")
    files = inventory.get("files")
    if not isinstance(files, list):
        errors.append("source inventory files must be an array")
        return errors
    seen_ids = set()
    for index, entry in enumerate(files):
        prefix = f"source inventory files[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix} must be an object")
            continue
        errors.extend(require_fields(entry, [
            "document_id", "relative_path", "extension", "size_bytes", "modified_time_ns",
            "sha256", "classification", "classification_status", "adapter", "support_status",
        ], prefix))
        relative = entry.get("relative_path")
        path_errors = validate_relative_project_path(relative, f"{prefix}.relative_path")
        errors.extend(path_errors)
        if isinstance(relative, str) and relative.startswith(".manga-studio/"):
            errors.append(f"{prefix}.relative_path must not inventory .manga-studio")
        document_id = entry.get("document_id")
        if document_id:
            if document_id in seen_ids:
                errors.append(f"duplicate source document_id: {document_id}")
            seen_ids.add(document_id)
        if entry.get("id_match_status") == "ambiguous" and not entry.get("id_match_candidates"):
            errors.append(f"{prefix} ambiguous match must list candidates for review")
        if entry.get("support_status") == "unsupported" and not entry.get("message"):
            errors.append(f"{prefix} unsupported source must include an actionable message")
    return errors


def _validate_gate_artifacts(context: ProjectContext) -> List[str]:
    locks = context.config.get("stage_locks", {})
    errors: List[str] = []
    requirements = {
        "DIAGNOSTIC_APPROVED": "approvals/diagnostic.json",
        "REVISION_PLAN_APPROVED": "approvals/revision-plan.json",
        "STORYBOARD_APPROVED": "approvals/storyboard.json",
    }
    for gate, path in requirements.items():
        if locks.get(gate) and not context.workspace_path(path).is_file():
            errors.append(f"{gate} requires .manga-studio/{path}")
    if locks.get("CANON_APPROVED") and not context.config.get("active_canon_version"):
        errors.append("CANON_APPROVED requires active_canon_version")
    if locks.get("MANUSCRIPT_APPROVED") and not context.config.get("active_manuscript_version"):
        errors.append("MANUSCRIPT_APPROVED requires active_manuscript_version")
    if locks.get("STORYBOARD_APPROVED") and not context.config.get("active_storyboard_version"):
        errors.append("STORYBOARD_APPROVED requires active_storyboard_version")
    return errors


def _validate_preproduction(context: ProjectContext) -> List[str]:
    errors: List[str] = []
    schemas = context.install_root / "schemas"
    for page_path in sorted(context.workspace_path("pages").glob("*.json")):
        if page_path.name.startswith("._"):
            continue
        errors.extend(_schema_errors(page_path, schemas / "page.schema.json", context.project_root))
        errors.extend(
            f"{page_path.relative_to(context.project_root)}: {message}"
            for message in validate_page_spec(page_path, context.project_root)
        )

    seen_job_ids = set()
    for job_path in sorted(context.workspace_path("handoff/pending").glob("*.json")):
        if job_path.name.startswith("._"):
            continue
        try:
            job = load_json(job_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"failed to load deferred image job '{job_path}': {exc}")
            continue
        job_id = job.get("job_id")
        if job_id in seen_job_ids:
            errors.append(f"duplicate image job_id: {job_id}")
        seen_job_ids.add(job_id)
        errors.extend(_schema_errors(job_path, schemas / "image-job.schema.json", context.project_root))
        if job.get("release_status") != "deferred" and image_ready_reasons(context):
            errors.append(f"{job_path.name}: active image job is blocked until IMAGE_READY prerequisites pass")
        errors.extend(
            f"{job_path.relative_to(context.project_root)}: {message}"
            for message in validate_image_job(
                job_path,
                context.project_root,
                check_reference_existence=False,
            )
        )
    return errors


def _validate_production(context: ProjectContext) -> List[str]:
    errors: List[str] = []
    reasons = image_ready_reasons(context)
    if context.config.get("stage_locks", {}).get("IMAGE_READY") is not True:
        errors.append("production requires stage_locks.IMAGE_READY to be true")
    errors.extend(f"production blocked: {reason}" for reason in reasons)

    page_paths = sorted(context.workspace_path("pages").glob("*.json"))
    if not page_paths:
        errors.append("production requires at least one page plan under .manga-studio/pages/")
    for page_path in page_paths:
        page = load_json(page_path)
        for panel in page.get("panels", []):
            art_path = panel.get("art_path")
            panel_id = panel.get("panel_id", "unknown")
            if not art_path:
                errors.append(f"page {page.get('page_id')} panel {panel_id} has no approved artwork")
                continue
            path_errors = validate_relative_project_path(art_path, f"panel {panel_id}.art_path")
            errors.extend(path_errors)
            if not path_errors:
                if not art_path.startswith(APPROVED_PREFIX):
                    errors.append(f"panel {panel_id} artwork is not under {APPROVED_PREFIX}")
                elif not context.project_path(art_path).is_file():
                    errors.append(f"approved panel artwork is missing: {art_path}")
        page_id = page.get("page_id")
        if page_id:
            if not context.workspace_path(f"lettering/{page_id}-lettered.svg").is_file():
                errors.append(f"lettered page is missing: .manga-studio/lettering/{page_id}-lettered.svg")
            if not context.workspace_path(f"pages/{page_id}-composed.svg").is_file():
                errors.append(f"composed page is missing: .manga-studio/pages/{page_id}-composed.svg")
    return errors


def validate_profile(context: ProjectContext, profile: str) -> List[str]:
    if profile not in VALIDATION_PROFILES:
        return [f"unknown validation profile '{profile}'"]
    errors: List[str] = []
    errors.extend(_validate_story_schemas(context))
    errors.extend(_validate_project_config(context))
    errors.extend(_validate_workspace(context))
    errors.extend(_validate_inventory(context))
    errors.extend(provenance_errors(context))
    errors.extend(_validate_gate_artifacts(context))
    if profile in {"preproduction", "production"}:
        errors.extend(_validate_preproduction(context))
    if profile == "production":
        errors.extend(_validate_production(context))
    return errors
