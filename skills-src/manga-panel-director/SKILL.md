---
name: manga-panel-director
description: Turn approved storyboard beats into structured panel plans with staging, camera, continuity, required elements, and dialogue-safe zones without creating artwork.
metadata:
  namespace: manga-studio
  version: "3.3.0"
---

# Manga Panel Director

## Purpose

Define panel-level visual intent precisely enough for later structured image jobs and deterministic page layout.

## Activation Conditions

Use when an approved storyboard needs panel plans, camera/staging revisions, or safe-zone definitions.

## Compatible Operating Modes

`adapt_existing_to_manga`, `continue_existing`, and `prepare_visual_production`.

## Required Inputs

Active approved storyboard, page beat, approved canon, continuity state, reading direction, page geometry, and stable entity IDs.

## Optional Inputs

Approved visual-reference metadata, dialogue draft, prior panel plans, and page-level composition constraints.

## Project Discovery

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Use shared discovery and stop if missing. Never initialize or infer the project from character names or sample pages.

## Source Of Truth

Approved storyboard governs beats and order; approved canon governs facts; continuity snapshots govern entering state; approved visual references eventually govern appearance.

## Owned Outputs

Versioned panel plans under `.manga-studio/storyboard/` and page specifications under `.manga-studio/pages/` before production.

## Procedure

1. Validate preproduction prerequisites and load the target page by stable ID.
2. Define exactly one dominant event with type, intensity, importance, action, emotional beat, shot size, camera angle/motion, action direction, transition, show-don't-tell cue, and entering/exiting continuity anchors.
3. Stage characters with readable silhouettes, expressions, eyelines, handedness, prop interaction, and motivated depth. Avoid repeating a shot unless repetition is an intentional rhythm device.
4. Define the rectangular art frame plus an optional non-self-intersecting `clip_polygon`, focus point, fit, z-index, inset/bleed state, border, and explicit overlap permission. Geometry must serve the event and reading flow.
5. Declare the intended source-image canvas and define dialogue-safe zones as normalized source-image boxes (`source_normalized`). Verify how each zone projects through cover/contain fit and focus before accepting the page placement. Keep critical faces, hands, props, action paths, and reveal information outside those zones.
6. List required and prohibited visual elements; prohibit embedded dialogue, captions, balloons, SFX, panel borders, page numbers, signatures, watermarks, and color in black-and-white panel artwork.
7. Check neighboring screen direction, eyelines, spatial anchors, state continuity, and the page's explicit reading sequence.
8. Save a versioned plan for consistency review.

## Required Schemas

`project.schema.json`, `page.schema.json`, `panel.schema.json`, `continuity-state.schema.json`, and stable/canon schemas.

## Next-Skill Handoff

Pass approved panel plans to `manga-consistency-manager`, then to `manga-image-job-builder` only when storyboard and image gates permit.

## Approval Requirements

Panel plans require storyboard approval; locking remains an explicit user action.

## Failure Behavior

Stop on missing storyboards, ambiguous entities, impossible geometry, continuity conflicts, or any request to render/edit a panel.

## Non-Destructive Constraints

Do not overwrite prior plans, alter authoritative story files, or create artwork. Safe zones are instructions, not image edits.

## Out Of Scope

Page-level beat allocation, image generation, lettering execution, and final composition.

## Representative Example

Example: define a close-up with a 1400x2200 source canvas and one normalized upper-left safe zone, then prove the page crop preserves that zone without embedding dialogue or assuming any sample cast.

## Acceptance Criteria

Each panel traces to an approved beat and nemu block, communicates one readable event through staging, has valid dynamic geometry and camera direction, preserves continuity, protects normalized lettering space after crop projection, and is ready for job construction without containing artwork.
