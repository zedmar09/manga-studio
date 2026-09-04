from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .adapters import NORMALIZATION_PROFILE, PARSER_COMPATIBILITY_VERSION, adapter_by_name, adapter_for_extension
from .validation import load_json, validate_relative_project_path, write_json


SCHEMA_VERSION = "3.0.0"
WORKSPACE_NAME = ".manga-studio"
PROJECT_FILE = "project.json"
INVENTORY_FILE = "source/inventory.json"
ID_MAP_FILE = "source/id-map.json"
PROVENANCE_FILE = "source/provenance.json"
MANAGED_START = "<!-- BEGIN MANGA STUDIO MANAGED -->"
MANAGED_END = "<!-- END MANGA STUDIO MANAGED -->"

WORKSPACE_DIRECTORIES = (
    "source",
    "source/documents",
    "source/maps",
    "story",
    "canon",
    "analysis",
    "analysis/diagnostics",
    "revisions",
    "revisions/policies",
    "revisions/plans",
    "revisions/change-sets",
    "revisions/diffs",
    "manuscript",
    "manuscript/versions",
    "storyboard",
    "continuity",
    "approvals",
    "decisions",
    "locks",
    "handoff/pending",
    "handoff/generated",
    "handoff/approved",
    "handoff/corrections",
    "panels",
    "lettering",
    "pages",
    "exports",
)

STAGE_GATES = (
    "SOURCE_LOCKED",
    "CANON_APPROVED",
    "DIAGNOSTIC_APPROVED",
    "REVISION_PLAN_APPROVED",
    "MANUSCRIPT_APPROVED",
    "STORY_LOCKED",
    "STORYBOARD_APPROVED",
    "STORYBOARD_LOCKED",
    "IMAGE_READY",
)

STABLE_ID_NAMESPACES = (
    "source_documents",
    "chapters",
    "scenes",
    "characters",
    "locations",
    "organizations",
    "props",
    "timeline_events",
    "plot_threads",
    "setups_payoffs",
    "source_units",
)

USAGE_ROLES = (
    "primary_manuscript",
    "supplementary_manuscript",
    "outline",
    "author_notes",
    "canon_reference",
    "research",
    "excluded",
)

IMPORTABLE_CLASSIFICATION_STATUSES = {"approved", "corrected"}

OPERATING_MODES = (
    "create_new",
    "import_existing",
    "diagnose_existing",
    "repair_existing",
    "continue_existing",
    "adapt_existing_to_manga",
    "continuity_audit",
    "prepare_visual_production",
)

VERSION_AREAS = (
    "canon",
    "analysis",
    "revisions",
    "manuscript",
    "storyboard",
    "continuity",
    "decisions",
    "lettering",
    "pages",
)

DEFAULT_EXCLUSIONS = (
    ".manga-studio/**",
    ".git/**",
    "build/**",
    "dist/**",
    "out/**",
    "target/**",
    "node_modules/**",
    "__pycache__/**",
    ".pytest_cache/**",
    ".mypy_cache/**",
    ".ruff_cache/**",
    "*.tmp",
    "*.temp",
    "*.swp",
    "._*",
    "**/._*",
    "AGENTS.md",
    ".DS_Store",
)

TEXT_LIKE_UNSUPPORTED = {".doc", ".docx", ".odt", ".rtf", ".pdf"}

AGENTS_MANAGED_SECTION = f"""{MANAGED_START}
## Manga Studio

- Treat original story files outside `.manga-studio/` as immutable source evidence.
- Store normalized derivatives and every revision as separate versioned files under `.manga-studio/`.
- Require explicit approval before adopting revisions or changing approved canon.
- Approved canon is authoritative over analysis, drafts, storyboards, and production notes; original sources remain the provenance authority.
- Image generation is disabled by default and may be enabled only after the story and storyboard gates are locked.
- Codex must never generate or edit artwork. Character, location, prop, panel, cover, splash-page, and correction art must be represented by structured ChatGPT Image Generation Jobs.
- ChatGPT Image Generation is reserved for eventual external image production; Codex may validate, organize, letter, compose, review, and export approved outputs.
{MANAGED_END}"""


class ProjectDiscoveryError(RuntimeError):
    pass


class ProjectOperationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProjectContext:
    project_root: Path
    workspace_root: Path
    project_file: Path
    install_root: Path
    config: Dict[str, Any]

    @property
    def source_roots(self) -> List[Path]:
        roots: List[Path] = []
        for value in self.config.get("source_roots", ["."]):
            errors = validate_relative_project_path(value, "source_roots[]")
            if errors:
                raise ProjectOperationError("; ".join(errors))
            roots.append((self.project_root / value).resolve())
        return roots

    def workspace_path(self, relative: str) -> Path:
        return self.workspace_root.joinpath(*PurePosixPath(relative).parts)

    def project_path(self, relative: str) -> Path:
        return self.project_root.joinpath(*PurePosixPath(relative).parts)


def toolkit_install_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _normalize_start(path: Optional[Path]) -> Path:
    start = (path or Path.cwd()).expanduser().resolve()
    if start.is_file():
        return start.parent
    return start


def discover_project(path: Optional[Path] = None) -> ProjectContext:
    """Discover a story by searching upward. There is intentionally no sample fallback."""
    start = _normalize_start(path)
    candidates = [start, *start.parents]
    for candidate in candidates:
        if candidate.name == WORKSPACE_NAME and (candidate / PROJECT_FILE).is_file():
            workspace_root = candidate
            project_root = candidate.parent
            break
        project_file = candidate / WORKSPACE_NAME / PROJECT_FILE
        if project_file.is_file():
            project_root = candidate
            workspace_root = candidate / WORKSPACE_NAME
            break
    else:
        supplied = f" from '{start}'" if path is not None else f" from current directory '{start}'"
        raise ProjectDiscoveryError(
            "No Manga Studio project was found"
            f"{supplied}. Run 'scripts/manga_studio.py init <story-directory>' with manga-creator, "
            "or pass the correct story path. Specialist skills must stop here."
        )

    project_file = workspace_root / PROJECT_FILE
    try:
        config = load_json(project_file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ProjectDiscoveryError(f"Found project metadata but could not read '{project_file}': {exc}") from exc
    return ProjectContext(
        project_root=project_root.resolve(),
        workspace_root=workspace_root.resolve(),
        project_file=project_file.resolve(),
        install_root=toolkit_install_root().resolve(),
        config=config,
    )


def project_relative(project_root: Path, path: Path) -> str:
    resolved_root = project_root.resolve()
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise ProjectOperationError(f"Path is outside project_root and cannot be stored: {resolved_path}") from exc


def default_project_config(project_root: Path, mode: str, title: Optional[str] = None) -> Dict[str, Any]:
    if mode not in OPERATING_MODES:
        raise ProjectOperationError(f"Unsupported operating mode '{mode}'")
    project_type = "new_story" if mode == "create_new" else "existing_story"
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": f"ms-{uuid.uuid4().hex}",
        "title": title or project_root.name,
        "source_language": "und",
        "output_language": "und",
        "project_type": project_type,
        "genre": [],
        "source_roots": ["."],
        "source_inclusion_patterns": ["**/*", "*"],
        "source_exclusion_patterns": list(DEFAULT_EXCLUSIONS),
        "chapter_detection_strategy": {
            "mode": "auto",
            "filename_patterns": ["chapter*", "ch-*", "ch_*"],
            "heading_levels": [1, 2],
            "require_review_on_ambiguity": True,
        },
        "existing_structure_preservation": {
            "preserve_original_paths": True,
            "preserve_chapter_order": True,
            "preserve_titles": True,
            "never_rewrite_originals": True,
        },
        "revision_mode": "proposal_only",
        "author_voice_preservation": {
            "required": True,
            "notes": [],
        },
        "reading_direction": "right-to-left",
        "target_manga_format": {
            "color_mode": "black-and-white",
            "page_width_px": 1654,
            "page_height_px": 2339,
        },
        "workflow_phase": "story_foundation",
        "operating_mode": mode,
        "stage_locks": {gate: False for gate in STAGE_GATES},
        "stage_lock_records": {gate: None for gate in STAGE_GATES},
        "image_generation_enabled": False,
        "active_manuscript_version": None,
        "active_canon_version": None,
        "active_storyboard_version": None,
        "blocking_reasons": [
            "Story and storyboard approvals are incomplete.",
            "Image generation is disabled by default.",
        ],
    }


