from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .project import STAGE_GATES, ProjectContext, ProjectOperationError, image_ready_reasons, project_relative, sha256_file
from .json_schema import validate_json_file
from .print_preflight import preflight_project
from .structure import validate_source_maps
from .validation import (
    load_json,
    validate_image_job,
    validate_project_path_containment,
    validate_relative_project_path,
    validate_success_plan,
    write_json,
)


APPROVAL_STATUSES = {"approved", "rejected", "superseded", "invalidated"}
ARTIFACT_TYPES = {
    "source_inventory",
    "source_structure",
    "source_map",
    "creative_brief",
    "success_plan",
    "story_model",
    "canon",
    "diagnostic_report",
    "revision_policy",
    "revision_plan",
    "change_set",
    "manuscript",
    "continuity",
    "storyboard",
    "nemu",
    "page_plan",
    "panel_plan",
    "generated_image",
    "print_preflight",
}

GATE_APPROVAL_TYPES = {
    "SOURCE_LOCKED": {"source_inventory", "source_structure"},
    "CANON_APPROVED": {"canon"},
    "DIAGNOSTIC_APPROVED": {"diagnostic_report"},
    "REVISION_PLAN_APPROVED": {"revision_plan"},
    "MANUSCRIPT_APPROVED": {"manuscript"},
    "STORY_LOCKED": {"creative_brief"},
    "STORYBOARD_APPROVED": {"storyboard"},
    "STORYBOARD_LOCKED": set(),
    "IMAGE_READY": {"continuity", "nemu"},
}

GATE_PREREQUISITES = {
    "SOURCE_LOCKED": set(),
    "CANON_APPROVED": {"SOURCE_LOCKED"},
    "DIAGNOSTIC_APPROVED": {"SOURCE_LOCKED"},
    "REVISION_PLAN_APPROVED": {"DIAGNOSTIC_APPROVED"},
    "MANUSCRIPT_APPROVED": {"REVISION_PLAN_APPROVED"},
    "STORY_LOCKED": {"SOURCE_LOCKED", "CANON_APPROVED", "MANUSCRIPT_APPROVED"},
    "STORYBOARD_APPROVED": {"STORY_LOCKED"},
    "STORYBOARD_LOCKED": {"STORYBOARD_APPROVED"},
    "IMAGE_READY": {"CANON_APPROVED", "STORY_LOCKED", "STORYBOARD_LOCKED"},
}

GATE_FIXED_TARGETS = {
    "SOURCE_LOCKED": {
        "source_inventory": ".manga-studio/source/inventory.json",
        "source_structure": ".manga-studio/source/structure.json",
    },
    "IMAGE_READY": {"continuity": ".manga-studio/continuity/state.json"},
}

GATE_ACTIVE_TARGET_FIELDS = {
    "CANON_APPROVED": {"canon": "active_canon_version"},
    "MANUSCRIPT_APPROVED": {"manuscript": "active_manuscript_version"},
    "STORY_LOCKED": {"creative_brief": "active_creative_brief_version"},
    "STORYBOARD_APPROVED": {"storyboard": "active_storyboard_version"},
    "IMAGE_READY": {"nemu": "active_nemu_version"},
}

GATE_TARGET_PREFIXES = {
    "DIAGNOSTIC_APPROVED": {"diagnostic_report": ".manga-studio/analysis/diagnostics/"},
    "REVISION_PLAN_APPROVED": {"revision_plan": ".manga-studio/revisions/plans/"},
    "STORY_LOCKED": {"creative_brief": ".manga-studio/story/briefs/"},
    "IMAGE_READY": {"nemu": ".manga-studio/storyboard/nemu/"},
}

GATE_ARTIFACT_SCHEMAS = {
    "source_inventory": "source-inventory.schema.json",
    "creative_brief": "creative-brief.schema.json",
    "canon": "canon.schema.json",
    "diagnostic_report": "diagnostic-report.schema.json",
    "revision_plan": "revision-plan.schema.json",
    "continuity": "continuity-state.schema.json",
    "nemu": "nemu.schema.json",
}

