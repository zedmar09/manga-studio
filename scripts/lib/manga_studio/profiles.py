from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .json_schema import validate_json_file
from .page_pipeline import latest_version_path
from .print_preflight import preflight_project
from .project import (
    INVENTORY_FILE,
    PROJECT_FILE,
    SCHEMA_VERSION,
    STAGE_GATES,
    USAGE_ROLES,
    WORKSPACE_DIRECTORIES,
    ProjectContext,
    image_ready_reasons,
    provenance_errors,
    sha256_file,
)
from .validation import (
    APPROVED_PREFIX,
    load_json,
    require_fields,
    validate_creative_brief,
    validate_image_job,
    validate_nemu,
    validate_page_spec,
    validate_project_path_containment,
    validate_relative_project_path,
    validate_success_plan,
)
from .story import validate_story_artifacts


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
    "stage_lock_records",
    "image_generation_enabled",
    "active_manuscript_version",
    "active_canon_version",
    "active_storyboard_version",
)


def _schema_errors(instance: Path, schema: Path, project_root: Path) -> List[str]:
    if not instance.is_file():
        return []
    try:
        instance.resolve().relative_to(project_root.resolve())
        return [
            f"{instance.relative_to(project_root)}: {message}"
            for message in validate_json_file(instance, schema)
        ]
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
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
    for pattern, schema_name in (
        ("story/briefs/*.json", "creative-brief.schema.json"),
        ("story/success-plans/*.json", "success-plan.schema.json"),
        ("storyboard/nemu/*.json", "nemu.schema.json"),
        ("continuity/intake/*.json", "generated-image.schema.json"),
    ):
        cases.extend(
            (path, schemas / schema_name)
            for path in sorted(context.workspace_path(".").glob(pattern))
            if not path.name.startswith("._")
        )
    for directory, schema_name in (
        ("canon/characters", "character.schema.json"),
        ("canon/locations", "location.schema.json"),
        ("canon/props", "prop.schema.json"),
    ):
        cases.extend(
            (path, schemas / schema_name)
            for path in sorted(context.workspace_path(directory).glob("*.json"))
            if not path.name.startswith("._")
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
    target_format = config.get("target_manga_format")
    if isinstance(target_format, dict):
        output_intent = target_format.get("output_intent", "screen")
        if output_intent not in {"screen", "print", "both"}:
            errors.append(f"target_manga_format.output_intent has unsupported value: {output_intent}")
        if output_intent in {"print", "both"} and not isinstance(target_format.get("print_profile"), dict):
            errors.append("print or both output intent requires target_manga_format.print_profile")
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
    lock_records = config.get("stage_lock_records")
    if not isinstance(lock_records, dict):
        errors.append("stage_lock_records must be an object")
    else:
        missing = [gate for gate in STAGE_GATES if gate not in lock_records]
        extra = sorted(set(lock_records) - set(STAGE_GATES))
        if missing:
            errors.append(f"stage_lock_records is missing: {', '.join(missing)}")
        if extra:
            errors.append(f"stage_lock_records contains unknown gates: {', '.join(extra)}")
        for gate, value in lock_records.items():
            if value is not None:
                errors.extend(validate_relative_project_path(value, f"stage_lock_records.{gate}"))

    for field in (
        "active_manuscript_version", "active_canon_version", "active_storyboard_version",
        "active_creative_brief_version", "active_success_plan_version", "active_nemu_version",
    ):
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

    success_plan_rel = config.get("active_success_plan_version")
    if isinstance(success_plan_rel, str):
        success_plan_path_errors = validate_project_path_containment(
            context.project_root,
            success_plan_rel, "active_success_plan_version"
        )
        if success_plan_path_errors:
            return errors
        if not success_plan_rel.startswith(".manga-studio/story/success-plans/"):
            errors.append(
                "active_success_plan_version must be under .manga-studio/story/success-plans/"
            )
            return errors
        success_plan_path = context.project_path(success_plan_rel)
        errors.extend(
            validate_success_plan(
                success_plan_path, config.get("project_id"), context.project_root
            )
        )
        active_brief = config.get("active_creative_brief_version")
        if success_plan_path.is_file():
            try:
                success_plan = load_json(success_plan_path)
                if success_plan.get("creative_brief_path") != active_brief:
                    errors.append(
                        "active success plan must reference active_creative_brief_version"
                    )
            except (OSError, ValueError, json.JSONDecodeError):
                pass
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
            "usage_role",
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
        if entry.get("usage_role") is not None and entry.get("usage_role") not in USAGE_ROLES:
            errors.append(f"{prefix}.usage_role has unsupported value: {entry.get('usage_role')}")
        if entry.get("support_status") == "unsupported" and not entry.get("message"):
            errors.append(f"{prefix} unsupported source must include an actionable message")
    return errors


def _validate_gate_artifacts(context: ProjectContext) -> List[str]:
    locks = context.config.get("stage_locks", {})
    errors: List[str] = []
    if locks.get("CANON_APPROVED") and not context.config.get("active_canon_version"):
        errors.append("CANON_APPROVED requires active_canon_version")
    if locks.get("MANUSCRIPT_APPROVED") and not context.config.get("active_manuscript_version"):
        errors.append("MANUSCRIPT_APPROVED requires active_manuscript_version")
    if locks.get("STORYBOARD_APPROVED") and not context.config.get("active_storyboard_version"):
        errors.append("STORYBOARD_APPROVED requires active_storyboard_version")
    if locks.get("STORY_LOCKED") and not context.config.get("active_creative_brief_version"):
        errors.append("STORY_LOCKED requires active_creative_brief_version")
    if locks.get("IMAGE_READY") and not context.config.get("active_nemu_version"):
        errors.append("IMAGE_READY requires active_nemu_version")
    return errors


def _validate_preproduction(context: ProjectContext) -> List[str]:
    errors: List[str] = []
    schemas = context.install_root / "schemas"
    page_paths = [path for path in sorted(context.workspace_path("pages").glob("*.json")) if not path.name.startswith("._")]
    job_paths = [path for path in sorted(context.workspace_path("handoff/pending").glob("*.json")) if not path.name.startswith("._")]
    storyboard_paths = [
        path
        for pattern in ("storyboard/*.json", "storyboard/versions/*.json")
        for path in sorted(context.workspace_path(".").glob(pattern))
        if not path.name.startswith("._")
    ]
    visual_work_present = bool(page_paths or job_paths or storyboard_paths)
    active_brief: Dict[str, Any] | None = None
    active_nemu: Dict[str, Any] | None = None
    character_ids: set[str] = set()

    if visual_work_present:
        brief_rel = context.config.get("active_creative_brief_version")
        if not isinstance(brief_rel, str):
            errors.append("preproduction requires active_creative_brief_version")
        else:
            brief_path = context.project_path(brief_rel)
            errors.extend(validate_creative_brief(brief_path, context.config.get("project_id")))
            try:
                active_brief = load_json(brief_path)
            except (OSError, ValueError, json.JSONDecodeError):
                active_brief = None
        nemu_rel = context.config.get("active_nemu_version")
        if not isinstance(nemu_rel, str):
            errors.append("preproduction requires active_nemu_version")
        else:
            nemu_path = context.project_path(nemu_rel)
            errors.extend(validate_nemu(nemu_path, context.config.get("project_id")))
            try:
                active_nemu = load_json(nemu_path)
                source_storyboard = active_nemu.get("source_storyboard_path")
                source_sha = active_nemu.get("source_storyboard_sha256")
                if (source_storyboard is None) != (source_sha is None):
                    errors.append("active nemu source_storyboard_path and source_storyboard_sha256 must both be set or null")
                elif isinstance(source_storyboard, str):
                    source_errors = validate_project_path_containment(
                        context.project_root, source_storyboard, "active nemu source_storyboard_path"
                    )
                    errors.extend(source_errors)
                    source_path = context.project_path(source_storyboard)
                    if not source_errors and not source_path.is_file():
                        errors.append(f"active nemu source storyboard is missing: {source_storyboard}")
                    elif not source_errors and sha256_file(source_path) != source_sha:
                        errors.append(f"active nemu source storyboard checksum changed: {source_storyboard}")
            except (OSError, ValueError, json.JSONDecodeError):
                active_nemu = None

        for character_path in sorted(context.workspace_path("canon/characters").glob("*.json")):
            if character_path.name.startswith("._"):
                continue
            try:
                character = load_json(character_path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"failed to load production character {character_path.name}: {exc}")
                continue
            character_id = character.get("character_id")
            if isinstance(character_id, str):
                if character_id in character_ids:
                    errors.append(f"duplicate character_id in canon: {character_id}")
                character_ids.add(character_id)
            if not isinstance(character.get("dramatic_profile"), dict):
                errors.append(
                    f"{character_path.relative_to(context.project_root)}: visual production requires dramatic_profile"
                )

    target_format = context.config.get("target_manga_format", {})
    for page_path in page_paths:
        if page_path.name.startswith("._"):
            continue
        errors.extend(_schema_errors(page_path, schemas / "page.schema.json", context.project_root))
        errors.extend(
            f"{page_path.relative_to(context.project_root)}: {message}"
            for message in validate_page_spec(page_path, context.project_root)
        )
        try:
            page = load_json(page_path)
            page_size = page.get("page_size", {})
            if (
                page_size.get("width") != target_format.get("page_width_px")
                or page_size.get("height") != target_format.get("page_height_px")
            ):
                errors.append(
                    f"{page_path.relative_to(context.project_root)}: page_size must match target_manga_format pixel dimensions"
                )
            nemu_pages = {
                item.get("page_id"): item
                for item in active_nemu.get("pages", [])
                if isinstance(item, dict) and isinstance(item.get("page_id"), str)
            } if isinstance(active_nemu, dict) else {}
            nemu_page = nemu_pages.get(page.get("page_id"))
            if active_nemu is not None and nemu_page is None:
                errors.append(
                    f"{page_path.relative_to(context.project_root)}: page_id is missing from active nemu"
                )
            elif isinstance(nemu_page, dict):
                if nemu_page.get("page_size") != page_size:
                    errors.append(
                        f"{page_path.relative_to(context.project_root)}: page_size does not match active nemu"
                    )
                if nemu_page.get("reading_order") != page.get("reading_order"):
                    errors.append(
                        f"{page_path.relative_to(context.project_root)}: reading_order does not match active nemu"
                    )
                if nemu_page.get("reading_sequence") != page.get("reading_sequence"):
                    errors.append(
                        f"{page_path.relative_to(context.project_root)}: reading_sequence does not match active nemu"
                    )
                nemu_panels = {
                    item.get("panel_id"): item
                    for item in nemu_page.get("panels", [])
                    if isinstance(item, dict)
                }
                width = page_size.get("width")
                height = page_size.get("height")
                if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
                    for panel in page.get("panels", []):
                        if not isinstance(panel, dict):
                            continue
                        nemu_panel = nemu_panels.get(panel.get("panel_id"))
                        if not isinstance(nemu_panel, dict):
                            errors.append(
                                f"{page_path.relative_to(context.project_root)}: panel {panel.get('panel_id')} is missing from active nemu"
                            )
                            continue
                        frame = panel.get("frame", {})
                        if not isinstance(frame, dict) or not all(
                            isinstance(frame.get(key), (int, float))
                            for key in ("x", "y", "width", "height")
                        ):
                            continue
                        normalized = {
                            "x": frame.get("x", 0) / width,
                            "y": frame.get("y", 0) / height,
                            "width": frame.get("width", 0) / width,
                            "height": frame.get("height", 0) / height,
                        }
                        nemu_frame = nemu_panel.get("frame", {})
                        if not isinstance(nemu_frame, dict) or any(
                            not isinstance(nemu_frame.get(key), (int, float))
                            or abs(normalized[key] - nemu_frame[key]) > 0.00001
                            for key in normalized
                        ):
                            errors.append(
                                f"{page_path.relative_to(context.project_root)}: panel {panel.get('panel_id')} frame does not match active nemu"
                            )
                    nemu_lettering = {
                        item.get("lettering_id"): item
                        for item in nemu_page.get("lettering_plan", [])
                        if isinstance(item, dict)
                    }
                    for item in page.get("lettering", []):
                        if not isinstance(item, dict):
                            continue
                        nemu_item = nemu_lettering.get(item.get("lettering_id"))
                        if not isinstance(nemu_item, dict):
                            errors.append(
                                f"{page_path.relative_to(context.project_root)}: lettering {item.get('lettering_id')} is missing from active nemu"
                            )
                            continue
                        box = item.get("box", {})
                        if not isinstance(box, dict) or not all(
                            isinstance(box.get(key), (int, float))
                            for key in ("x", "y", "width", "height")
                        ):
                            continue
                        normalized = {
                            "x": box.get("x", 0) / width,
                            "y": box.get("y", 0) / height,
                            "width": box.get("width", 0) / width,
                            "height": box.get("height", 0) / height,
                        }
                        nemu_zone = nemu_item.get("zone", {})
                        if not isinstance(nemu_zone, dict) or any(
                            not isinstance(nemu_zone.get(key), (int, float))
                            or abs(normalized[key] - nemu_zone[key]) > 0.00001
                            for key in normalized
                        ):
                            errors.append(
                                f"{page_path.relative_to(context.project_root)}: lettering {item.get('lettering_id')} zone does not match active nemu"
                            )
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    for panel_pattern in ("panels/*.json", "panels/plans/*.json"):
        for panel_path in sorted(context.workspace_path(".").glob(panel_pattern)):
            if not panel_path.name.startswith("._"):
                errors.extend(_schema_errors(panel_path, schemas / "panel.schema.json", context.project_root))

    for snapshot_path in sorted(context.workspace_path("continuity/snapshots").glob("*.json")):
        if not snapshot_path.name.startswith("._"):
            errors.extend(_schema_errors(snapshot_path, schemas / "continuity-state.schema.json", context.project_root))

    for storyboard_path in storyboard_paths:
        try:
            storyboard = load_json(storyboard_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"failed to load storyboard version '{storyboard_path}': {exc}")
            continue
        errors.extend(
            f"{storyboard_path.relative_to(context.project_root)}: {message}"
            for message in require_fields(
                storyboard, ["schema_version", "project_id", "storyboard_id", "version", "status", "page_plan_paths"], "storyboard"
            )
        )
        if storyboard.get("project_id") != context.config.get("project_id"):
            errors.append(f"{storyboard_path.relative_to(context.project_root)}: project_id does not match project.json")

    seen_job_ids = set()
    seen_output_filenames = set()
    jobs_by_id: Dict[str, Dict[str, Any]] = {}
    for job_path in job_paths:
        try:
            job = load_json(job_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"failed to load deferred image job '{job_path}': {exc}")
            continue
        job_id = job.get("job_id")
        if job_id in seen_job_ids:
            errors.append(f"duplicate image job_id: {job_id}")
        seen_job_ids.add(job_id)
        if isinstance(job_id, str):
            jobs_by_id[job_id] = job
        output_filename = job.get("output_filename")
        if isinstance(output_filename, str):
            if output_filename in seen_output_filenames:
                errors.append(f"duplicate image-job output_filename: {output_filename}")
            seen_output_filenames.add(output_filename)
        for character_id in job.get("character_state", {}):
            if character_id not in character_ids:
                errors.append(
                    f"{job_path.relative_to(context.project_root)}: character_state references unknown canon character_id {character_id}"
                )
        if active_brief is not None and job.get("content_constraints") != active_brief.get("target_audience"):
            errors.append(
                f"{job_path.relative_to(context.project_root)}: content_constraints must exactly match the active creative brief target_audience"
            )
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

    dependency_types = {
        "character_reference": "character_reference",
        "location_reference": "location_reference",
        "prop_reference": "prop_reference",
        "panel_reference": "manga_panel",
        "storyboard_thumbnail": "storyboard_thumbnail",
    }
    dependency_graph: Dict[str, List[str]] = {}
    for job_id, job in jobs_by_id.items():
        dependency_graph[job_id] = []
        for dependency in job.get("deferred_reference_dependencies", []):
            if not isinstance(dependency, dict):
                continue
            source_job_id = dependency.get("source_job_id")
            if not isinstance(source_job_id, str):
                continue
            source_job = jobs_by_id.get(source_job_id)
            if source_job is None:
                errors.append(f"{job_id}: deferred reference source job is missing: {source_job_id}")
                continue
            expected_type = dependency_types.get(dependency.get("kind"))
            if source_job.get("job_type") != expected_type:
                errors.append(
                    f"{job_id}: deferred reference {dependency.get('reference_id')} expects "
                    f"{expected_type}, but {source_job_id} is {source_job.get('job_type')}"
                )
            dependency_graph[job_id].append(source_job_id)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(job_id: str, trail: List[str]) -> None:
        if job_id in visited:
            return
        if job_id in visiting:
            cycle_start = trail.index(job_id) if job_id in trail else 0
            errors.append("deferred image-job dependency cycle: " + " -> ".join([*trail[cycle_start:], job_id]))
            return
        visiting.add(job_id)
        for source_job_id in dependency_graph.get(job_id, []):
            visit(source_job_id, [*trail, job_id])
        visiting.remove(job_id)
        visited.add(job_id)

    for job_id in dependency_graph:
        visit(job_id, [])

    for page_path in page_paths:
        try:
            page = load_json(page_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        for panel in page.get("panels", []):
            if not isinstance(panel, dict):
                continue
            source_job_id = panel.get("source_job_id")
            job = jobs_by_id.get(source_job_id)
            if not job or job.get("job_type") != "manga_panel":
                errors.append(
                    f"{page_path.relative_to(context.project_root)}: panel {panel.get('panel_id')} source_job_id does not identify a pending manga_panel job"
                )
                continue
            expected_canvas = {
                "width": job.get("output_spec", {}).get("width"),
                "height": job.get("output_spec", {}).get("height"),
            }
            if panel.get("source_canvas") != expected_canvas:
                errors.append(
                    f"{page_path.relative_to(context.project_root)}: panel {panel.get('panel_id')} source_canvas does not match image-job output_spec"
                )
            if panel.get("dialogue_safe_zones") != job.get("dialogue_safe_zones"):
                errors.append(
                    f"{page_path.relative_to(context.project_root)}: panel {panel.get('panel_id')} dialogue_safe_zones do not match its image job"
                )
    return errors


def _approved_production_reviews(
    context: ProjectContext,
) -> tuple[Dict[str, List[Dict[str, Any]]], bool]:
    approved_intakes: Dict[str, List[Dict[str, Any]]] = {}
    current_print_preflight_approved = False
    from .approvals import validate_approval

    for approval_path in context.workspace_path("approvals").glob("*.json"):
        if approval_path.name.startswith("._"):
            continue
        try:
            approval = load_json(approval_path)
            if (
                approval.get("status") != "approved"
                or approval.get("decision") != "approved"
                or validate_approval(context, approval_path)
            ):
                continue
            if approval.get("artifact_type") == "print_preflight":
                current_print_preflight_approved = True
                continue
            if approval.get("artifact_type") != "generated_image":
                continue
            review = load_json(context.project_path(approval["target_relative_path"]))
            intake = load_json(context.project_path(review["target"]))
            approved_intakes.setdefault(intake["job_id"], []).append(intake)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    return approved_intakes, current_print_preflight_approved


def validate_approved_panel_artwork(
    context: ProjectContext,
    page: Dict[str, Any],
    approved_intakes: Dict[str, List[Dict[str, Any]]] | None = None,
) -> List[str]:
    errors: List[str] = []
    if approved_intakes is None:
        approved_intakes, _ = _approved_production_reviews(context)
    for panel in page.get("panels", []):
        art_path = panel.get("art_path")
        panel_id = panel.get("panel_id", "unknown")
        if not art_path:
            errors.append(f"page {page.get('page_id')} panel {panel_id} has no approved artwork")
            continue
        path_errors = validate_project_path_containment(
            context.project_root, art_path, f"panel {panel_id}.art_path"
        )
        errors.extend(path_errors)
        if path_errors:
            continue
        if not art_path.startswith(APPROVED_PREFIX):
            errors.append(f"panel {panel_id} artwork is not under {APPROVED_PREFIX}")
            continue
        art_file = context.project_path(art_path)
        if not art_file.is_file():
            errors.append(f"approved panel artwork is missing: {art_path}")
            continue
        source_job_id = panel.get("source_job_id")
        art_sha = sha256_file(art_file)
        matching_intakes = approved_intakes.get(source_job_id, [])
        if not any(intake.get("file", {}).get("sha256") == art_sha for intake in matching_intakes):
            errors.append(
                f"panel {panel_id} artwork has no hash-matching approved generated-image visual review"
            )
    return errors


def validate_print_production_readiness(context: ProjectContext) -> List[str]:
    if context.config.get("target_manga_format", {}).get("output_intent") not in {"print", "both"}:
        return []
    errors, _, _ = preflight_project(context)
    results = [f"print preflight: {message}" for message in errors]
    _, current_print_preflight_approved = _approved_production_reviews(context)
    if not current_print_preflight_approved:
        results.append("print production requires a current approved print-preflight review")
    return results


def _validate_production(context: ProjectContext) -> List[str]:
    errors: List[str] = []
    reasons = image_ready_reasons(context)
    if context.config.get("stage_locks", {}).get("IMAGE_READY") is not True:
        errors.append("production requires stage_locks.IMAGE_READY to be true")
    errors.extend(f"production blocked: {reason}" for reason in reasons)

    errors.extend(validate_print_production_readiness(context))

    page_paths = [
        path
        for path in sorted(context.workspace_path("pages").glob("*.json"))
        if not path.name.startswith("._")
    ]
    if not page_paths:
        errors.append("production requires at least one page plan under .manga-studio/pages/")
    approved_intakes, _ = _approved_production_reviews(context)

    for page_path in page_paths:
        try:
            page = load_json(page_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"failed to load production page {page_path.name}: {exc}")
            continue
        errors.extend(validate_approved_panel_artwork(context, page, approved_intakes))
        page_id = page.get("page_id")
        if page_id:
            lettered = latest_version_path(
                context.workspace_path("lettering"), f"{page_id}-lettered", ".svg"
            ) or context.workspace_path(f"lettering/{page_id}-lettered.svg")
            composed = latest_version_path(
                context.workspace_path("pages"), f"{page_id}-composed", ".svg"
            ) or context.workspace_path(f"pages/{page_id}-composed.svg")
            if not lettered.is_file():
                errors.append(
                    f"lettered page is missing: .manga-studio/lettering/{page_id}-lettered-v###.svg"
                )
            if not composed.is_file():
                errors.append(
                    f"composed page is missing: .manga-studio/pages/{page_id}-composed-v###.svg"
                )
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
    errors.extend(validate_story_artifacts(context))
    errors.extend(_validate_gate_artifacts(context))
    if profile in {"preproduction", "production"}:
        errors.extend(_validate_preproduction(context))
    if profile == "production":
        errors.extend(_validate_production(context))
    return errors