def update_agents_file(project_root: Path) -> Tuple[Path, str]:
    agents_path = project_root / "AGENTS.md"
    original = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
    start_count = original.count(MANAGED_START)
    end_count = original.count(MANAGED_END)
    if start_count != end_count or start_count > 1:
        raise ProjectOperationError(
            f"AGENTS.md has malformed or duplicate Manga Studio managed markers: {agents_path}. "
            "Repair the markers before initialization continues."
        )
    start = original.find(MANAGED_START)
    end = original.find(MANAGED_END)
    if start >= 0 and end >= start:
        end += len(MANAGED_END)
        updated = original[:start] + AGENTS_MANAGED_SECTION + original[end:]
        action = "updated" if updated != original else "preserved"
    else:
        separator = "" if not original else ("\n" if original.endswith("\n") else "\n\n")
        updated = original + separator + AGENTS_MANAGED_SECTION + "\n"
        action = "created" if not original else "appended"
    if updated != original:
        agents_path.write_text(updated, encoding="utf-8")
    return agents_path, action


def empty_id_map(project_id: str) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "namespaces": {namespace: [] for namespace in STABLE_ID_NAMESPACES},
    }


def initialize_project(
    path: Path,
    *,
    mode: str = "import_existing",
    title: Optional[str] = None,
) -> Tuple[ProjectContext, List[str]]:
    project_root = path.expanduser().resolve()
    if project_root.exists() and not project_root.is_dir():
        raise ProjectOperationError(f"Story path is not a directory: {project_root}")
    project_root.mkdir(parents=True, exist_ok=True)
    workspace_root = project_root / WORKSPACE_NAME
    workspace_root.mkdir(exist_ok=True)
    actions: List[str] = []
    for relative in WORKSPACE_DIRECTORIES:
        directory = workspace_root / relative
        if not directory.exists():
            directory.mkdir(parents=True)
            actions.append(f"created {project_relative(project_root, directory)}/")

    project_file = workspace_root / PROJECT_FILE
    if project_file.exists():
        config = load_json(project_file)
        actions.append(f"preserved {project_relative(project_root, project_file)}")
    else:
        config = default_project_config(project_root, mode, title)
        write_json(project_file, config)
        actions.append(f"created {project_relative(project_root, project_file)}")

    id_map_path = workspace_root / ID_MAP_FILE
    if not id_map_path.exists():
        write_json(id_map_path, empty_id_map(config["project_id"]))
        actions.append(f"created {project_relative(project_root, id_map_path)}")

    agents_path, agents_action = update_agents_file(project_root)
    actions.append(f"{agents_action} {project_relative(project_root, agents_path)}")
    return discover_project(project_root), actions


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_version(context: ProjectContext, source: Path, area: str) -> Path:
    if area not in VERSION_AREAS:
        raise ProjectOperationError(f"Unsupported version area '{area}'")
    source = source.expanduser().resolve()
    if not source.is_file():
        raise ProjectOperationError(f"Version source is not a file: {source}")
    destination_dir = context.workspace_path(area)
    destination_dir.mkdir(parents=True, exist_ok=True)
    base = re.sub(r"-v\d{3}$", "", source.stem)
    existing_versions = []
    for path in destination_dir.glob(f"{base}-v???{source.suffix}"):
        match = re.search(r"-v(\d{3})$", path.stem)
        if match:
            existing_versions.append(int(match.group(1)))
    version = max(existing_versions, default=0) + 1
    destination = destination_dir / f"{base}-v{version:03d}{source.suffix}"
    if destination.exists():
        raise ProjectOperationError(f"Refusing to overwrite existing version: {destination}")
    destination.write_bytes(source.read_bytes())
    return destination


def _matches_any(path: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) or PurePosixPath(path).match(pattern) for pattern in patterns)


def _is_excluded(path: str, patterns: Sequence[str]) -> bool:
    parts = PurePosixPath(path).parts
    if any(part in {WORKSPACE_NAME, ".git", "node_modules", "__pycache__"} for part in parts):
        return True
    return _matches_any(path, patterns)


