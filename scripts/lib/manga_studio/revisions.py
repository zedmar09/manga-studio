from __future__ import annotations

import difflib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .approvals import invalidate_stale_approvals, validate_approval
from .json_schema import validate_json_file
from .project import ProjectContext, ProjectOperationError, sha256_file
from .validation import load_json, validate_relative_project_path, write_json


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _approved_change_set(context: ProjectContext, change_set_path: Path) -> Dict[str, Any]:
    schema = context.install_root / "schemas" / "change-set.schema.json"
    schema_errors = validate_json_file(change_set_path, schema)
    if schema_errors:
        raise ProjectOperationError("change set schema validation failed: " + "; ".join(schema_errors))
    change_set = load_json(change_set_path)
    if change_set.get("project_id") != context.config.get("project_id"):
        raise ProjectOperationError("change set belongs to another project")
    if change_set.get("approval_status") != "approved":
        raise ProjectOperationError("change set is not marked approved")
    relative = change_set_path.resolve().relative_to(context.project_root).as_posix()
    matching = []
    for approval_path in context.workspace_path("approvals").glob("*.json"):
        try:
            approval = load_json(approval_path)
        except Exception:
            continue
        if approval.get("artifact_type") == "change_set" and approval.get("target_relative_path") == relative:
            matching.append((approval_path, approval))
    if not matching:
        raise ProjectOperationError("change set requires a separate approval record")
    for approval_path, approval in matching:
        if approval.get("status") == "approved" and not validate_approval(context, approval_path):
            return change_set
    raise ProjectOperationError("change set has no current approval with a matching target SHA-256")


def _apply_operation(text: str, operation: Dict[str, Any]) -> str:
    operation_type = operation.get("type")
    if operation_type == "replace_text":
        before = operation.get("before")
        after = operation.get("after")
        if not isinstance(before, str) or not before:
            raise ProjectOperationError("replace_text requires a non-empty before string")
        if not isinstance(after, str):
            raise ProjectOperationError("replace_text requires an after string")
        occurrences = text.count(before)
        if occurrences != 1:
            raise ProjectOperationError(f"replace_text expected exactly one match; found {occurrences}")
        return text.replace(before, after, 1)
    if operation_type == "append_text":
        addition = operation.get("text")
        if not isinstance(addition, str):
            raise ProjectOperationError("append_text requires text")
        return text + addition
    if operation_type == "insert_after":
        anchor = operation.get("anchor")
        addition = operation.get("text")
        if not isinstance(anchor, str) or not anchor or not isinstance(addition, str):
            raise ProjectOperationError("insert_after requires non-empty anchor and text strings")
        occurrences = text.count(anchor)
        if occurrences != 1:
            raise ProjectOperationError(f"insert_after expected exactly one anchor; found {occurrences}")
        return text.replace(anchor, anchor + addition, 1)
    raise ProjectOperationError(f"unsupported change-set operation: {operation_type}")


def _next_version_path(context: ProjectContext, target: Path) -> Tuple[Path, str]:
    base = re.sub(r"-v\d{3}$", "", target.stem)
    suffix = target.suffix or ".md"
    directory = context.workspace_path("manuscript/versions")
    directory.mkdir(parents=True, exist_ok=True)
    versions: List[int] = []
    for path in directory.glob(f"{base}-v???{suffix}"):
        match = re.search(r"-v(\d{3})$", path.stem)
        if match:
            versions.append(int(match.group(1)))
    version = max(versions, default=0) + 1
    label = f"v{version:03d}"
    return directory / f"{base}-{label}{suffix}", label


def apply_change_set(context: ProjectContext, change_set_path: Path, *, actor: str) -> Dict[str, str]:
    change_set_path = change_set_path.expanduser().resolve()
    change_set = _approved_change_set(context, change_set_path)
    operation = change_set["operation"]
    target_rel = operation.get("target_relative_path")
    path_errors = validate_relative_project_path(target_rel, "operation.target_relative_path")
    if path_errors:
        raise ProjectOperationError("; ".join(path_errors))
    if not target_rel.startswith(".manga-studio/manuscript/versions/"):
        raise ProjectOperationError(
            "change sets may target only managed versions under .manga-studio/manuscript/versions/"
        )
    target = context.project_path(target_rel)
    if not target.is_file():
        raise ProjectOperationError(f"change-set target does not exist: {target_rel}")
    expected_sha = operation.get("target_sha256")
    if sha256_file(target) != expected_sha:
        invalidate_stale_approvals(context)
        raise ProjectOperationError("change-set target SHA-256 does not match; rebase and reapprove the change set")

    before = target.read_text(encoding="utf-8")
    after = _apply_operation(before, operation)
    if after == before:
        raise ProjectOperationError("change-set operation produced no change")
    destination, version = _next_version_path(context, target)
    if destination.exists():
        raise ProjectOperationError(f"refusing to overwrite manuscript version: {destination}")
    destination.write_text(after, encoding="utf-8")

    change_set_id = change_set["change_set_id"]
    diff_rel = f".manga-studio/revisions/diffs/{change_set_id}-{version}.diff"
    diff_path = context.project_path(diff_rel)
    diff_text = "".join(difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=target_rel,
        tofile=destination.relative_to(context.project_root).as_posix(),
    ))
    if diff_path.exists():
        raise ProjectOperationError(f"refusing to overwrite revision diff: {diff_rel}")
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text(diff_text, encoding="utf-8")

    decision_rel = f".manga-studio/decisions/decision-{change_set_id}-{version}.json"
    decision = {
        "schema_version": "3.0.0",
        "decision_id": f"decision-{uuid.uuid4().hex}",
        "project_id": context.config["project_id"],
        "decision_type": "apply_change_set",
        "subject_ids": [change_set_id, *change_set.get("target_stable_ids", [])],
        "decision": "applied",
        "rationale": change_set["expected_result"],
        "actor": actor,
        "decided_at": _timestamp(),
        "evidence": change_set.get("source_evidence", []),
        "result_artifacts": [
            destination.relative_to(context.project_root).as_posix(),
            diff_rel,
        ],
        "supersedes_decision_id": None,
    }
    write_json(context.project_path(decision_rel), decision)

    config = load_json(context.project_file)
    config["active_manuscript_version"] = destination.relative_to(context.project_root).as_posix()
    for gate in ("MANUSCRIPT_APPROVED", "STORY_LOCKED", "STORYBOARD_APPROVED", "STORYBOARD_LOCKED", "IMAGE_READY"):
        config.setdefault("stage_locks", {})[gate] = False
    write_json(context.project_file, config)
    invalidate_stale_approvals(context)
    return {
        "manuscript_version": destination.relative_to(context.project_root).as_posix(),
        "diff": diff_rel,
        "decision": decision_rel,
    }
