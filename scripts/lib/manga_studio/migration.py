from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List

from .project import ID_MAP_FILE, INVENTORY_FILE, PROVENANCE_FILE, SCHEMA_VERSION, STAGE_GATES, WORKSPACE_DIRECTORIES, ProjectContext, ProjectOperationError, sha256_file
from .validation import load_json, write_json


LEGACY_ROLE_MAP = {
    "manuscript": "primary_manuscript",
    "outline": "outline",
    "notes": "author_notes",
    "reference": "canon_reference",
    "primary_manuscript": "primary_manuscript",
    "supplementary_manuscript": "supplementary_manuscript",
    "author_notes": "author_notes",
    "canon_reference": "canon_reference",
    "research": "research",
}


def _backup(path: Path, root: Path, workspace_root: Path) -> None:
    if not path.is_file():
        return
    destination = root / path.relative_to(workspace_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


def migrate_project(context: ProjectContext) -> List[str]:
    current = context.config.get("schema_version")
    if current == SCHEMA_VERSION:
        actions: List[str] = []
        for relative in WORKSPACE_DIRECTORIES:
            path = context.workspace_path(relative)
            if not path.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                actions.append(f"created .manga-studio/{relative}/")
        config = load_json(context.project_file)
        target = config.setdefault("target_manga_format", {})
        changed = False
        for key, value in (
            ("output_intent", "screen"),
            ("print_profile", None),
        ):
            if key not in target:
                target[key] = value
                changed = True
        for key in ("active_creative_brief_version", "active_success_plan_version", "active_nemu_version"):
            if key not in config:
                config[key] = None
                changed = True
        if changed:
            write_json(context.project_file, config)
            actions.append("added Manga Studio 3.3 project defaults without changing story sources")
        return actions or [f"project already uses schema {SCHEMA_VERSION} and current workspace layout"]
    if current != "2.0.0":
        raise ProjectOperationError(f"no migration path from project schema {current!r} to {SCHEMA_VERSION}")
    backup_root = context.workspace_path("migrations/v2-to-v3")
    if backup_root.exists():
        raise ProjectOperationError(f"migration backup already exists: {backup_root}")
    actions: List[str] = []
    for relative in WORKSPACE_DIRECTORIES:
        path = context.workspace_path(relative)
        path.mkdir(parents=True, exist_ok=True)
    for relative in ("project.json", INVENTORY_FILE, ID_MAP_FILE, PROVENANCE_FILE):
        _backup(context.workspace_path(relative), backup_root, context.workspace_root)

    config = load_json(context.project_file)
    config["schema_version"] = SCHEMA_VERSION
    config.setdefault("stage_lock_records", {gate: None for gate in STAGE_GATES})
    for gate in STAGE_GATES:
        config["stage_lock_records"].setdefault(gate, None)
    write_json(context.project_file, config)
    actions.append("migrated project.json to 3.0.0")

    inventory_path = context.workspace_path(INVENTORY_FILE)
    inventory_by_document: Dict[str, Dict[str, Any]] = {}
    if inventory_path.is_file():
        inventory = load_json(inventory_path)
        inventory["schema_version"] = SCHEMA_VERSION
        for entry in inventory.get("files", []):
            status = entry.get("classification_status", "suggested")
            role = LEGACY_ROLE_MAP.get(entry.get("classification"))
            entry.setdefault("usage_role", role if status in {"approved", "corrected"} else None)
            if entry.get("document_id"):
                inventory_by_document[entry["document_id"]] = entry
        write_json(inventory_path, inventory)
        actions.append("migrated source inventory without inventing approvals")

    id_map_path = context.workspace_path(ID_MAP_FILE)
    if id_map_path.is_file():
        id_map = load_json(id_map_path)
        id_map["schema_version"] = SCHEMA_VERSION
        id_map.setdefault("namespaces", {}).setdefault("source_units", [])
        write_json(id_map_path, id_map)
        actions.append("added source-unit stable-ID namespace")

    provenance_path = context.workspace_path(PROVENANCE_FILE)
    if provenance_path.is_file():
        provenance = load_json(provenance_path)
        provenance["schema_version"] = SCHEMA_VERSION
        for record in provenance.get("records", []):
            normalized = context.project_path(record["normalized_path"])
            record.setdefault("normalized_sha256", sha256_file(normalized) if normalized.is_file() else "")
            record.setdefault("adapter_version", "0.0.0")
            record.setdefault("normalization_profile", "legacy-v2")
            record.setdefault("parser_version", None)
            record.setdefault("source_map_path", None)
            record.setdefault("source_map_checksum", None)
            inventory_entry = inventory_by_document.get(record.get("document_id"), {})
            record.setdefault("classification_status", inventory_entry.get("classification_status", "suggested"))
            record.setdefault("usage_role", inventory_entry.get("usage_role"))
        provenance.setdefault("import_summary", {}).setdefault("blocked", [])
        write_json(provenance_path, provenance)
        actions.append("added normalized provenance fields; source maps remain required")
    actions.append(f"preserved pre-migration metadata under {backup_root.relative_to(context.project_root)}")
    return actions
