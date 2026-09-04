---
name: manga-story-architect
description: Design or revise story structure, scene purpose, arcs, plot threads, setups, and payoffs as versioned plans without assuming chapters or a particular genre.
metadata:
  namespace: manga-studio
  version: "3.3.0"
---

# Manga Story Architect

## Purpose

Create a coherent story architecture for new work, approved repairs, continuations, or manga adaptations while preserving existing structure when configured.

## Activation Conditions

Use for high-level story design, structural revision, scene sequencing, continuation planning, or a project-specific manga success strategy after required approvals.

## Compatible Operating Modes

`create_new`, `repair_existing`, `continue_existing`, and `adapt_existing_to_manga`.

## Required Inputs

Project configuration, active canon when present, stable IDs, and the available concept, source evidence, or approved revision plan.

## Optional Inputs

Source snapshots, diagnostics, unresolved plot threads, target length, chapter-detection preferences, intended readers, publication goals, sustainable capacity, feedback access, and user-provided or researched market evidence.

## Project Discovery

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Use shared discovery and stop if missing. Only `manga-creator` may initialize the story workspace.

## Source Of Truth

Approved canon and user decisions constrain architecture. Existing approved manuscript structure is preserved according to project rules. Architecture proposals do not become canon by themselves. A success plan is an advisory strategy: it may test reader or market hypotheses but cannot redefine approved story truth or protected creative elements.

## Owned Outputs

Versioned creative briefs under `.manga-studio/story/briefs/`, versioned success plans under `.manga-studio/story/success-plans/`, plus structural plans, scene maps, plot-thread maps, and setup/payoff maps under `.manga-studio/manuscript/` or `.manga-studio/revisions/` as appropriate.

## Procedure

1. Validate the story profile and relevant approval gates.
2. Create or verify a creative brief covering premise, message, thematic question, takeaway, story promise, target audience, content boundaries, genre/tone, target length, opening hook, originality boundaries, and show-don't-tell policy. Treat the needle-drop opening and Kishotenketsu as selectable tools, not mandatory formulas.
3. When success planning is requested, create a `success-plan.schema.json` artifact linked to the exact creative-brief path and checksum. Define one to three primary outcomes, intended readers and reader need, a one-line logline, protagonist want/need/stakes, emotional core, early hook, unit movement and ending promises, sustainable cadence/buffer, distribution status, discoverability and community strategy, collaborator scope/payment/credit/IP requirements, efficient repeatable practices, feedback checkpoints, one to three metrics, small experiments, pivot rules, protected elements, risks, and assumptions.
4. Treat demographics, genres, and delivery formats as distinct signals. Do not prescribe generic arc lengths, update frequency, platform, monetization, or marketing tactics as universal truths; record them as story-specific decisions or explicitly unvalidated hypotheses. Current platform, legal, and market claims require dated sources or qualified human review as appropriate.
5. Plan promotional visuals only as externally owned deliverables. Covers, thumbnails, strips, key images, and reference sheets must become structured ChatGPT Image Generation Jobs after production gates; video and other media stay with an explicitly named external owner.
6. Resolve chapters, scenes, threads, and events by stable IDs; create IDs through the shared CLI when needed.
7. Model structure appropriate to the story, including a chapterless story when configured. Test scene purpose, causality, escalation, reversals, breathing room, arcs, unresolved threads, and setups/payoffs.
8. Make every major turn arise from character choice, world pressure, or established setup; flag generic genre imitation and unearned surprise.
9. Compare against active versions and write a new proposal.
10. Request approval for the creative brief, success plan when present, and architecture before downstream work treats them as active.

## Required Schemas

`project.schema.json`, `creative-brief.schema.json`, `success-plan.schema.json` when active, `stable-id-map.schema.json`, provenance schemas, and canon entity schemas relevant to the story.

## Next-Skill Handoff

Pass approved architecture to character/world bible skills or to chapter and dialogue writing. For adaptation, hand off to storyboard only after manuscript approval and story lock.

## Approval Requirements

Structural changes affecting approved material require approval and may require a canon decision. Do not set story locks automatically.

## Failure Behavior

Stop on ambiguous entities, unapproved required revisions, unresolved canon contradictions, or a request that violates structure-preservation rules.

## Non-Destructive Constraints

Never edit original sources or overwrite an active manuscript. Create separate proposed versions and diffs.

## Out Of Scope

Line-level prose, final dialogue, visual panel direction, and artwork.

## Representative Example

Example: organize a single-file short story into stable scenes without inventing chapter folders or changing its original Markdown file.

## Acceptance Criteria

The structure is story-specific, stable-ID based, canon-compatible, versioned, and clear enough for scoped writing without forcing a genre template. Any success plan distinguishes controllable craft and production choices from uncertain market outcomes, has measurable but limited signals, protects the work's identity and creator health, and assigns every visual asset outside Codex.
