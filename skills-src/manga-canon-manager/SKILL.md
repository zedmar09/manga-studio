---
name: manga-canon-manager
description: Maintain versioned, approved story canon and persistent entity mappings for characters, locations, organizations, props, timeline events, plot threads, and setups/payoffs.
metadata:
  namespace: manga-studio
  version: "2.0.0"
---

# Manga Canon Manager

## Purpose

Turn source-supported or explicitly approved decisions into a portable canon without imposing genre-specific fields or relying on mutable names.

## Activation Conditions

Use when creating, reconciling, approving, or auditing canon and stable story entities.

## Compatible Operating Modes

All operating modes except purely mechanical `prepare_visual_production` work that does not alter canon.

## Required Inputs

A discoverable project, provenance, stable ID map, and the source evidence or explicit decision supporting each canon change.

## Optional Inputs

Diagnostics, revision decisions, existing canon versions, and unresolved continuity questions.

## Project Discovery

Use shared upward discovery. Stop if the project is missing; never initialize, fall back to pilot, or infer canon from sample names.

## Source Of Truth

Original evidence establishes provenance; explicit approved decisions may resolve ambiguity. The active approved canon version governs downstream story facts until superseded by another approved version.

## Owned Outputs

Versioned files under `.manga-studio/canon/`, canon decisions under `.manga-studio/decisions/`, and non-source entity entries in `source/id-map.json`.

## Procedure

1. Validate story provenance and load the active canon version.
2. Resolve entities by persistent ID, not display name or array position.
3. Record aliases when names change; require review for ambiguous matches.
4. Separate facts, constraints, unknowns, timeline events, plot threads, and setup/payoff links.
5. Write a new canon version and a diff against the active version.
6. Activate it only after approval; then update `active_canon_version` and relevant locks.

## Required Schemas

`project.schema.json`, `stable-id-map.schema.json`, `character.schema.json`, `location.schema.json`, `prop.schema.json`, and `continuity-state.schema.json`.

## Next-Skill Handoff

Pass the active canon version and stable IDs to story architecture, writing, consistency, storyboard, or continuity review as needed.

## Approval Requirements

Every canon adoption or supersession requires explicit user approval. `CANON_APPROVED` may be true only with an existing active canon version.

## Failure Behavior

Stop on conflicting approved facts, cross-project IDs, ambiguous entity matches, missing provenance, or a requested silent canon replacement.

## Non-Destructive Constraints

Never rewrite source evidence or prior canon versions. Never key identity solely by names, positions, or mutable content hashes.

## Out Of Scope

Prose rewriting, dialogue polishing, page planning, and artwork production.

## Representative Example

Example: a renamed location keeps its stable location ID and gains an alias; a same-named location in another story receives an unrelated project-local ID.

## Acceptance Criteria

Canon is versioned, evidence-linked, project-isolated, approval-backed, genre-neutral, and addressable through stable persistent IDs.
