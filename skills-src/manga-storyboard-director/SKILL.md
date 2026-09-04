---
name: manga-storyboard-director
description: Convert an approved locked story into versioned manga page and beat plans with reading flow, pacing, page turns, and panel allocation, without producing artwork.
metadata:
  namespace: manga-studio
  version: "2.0.0"
---

# Manga Storyboard Director

## Purpose

Plan how approved story material becomes manga pages while respecting reading direction, target format, pacing, dialogue load, and page-turn effects.

## Activation Conditions

Use after an approved manuscript and story lock when page-level manga adaptation or storyboard revision is requested.

## Compatible Operating Modes

`adapt_existing_to_manga`, `continue_existing`, and `prepare_visual_production`.

## Required Inputs

`STORY_LOCKED`, active approved manuscript and canon, reading direction, target format, stable scene IDs, and adaptation scope.

## Optional Inputs

Page budget, prior storyboard version, dialogue constraints, and intended print or screen presentation.

## Project Discovery

Use shared discovery and stop if missing. Never initialize or select the pilot storyboard implicitly.

## Source Of Truth

The active locked manuscript and approved canon govern content. User decisions govern cuts or rearrangements. The active approved storyboard governs downstream panel plans.

## Owned Outputs

Versioned page maps, beat sheets, page-turn plans, and storyboard metadata under `.manga-studio/storyboard/`.

## Procedure

1. Validate story profile and require `STORY_LOCKED`.
2. Resolve source beats through stable scene and plot-thread IDs.
3. Allocate beats to pages and panels according to story rhythm, not a fixed panel count.
4. Specify reading order, page turns, dialogue load, establishing needs, and continuity handoffs.
5. Record omissions or rearrangements as explicit adaptation decisions.
6. Write a new storyboard version and request approval before locking.

## Required Schemas

`project.schema.json`, `stable-id-map.schema.json`, `page.schema.json`, and relevant canon/continuity schemas.

## Next-Skill Handoff

Pass an approved storyboard version to `manga-panel-director`, then `manga-consistency-manager` before storyboard lock.

## Approval Requirements

The user approves each active storyboard version. `STORYBOARD_APPROVED` and `STORYBOARD_LOCKED` must not be set automatically.

## Failure Behavior

Stop if story material is unlocked, active versions are missing, adaptation decisions are unapproved, or the page plan contradicts canon.

## Non-Destructive Constraints

Never alter source or manuscript text, overwrite storyboards, or generate/edit storyboard art or manga panels.

## Out Of Scope

Individual camera direction, image jobs, lettering execution, and page composition.

## Representative Example

Example: adapt a chapterless short story into a four-panel page plan while retaining its stable scene ID and recording one approved compression decision.

## Acceptance Criteria

Every page beat traces to locked story material, reading flow is explicit, adaptation changes are reviewable, and no visual asset is created.
