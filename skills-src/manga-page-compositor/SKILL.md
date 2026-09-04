---
name: manga-page-compositor
description: Deterministically place only approved panel images into planned page frames and produce versioned composed pages without retouching or regenerating artwork.
metadata:
  namespace: manga-studio
  version: "2.0.0"
---

# Manga Page Compositor

## Purpose

Assemble approved panel files into page geometry, clips, and borders while keeping the visual artwork byte-identical and externally linked.

## Activation Conditions

Use only after IMAGE_READY and when every panel path references an existing approved image.

## Compatible Operating Modes

`prepare_visual_production` during the composition stage.

## Required Inputs

Approved page specification, valid frames, approved panel files under `.manga-studio/handoff/approved/`, and passing production dependencies.

## Optional Inputs

Explicit output path and a prior composed-page version for comparison.

## Project Discovery

Use shared discovery and stop if missing. Never initialize, use generated/correction files directly, or fall back to a sample page.

## Source Of Truth

Approved page plan governs geometry; approved panel files govern visual content; reading direction governs order; composition output does not become canon.

## Owned Outputs

Versioned unlettered composed SVG pages under `.manga-studio/pages/`.

## Procedure

1. Run production validation and verify IMAGE_READY.
2. Confirm every `art_path` is relative, exists, and is under `.manga-studio/handoff/approved/`.
3. Run `scripts/compose_page.py <page-spec> --project <project-root>`.
4. Verify frames, clipping, borders, dimensions, reading order, and unchanged source image checksums.
5. Record the composed-page version and hand off for lettering.

## Required Schemas

`project.schema.json`, `page.schema.json`, `panel.schema.json`, and approved-image review records.

## Next-Skill Handoff

Pass the composed page to `manga-lettering`; route panel defects to `manga-continuity-reviewer` and correction-job planning.

## Approval Requirements

All panel art must be explicitly approved. Composition review is required before final lettering/export.

## Failure Behavior

Stop on unmet gates, null/missing art paths, raw generated/correction paths, invalid geometry, or checksum changes to approved images.

## Non-Destructive Constraints

Never retouch, repaint, regenerate, flatten text into, or overwrite panel artwork. Placement and non-destructive clipping are allowed.

## Out Of Scope

Artwork generation/editing, panel direction, dialogue writing, and final visual approval.

## Representative Example

Example: place four approved monochrome panels into a page SVG with planned borders while retaining linked source files unchanged.

## Acceptance Criteria

Only approved images are used, composition matches page geometry, image checksums are unchanged, output is versioned, and lettering remains separate.
