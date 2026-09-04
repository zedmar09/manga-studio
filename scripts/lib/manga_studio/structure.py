from __future__ import annotations

import hashlib
import fnmatch
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .json_schema import validate_json_file
from .adapters import PARSER_COMPATIBILITY_VERSION
from .project import PROVENANCE_FILE, ProjectContext, ProjectOperationError, get_or_create_entity_id, sha256_file
from .validation import load_json, validate_relative_project_path, write_json


PARSER_NAME = "manga_studio_text_structure"
PARSER_VERSION = PARSER_COMPATIBILITY_VERSION
MANUAL_BOUNDARIES_FILE = "source/manual-boundaries.json"
STRUCTURE_INDEX_FILE = "source/structure.json"

_MARKDOWN_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_EXPLICIT_CHAPTER = re.compile(r"^(?:chapter|chap(?:ter)?\.?|part|book)\s+(?:\d+|[ivxlcdm]+|[a-z])(?:\s*[:.-]\s*|\s+)?(.*)$", re.I)
_EXPLICIT_SCENE = re.compile(r"^scene\s+(?:\d+|[ivxlcdm]+|[a-z])(?:\s*[:.-]\s*|\s+)?(.*)$", re.I)
_COMMENT_BOUNDARY = re.compile(
    r'^\s*<!--\s*manga-studio:(chapter|scene)(?:\s+title="([^"]+)")?\s*-->\s*$', re.I
)
_PLAIN_BOUNDARY = re.compile(r"^\s*\[(chapter|scene)(?:\s*:\s*([^\]]+))?\]\s*$", re.I)
_SPEAKER_DIALOGUE = re.compile(r"^[A-Z][A-Z0-9 _'-]{0,40}:\s+\S")


