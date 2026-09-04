---
name: manga-lettering
description: Prepare and apply versioned dialogue, captions, thoughts, structured SFX, and professional balloon geometry to composed manga pages without changing artwork.
metadata:
  namespace: manga-studio
  version: "3.3.0"
---

# Manga Lettering

## Purpose

Turn approved page text, sound intent, and safe-zone data into deterministic professional vector lettering after panel art has been externally generated, reviewed, approved, and composed.

## Activation Conditions

Use only when the production gate passes, a composed page exists, and page text is approved.

## Compatible Operating Modes

`prepare_visual_production` during the post-approval production stage.

## Required Inputs

Discoverable project, `IMAGE_READY`, approved panel dependencies, composed page SVG, approved page specification, and dialogue-safe zones.

## Optional Inputs

Project-relative TTF/OTF font file, embedding policy, language/script and line-break profile, ruby/furigana, localization variants, balloon-tail coordinates, SFX source/meaning/translation, writing direction, and prior lettering version.

## Project Discovery

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Use shared discovery and stop if missing. Never initialize or resolve a page from the pilot implicitly.

## Source Of Truth

Approved page text governs words; the approved storyboard/page plan governs association and order; composed-page geometry and safe zones govern placement.

## Owned Outputs

Versioned lettering layers and lettered page SVG files under `.manga-studio/lettering/`.

## Procedure

1. Run production validation and confirm approved dependencies.
2. Give every item a stable ID and unique reading order. Use speech, caption, thought, whisper, shout, radio, narration, or SFX according to meaning rather than visual novelty.
3. For SFX, record the real source, reader-facing meaning, intensity, language, and translation/romanization when relevant. Keep SFX out of generated artwork and add it only in this vector layer.
4. Choose ellipse, rounded, rectangle, cloud, burst, jagged, or no-balloon treatment; set typography, rotation, horizontal/vertical writing, ruby, and tails deliberately.
5. Use a project-relative TTF/OTF when reproducible font metrics matter. Select Latin or Japanese line breaking explicitly, apply kinsoku punctuation constraints for Japanese, and retain a documented Unicode-width fallback only when no font file is available.
6. Verify boxes and tails remain inside safe zones after source-to-page crop projection, text fits at the minimum readable size, and unapproved collisions/cross-panel placements do not occur.
7. Use the shared launcher command `add-lettering <page-spec> --project <project-root>` for deterministic, non-overwriting placement.
8. Run the shared launcher command `review-page <page-spec> --project <project-root>` and route dialogue clarity, composition, or art defects to their owning skills.

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

Lettering and sounds are readable in the configured language/script, use reproducible metrics when a font is supplied, obey applicable line-breaking rules, are semantically clear and correctly ordered, remain collision-free unless explicitly layered, and stay separable from artwork.