APPROVAL_TARGET_SCHEMAS = {
    "generated_image": "review.schema.json",
    "print_preflight": "review.schema.json",
}


def _validate_special_approval_target(
    context: ProjectContext, target: Path, artifact_type: str
) -> List[str]:
    schema_name = APPROVAL_TARGET_SCHEMAS.get(artifact_type)
    if schema_name is None:
        return []
    errors = validate_json_file(target, context.install_root / "schemas" / schema_name)
    if errors:
        return errors
    artifact = load_json(target)
    subject_rel = artifact.get("target")
    if not isinstance(subject_rel, str):
        errors.append("review target must be a project-relative path")
    else:
        subject_errors = validate_project_path_containment(
            context.project_root, subject_rel, "review target"
        )
        errors.extend(subject_errors)
        subject = context.project_path(subject_rel)
        if not subject_errors and not subject.is_file():
            errors.append(f"review target is missing: {subject_rel}")
        elif not subject_errors and sha256_file(subject) != artifact.get("target_sha256"):
            errors.append(f"review target checksum changed: {subject_rel}")
    if artifact_type == "generated_image":
        if artifact.get("review_type") != "generated_image":
            errors.append("generated_image approval must target a generated-image visual review")
        if artifact.get("metric_scope") != "human_visual_assessment" or not isinstance(
            artifact.get("visual_assessment"), dict
        ):
            errors.append("generated_image approval requires a completed human visual assessment")
        else:
            assessment = artifact["visual_assessment"]
            score_fields = (
                "story_clarity", "event_readability", "reference_adherence", "character_acting",
                "composition", "monochrome_finish", "continuity", "lettering_readability",
                "content_boundary_compliance",
            )
            below_threshold = [
                field for field in score_fields
                if not isinstance(assessment.get(field), int)
                or isinstance(assessment.get(field), bool)
                or assessment[field] < 4
            ]
            if below_threshold:
                errors.append(
                    "generated-image visual review has quality scores below 4: "
                    + ", ".join(below_threshold)
                )
            failed_checks = [
                field for field in (
                    "required_elements_present", "prohibited_elements_absent",
                    "dialogue_safe_zones_usable", "artifact_free",
                )
                if assessment.get(field) is not True
            ]
            if failed_checks:
                errors.append(
                    "generated-image visual review has failed required checks: "
                    + ", ".join(failed_checks)
                )
            if any(
                isinstance(finding, dict) and finding.get("severity") == "error"
                for finding in artifact.get("findings", [])
            ):
                errors.append("generated-image visual review has unresolved error findings")
        if artifact.get("automated") is not False:
            errors.append("generated-image visual review must be explicitly human, not automated")
        if artifact.get("status") not in {"review_ready", "approved"}:
            errors.append("generated-image visual review must be review_ready before approval")
        intake_rel = subject_rel
        if not isinstance(intake_rel, str) or not intake_rel.startswith(".manga-studio/continuity/intake/"):
            errors.append("generated-image visual review target must be an intake record")
        else:
            intake_path = context.project_path(intake_rel)
            intake_errors = validate_json_file(
                intake_path, context.install_root / "schemas" / "generated-image.schema.json"
            )
            errors.extend(f"intake: {message}" for message in intake_errors)
            if not intake_errors:
                intake = load_json(intake_path)
                if intake.get("project_id") != context.config.get("project_id"):
                    errors.append("generated-image intake belongs to another project")
                if intake.get("status") == "blocked":
                    errors.append("a blocked generated-image intake cannot be approved")
                job_rel = intake.get("job_path")
                job_path_errors = validate_project_path_containment(
                    context.project_root, job_rel, "generated-image intake job_path"
                )
                errors.extend(job_path_errors)
                job_path = context.project_path(job_rel) if isinstance(job_rel, str) else None
                if not isinstance(job_rel, str) or not job_rel.startswith(".manga-studio/handoff/pending/"):
                    errors.append("generated-image intake job_path must be under handoff/pending")
                if job_path is None or job_path_errors or not job_path.is_file() or sha256_file(job_path) != intake.get("job_sha256"):
                    errors.append("generated-image intake job is missing or its checksum changed")
                else:
                    job = load_json(job_path)
                    errors.extend(
                        f"image job: {message}"
                        for message in validate_json_file(
                            job_path, context.install_root / "schemas" / "image-job.schema.json"
                        )
                    )
                    errors.extend(
                        f"image job: {message}"
                        for message in validate_image_job(
                            job_path, context.project_root, check_reference_existence=True
                        )
                    )
                    if job.get("job_id") != intake.get("job_id"):
                        errors.append("generated-image intake job_id does not match its source job")
                    if job.get("output_filename") != intake.get("image_path"):
                        errors.append("generated-image intake image_path does not match job output_filename")
                    if job.get("release_status") not in {"ready", "released", "completed"}:
                        errors.append("generated-image intake source job was not released for external generation")
                image_rel = intake.get("image_path")
                image_path_errors = validate_project_path_containment(
                    context.project_root, image_rel, "generated-image intake image_path"
                )
                errors.extend(image_path_errors)
                image_path = context.project_path(image_rel) if isinstance(image_rel, str) else None
                if image_path is None or image_path_errors or not image_path.is_file() or sha256_file(image_path) != intake.get("file", {}).get("sha256"):
                    errors.append("generated-image intake file is missing or its checksum changed")
    elif artifact_type == "print_preflight":
        if artifact.get("review_type") != "print_preflight":
            errors.append("print_preflight approval must target a print-preflight review")
        if artifact.get("metric_scope") != "technical_preflight":
            errors.append("print_preflight approval requires technical_preflight scope")
        if artifact.get("status") not in {"review_ready", "approved"}:
            errors.append("blocked print preflight cannot be approved")
        if subject_rel != ".manga-studio/project.json":
            errors.append("print-preflight review must target .manga-studio/project.json")
        current_targets = {
            path.relative_to(context.project_root).as_posix(): sha256_file(path)
            for path in [
                context.project_file,
                *(
                    path for path in sorted(context.workspace_path("pages").glob("*.json"))
                    if not path.name.startswith("._")
                ),
            ]
        }
        recorded_targets = {
            item.get("relative_path"): item.get("sha256")
            for item in artifact.get("target_hashes", [])
            if isinstance(item, dict)
        }
        if len(recorded_targets) != len(artifact.get("target_hashes", [])):
            errors.append("print-preflight target hashes contain duplicate paths")
        if recorded_targets != current_targets:
            errors.append("print-preflight target hashes do not match the current project and page specifications")
        print_errors, _, _ = preflight_project(context)
        errors.extend(f"current print preflight: {message}" for message in print_errors)
    return errors


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _approval_path(context: ProjectContext, approval_id: str) -> Path:
    return context.workspace_path(f"approvals/{approval_id}.json")