def classify_candidate(relative_path: str) -> str:
    lower = relative_path.lower()
    stem = PurePosixPath(lower).stem
    parts = set(PurePosixPath(lower).parts)
    if "outline" in stem or "outlines" in parts:
        return "outline"
    if any(token in stem for token in ("note", "idea", "todo")) or "notes" in parts:
        return "author_notes"
    if any(token in stem for token in ("reference", "bible", "lore")) or parts.intersection({"references", "reference", "lore"}):
        return "canon_reference"
    if any(token in stem for token in ("chapter", "manuscript", "novel", "story")) or parts.intersection({"chapters", "manuscript"}):
        return "primary_manuscript"
    return "unknown"


def _load_id_map(context: ProjectContext) -> Dict[str, Any]:
    path = context.workspace_path(ID_MAP_FILE)
    if not path.exists():
        data = empty_id_map(context.config["project_id"])
        write_json(path, data)
        return data
    return load_json(path)


def _source_id_for(
    id_map: Dict[str, Any],
    relative_path: str,
    checksum: str,
    current_paths: set[str],
) -> Tuple[Optional[str], str, List[str]]:
    records = id_map["namespaces"]["source_documents"]
    for record in records:
        if record.get("path") == relative_path or relative_path in record.get("aliases", []):
            record["checksum"] = checksum
            return record["id"], "matched_path", []

    movable = [
        record
        for record in records
        if record.get("checksum") == checksum and record.get("path") not in current_paths
    ]
    if len(movable) == 1:
        record = movable[0]
        old_path = record.get("path")
        if old_path and old_path != relative_path:
            aliases = record.setdefault("aliases", [])
            if old_path not in aliases:
                aliases.append(old_path)
            record["path"] = relative_path
        return record["id"], "matched_checksum_after_move", []
    if len(movable) > 1:
        return None, "ambiguous", [record["id"] for record in movable]

    document_id = f"doc-{uuid.uuid4().hex}"
    records.append({
        "id": document_id,
        "path": relative_path,
        "checksum": checksum,
        "aliases": [],
    })
    return document_id, "new", []


def inventory_sources(context: ProjectContext) -> Dict[str, Any]:
    config = context.config
    inclusions = config.get("source_inclusion_patterns", ["**/*", "*"])
    exclusions = config.get("source_exclusion_patterns", list(DEFAULT_EXCLUSIONS))
    candidates: Dict[str, Path] = {}

    for source_root in context.source_roots:
        try:
            source_root.relative_to(context.project_root)
        except ValueError as exc:
            raise ProjectOperationError(f"Configured source root is outside project_root: {source_root}") from exc
        if not source_root.exists():
            continue
        for path in source_root.rglob("*"):
            if not path.is_file():
                continue
            relative = project_relative(context.project_root, path)
            if _is_excluded(relative, exclusions):
                continue
            if not _matches_any(relative, inclusions):
                continue
            candidates[relative] = path

    existing_inventory_path = context.workspace_path(INVENTORY_FILE)
    existing_by_path: Dict[str, Dict[str, Any]] = {}
    existing_by_document: Dict[str, Dict[str, Any]] = {}
    if existing_inventory_path.exists():
        existing = load_json(existing_inventory_path)
        existing_by_path = {
            item.get("relative_path"): item
            for item in existing.get("files", [])
            if isinstance(item, dict) and isinstance(item.get("relative_path"), str)
        }
        existing_by_document = {
            item.get("document_id"): item
            for item in existing.get("files", [])
            if isinstance(item, dict) and isinstance(item.get("document_id"), str)
        }

    id_map = _load_id_map(context)
    current_paths = set(candidates)
    files: List[Dict[str, Any]] = []
    for relative, path in sorted(candidates.items()):
        stat = path.stat()
        checksum = sha256_file(path)
        document_id, match_status, match_candidates = _source_id_for(
            id_map, relative, checksum, current_paths
        )
        suffix = path.suffix.lower()
        source_adapter = adapter_for_extension(suffix)
        adapter = source_adapter.name if source_adapter else None
        previous = existing_by_document.get(document_id, existing_by_path.get(relative, {}))
        suggested = classify_candidate(relative)
        classification = previous.get("classification", suggested)
        classification_status = previous.get("classification_status", "suggested")
        usage_role = previous.get("usage_role")
        if match_status == "ambiguous":
            classification_status = "ambiguous"
            usage_role = None
        support_status = "supported" if adapter else "unsupported"
        message = None
        if not adapter:
            if suffix in TEXT_LIKE_UNSUPPORTED:
                message = f"No {suffix or 'unknown'} adapter is installed; preserve the file and add an adapter before import."
            else:
                message = f"Unsupported source type '{suffix or '[no extension]'}'; file is inventoried and preserved."
        files.append({
            "document_id": document_id,
            "id_match_status": match_status,
            "id_match_candidates": match_candidates,
            "relative_path": relative,
            "extension": suffix,
            "size_bytes": stat.st_size,
            "modified_time_ns": stat.st_mtime_ns,
            "sha256": checksum,
            "classification": classification,
            "classification_status": classification_status,
            "usage_role": usage_role,
            "adapter": adapter,
            "support_status": support_status,
            "message": message,
        })

    inventory = {
        "schema_version": SCHEMA_VERSION,
        "project_id": config["project_id"],
        "project_root": ".",
        "source_roots": config.get("source_roots", ["."]),
        "files": files,
    }
    write_json(existing_inventory_path, inventory)
    write_json(context.workspace_path(ID_MAP_FILE), id_map)
    return inventory


