---
name: manga-continuity-reviewer
description: Review image jobs, externally generated outputs, approved panels, lettering, composed pages, and exports for production continuity without editing artwork or granting approval automatically.
metadata:
  namespace: manga-studio
  version: "3.3.0"
---

# Manga Continuity Reviewer

## Purpose

Perform production-facing continuity and compliance review after planning or external image delivery, distinct from textual cross-stage consistency management.

## Activation Conditions

Use for deferred/ready job review, generated-output intake, panel continuity, page review, correction assessment, or export QA.

## Compatible Operating Modes

`continuity_audit` and `prepare_visual_production`.

## Required Inputs

Active canon/storyboard/continuity versions, target job or received output, provenance, reference priority, and relevant page specification.

## Optional Inputs

Prior output versions, correction history, lettering layer, composed page, and export manifest.

## Project Discovery

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Use shared discovery and stop if missing. Never initialize or compare against pilot references unless the pilot itself is the discovered project.

## Source Of Truth

Approved canon and storyboard govern content; locked approved references govern appearance; continuity snapshots govern state; job/revision history governs expected output lineage.

## Owned Outputs

Versioned technical intake records under `.manga-studio/continuity/intake/`, visual review records under `.manga-studio/continuity/`, and approval records under `.manga-studio/approvals/`; correction recommendations may be handed to the image-job builder.

## Procedure

1. Validate the relevant profile and identify targets by project-local stable IDs.
2. For every externally returned file, run `validate-generated-image <job> <image> --project <root>`. Treat format, dimensions, alpha, hash, and container mode as technical facts, not artistic ratings.
3. Inspect the actual image separately and complete a `generated_image` review with `metric_scope: human_visual_assessment`: story clarity, event readability, locked-reference adherence, character acting, composition, monochrome finish, continuity, reserved lettering usability, audience/content compliance, required/prohibited-element checks, and visible artifacts. Do not recommend approval unless every score is at least 4/5, all binary checks pass, and no error finding remains.
4. Review required/prohibited elements, character/location/prop state, handedness, eyelines, screen direction, camera progression, panel-to-panel continuity, safe zones, lettering/SFX, page flow, and export completeness.
5. Run `review-page <page-spec> --project <project-root>` for deterministic geometry, collision, reading-order, text-fit, shot-variety, continuity, pacing, and page-impact planning indicators. Never present those scores as judgments of the rendered drawing.
6. Record evidence and severity without modifying the target. Recommend approval, blocking, or a new review-bound correction job; never overwrite an old output.
7. Approve only a visual review whose target intake is non-blocked and hash-current. Then copy the exact reviewed bytes into a new approved path; production verifies the hash chain before composition.

## Required Schemas

`review.schema.json`, `generated-image.schema.json`, `image-job.schema.json`, `continuity-state.schema.json`, `page.schema.json`, `panel.schema.json`, and relevant canon schemas.

## Next-Skill Handoff

Send correction requirements to `manga-image-job-builder`, page text issues to `manga-lettering`, composition issues to `manga-page-compositor`, or approved final pages to export.

## Approval Requirements

The reviewer may recommend but never auto-approve an image, replacement reference, correction, lettered page, or export.

## Failure Behavior

Stop on missing job provenance, wrong-project references, absent locked references, unversioned replacement attempts, or unavailable required assets.

## Non-Destructive Constraints

Never generate, edit, repair, overwrite, or silently substitute artwork. Reviews and correction jobs are separate versioned records.

## Out Of Scope

Story rewriting, canon adoption, external image execution, and direct image correction.

## Representative Example

Example: flag a changed prop state in an externally generated panel and request a versioned correction job while preserving both received files.

## Acceptance Criteria

The review is evidence-based, project-isolated, hash-bound to exact versions, keeps technical intake, planning indicators, and human visual judgment distinct, distinguishes blockers from warnings, never auto-approves, and leaves every visual asset untouched.