def record_approval(
    context: ProjectContext,
    target: Path,
    *,
    artifact_type: str,
    target_version: str,
    actor: str,
    decision: str,
    notes: str = "",
    supersedes_approval_id: Optional[str] = None,
) -> Path:
    if artifact_type not in ARTIFACT_TYPES:
        raise ProjectOperationError(f"unsupported approval artifact type: {artifact_type}")
    if decision not in {"approved", "rejected"}:
        raise ProjectOperationError("approval decision must be approved or rejected")
    target = target.expanduser().resolve()
    if not target.is_file():
        raise ProjectOperationError(f"approval target does not exist: {target}")
    special_errors: List[str] = []
    if decision == "approved":
        if artifact_type == "success_plan":
            special_errors.extend(
                validate_json_file(
                    target, context.install_root / "schemas" / "success-plan.schema.json"
                )
            )
            special_errors.extend(
                validate_success_plan(
                    target, context.config.get("project_id"), context.project_root
                )
            )
        else:
            special_errors.extend(
                _validate_special_approval_target(context, target, artifact_type)
            )
    if special_errors:
        raise ProjectOperationError("; ".join(special_errors))
    target_rel = project_relative(context.project_root, target)
    errors = validate_relative_project_path(target_rel, "target_relative_path")
    if errors:
        raise ProjectOperationError("; ".join(errors))
    approval_id = f"approval-{uuid.uuid4().hex}"
    record = {
        "schema_version": "3.0.0",
        "approval_id": approval_id,
        "project_id": context.config["project_id"],
        "artifact_type": artifact_type,
        "target_relative_path": target_rel,
        "target_version": target_version,
        "target_sha256": sha256_file(target),
        "status": decision,
        "decision": decision,
        "decided_at": _timestamp(),
        "actor": actor,
        "notes": notes,
        "supersedes_approval_id": supersedes_approval_id,
        "superseded_by_approval_id": None,
        "invalidated_at": None,
        "invalidation_reason": None,
    }
    path = _approval_path(context, approval_id)
    write_json(path, record)
    if supersedes_approval_id:
        previous_path = _approval_path(context, supersedes_approval_id)
        if not previous_path.is_file():
            path.unlink()
            raise ProjectOperationError(f"superseded approval does not exist: {supersedes_approval_id}")
        previous = load_json(previous_path)
        if previous.get("project_id") != context.config["project_id"]:
            path.unlink()
            raise ProjectOperationError("superseded approval belongs to another project")
        previous["status"] = "superseded"
        previous["superseded_by_approval_id"] = approval_id
        write_json(previous_path, previous)
    return path