def import_sources(context: ProjectContext) -> Dict[str, Any]:
    inventory_path = context.workspace_path(INVENTORY_FILE)
    if not inventory_path.exists():
        raise ProjectOperationError(
            f"Source inventory is required before import. Run 'scripts/manga_studio.py inventory {context.project_root}'."
        )
    inventory = load_json(inventory_path)
    provenance_records: List[Dict[str, Any]] = []
    existing_provenance_path = context.workspace_path(PROVENANCE_FILE)
    if existing_provenance_path.exists():
        existing = load_json(existing_provenance_path)
        provenance_records = list(existing.get("records", []))
    by_version = {
        (
            record.get("document_id"),
            record.get("original_sha256"),
            record.get("adapter_version", "legacy"),
            record.get("normalization_profile", "legacy"),
            record.get("parser_version", "legacy"),
        ): record
        for record in provenance_records
    }

    imported = 0
    skipped = 0
    blocked: List[Dict[str, str]] = []
    for entry in inventory.get("files", []):
        relative = entry.get("relative_path", "[unknown]")
        if entry.get("support_status") != "supported":
            skipped += 1
            continue
        if entry.get("classification_status") not in IMPORTABLE_CLASSIFICATION_STATUSES:
            skipped += 1
            if entry.get("classification_status") != "rejected":
                blocked.append({
                    "relative_path": relative,
                    "reason": f"classification_status is {entry.get('classification_status')!r}; approved or corrected is required",
                })
            continue
        usage_role = entry.get("usage_role")
        if usage_role not in USAGE_ROLES or usage_role == "excluded":
            skipped += 1
            if usage_role != "excluded":
                blocked.append({
                    "relative_path": relative,
                    "reason": "an explicit supported usage_role is required",
                })
            continue
        if entry.get("id_match_status") == "ambiguous" or not entry.get("document_id"):
            skipped += 1
            blocked.append({
                "relative_path": relative,
                "reason": "stable document match is ambiguous",
            })
            continue
        document_id = entry.get("document_id")
        source = context.project_path(relative)
        current_checksum = sha256_file(source)
        if current_checksum != entry.get("sha256"):
            raise ProjectOperationError(
                f"Source changed after inventory: '{relative}'. Re-run inventory and review the classification before importing."
            )
        suffix = source.suffix.lower() or ".bin"
        snapshot_rel = f"{WORKSPACE_NAME}/source/snapshots/{document_id}/{current_checksum}{suffix}"
        adapter = adapter_by_name(entry["adapter"])
        adapter_version = adapter.version
        normalized_rel = (
            f"{WORKSPACE_NAME}/source/normalized/{document_id}/{current_checksum}/"
            f"{adapter.name}-v{adapter_version}-{NORMALIZATION_PROFILE}-parser-v{PARSER_COMPATIBILITY_VERSION}.txt"
        )
        snapshot = context.project_path(snapshot_rel)
        normalized = context.project_path(normalized_rel)
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        normalized.parent.mkdir(parents=True, exist_ok=True)
        raw = source.read_bytes()
        if snapshot.exists():
            if sha256_file(snapshot) != current_checksum:
                raise ProjectOperationError(f"Immutable snapshot checksum mismatch: '{snapshot_rel}'")
        else:
            snapshot.write_bytes(raw)
        try:
            normalized_text = adapter.normalize(raw, source)
        except ValueError as exc:
            raise ProjectOperationError(str(exc)) from exc
        normalized_bytes = normalized_text.encode("utf-8")
        normalized_sha256 = hashlib.sha256(normalized_bytes).hexdigest()
        if normalized.exists():
            if sha256_file(normalized) != normalized_sha256:
                raise ProjectOperationError(
                    f"Normalized derivative was modified; refusing to overwrite: '{normalized_rel}'"
                )
        else:
            normalized.write_bytes(normalized_bytes)
        current_version_key = (
            document_id, current_checksum, adapter_version, NORMALIZATION_PROFILE, PARSER_COMPATIBILITY_VERSION
        )
        for version_key, existing_record in by_version.items():
            existing_document_id = version_key[0]
            if existing_document_id == document_id and version_key != current_version_key:
                existing_record["source_status"] = "superseded"
        by_version[current_version_key] = {
            "document_id": document_id,
            "original_path": relative,
            "original_sha256": current_checksum,
            "snapshot_path": snapshot_rel,
            "snapshot_sha256": current_checksum,
            "normalized_path": normalized_rel,
            "normalized_sha256": normalized_sha256,
            "adapter": adapter.name,
            "adapter_version": adapter_version,
            "normalization_profile": NORMALIZATION_PROFILE,
            "parser_version": PARSER_COMPATIBILITY_VERSION,
            "source_map_path": None,
            "source_map_checksum": None,
            "classification": entry["classification"],
            "classification_status": entry["classification_status"],
            "usage_role": usage_role,
            "source_modified_time_ns": entry["modified_time_ns"],
            "source_status": "active",
        }
        imported += 1

    provenance = {
        "schema_version": SCHEMA_VERSION,
        "project_id": context.config["project_id"],
        "records": sorted(
            by_version.values(),
            key=lambda item: (item["document_id"], item["source_modified_time_ns"], item["original_sha256"]),
        ),
        "import_summary": {"imported": imported, "skipped": skipped, "blocked": blocked},
    }
    write_json(existing_provenance_path, provenance)
    return provenance


