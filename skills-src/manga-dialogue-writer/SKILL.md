---
name: manga-dialogue-writer
description: Draft and refine versioned dialogue for story manuscripts or manga scripts using approved character voices, scene intent, language, and lettering constraints.
metadata:
  namespace: manga-studio
  version: "3.3.0"
---

# Manga Dialogue Writer

## Purpose

Shape dialogue, captions, and internal thought as text artifacts while preserving character voice, subtext, pacing, and later lettering feasibility.

## Activation Conditions

Use for dialogue drafting, revision, translation adaptation, balloon-load reduction, or voice consistency work.

## Compatible Operating Modes

`create_new`, `repair_existing`, `continue_existing`, and `adapt_existing_to_manga`.

## Required Inputs

Scene intent, active canon, character voice records, configured output language, and the manuscript or script version being revised.

## Optional Inputs

Panel or page word budgets, localization constraints, prior dialogue variants, and approved revision findings.

## Project Discovery

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Use shared discovery and stop if missing. This skill cannot initialize or borrow dialogue context from the pilot.

## Source Of Truth

Approved character canon governs voice and facts; active manuscript context governs scene meaning; approved storyboard constrains panel-level dialogue space when present.

## Owned Outputs

Versioned dialogue drafts or manuscript variants under `.manga-studio/manuscript/`; approved lettering text may later be copied into page specifications.

## Procedure

1. Validate relevant story state and identify the target by stable scene or page IDs.
2. Preserve factual content, intent, language, and author-voice rules.
3. Refine distinct voice, subtext, turn-taking, rhythm, and readable text load. Prefer immediate, natural wording; make speaker, intent, referents, and event sequence understandable without flattening character voice. Remove lines that only repeat visible action.
4. Check age/genre-appropriate content, accidental ambiguity, unexplained terminology, repetitive exposition, and balloon word load. Flag uncertain audience or sensitivity requirements instead of guessing.
5. Record sound cues separately with source, reader-facing meaning, intensity, language, script, and translation/romanization when relevant. Use a readable SFX expression that supports the event rather than decorative noise.
6. Keep panel-art jobs free of dialogue, captions, balloons, and sound-effect text.
7. Save a new version and diff; request approval before replacing active dialogue.

## Required Schemas

`project.schema.json`, `stable-id-map.schema.json`, `character.schema.json`, `page.schema.json` when page text exists, and provenance schemas.

## Next-Skill Handoff

Pass manuscript dialogue to `manga-consistency-manager`; pass approved page text to `manga-lettering` only after production dependencies exist.

## Approval Requirements

Material dialogue changes require manuscript approval. Translation choices that change meaning require an explicit decision.

## Failure Behavior

Stop if voice canon is contradictory, the target version is unknown, required context is missing, or text would be embedded into an image-generation request.

## Non-Destructive Constraints

Do not overwrite source or active manuscript versions and never place lettering into generated artwork.

## Out Of Scope

Story architecture, canon decisions, visual direction, page composition, and artwork generation.

## Representative Example

Example: shorten a page's approved conversation to fit safe zones while preserving each speaker's intent and saving the result as a separate dialogue version.

## Acceptance Criteria

Dialogue and sound cues are voice-consistent, context-faithful, audience-appropriate, easy to follow across the configured language/script, lettering-feasible, versioned, and kept out of artwork-generation jobs.