def validate_approval(context: ProjectContext, approval_path: Path) -> List[str]:
    errors: List[str] = []
    approval_path = approval_path.expanduser().resolve()
    try:
        approval_path.relative_to(context.workspace_path("approvals").resolve())
    except ValueError:
        errors.append("approval record must live under .manga-studio/approvals/")
    try:
        record = load_json(approval_path)
    except Exception as exc:  # validation reports malformed records rather than mutating them
        return [f"failed to load approval '{approval_path}': {exc}"]
    try:
        errors.extend(validate_json_file(approval_path, context.install_root / "schemas" / "approval.schema.json"))
    except Exception as exc:
        errors.append(f"approval schema validation failed: {exc}")
    required = {
        "schema_version", "approval_id", "project_id", "artifact_type", "target_relative_path",
        "target_version", "target_sha256", "status", "decision", "decided_at", "actor", "notes",
        "supersedes_approval_id", "superseded_by_approval_id",
    }
    for field in sorted(required - set(record)):
        errors.append(f"approval is missing required field '{field}'")
    if record.get("project_id") != context.config.get("project_id"):
        errors.append("approval project_id does not match project.json")
    if record.get("artifact_type") not in ARTIFACT_TYPES:
        errors.append(f"unsupported approval artifact type: {record.get('artifact_type')}")
    if record.get("status") not in APPROVAL_STATUSES:
        errors.append(f"unsupported approval status: {record.get('status')}")
    target_rel = record.get("target_relative_path")
    path_errors = validate_project_path_containment(
        context.project_root, target_rel, "approval.target_relative_path"
    )
    errors.extend(path_errors)
    if not path_errors:
        target = context.project_path(target_rel)
        if not target.is_file():
            errors.append(f"approval target is missing: {target_rel}")
        elif sha256_file(target) != record.get("target_sha256"):
            errors.append(f"approval target checksum changed: {target_rel}")
        elif record.get("decision") == "approved":
            errors.extend(
                _validate_special_approval_target(context, target, record.get("artifact_type"))
            )
    return errors


def valid_approved_record(context: ProjectContext, approval_path: Path) -> Dict[str, Any]:
    errors = validate_approval(context, approval_path)
    if errors:
        raise ProjectOperationError("; ".join(errors))
    record = load_json(approval_path)
    if record.get("status") != "approved" or record.get("decision") != "approved":
        raise ProjectOperationError(f"approval is not currently approved: {record.get('approval_id')}")
    return record


def find_approval(context: ProjectContext, approval_id: str) -> Optional[Path]:
    direct = _approval_path(context, approval_id)
    if direct.is_file():
        return direct
    for path in context.workspace_path("approvals").glob("*.json"):
        if path.name.startswith("._"):
            continue
        try:
            if load_json(path).get("approval_id") == approval_id:
                return path
        except Exception:
            continue
    return None