def provenance_errors(context: ProjectContext) -> List[str]:
    path = context.workspace_path(PROVENANCE_FILE)
    if not path.exists():
        return []
    try:
        provenance = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"failed to load provenance '{path}': {exc}"]
    errors: List[str] = []
    for record in provenance.get("records", []):
        original_rel = record.get("original_path")
        snapshot_rel = record.get("snapshot_path")
        normalized_rel = record.get("normalized_path")
        if not isinstance(original_rel, str) or not isinstance(snapshot_rel, str) or not isinstance(normalized_rel, str):
            errors.append("provenance record is missing original_path, snapshot_path, or normalized_path")
            continue
        path_errors: List[str] = []
        path_errors.extend(validate_relative_project_path(original_rel, "provenance.original_path"))
        path_errors.extend(validate_relative_project_path(snapshot_rel, "provenance.snapshot_path"))
        path_errors.extend(validate_relative_project_path(normalized_rel, "provenance.normalized_path"))
        if path_errors:
            errors.extend(path_errors)
            continue
        if not snapshot_rel.startswith(f"{WORKSPACE_NAME}/source/snapshots/"):
            errors.append(f"snapshot path is outside the snapshot store: {snapshot_rel}")
        if not normalized_rel.startswith(f"{WORKSPACE_NAME}/source/normalized/"):
            errors.append(f"normalized path is outside the normalized store: {normalized_rel}")
        original = context.project_path(original_rel)
        snapshot = context.project_path(snapshot_rel)
        normalized = context.project_path(normalized_rel)
        if record.get("source_status", "active") == "active":
            if not original.exists():
                errors.append(f"original source is missing: {original_rel}")
            elif sha256_file(original) != record.get("original_sha256"):
                errors.append(f"original source checksum changed: {original_rel}")
        if not snapshot.exists():
            errors.append(f"immutable snapshot is missing: {snapshot_rel}")
        elif sha256_file(snapshot) != record.get("snapshot_sha256"):
            errors.append(f"immutable snapshot checksum changed: {snapshot_rel}")
        if not normalized.exists():
            errors.append(f"normalized derivative is missing: {normalized_rel}")
        elif sha256_file(normalized) != record.get("normalized_sha256"):
            errors.append(f"normalized derivative checksum changed: {normalized_rel}")
        source_map_rel = record.get("source_map_path")
        source_map_checksum = record.get("source_map_checksum")
        if source_map_rel is None or source_map_checksum is None:
            errors.append(f"source map is missing for normalized derivative: {normalized_rel}")
        else:
            source_map_errors = validate_relative_project_path(source_map_rel, "provenance.source_map_path")
            errors.extend(source_map_errors)
            if not source_map_errors:
                source_map = context.project_path(source_map_rel)
                if not source_map.is_file():
                    errors.append(f"source map is missing: {source_map_rel}")
                elif sha256_file(source_map) != source_map_checksum:
                    errors.append(f"source map checksum changed: {source_map_rel}")
    return errors


