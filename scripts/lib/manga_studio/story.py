from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple

from .approvals import validate_approval, validate_locks
from .json_schema import validate_json_file
from .project import IMPORTABLE_CLASSIFICATION_STATUSES, INVENTORY_FILE, PROVENANCE_FILE, USAGE_ROLES, ProjectContext
from .structure import STRUCTURE_INDEX_FILE, validate_source_maps
from .validation import load_json


ARTIFACT_PATTERNS: Tuple[Tuple[str, str], ...] = (
    ("source/documents/*.json", "source-document.schema.json"),
    ("story/story-model*.json", "story-model.schema.json"),
    ("story/arcs/*.json", "story-arc.schema.json"),
    ("story/chapters/*.json", "chapter.schema.json"),
    ("story/scenes/*.json", "scene.schema.json"),
    ("canon/story/*.json", "canon.schema.json"),
    ("canon/timeline/*.json", "timeline-event.schema.json"),
    ("canon/relationships/*.json", "relationship.schema.json"),
    ("canon/plot-threads/*.json", "plot-thread.schema.json"),
    ("canon/setups-payoffs/*.json", "setup-payoff.schema.json"),
    ("continuity/character-states/*.json", "character-state.schema.json"),
    ("canon/voice-guides/*.json", "voice-guide.schema.json"),
    ("analysis/issues/*.json", "story-issue.schema.json"),
    ("analysis/diagnostics/*.json", "diagnostic-report.schema.json"),
    ("revisions/policies/*.json", "revision-policy.schema.json"),
    ("revisions/plans/*.json", "revision-plan.schema.json"),
    ("revisions/change-sets/*.json", "change-set.schema.json"),
    ("approvals/*.json", "approval.schema.json"),
    ("decisions/*.json", "decision-log.schema.json"),
    ("locks/*.json", "stage-lock.schema.json"),
)


def _schema_validate(context: ProjectContext, path: Path, schema_name: str) -> List[str]:
    try:
        return [
            f"{path.relative_to(context.project_root)}: {message}"
            for message in validate_json_file(path, context.install_root / "schemas" / schema_name)
        ]
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return [f"schema validation failed for {path}: {exc}"]


def _validate_inventory_approval(context: ProjectContext) -> List[str]:
    inventory_path = context.workspace_path(INVENTORY_FILE)
    provenance_path = context.workspace_path(PROVENANCE_FILE)
    if not inventory_path.is_file() or not provenance_path.is_file():
        return []
    inventory = load_json(inventory_path)
    provenance = load_json(provenance_path)
    by_document = {
        item.get("document_id"): item
        for item in inventory.get("files", [])
        if isinstance(item, dict) and item.get("document_id")
    }
    errors: List[str] = []
    for record in provenance.get("records", []):
        entry = by_document.get(record.get("document_id"))
        if entry is None:
            errors.append(f"provenance document is absent from inventory: {record.get('document_id')}")
            continue
        if entry.get("classification_status") not in IMPORTABLE_CLASSIFICATION_STATUSES:
            errors.append(f"imported document lacks approved classification: {record.get('document_id')}")
        if entry.get("usage_role") not in USAGE_ROLES or entry.get("usage_role") == "excluded":
            errors.append(f"imported document lacks an importable usage_role: {record.get('document_id')}")
        if record.get("classification_status") != entry.get("classification_status"):
            errors.append(f"provenance classification_status differs from inventory: {record.get('document_id')}")
        if record.get("usage_role") != entry.get("usage_role"):
            errors.append(f"provenance usage_role differs from inventory: {record.get('document_id')}")
    return errors


