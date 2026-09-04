---
name: manga-storyboard-director
description: Convert an approved locked story into versioned manga page and beat plans with reading flow, pacing, page turns, and panel allocation, without producing artwork.
metadata:
  namespace: manga-studio
  version: "3.3.0"
---

# Manga Storyboard Director

## Purpose

Plan how approved story material becomes manga pages while respecting reading direction, target format, pacing, dialogue load, and page-turn effects.

## Activation Conditions

Use after an approved manuscript and story lock when page-level manga adaptation or storyboard revision is requested.

## Compatible Operating Modes

`adapt_existing_to_manga`, `continue_existing`, and `prepare_visual_production`.

## Required Inputs

`STORY_LOCKED`, approved creative brief, active approved manuscript and canon, reading direction, target format, stable scene IDs, and adaptation scope.

## Optional Inputs

Page budget, prior storyboard version, dialogue constraints, intended print or screen presentation, and active success-plan readability or feedback checkpoints.

## Project Discovery

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Use shared discovery and stop if missing. Never initialize or select the pilot storyboard implicitly.

## Source Of Truth

The active locked manuscript and approved canon govern content. User decisions govern cuts or rearrangements. The active approved storyboard governs downstream panel plans.

## Owned Outputs

Versioned page maps, beat sheets, page-turn plans, storyboard metadata, and structured geometry-only nemu bundles under `.manga-studio/storyboard/nemu/`.

## Procedure

1. Validate story profile and require `STORY_LOCKED`.
2. Resolve source beats through stable scene and plot-thread IDs.
3. Give each page a purpose, pacing mode, reader effect, emotional curve, dominant event, and page-turn setup. Allocate beats according to story rhythm, not a fixed panel count; fewer/larger panels slow and emphasize, while denser sequences accelerate only when clarity survives.
4. Give every panel one dominant event with intensity and importance. Select `dialogue`, `cinematic`, `action`, `reveal`, `montage`, `suspense`, `comedy`, or `custom` layout intent because it serves those events, not merely to make the page look busy.
5. Specify an explicit reading sequence, dialogue load, establishing needs, SFX beats, and continuity handoffs. Reserve larger or more disruptive geometry for the page's most important beat.
6. Vary shot size and camera angle with narrative motivation; preserve screen direction across action unless a deliberate, marked axis break reorients the reader.
7. Create a structured nemu with normalized panel blocks, reading sequence, balloon placeholders, visual focus, page-turn intent, and per-page checklist. This nemu is planning geometry, not artwork.
8. When a hand-drawn visual thumbnail is needed, represent it as a `storyboard_thumbnail` ChatGPT Image Generation Job; never draw or edit it in Codex.
9. When a success plan is active, preserve its hook deadline, unit movement, readability floor, and protected elements, then define what a first-time reader should be able to recount at the planned feedback checkpoint. Do not optimize panel density or page turns for an assumed platform without evidence.
10. Record omissions or rearrangements as explicit adaptation decisions.
11. Write new storyboard and nemu versions and request approval before locking or creating panel jobs.

## Required Schemas

`project.schema.json`, `creative-brief.schema.json`, `success-plan.schema.json` when active, `stable-id-map.schema.json`, `nemu.schema.json`, `page.schema.json`, and relevant canon/continuity schemas.

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

Every page beat traces to locked story material, page intent and reading flow are explicit, panel scale follows event importance, the nemu is structured and approved, adaptation changes are reviewable, and no visual asset is created.
