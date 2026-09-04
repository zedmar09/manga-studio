---
name: manga-source-ingestor
description: Inventory, classify, snapshot, normalize, and record provenance for existing story sources using portable Manga Studio adapters without changing originals.
metadata:
  namespace: manga-studio
  version: "3.0.0"
---

# Manga Source Ingestor

## Purpose

Build a reviewable source inventory, immutable import record, and parser-versioned source map for arbitrary story layouts. Plain text and Markdown are deterministic core adapters; unsupported files are preserved and reported.

## Activation Conditions

Use when an initialized project needs source discovery, classification review, snapshot import, or import repair.

## Compatible Operating Modes

`import_existing`, `diagnose_existing`, `repair_existing`, `continue_existing`, `adapt_existing_to_manga`, and `continuity_audit`.

## Required Inputs

A discoverable project and configured source roots, inclusion patterns, and exclusion patterns.

## Optional Inputs

User-approved classifications with an explicit usage role, manual chapter or scene boundaries, custom source roots, and future format adapters.

## Project Discovery

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Run `manga_studio.py discover --project <path>`. Stop with its actionable error if no project exists; this specialist must never initialize or fall back to the pilot.

## Source Of Truth

Original bytes and checksums are provenance authority. The user-reviewed inventory governs classification. Snapshots are immutable evidence; normalized derivatives are disposable inputs, not source replacements.

## Owned Outputs

`.manga-studio/source/inventory.json`, source-document and stable-ID records, immutable snapshots, versioned normalized derivatives, parser-versioned source maps, the structure index, and provenance.

## Procedure

1. Run `manga_studio.py inventory --project <project-root>` before import.
2. Review every suggested classification; set `classification_status` to `approved`, `corrected`, or `rejected` and select an explicit usage role. Suggested, unknown, ambiguous, rejected, and excluded records cannot import.
3. Use only `primary_manuscript`, `supplementary_manuscript`, `outline`, `author_notes`, `canon_reference`, `research`, or `excluded` as usage roles.
4. Report unsupported formats with their recorded message and leave them untouched.
5. Run `manga_studio.py import --project <project-root>`.
6. Run `structure`; resolve every review-required boundary with an approved manual boundary before source lock.
7. Run `validate-source-map` and story-profile validation. Compare original, snapshot, normalized, and source-map checksums with provenance.

## Required Schemas

`project.schema.json`, `source-inventory.schema.json`, `provenance.schema.json`, `stable-id-map.schema.json`, `source-document.schema.json`, and `source-map.schema.json`.

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
