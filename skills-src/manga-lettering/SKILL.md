---
name: manga-lettering
description: Prepare and apply versioned dialogue, caption, thought, and balloon geometry to composed manga pages after approved production dependencies exist, without changing artwork.
metadata:
  namespace: manga-studio
  version: "2.0.0"
---

# Manga Lettering

## Purpose

Turn approved page text and safe-zone data into deterministic lettering layers after panel art has been externally generated, reviewed, approved, and composed.

## Activation Conditions

Use only when the production gate passes, a composed page exists, and page text is approved.

## Compatible Operating Modes

`prepare_visual_production` during the post-approval production stage.

## Required Inputs

Discoverable project, `IMAGE_READY`, approved panel dependencies, composed page SVG, approved page specification, and dialogue-safe zones.

## Optional Inputs

Typography settings, localization variants, balloon-tail coordinates, and prior lettering version.

## Project Discovery

Use shared discovery and stop if missing. Never initialize or resolve a page from the pilot implicitly.

## Source Of Truth

Approved page text governs words; the approved storyboard/page plan governs association and order; composed-page geometry and safe zones govern placement.

## Owned Outputs

Versioned lettering layers and lettered page SVG files under `.manga-studio/lettering/`.

## Procedure

1. Run production validation and confirm approved dependencies.
2. Verify each lettering item targets a real panel and fits an approved safe zone.
3. Use `scripts/add_lettering.py <page-spec> --project <project-root>` for deterministic placement.
4. Check reading order, speaker attribution, clipping, overflow, and page geometry.
5. Save a new lettering version; route visual/content issues to the owning skill.

## Required Schemas

`project.schema.json`, `page.schema.json`, `panel.schema.json`, and relevant review records.

## Next-Skill Handoff

Pass the lettered page to `manga-continuity-reviewer` for final page review and then export when approved.

## Approval Requirements

Page text and production inputs must already be approved. The lettered page requires review before export.

## Failure Behavior

Stop if IMAGE_READY is false, composed input or approved panel dependencies are missing, text is unapproved, or geometry is invalid.

## Non-Destructive Constraints

Add a separate vector lettering layer only. Never paint text into, retouch, crop destructively, or overwrite approved artwork.

## Out Of Scope

Dialogue rewriting beyond approved corrections, image generation/editing, panel approval, and page layout planning.

## Representative Example

Example: place approved speech and caption text in two safe zones on a composed page while leaving every linked panel image unchanged.

## Acceptance Criteria

Lettering is readable, correctly ordered, traceable to approved text, contained by page geometry, versioned, and separable from artwork.