def _source_map_index(context: ProjectContext) -> Tuple[Dict[str, Dict[str, Any]], Set[str], Set[str], Set[str]]:
    units: Dict[str, Dict[str, Any]] = {}
    chapters: Set[str] = set()
    scenes: Set[str] = set()
    documents: Set[str] = set()
    paths: List[Path] = []
    provenance_path = context.workspace_path(PROVENANCE_FILE)
    if provenance_path.is_file():
        provenance = load_json(provenance_path)
        paths = [
            context.project_path(record["source_map_path"])
            for record in provenance.get("records", [])
            if record.get("source_status") == "active" and isinstance(record.get("source_map_path"), str)
        ]
    for path in paths:
        if not path.is_file():
            continue
        data = load_json(path)
        documents.add(data.get("document_id"))
        chapters.update(item.get("chapter_id") for item in data.get("chapters", []) if item.get("chapter_id"))
        scenes.update(item.get("scene_id") for item in data.get("scenes", []) if item.get("scene_id"))
        units.update({item["source_unit_id"]: item for item in data.get("source_units", []) if item.get("source_unit_id")})
    return units, chapters, scenes, documents


def _validate_diagnostic_links(context: ProjectContext) -> List[str]:
    units, chapters, scenes, documents = _source_map_index(context)
    provenance_path = context.workspace_path(PROVENANCE_FILE)
    provenance = load_json(provenance_path) if provenance_path.is_file() else {"records": []}
    map_checksums = {
        record["source_map_checksum"]
        for record in provenance.get("records", [])
        if record.get("source_status") == "active" and isinstance(record.get("source_map_checksum"), str)
    }
    errors: List[str] = []
    seen_issues: Set[str] = set()
    for path in context.workspace_path("analysis/diagnostics").glob("*.json"):
        if path.name.startswith("._"):
            continue
        report = load_json(path)
        if report.get("project_id") != context.config.get("project_id"):
            errors.append(f"{path.name}: diagnostic report references another project")
        for checksum in report.get("source_map_checksums", []):
            if checksum not in map_checksums:
                errors.append(f"{path.name}: diagnostic report references an unknown source-map checksum")
        for finding in report.get("findings", []):
            issue_id = finding.get("issue_id")
            if issue_id in seen_issues:
                errors.append(f"duplicate diagnostic issue_id: {issue_id}")
            if issue_id:
                seen_issues.add(issue_id)
            for chapter_id in finding.get("affected_chapter_ids", []):
                if chapter_id not in chapters:
                    errors.append(f"{issue_id}: unknown affected chapter ID {chapter_id}")
            for scene_id in finding.get("affected_scene_ids", []):
                if scene_id not in scenes:
                    errors.append(f"{issue_id}: unknown affected scene ID {scene_id}")
            for evidence in finding.get("evidence", []):
                if not isinstance(evidence, dict):
                    errors.append(f"{issue_id}: evidence locator must be an object")
                    continue
                if evidence.get("project_id") != context.config.get("project_id"):
                    errors.append(f"{issue_id}: evidence references another project")
                if evidence.get("document_id") not in documents:
                    errors.append(f"{issue_id}: unknown evidence document ID {evidence.get('document_id')}")
                unit = units.get(evidence.get("source_unit_id"))
                if unit is None:
                    errors.append(f"{issue_id}: unknown evidence source unit {evidence.get('source_unit_id')}")
                    continue
                line_start = evidence.get("line_start")
                line_end = evidence.get("line_end")
                byte_start = evidence.get("byte_start")
                byte_end = evidence.get("byte_end")
                if all(isinstance(value, int) for value in (line_start, line_end, unit.get("line_start"), unit.get("line_end"))) and (
                    line_start < unit["line_start"] or line_end > unit["line_end"]
                ):
                    errors.append(f"{issue_id}: evidence line range falls outside its source unit")
                if all(isinstance(value, int) for value in (byte_start, byte_end, unit.get("byte_start"), unit.get("byte_end"))) and (
                    byte_start < unit["byte_start"] or byte_end > unit["byte_end"]
                ):
                    errors.append(f"{issue_id}: evidence byte range falls outside its source unit")
                if evidence.get("content_fingerprint") != unit.get("content_fingerprint"):
                    errors.append(f"{issue_id}: evidence content fingerprint does not match source map")
    return errors