def invalidate_stale_approvals(context: ProjectContext) -> List[str]:
    invalidated: List[str] = []
    for path in sorted(context.workspace_path("approvals").glob("*.json")):
        if path.name.startswith("._"):
            continue
        try:
            record = load_json(path)
        except Exception:
            continue
        if record.get("status") != "approved":
            continue
        target_rel = record.get("target_relative_path")
        path_errors = validate_relative_project_path(target_rel, "approval.target_relative_path")
        target = context.project_path(target_rel) if not path_errors else None
        reason: Optional[str] = None
        if target is None or not target.is_file():
            reason = "target is missing"
        elif sha256_file(target) != record.get("target_sha256"):
            reason = "target SHA-256 no longer matches"
        if reason:
            record["status"] = "invalidated"
            record["invalidated_at"] = _timestamp()
            record["invalidation_reason"] = reason
            write_json(path, record)
            invalidated.append(record.get("approval_id", path.stem))
    return invalidated


def _next_lock_version(context: ProjectContext, gate: str) -> int:
    versions: List[int] = []
    for path in context.workspace_path("locks").glob(f"{gate}-v*.json"):
        try:
            versions.append(int(path.stem.rsplit("-v", 1)[1]))
        except (IndexError, ValueError):
            continue
    return max(versions, default=0) + 1


def _write_project_config(context: ProjectContext, config: Dict[str, Any]) -> None:
    write_json(context.project_file, config)


def _gate_approval_errors(
    context: ProjectContext,
    gate: str,
    approval_records: List[Dict[str, Any]],
    config: Dict[str, Any],
) -> List[str]:
    errors: List[str] = []
    required_types = GATE_APPROVAL_TYPES[gate]
    records_by_type: Dict[str, List[Dict[str, Any]]] = {}
    for record in approval_records:
        artifact_type = record.get("artifact_type")
        if not isinstance(artifact_type, str):
            errors.append(f"{gate} references an approval without a valid artifact_type")
            continue
        records_by_type.setdefault(artifact_type, []).append(record)

    unexpected_types = sorted(set(records_by_type) - required_types)
    if unexpected_types:
        errors.append(f"{gate} received approvals for unrelated artifact types: {', '.join(unexpected_types)}")
    for artifact_type in sorted(required_types):
        records = records_by_type.get(artifact_type, [])
        if len(records) != 1:
            errors.append(f"{gate} requires exactly one valid {artifact_type} approval; found {len(records)}")
            continue
        record = records[0]
        target_rel = record.get("target_relative_path")
        path_errors = validate_relative_project_path(target_rel, "approval.target_relative_path")
        if path_errors:
            errors.extend(path_errors)
            continue

        fixed_target = GATE_FIXED_TARGETS.get(gate, {}).get(artifact_type)
        if fixed_target and target_rel != fixed_target:
            errors.append(f"{artifact_type} approval must target {fixed_target}; found {target_rel}")

        active_field = GATE_ACTIVE_TARGET_FIELDS.get(gate, {}).get(artifact_type)
        if active_field:
            active_target = config.get(active_field)
            if not active_target:
                errors.append(f"{gate} requires {active_field} to identify the approved artifact")
            elif target_rel != active_target:
                errors.append(
                    f"{artifact_type} approval targets {target_rel}, not current {active_field} {active_target}"
                )

        prefix = GATE_TARGET_PREFIXES.get(gate, {}).get(artifact_type)
        if prefix and not target_rel.startswith(prefix):
            errors.append(f"{artifact_type} approval must target a managed artifact under {prefix}")

        target = context.project_path(target_rel)
        schema_name = GATE_ARTIFACT_SCHEMAS.get(artifact_type)
        if schema_name and target.is_file():
            try:
                errors.extend(
                    f"{artifact_type} target: {message}"
                    for message in validate_json_file(target, context.install_root / "schemas" / schema_name)
                )
            except Exception as exc:
                errors.append(f"{artifact_type} target schema validation failed: {exc}")
        if artifact_type == "source_structure" and target.is_file():
            try:
                structure = load_json(target)
            except Exception as exc:
                errors.append(f"source_structure target is unreadable: {exc}")
            else:
                if structure.get("project_id") != config.get("project_id"):
                    errors.append("source_structure target belongs to another project")
                if not isinstance(structure.get("documents"), list):
                    errors.append("source_structure target must contain a documents array")
                try:
                    source_map_errors = validate_source_maps(context)
                except Exception as exc:
                    errors.append(f"source_structure source-map validation failed: {exc}")
                else:
                    errors.extend(f"source_structure target: {message}" for message in source_map_errors)
        if artifact_type == "storyboard" and target.is_file():
            try:
                storyboard = load_json(target)
            except Exception as exc:
                errors.append(f"storyboard target is unreadable: {exc}")
            else:
                required = {"schema_version", "project_id", "storyboard_id", "version", "status", "page_plan_paths"}
                missing = sorted(required - set(storyboard))
                if missing:
                    errors.append(f"storyboard target is missing: {', '.join(missing)}")
                if storyboard.get("project_id") != config.get("project_id"):
                    errors.append("storyboard target belongs to another project")
    return errors


