---
name: manga-image-job-builder
description: Build and validate deferred or gate-approved structured ChatGPT Image Generation Jobs for references, panels, covers, splash pages, and corrections without generating or editing images.
metadata:
  namespace: manga-studio
  version: "3.3.0"
---

# Manga Image Job Builder

## Purpose

Represent every eventual visual request as a structured, versioned external ChatGPT Image Generation Job while enforcing reference and release gates.

## Activation Conditions

Use for deferred job templates during preproduction or active jobs only after `IMAGE_READY` prerequisites pass.

## Compatible Operating Modes

`prepare_visual_production`, plus deferred examples in `adapt_existing_to_manga`.

## Required Inputs

Approved storyboard, approved nemu, panel plan, active canon and continuity, intended output path/specification, and real approved reference paths for any strict-ready job.

## Optional Inputs

Prior job version, correction review, reference priority, style constraints, dialogue-safe zones, and an active success plan for explicitly planned discoverability deliverables.

## Project Discovery

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Use shared discovery and stop if missing. Never initialize, fall back to pilot, or construct paths from sample entities.

## Source Of Truth

Approved canon and storyboard govern content; approved reference files govern appearance; continuity approval governs entering state; revision history governs job lineage.

## Owned Outputs

Job JSON and deterministic paste-ready Markdown companions under `.manga-studio/handoff/pending/`. JSON remains authoritative. External systems own image generation; generated, approved, and correction directories hold received versions without overwrite.

## Procedure

1. Run preproduction validation and inspect IMAGE_READY blockers.
2. Build every image-job `1.3.0` field from approved plans and real project-relative paths. Copy `content_constraints` exactly from the active approved creative brief, then declare exact format, source canvas dimensions, color mode, alpha policy, and `source_normalized` safe-zone coordinates. For active production use `quality_profile.tier: high`, locked continuity, high detail budget, required self-check, and event-driven variation for panels.
3. Use `release_status: deferred` with explicit blockers until all gates pass.
4. Never release an active job unless `STORY_LOCKED`, `STORYBOARD_LOCKED`, canon/continuity checks, image enablement, and `IMAGE_READY` pass.
5. For panel jobs, copy the exact dominant event, intensity, importance, shot size, camera angle/motion, action direction, emotional beat, pose/expression, show-don't-tell cue, reading focus, background priority, and normalized safe zones into `composition`. Request one borderless panel, never a page or collage.
6. Specify linework, line-weight hierarchy, solid-black strategy, screen tones, contrast, depth, motion language, and genre for every job. Character references need turnaround, expressions, proportions, and identity anchors; location references need spatial maps, scale cues, landmarks, and lighting states; prop references need scale, functional states, and continuity marks.
7. For panel jobs, prohibit dialogue text, captions, speech balloons, sound-effect text, panel borders, page numbers, signatures, watermarks, and color. SFX remains structured lettering even when the scene contains a loud sound.
8. Validate structurally while deferred and strictly before external handoff.
9. For a `ready` or `released` job, run `export-chatgpt-handoff <job.json>` to create a same-name Markdown packet. Give the user that complete packet and its ordered attachment checklist; never hand-author a competing prompt.
10. For covers, thumbnails, promo strips, key images, or character sheets named by a success plan, verify that the deliverable owner is `chatgpt_image_generation`, then create the same structured, gated job used for other visual work. A marketing goal never relaxes reference, content, originality, or approval rules; video remains outside this image-job workflow.
11. Bind every correction to a source review, list only requested changes, list all elements that must remain unchanged, and create new job/output versions.

## Required Schemas

`image-job.schema.json`, `project.schema.json`, `success-plan.schema.json` when a deliverable comes from it, `nemu.schema.json`, `page.schema.json`, `panel.schema.json`, and `continuity-state.schema.json`.

## Next-Skill Handoff

Hand the exported Markdown and exactly its approved attachments to external ChatGPT Image Generation. The Markdown embeds canonical JSON, attachment hashes, priority, and requested filename. After return, place the file only at its declared generated path, run `validate-generated-image`, and route its intake record plus image to `manga-continuity-reviewer`; do not approve automatically.

## Approval Requirements

Image enablement, job release, reference replacement, and generated-image approval require explicit user approval and passing gates.

## Failure Behavior

Fail clearly on deferred release status, missing or unlocked references, invented or absolute paths, changed locked references, reused output filenames, unmet gates, malformed revision history, or an attempt to overwrite a different Markdown packet.

## Non-Destructive Constraints

Never generate, edit, retouch, or correct artwork. Never overwrite generated files or silently replace approved references.

## Out Of Scope

Creative image execution, rendered-image approval, lettering, and page composition.

## Representative Example

Example: a panel job may be saved as deferred with a known reference job dependency, but cannot be released until the corresponding approved file actually exists.

## Acceptance Criteria

The job is schema-valid at `1.3.0`, versioned, project-relative, gate-compliant, exact about audience/content constraints, output, and normalized geometry, high-quality for active production, explicit about blockers and event direction, free of embedded lettering, and accompanied by one deterministic packet only when approved for external execution.