def get_or_create_entity_id(
    context: ProjectContext,
    namespace: str,
    external_key: str,
    display_name: str,
) -> str:
    if namespace not in STABLE_ID_NAMESPACES:
        raise ProjectOperationError(f"Unknown stable-ID namespace '{namespace}'")
    id_map = _load_id_map(context)
    records = id_map["namespaces"][namespace]
    for record in records:
        if record.get("external_key") == external_key:
            previous_name = record.get("display_name")
            if previous_name != display_name:
                aliases = record.setdefault("display_name_aliases", [])
                if previous_name and previous_name not in aliases:
                    aliases.append(previous_name)
                record["display_name"] = display_name
                write_json(context.workspace_path(ID_MAP_FILE), id_map)
            return record["id"]
    prefix = namespace.rstrip("s").replace("_", "-")
    entity_id = f"{prefix}-{uuid.uuid4().hex}"
    records.append({
        "id": entity_id,
        "external_key": external_key,
        "display_name": display_name,
        "display_name_aliases": [],
    })
    write_json(context.workspace_path(ID_MAP_FILE), id_map)
    return entity_id


def image_ready_reasons(
    context: ProjectContext,
    *,
    ignore_configured_image_ready: bool = False,
) -> List[str]:
    config = context.config
    locks = config.get("stage_locks", {})
    reasons: List[str] = []
    for gate in ("CANON_APPROVED", "STORY_LOCKED", "STORYBOARD_LOCKED"):
        if locks.get(gate) is not True:
            reasons.append(f"{gate} is not true")
    if config.get("image_generation_enabled") is not True:
        reasons.append("image_generation_enabled is false")
    continuity_approved = False
    for continuity_approval in context.workspace_path("approvals").glob("*.json"):
        try:
            approval = load_json(continuity_approval)
            if approval.get("project_id") != config.get("project_id"):
                continue
            if approval.get("artifact_type") != "continuity" or approval.get("status") != "approved":
                continue
            target_rel = approval.get("target_relative_path")
            if not isinstance(target_rel, str):
                continue
            target = context.project_path(target_rel)
            if target.is_file() and sha256_file(target) == approval.get("target_sha256"):
                continuity_approved = True
                break
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    if not continuity_approved:
        reasons.append("a valid continuity approval is missing")
    reasons.extend(provenance_errors(context))
    return reasons


def project_status(context: ProjectContext) -> Dict[str, Any]:
    configured_ready = context.config.get("stage_locks", {}).get("IMAGE_READY") is True
    reasons = image_ready_reasons(context)
    return {
        "project_id": context.config.get("project_id"),
        "title": context.config.get("title"),
        "project_root": str(context.project_root),
        "workspace_root": str(context.workspace_root),
        "source_roots": [project_relative(context.project_root, path) or "." for path in context.source_roots],
        "manga_studio_install_root": str(context.install_root),
        "workflow_phase": context.config.get("workflow_phase"),
        "operating_mode": context.config.get("operating_mode"),
        "stage_locks": context.config.get("stage_locks", {}),
        "image_generation_enabled": context.config.get("image_generation_enabled", False),
        "image_ready": configured_ready and not reasons,
        "image_ready_blocking_reasons": reasons,
    }
