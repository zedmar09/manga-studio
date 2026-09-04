---
name: manga-canon-manager
description: Maintain versioned, approved story canon and persistent entity mappings for characters, locations, organizations, props, timeline events, plot threads, and setups/payoffs.
metadata:
  namespace: manga-studio
  version: "3.3.0"
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

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Use shared upward discovery. Stop if the project is missing; never initialize, fall back to pilot, or infer canon from sample names.

## Source Of Truth

Original evidence establishes provenance; explicit approved decisions may resolve ambiguity. The active approved canon version governs downstream story facts until superseded by another approved version.

## Owned Outputs

Versioned story-canon files under `.manga-studio/canon/`, canon decisions under `.manga-studio/decisions/`, and non-source entity entries in `source/id-map.json`. Visual references remain separate production artifacts.

## Procedure

1. Validate story provenance and load the active canon version.
2. Resolve entities by persistent ID, not display name or array position.
3. Record aliases when names change; require review for ambiguous matches.
4. Separate facts, constraints, unknowns, timeline events, plot threads, and setup/payoff links. For characters, keep stable dramatic canon such as desire, fear, contradiction, and moral limits distinct from changing scene state.
5. Write a new canon version and a diff against the active version.
6. After a separate approval exists, present the explicit active-version and lock commands; never mutate approval or lock state as part of canon creation.

## Required Schemas

`canon.schema.json`, `character.schema.json`, `timeline-event.schema.json`, `relationship.schema.json`, `plot-thread.schema.json`, `setup-payoff.schema.json`, `character-state.schema.json`, `voice-guide.schema.json`, provenance, and stable-ID schemas.

## Next-Skill Handoff

Pass the active canon version and stable IDs to story architecture, writing, consistency, storyboard, or continuity review as needed.

## Approval Requirements

Every fact requires source evidence or an explicit approved decision. Canon adoption or supersession requires a separate hash-bound approval; this skill may not approve or lock its own output.

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
