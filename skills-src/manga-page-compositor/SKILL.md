---
name: manga-page-compositor
description: Deterministically place only approved panel images into planned page frames and produce versioned composed pages without retouching or regenerating artwork.
metadata:
  namespace: manga-studio
  version: "3.3.0"
---

# Manga Page Compositor

## Purpose

Assemble approved panel files into page geometry, clips, and borders while keeping the visual artwork byte-identical and externally linked.

## Activation Conditions

Use only after IMAGE_READY and when every panel path references an existing approved image.

## Compatible Operating Modes

`prepare_visual_production` during the composition stage.

## Required Inputs

Approved page specification, valid frames and clip polygons, source canvases and normalized safe zones, hash-matching approved generated-image visual reviews, approved panel files under `.manga-studio/handoff/approved/`, and passing production dependencies.

## Optional Inputs

Explicit output path and a prior composed-page version for comparison.

## Project Discovery

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Use shared discovery and stop if missing. Never initialize, use generated/correction files directly, or fall back to a sample page.

## Source Of Truth

Approved page plan governs geometry; approved panel files govern visual content; reading direction governs order; composition output does not become canon.

## Owned Outputs

Versioned unlettered composed SVG pages under `.manga-studio/pages/`.

## Procedure

1. Run production validation and verify IMAGE_READY.
2. Confirm every `art_path` is relative, exists, is under `.manga-studio/handoff/approved/`, and matches the SHA-256 captured by an approved intake and human visual-review chain for its source job.
3. Validate polygons, permitted overlaps, z-index order, bleed/inset intent, focus points, image fit, gutters, and reading sequence. Project each normalized source safe zone through the exact cover/contain/focus transform and reject cropped lettering space.
4. Run the shared launcher command `compose-page <page-spec> --project <project-root>` to create the next versioned SVG. Never reuse an existing output path.
5. Verify frames, non-destructive polygon clipping, borders, dimensions, reading flow, and unchanged source image checksums.
6. For print/both output, run `preflight-print` and block print production until its current hash-bound review is approved. The repository currently exports SVG page packages; any printer-required PDF/raster conversion remains an explicit downstream step unless a validated renderer is configured.
7. Record the composed-page version and hand off for lettering.

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

Example: place four approved monochrome panels into a suspense layout with diagonal clips and one dominant payoff panel while retaining linked source files unchanged.

## Acceptance Criteria

Only technically inspected and human-approved images are used, normalized zones survive placement, irregular geometry and z-order match the plan, image checksums are unchanged, output is non-overwriting and versioned, print geometry is preflighted when applicable, and lettering remains separate.
