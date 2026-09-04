---
name: manga-chapter-writer
description: Draft or revise versioned story manuscript units from approved architecture and canon, supporting chapterless stories and preserving author voice and source immutability.
metadata:
  namespace: manga-studio
  version: "3.0.0"
---

# Manga Chapter Writer

## Purpose

Write the next approved manuscript unit, whether it is a chapter, scene, episode, or short-story revision, without assuming a fixed chapter model.

## Activation Conditions

Use when the user asks for manuscript drafting or implementation of an approved revision or continuation plan.

## Compatible Operating Modes

`create_new`, `repair_existing`, `continue_existing`, and `adapt_existing_to_manga`.

## Required Inputs

Approved architecture or revision scope, active canon, stable IDs, author-voice rules, and the preceding active manuscript context when continuing.

## Optional Inputs

Source snapshots, target length, scene constraints, dialogue draft, and unresolved plot threads.

## Project Discovery

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Use shared discovery and stop if missing. Never initialize or assume a pilot chapter.

## Source Of Truth

Active approved canon and user-approved architecture constrain content. Original source and prior manuscript versions remain immutable. The newly drafted version is provisional until approved.

## Owned Outputs

Versioned manuscript files and metadata under `.manga-studio/manuscript/`.

## Procedure

1. Validate story profile and required approvals.
2. Resolve the target unit and related entities through stable IDs.
3. Load only the source, canon, architecture, and preceding context required for the draft.
4. Draft in the configured output language and preserve author voice.
5. Check causality, unresolved threads, canon, and neighboring scene continuity.
6. Save a new version and deterministic diff; request approval before activation.

## Required Schemas

`project.schema.json`, `stable-id-map.schema.json`, provenance schemas, and relevant canon schemas.

## Next-Skill Handoff

Pass the manuscript draft to `manga-dialogue-writer` for focused dialogue work or `manga-consistency-manager` for validation before approval.

## Approval Requirements

User approval is required before setting `active_manuscript_version`, `MANUSCRIPT_APPROVED`, or `STORY_LOCKED`.

## Failure Behavior

Stop on missing approved scope, contradictory canon, unresolved target identity, or an instruction to overwrite source.

## Non-Destructive Constraints

Create new manuscript versions only. Preserve original files byte-for-byte and do not generate visual assets.

## Out Of Scope

Canon approval, final dialogue-only polish outside the requested scope, storyboarding, and image jobs.

## Representative Example

Example: continue a chapter-per-file novel with a new versioned scene while retaining unresolved plot-thread IDs and leaving every original chapter file unchanged.

## Acceptance Criteria

The draft fulfills approved structure, preserves voice, respects canon, uses stable references, and remains separate from authoritative source and active versions until approved.
