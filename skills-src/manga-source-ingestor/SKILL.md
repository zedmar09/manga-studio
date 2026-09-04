---
name: manga-source-ingestor
description: Inventory, classify, snapshot, normalize, and record provenance for existing story sources using portable Manga Studio adapters without changing originals.
metadata:
  namespace: manga-studio
  version: "2.0.0"
---

# Manga Source Ingestor

## Purpose

Build a reviewable source inventory and immutable import record for arbitrary story layouts. Plain text and Markdown are deterministic core adapters; unsupported files are preserved and reported.

## Activation Conditions

Use when an initialized project needs source discovery, classification review, snapshot import, or import repair.

## Compatible Operating Modes

`import_existing`, `diagnose_existing`, `repair_existing`, `continue_existing`, `adapt_existing_to_manga`, and `continuity_audit`.

## Required Inputs

A discoverable project and configured source roots, inclusion patterns, and exclusion patterns.

## Optional Inputs

User-approved classification corrections, custom source roots, and future format adapters.

## Project Discovery

Run `manga_studio.py discover --project <path>`. Stop with its actionable error if no project exists; this specialist must never initialize or fall back to the pilot.

## Source Of Truth

Original bytes and checksums are provenance authority. The user-reviewed inventory governs classification. Snapshots are immutable evidence; normalized derivatives are disposable inputs, not source replacements.

## Owned Outputs

`.manga-studio/source/inventory.json`, `source/id-map.json` source-document entries, `source/snapshots/`, `source/normalized/`, and `source/provenance.json`.

## Procedure

1. Run `manga_studio.py inventory --project <project-root>` before import.
2. Review every `suggested` classification; do not assume text-like means manuscript.
3. Correct classification and mark it approved, corrected, or rejected when the user decides.
4. Report unsupported formats with their recorded message and leave them untouched.
5. Run `manga_studio.py import --project <project-root>`.
6. Run story-profile validation and compare original checksums with provenance.

## Required Schemas

`project.schema.json`, `source-inventory.schema.json`, `provenance.schema.json`, and `stable-id-map.schema.json`.

## Next-Skill Handoff

Pass inventory paths, immutable snapshot provenance, classifications, unsupported-format blockers, and stable document IDs to `manga-story-diagnostician` or `manga-canon-manager`.

## Approval Requirements

Classification corrections require user review. Locking the source set requires explicit approval and a clean provenance check.

## Failure Behavior

Stop if source content changes after inventory, a snapshot checksum differs, a path escapes the story root, decoding fails, or an ID match is ambiguous.

## Non-Destructive Constraints

Never write to, rename, move, delete, or normalize in place any original source file. Store paths relative to `project_root`.

## Out Of Scope

Story diagnosis, canon decisions, prose revision, proprietary document parsing, and artwork handling.

## Representative Example

Example: classify `chapters/01.md` as manuscript, `notes/ideas.txt` as notes, and `map.pdf` as unsupported while preserving all three.

## Acceptance Criteria

Every candidate is inventoried once, supported imports have byte-identical snapshots and separate normalized files, unsupported inputs remain intact, and persistent IDs survive safe file moves.