def set_lock(
    context: ProjectContext,
    gate: str,
    *,
    approval_paths: Iterable[Path],
    actor: str,
    notes: str = "",
) -> Path:
    if gate not in STAGE_GATES:
        raise ProjectOperationError(f"unknown stage gate: {gate}")
    config = load_json(context.project_file)
    existing_lock_errors = validate_locks(context)
    if existing_lock_errors:
        raise ProjectOperationError("existing stage locks are invalid: " + "; ".join(existing_lock_errors))
    missing_gates = sorted(gate_name for gate_name in GATE_PREREQUISITES[gate] if config.get("stage_locks", {}).get(gate_name) is not True)
    if missing_gates:
        raise ProjectOperationError(f"{gate} requires locked gates: {', '.join(missing_gates)}")

    approval_records = [valid_approved_record(context, path.expanduser().resolve()) for path in approval_paths]
    approval_errors = _gate_approval_errors(context, gate, approval_records, config)
    if approval_errors:
        raise ProjectOperationError(f"{gate} approvals are invalid: " + "; ".join(approval_errors))
    if gate == "IMAGE_READY":
        ready_context = ProjectContext(
            project_root=context.project_root,
            workspace_root=context.workspace_root,
            project_file=context.project_file,
            install_root=context.install_root,
            config=config,
        )
        reasons = image_ready_reasons(ready_context, ignore_configured_image_ready=True)
        if reasons:
            raise ProjectOperationError("IMAGE_READY prerequisites fail: " + "; ".join(reasons))

    version = _next_lock_version(context, gate)
    previous_rel = config.get("stage_lock_records", {}).get(gate)
    previous_id = None
    if previous_rel and context.project_path(previous_rel).is_file():
        previous_id = load_json(context.project_path(previous_rel)).get("lock_id")
    lock_id = f"lock-{uuid.uuid4().hex}"
    lock_rel = f".manga-studio/locks/{gate}-v{version:03d}.json"
    record = {
        "schema_version": "3.0.0",
        "lock_id": lock_id,
        "project_id": config["project_id"],
        "gate": gate,
        "status": "locked",
        "lock_version": f"v{version:03d}",
        "recorded_at": _timestamp(),
        "actor": actor,
        "notes": notes,
        "prerequisite_gates": sorted(GATE_PREREQUISITES[gate]),
        "approval_ids": [record["approval_id"] for record in approval_records],
        "target_hashes": [
            {"relative_path": record["target_relative_path"], "sha256": record["target_sha256"]}
            for record in approval_records
        ],
        "supersedes_lock_id": previous_id,
    }
    write_json(context.project_path(lock_rel), record)
    config.setdefault("stage_locks", {})[gate] = True
    config.setdefault("stage_lock_records", {name: None for name in STAGE_GATES})[gate] = lock_rel
    _write_project_config(context, config)
    return context.project_path(lock_rel)