def _validate_decision_outputs(context: ProjectContext) -> List[str]:
    errors: List[str] = []
    for path in context.workspace_path("decisions").glob("*.json"):
        if path.name.startswith("._"):
            continue
        try:
            decision = load_json(path)
        except Exception:
            continue
        if decision.get("project_id") != context.config.get("project_id"):
            errors.append(f"{path.name}: decision belongs to another project")
        for artifact in decision.get("result_artifacts", []):
            if not context.project_path(artifact).is_file():
                errors.append(f"{path.name}: decision result artifact is missing: {artifact}")
    return errors


def _validate_all_evidence(context: ProjectContext) -> List[str]:
    units, _, _, documents = _source_map_index(context)
    errors: List[str] = []
    decision_ids = set()
    approval_ids = set()
    for path in context.workspace_path("decisions").glob("*.json"):
        try:
            decision = load_json(path)
            if decision.get("project_id") == context.config.get("project_id"):
                decision_ids.add(decision.get("decision_id"))
        except Exception:
            continue
    for path in context.workspace_path("approvals").glob("*.json"):
        try:
            approval = load_json(path)
            if (
                approval.get("project_id") == context.config.get("project_id")
                and approval.get("status") == "approved"
                and not validate_approval(context, path)
            ):
                approval_ids.add(approval.get("approval_id"))
        except Exception:
            continue

    def walk(value: Any, label: str) -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{label}[{index}]")
            return
        if not isinstance(value, dict):
            return
        if "source_unit_id" in value and "project_id" in value:
            unit = units.get(value.get("source_unit_id"))
            if value.get("project_id") != context.config.get("project_id"):
                errors.append(f"{label}: evidence references another project")
            if value.get("document_id") not in documents:
                errors.append(f"{label}: evidence document ID is not in a source map")
            if unit is None:
                errors.append(f"{label}: evidence source unit is not in a source map")
            elif value.get("content_fingerprint") != unit.get("content_fingerprint"):
                errors.append(f"{label}: evidence fingerprint does not match its source unit")
        if value.get("basis_type") == "approved_decision":
            reference = value.get("decision", {})
            if not isinstance(reference, dict):
                errors.append(f"{label}: approved decision basis must contain a decision reference")
            else:
                if reference.get("decision_id") not in decision_ids:
                    errors.append(f"{label}: approved decision record is missing")
                if reference.get("approval_id") not in approval_ids:
                    errors.append(f"{label}: approved decision approval is missing or invalid")
        for key, item in value.items():
            walk(item, f"{label}.{key}")

    for pattern, _ in ARTIFACT_PATTERNS:
        for path in context.workspace_path(".").glob(pattern):
            if path.name.startswith("._"):
                continue
            try:
                walk(load_json(path), path.relative_to(context.project_root).as_posix())
            except Exception:
                continue
    return errors


def validate_story_artifacts(context: ProjectContext) -> List[str]:
    errors: List[str] = []
    for pattern, schema_name in ARTIFACT_PATTERNS:
        for path in sorted(context.workspace_path(".").glob(pattern)):
            if path.name.startswith("._"):
                continue
            errors.extend(_schema_validate(context, path, schema_name))
            try:
                data = load_json(path)
            except Exception:
                continue
            if data.get("project_id") != context.config.get("project_id"):
                errors.append(f"{path.relative_to(context.project_root)}: project_id does not match project.json")
    errors.extend(_validate_inventory_approval(context))
    if context.workspace_path(PROVENANCE_FILE).is_file():
        errors.extend(validate_source_maps(context))
    errors.extend(_validate_diagnostic_links(context))
    errors.extend(_validate_all_evidence(context))
    errors.extend(_validate_decision_outputs(context))
    for path in sorted(context.workspace_path("approvals").glob("*.json")):
        if path.name.startswith("._"):
            continue
        errors.extend(f"{path.relative_to(context.project_root)}: {message}" for message in validate_approval(context, path))
    errors.extend(validate_locks(context))
    return errors