def _stable_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _line_records(text: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    offset = 0
    for number, raw in enumerate(text.splitlines(keepends=True), start=1):
        encoded = raw.encode("utf-8")
        records.append({
            "number": number,
            "text": raw.rstrip("\r\n"),
            "raw": raw,
            "byte_start": offset,
            "byte_end": offset + len(encoded),
        })
        offset += len(encoded)
    if not records and text == "":
        return []
    if text and not text.endswith(("\n", "\r")):
        return records
    return records


def _manual_boundaries(context: ProjectContext, document_id: str) -> Dict[int, List[Dict[str, Any]]]:
    path = context.workspace_path(MANUAL_BOUNDARIES_FILE)
    if not path.is_file():
        return {}
    data = load_json(path)
    if data.get("project_id") != context.config.get("project_id"):
        raise ProjectOperationError("manual boundaries project_id does not match project.json")
    result: Dict[int, List[Dict[str, Any]]] = {}
    for item in data.get("boundaries", []):
        if item.get("document_id") != document_id:
            continue
        line = item.get("line")
        if not isinstance(line, int) or line < 1:
            raise ProjectOperationError("manual boundary line must be a positive integer")
        if item.get("kind") not in {"chapter", "scene"}:
            raise ProjectOperationError("manual boundary kind must be chapter or scene")
        result.setdefault(line, []).append(item)
    return result


def _boundary_for_line(
    line: Dict[str, Any],
    *,
    mode: str,
    heading_levels: set[int],
    manual: Dict[int, List[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    manual_items = manual.get(line["number"], [])
    if manual_items:
        if len(manual_items) > 1:
            return {
                "kind": manual_items[0]["kind"],
                "title": manual_items[0].get("title") or f"Untitled {manual_items[0]['kind']}",
                "origin": "manual",
                "ambiguity_status": "review_required",
                "ambiguity_reason": "multiple manual boundaries target the same line",
            }
        item = manual_items[0]
        return {
            "kind": item["kind"],
            "title": item.get("title") or f"Untitled {item['kind']}",
            "origin": "manual",
            "ambiguity_status": "clear",
            "ambiguity_reason": None,
        }

    for pattern, origin in ((_COMMENT_BOUNDARY, "markup"), (_PLAIN_BOUNDARY, "markup")):
        match = pattern.match(line["text"])
        if match:
            kind = match.group(1).lower()
            return {
                "kind": kind,
                "title": (match.group(2) or f"Untitled {kind}").strip(),
                "origin": origin,
                "ambiguity_status": "clear",
                "ambiguity_reason": None,
            }

    if mode == "manual":
        return None
    heading = _MARKDOWN_HEADING.match(line["text"])
    if heading:
        level = len(heading.group(1))
        title = heading.group(2).strip()
        chapter_match = _EXPLICIT_CHAPTER.match(title)
        scene_match = _EXPLICIT_SCENE.match(title)
        if chapter_match:
            if mode in {"single_document", "file_per_chapter"}:
                return None
            return {
                "kind": "chapter",
                "title": title,
                "origin": "heading",
                "heading_level": level,
                "ambiguity_status": "clear",
                "ambiguity_reason": None,
            }
        if scene_match:
            return {
                "kind": "scene",
                "title": title,
                "origin": "heading",
                "heading_level": level,
                "ambiguity_status": "clear",
                "ambiguity_reason": None,
            }
        if mode in {"auto", "headings"} and level in heading_levels:
            return {
                "kind": "chapter" if level == min(heading_levels or {1}) else "scene",
                "title": title,
                "origin": "heading",
                "heading_level": level,
                "ambiguity_status": "review_required",
                "ambiguity_reason": "generic heading requires chapter/scene classification review",
            }
    if line["text"].strip() in {"***", "---"}:
        return {
            "kind": "scene",
            "title": "Scene break",
            "origin": "separator",
            "ambiguity_status": "review_required",
            "ambiguity_reason": "separator may be thematic rather than structural",
        }
    return None


def _is_dialogue(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    return all(
        (line.startswith(('"', "'", "\u201c", "\u2018", "\u2014")) and len(line) > 1)
        or bool(_SPEAKER_DIALOGUE.match(line))
        for line in lines
    )


def _parse_document(
    context: ProjectContext,
    record: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    document_id = record["document_id"]
    normalized_rel = record["normalized_path"]
    normalized = context.project_path(normalized_rel)
    if not normalized.is_file():
        raise ProjectOperationError(f"normalized derivative is missing: {normalized_rel}")
    if sha256_file(normalized) != record.get("normalized_sha256"):
        raise ProjectOperationError(f"normalized derivative checksum changed: {normalized_rel}")
    text = normalized.read_text(encoding="utf-8")
    lines = _line_records(text)
    strategy = context.config.get("chapter_detection_strategy", {})
    mode = strategy.get("mode", "auto")
    if mode == "auto":
        filename = Path(record["original_path"]).name.lower()
        if any(fnmatch.fnmatch(filename, pattern.lower()) for pattern in strategy.get("filename_patterns", [])):
            mode = "file_per_chapter"
    heading_levels = set(strategy.get("heading_levels", [1, 2]))
    manual = _manual_boundaries(context, document_id)
    invalid_manual_lines = sorted(line for line in manual if line > len(lines))
    if invalid_manual_lines:
        raise ProjectOperationError(
            f"manual boundary line is outside document {document_id}: {', '.join(str(line) for line in invalid_manual_lines)}"
        )
    boundary_profile_checksum = _stable_fingerprint(json.dumps(manual, sort_keys=True, separators=(",", ":")))

    boundaries: List[Dict[str, Any]] = []
    for line in lines:
        boundary = _boundary_for_line(
            line,
            mode=mode,
            heading_levels=heading_levels,
            manual=manual,
        )
        if boundary:
            boundary.update({
                "line_start": line["number"],
                "line_end": line["number"],
                "byte_start": line["byte_start"],
                "byte_end": line["byte_end"],
            })
            boundaries.append(boundary)

    has_chapter = any(item["kind"] == "chapter" for item in boundaries)
    if mode in {"single_document", "file_per_chapter"} or not has_chapter:
        title = Path(record["original_path"]).stem
        first_heading = next(
            (_MARKDOWN_HEADING.match(line["text"]) for line in lines if _MARKDOWN_HEADING.match(line["text"])),
            None,
        )
        if first_heading:
            title = first_heading.group(2).strip()
        boundaries.insert(0, {
            "kind": "chapter",
            "title": title,
            "origin": "implicit_file_chapter" if mode == "file_per_chapter" else "implicit_chapterless",
            "ambiguity_status": "clear",
            "ambiguity_reason": None,
            "line_start": 1,
            "line_end": 1,
            "byte_start": 0,
            "byte_end": 0,
        })
    else:
        first_chapter_byte = min(
            item["byte_start"] for item in boundaries if item["kind"] == "chapter"
        )
        has_leading_content = any(
            line["byte_start"] < first_chapter_byte and line["text"].strip()
            for line in lines
        )
        if has_leading_content:
            boundaries.insert(0, {
                "kind": "chapter",
                "title": "Front Matter",
                "origin": "implicit_leading_content",
                "ambiguity_status": "review_required",
                "ambiguity_reason": "content before the first explicit chapter requires classification review",
                "line_start": 1,
                "line_end": 1,
                "byte_start": 0,
                "byte_end": 0,
            })

    boundaries.sort(key=lambda item: (item["byte_start"], 0 if item["kind"] == "chapter" else 1))
    chapters: List[Dict[str, Any]] = []
    scenes: List[Dict[str, Any]] = []
    current_chapter: Optional[Dict[str, Any]] = None
    current_scene: Optional[Dict[str, Any]] = None
    for index, boundary in enumerate(boundaries):
        external_key = f"{document_id}:{boundary['kind']}:{boundary['byte_start']}:{index}"
        namespace = "chapters" if boundary["kind"] == "chapter" else "scenes"
        entity_id = get_or_create_entity_id(context, namespace, external_key, boundary["title"])
        boundary[f"{boundary['kind']}_id"] = entity_id
        if boundary["kind"] == "chapter":
            current_chapter = {
                "chapter_id": entity_id,
                "display_title": boundary["title"],
                "document_id": document_id,
                "source_order": len(chapters) + 1,
                "boundary": dict(boundary),
            }
            chapters.append(current_chapter)
            current_scene = None
        else:
            if current_chapter is None:
                raise ProjectOperationError(f"scene boundary appears before chapter in {normalized_rel}")
            current_scene = {
                "scene_id": entity_id,
                "display_title": boundary["title"],
                "document_id": document_id,
                "chapter_id": current_chapter["chapter_id"],
                "source_order": len(scenes) + 1,
                "boundary": dict(boundary),
            }
            scenes.append(current_scene)

    units: List[Dict[str, Any]] = []
    heading_path: List[str] = []
    current_chapter = None
    current_scene = None
    boundary_by_line: Dict[int, List[Dict[str, Any]]] = {}
    for boundary in boundaries:
        boundary_by_line.setdefault(boundary["line_start"], []).append(boundary)

    paragraph_lines: List[Dict[str, Any]] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines or current_chapter is None:
            paragraph_lines = []
            return
        paragraph_text = "".join(item["raw"] for item in paragraph_lines)
        start = paragraph_lines[0]
        end = paragraph_lines[-1]
        external_key = f"{document_id}:source-unit:{start['byte_start']}:{end['byte_end']}"
        unit_id = get_or_create_entity_id(context, "source_units", external_key, f"Source unit {len(units) + 1}")
        units.append({
            "source_unit_id": unit_id,
            "document_id": document_id,
            "chapter_id": current_chapter["chapter_id"],
            "scene_id": current_scene["scene_id"] if current_scene else None,
            "source_relative_path": record["original_path"],
            "heading_path": list(heading_path),
            "source_order": len(units) + 1,
            "unit_type": "dialogue" if _is_dialogue(paragraph_text) else "paragraph",
            "line_start": start["number"],
            "line_end": end["number"],
            "byte_start": start["byte_start"],
            "byte_end": end["byte_end"],
            "content_fingerprint": _stable_fingerprint(paragraph_text),
            "parser_version": PARSER_VERSION,
            "ambiguity_status": "clear",
        })
        paragraph_lines = []

    chapter_by_id = {item["chapter_id"]: item for item in chapters}
    scene_by_id = {item["scene_id"]: item for item in scenes}
    for line in lines:
        line_boundaries = boundary_by_line.get(line["number"], [])
        if line_boundaries:
            flush_paragraph()
            consumes_line = False
            for boundary in line_boundaries:
                if boundary["kind"] == "chapter":
                    current_chapter = chapter_by_id[boundary["chapter_id"]]
                    current_scene = None
                    heading_path = [boundary["title"]]
                else:
                    current_scene = scene_by_id[boundary["scene_id"]]
                    heading_path = [current_chapter["display_title"], boundary["title"]] if current_chapter else [boundary["title"]]
                if not boundary["origin"].startswith("implicit_"):
                    consumes_line = True
            if consumes_line:
                continue
        heading = _MARKDOWN_HEADING.match(line["text"])
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            heading_path = heading_path[: max(0, level - 1)] + [heading.group(2).strip()]
            continue
        if not line["text"].strip():
            flush_paragraph()
        else:
            paragraph_lines.append(line)
    flush_paragraph()

    ambiguities = [
        {"kind": item["kind"], "title": item["title"], "line": item["line_start"], "reason": item["ambiguity_reason"]}
        for item in boundaries
        if item["ambiguity_status"] == "review_required"
    ]
    source_map = {
        "schema_version": "3.0.0",
        "project_id": context.config["project_id"],
        "document_id": document_id,
        "source_relative_path": record["original_path"],
        "normalized_path": normalized_rel,
        "normalized_sha256": record["normalized_sha256"],
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "boundary_profile_checksum": boundary_profile_checksum,
        "structure_status": "review_required" if ambiguities else "parsed",
        "ambiguities": ambiguities,
        "chapters": chapters,
        "scenes": scenes,
        "source_units": units,
    }
    document = {
        "schema_version": "3.0.0",
        "project_id": context.config["project_id"],
        "document_id": document_id,
        "display_title": Path(record["original_path"]).stem,
        "aliases": [],
        "source_relative_path": record["original_path"],
        "usage_role": record["usage_role"],
        "classification": record["classification"],
        "classification_status": record["classification_status"],
        "source_status": record["source_status"],
        "structure_status": source_map["structure_status"],
        "provenance_original_sha256": record["original_sha256"],
        "source_map_path": None,
        "source_map_checksum": None,
    }
    return source_map, document


def structure_sources(context: ProjectContext) -> Dict[str, Any]:
    provenance_path = context.workspace_path(PROVENANCE_FILE)
    if not provenance_path.is_file():
        raise ProjectOperationError("source provenance is required before structure parsing")
    provenance = load_json(provenance_path)
    active_records = [item for item in provenance.get("records", []) if item.get("source_status") == "active"]
    documents: List[Dict[str, Any]] = []
    for record in active_records:
        source_map, document = _parse_document(context, record)
        map_rel = (
            f".manga-studio/source/maps/{record['document_id']}/"
            f"{record['normalized_sha256']}-{PARSER_NAME}-v{PARSER_VERSION}-"
            f"boundaries-{source_map['boundary_profile_checksum'][:16]}.json"
        )
        map_path = context.project_path(map_rel)
        encoded = (json.dumps(source_map, indent=2) + "\n").encode("utf-8")
        expected_checksum = hashlib.sha256(encoded).hexdigest()
        if map_path.exists():
            if sha256_file(map_path) != expected_checksum:
                raise ProjectOperationError(f"source map was modified; refusing to overwrite: {map_rel}")
        else:
            map_path.parent.mkdir(parents=True, exist_ok=True)
            map_path.write_bytes(encoded)
        record["parser_version"] = PARSER_VERSION
        record["source_map_path"] = map_rel
        record["source_map_checksum"] = expected_checksum
        document["source_map_path"] = map_rel
        document["source_map_checksum"] = expected_checksum
        document_rel = f".manga-studio/source/documents/{record['document_id']}.json"
        write_json(context.project_path(document_rel), document)
        documents.append({
            "document_id": record["document_id"],
            "source_relative_path": record["original_path"],
            "source_map_path": map_rel,
            "source_map_checksum": expected_checksum,
            "structure_status": source_map["structure_status"],
            "chapter_ids": [item["chapter_id"] for item in source_map["chapters"]],
            "scene_ids": [item["scene_id"] for item in source_map["scenes"]],
            "source_unit_ids": [item["source_unit_id"] for item in source_map["source_units"]],
        })
    write_json(provenance_path, provenance)
    index = {
        "schema_version": "3.0.0",
        "project_id": context.config["project_id"],
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "documents": documents,
    }
    write_json(context.workspace_path(STRUCTURE_INDEX_FILE), index)
    return index


def validate_source_maps(context: ProjectContext) -> List[str]:
    errors: List[str] = []
    provenance_path = context.workspace_path(PROVENANCE_FILE)
    if not provenance_path.is_file():
        return ["source provenance is missing"]
    provenance = load_json(provenance_path)
    schema = context.install_root / "schemas" / "source-map.schema.json"
    seen_ids: set[str] = set()
    for record in provenance.get("records", []):
        if record.get("source_status") != "active":
            continue
        map_rel = record.get("source_map_path")
        path_errors = validate_relative_project_path(map_rel, "source_map_path")
        errors.extend(path_errors)
        if path_errors:
            continue
        map_path = context.project_path(map_rel)
        if not map_path.is_file():
            errors.append(f"source map is missing: {map_rel}")
            continue
        if sha256_file(map_path) != record.get("source_map_checksum"):
            errors.append(f"source map checksum changed: {map_rel}")
            continue
        errors.extend(f"{map_rel}: {message}" for message in validate_json_file(map_path, schema))
        data = load_json(map_path)
        if data.get("project_id") != context.config.get("project_id"):
            errors.append(f"{map_rel}: project_id does not match project.json")
        normalized = context.project_path(record["normalized_path"])
        byte_length = len(normalized.read_bytes()) if normalized.is_file() else 0
        for collection, id_field in (("chapters", "chapter_id"), ("scenes", "scene_id"), ("source_units", "source_unit_id")):
            for item in data.get(collection, []):
                stable_id = item.get(id_field)
                if stable_id in seen_ids:
                    errors.append(f"duplicate stable structure ID: {stable_id}")
                if stable_id:
                    seen_ids.add(stable_id)
                start = item.get("byte_start", item.get("boundary", {}).get("byte_start"))
                end = item.get("byte_end", item.get("boundary", {}).get("byte_end"))
                if isinstance(start, int) and isinstance(end, int) and not (0 <= start <= end <= byte_length):
                    errors.append(f"{map_rel}: invalid byte range for {stable_id}")
        if data.get("structure_status") == "review_required":
            errors.append(f"{map_rel}: ambiguous boundaries require review")
    return errors


def show_structure(context: ProjectContext) -> Dict[str, Any]:
    path = context.workspace_path(STRUCTURE_INDEX_FILE)
    if not path.is_file():
        raise ProjectOperationError("structure index is missing; run the structure command first")
    return load_json(path)