def clear_lock(context: ProjectContext, gate: str, *, actor: str, notes: str = "") -> Path:
    if gate not in STAGE_GATES:
        raise ProjectOperationError(f"unknown stage gate: {gate}")
    config = load_json(context.project_file)
    dependents = sorted(
        name for name, prerequisites in GATE_PREREQUISITES.items()
        if gate in prerequisites and config.get("stage_locks", {}).get(name) is True
    )
    if dependents:
        raise ProjectOperationError(f"clear dependent locks first: {', '.join(dependents)}")
    version = _next_lock_version(context, gate)
    previous_rel = config.get("stage_lock_records", {}).get(gate)
    previous_id = None
    if previous_rel and context.project_path(previous_rel).is_file():
        previous_id = load_json(context.project_path(previous_rel)).get("lock_id")
    lock_rel = f".manga-studio/locks/{gate}-v{version:03d}.json"
    record = {
        "schema_version": "3.0.0",
        "lock_id": f"lock-{uuid.uuid4().hex}",
        "project_id": config["project_id"],
        "gate": gate,
        "status": "cleared",
        "lock_version": f"v{version:03d}",
        "recorded_at": _timestamp(),
        "actor": actor,
        "notes": notes,
        "prerequisite_gates": [],
        "approval_ids": [],
        "target_hashes": [],
        "supersedes_lock_id": previous_id,
    }
    write_json(context.project_path(lock_rel), record)
    config.setdefault("stage_locks", {})[gate] = False
    config.setdefault("stage_lock_records", {name: None for name in STAGE_GATES})[gate] = lock_rel
    _write_project_config(context, config)
    return context.project_path(lock_rel)


def validate_locks(context: ProjectContext) -> List[str]:
    errors: List[str] = []
    config = load_json(context.project_file)
    locks = config.get("stage_locks", {})
    active = config.get("stage_lock_records", {})
    for gate in STAGE_GATES:
        if locks.get(gate) is not True:
            continue
        lock_rel = active.get(gate)
        path_errors = validate_relative_project_path(lock_rel, f"stage_lock_records.{gate}")
        errors.extend(path_errors)
        if path_errors:
            continue
        path = context.project_path(lock_rel)
        if not path.is_file():
            errors.append(f"active lock record is missing for {gate}: {lock_rel}")
            continue
        record = load_json(path)
        try:
            errors.extend(
                f"{gate}: {message}"
                for message in validate_json_file(path, context.install_root / "schemas" / "stage-lock.schema.json")
            )
        except Exception as exc:
            errors.append(f"{gate}: lock schema validation failed: {exc}")
        if record.get("project_id") != config.get("project_id"):
            errors.append(f"{gate} lock belongs to another project")
        if record.get("gate") != gate or record.get("status") != "locked":
            errors.append(f"active lock record is not a locked {gate} record")
        for prerequisite in GATE_PREREQUISITES[gate]:
            if locks.get(prerequisite) is not True:
                errors.append(f"{gate} requires {prerequisite}")
        approval_records: List[Dict[str, Any]] = []
        for approval_id in record.get("approval_ids", []):
            approval_path = find_approval(context, approval_id)
            if approval_path is None:
                errors.append(f"{gate} references missing approval {approval_id}")
                continue
            approval_errors = validate_approval(context, approval_path)
            errors.extend(f"{gate}: {message}" for message in approval_errors)
            approval = load_json(approval_path)
            if approval.get("status") != "approved":
                errors.append(f"{gate} references non-approved approval {approval_id}")
            approval_records.append(approval)
        errors.extend(_gate_approval_errors(context, gate, approval_records, config))
        expected_targets = {
            (approval.get("target_relative_path"), approval.get("target_sha256"))
            for approval in approval_records
        }
        recorded_targets = {
            (target.get("relative_path"), target.get("sha256"))
            for target in record.get("target_hashes", [])
            if isinstance(target, dict)
        }
        if recorded_targets != expected_targets:
            errors.append(f"{gate} target_hashes do not match its approval records")
        for target in record.get("target_hashes", []):
            relative = target.get("relative_path")
            if isinstance(relative, str) and context.project_path(relative).is_file():
                if sha256_file(context.project_path(relative)) != target.get("sha256"):
                    errors.append(f"{gate} target checksum changed: {relative}")
            else:
                errors.append(f"{gate} target is missing: {relative}")
    return errors
