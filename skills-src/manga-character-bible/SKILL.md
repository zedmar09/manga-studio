---
name: manga-character-bible
description: Build and maintain versioned character canon, arcs, relationships, voice constraints, and continuity facts without creating visual reference artwork.
metadata:
  namespace: manga-studio
  version: "3.3.0"
---

# Manga Character Bible

## Purpose

Maintain character-specific canon and writing guidance using persistent project-local IDs rather than names.

## Activation Conditions

Use when creating, extending, repairing, or auditing character definitions, arcs, relationships, or voice constraints.

## Compatible Operating Modes

`create_new`, `diagnose_existing`, `repair_existing`, `continue_existing`, `adapt_existing_to_manga`, and `continuity_audit`.

## Required Inputs

Active canon or canon proposal, source provenance for existing stories, stable character IDs, and the requested character scope.

## Optional Inputs

Approved diagnostics, story architecture, manuscript scenes, relationship maps, and user decisions.

## Project Discovery

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Use shared upward discovery. Stop if missing; never initialize or resolve characters against another story.

## Source Of Truth

Approved canon governs character facts. Source snapshots provide provenance. Approved decisions may resolve ambiguity. Visual reference images, when eventually approved, govern appearance only and cannot rewrite story canon.

## Owned Outputs

Versioned character records under `.manga-studio/canon/characters/` and character-related decision proposals.

## Procedure

1. Validate story provenance and load active canon.
2. Resolve each character through the stable ID map, preserving aliases after renames.
3. Separate static canon in `character.schema.json` from changing scene/timeline state in `character-state.schema.json`.
4. For each production character, record external goal, internal need, core fear, stakes, flaw, contradiction, moral limits, arc direction, voice principles, relationship drivers, known facts, and explicit unknowns.
5. Test whether choices remain understandable under pressure and whether body-language opportunities can replace exposition.
6. Keep visual identity textual and evidence-based; do not request or create art here.
7. Write a new version and diff; route canon adoption through approval.

## Required Schemas

`project.schema.json`, `stable-id-map.schema.json`, `character.schema.json`, `character-state.schema.json`, `relationship.schema.json`, `voice-guide.schema.json`, and provenance schemas.

## Next-Skill Handoff

Pass approved character records to story architecture, chapter/dialogue writing, consistency review, storyboard planning, or image-job planning.

## Approval Requirements

New or changed character canon requires user approval through `manga-canon-manager`.

## Failure Behavior

Stop on same-name ambiguity, cross-project IDs, unsupported evidence required for a claim, or conflicts with approved canon.

## Non-Destructive Constraints

Do not overwrite prior character versions, original sources, or approved visual references. Never generate or edit character art.

## Out Of Scope

World canon, prose implementation, panel composition, and character reference image generation.

## Representative Example

Example: two independent stories may each contain a character named Alex; each receives an unrelated stable ID and canon record.

## Acceptance Criteria

Character records are project-isolated, versioned, evidence-linked, motivation-complete, voice-aware, explicit about moral limits and changing state, and free of implicit visual-generation work.
