---
name: manga-image-job-builder
description: Build and validate deferred or gate-approved structured ChatGPT Image Generation Jobs for references, panels, covers, splash pages, and corrections without generating or editing images.
metadata:
  namespace: manga-studio
  version: "3.0.0"
---

# Manga Image Job Builder

## Purpose

Represent every eventual visual request as a structured, versioned external ChatGPT Image Generation Job while enforcing reference and release gates.

## Activation Conditions

Use for deferred job templates during preproduction or active jobs only after `IMAGE_READY` prerequisites pass.

## Compatible Operating Modes

`prepare_visual_production`, plus deferred examples in `adapt_existing_to_manga`.

## Required Inputs

Approved storyboard and panel plan, active canon and continuity, intended output path, and real approved reference paths for any strict-ready job.

## Optional Inputs

Prior job version, correction review, reference priority, style constraints, and dialogue-safe zones.

## Project Discovery

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Use shared discovery and stop if missing. Never initialize, fall back to pilot, or construct paths from sample entities.

## Source Of Truth

Approved canon and storyboard govern content; approved reference files govern appearance; continuity approval governs entering state; revision history governs job lineage.

## Owned Outputs

Job JSON under `.manga-studio/handoff/pending/`. External systems own image generation; generated, approved, and correction directories hold received versions without overwrite.

## Procedure

1. Run preproduction validation and inspect IMAGE_READY blockers.
2. Build every required field from approved plans and real project-relative paths.
3. Use `release_status: deferred` with explicit blockers until all gates pass.
4. Never release an active job unless `STORY_LOCKED`, `STORYBOARD_LOCKED`, canon/continuity checks, image enablement, and `IMAGE_READY` pass.
5. For panel jobs, prohibit dialogue text, captions, speech balloons, sound-effect text, panel borders, page numbers, signatures, and watermarks.
6. Validate structurally while deferred and strictly before external handoff.
7. Create corrections as new job/output versions and preserve locked references.

## Required Schemas

`image-job.schema.json`, `project.schema.json`, `page.schema.json`, `panel.schema.json`, and `continuity-state.schema.json`.

## Next-Skill Handoff

Hand released JSON to external ChatGPT Image Generation. After return, route received files to `manga-continuity-reviewer`; do not approve them automatically.

## Approval Requirements

Image enablement, job release, reference replacement, and generated-image approval require explicit user approval and passing gates.

## Failure Behavior

Fail clearly on missing references, invented or absolute paths, changed locked references, reused output filenames, unmet gates, or malformed revision history.

## Non-Destructive Constraints

Never generate, edit, retouch, or correct artwork. Never overwrite generated files or silently replace approved references.

## Out Of Scope

Creative image execution, rendered-image approval, lettering, and page composition.

## Representative Example

Example: a panel job may be saved as deferred with a known reference job dependency, but cannot be released until the corresponding approved file actually exists.

## Acceptance Criteria

The job is schema-valid, versioned, project-relative, gate-compliant, explicit about blockers, free of embedded lettering instructions, and ready for external execution only when approved.
