---
name: manga-world-bible
description: Build and maintain versioned world canon for locations, organizations, props, rules, cultures, and timelines without imposing genre-specific concepts.
metadata:
  namespace: manga-studio
  version: "3.3.0"
---

# Manga World Bible

## Purpose

Maintain only the world facts the story needs, using neutral extensible records rather than mandatory magic, school, guild, battle, or romance fields.

## Activation Conditions

Use for worldbuilding, location/organization/prop canon, rule systems, timeline structure, or world-continuity audits.

## Compatible Operating Modes

`create_new`, `diagnose_existing`, `repair_existing`, `continue_existing`, `adapt_existing_to_manga`, and `continuity_audit`.

## Required Inputs

Project configuration, active canon or source evidence, and stable IDs for affected entities.

## Optional Inputs

Story architecture, manuscript scenes, diagnostics, research supplied by the user, and unresolved world questions.

## Project Discovery

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Use shared discovery and stop if missing. Never initialize or import pilot locations, props, or rules.

## Source Of Truth

Approved canon is authoritative; source snapshots establish provenance; explicit decisions resolve unknowns. Production references may clarify appearance but not silently change world rules.

## Owned Outputs

Versioned records under `.manga-studio/canon/locations/`, `organizations/`, `props/`, `timeline/`, and other project-defined canon subdirectories.

## Procedure

1. Validate story provenance and load active canon.
2. Resolve entities through stable project-local IDs.
3. Record only relevant facts, constraints, spatial rules, scale relationships, persistent landmarks, prop operating states, state transitions, timeline links, and unknowns.
4. Check proposed additions against manuscript evidence and existing canon.
5. Write versioned records and diffs; route adoption through canon approval.

## Required Schemas

`project.schema.json`, `stable-id-map.schema.json`, `location.schema.json`, `prop.schema.json`, and `continuity-state.schema.json`.

## Next-Skill Handoff

Pass approved world canon to story architecture, writing, consistency management, storyboard direction, or continuity review.

## Approval Requirements

World facts and rule changes require explicit canon approval.

## Failure Behavior

Stop on conflicting approved facts, ambiguous entity identity, cross-story references, or unsupported assumptions. Record unknowns instead of filling them speculatively.

## Non-Destructive Constraints

Never overwrite source or prior canon, and never generate or edit location or prop artwork.

## Out Of Scope

Character arcs, chapter prose, panel rendering, and visual-reference production.

## Representative Example

Example: a realistic kitchen and a fictional orbital habitat use the same neutral location fields plus story-specific extensions in canon, with neither template forced on the other.

## Acceptance Criteria

World records are minimal, sufficient, stable-ID based, genre-neutral, versioned, consistent with approved evidence, and precise enough to support later location/prop reference jobs without inventing appearance.
