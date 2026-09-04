---
name: manga-story-architect
description: Design or revise story structure, scene purpose, arcs, plot threads, setups, and payoffs as versioned plans without assuming chapters or a particular genre.
metadata:
  namespace: manga-studio
  version: "2.0.0"
---

# Manga Story Architect

## Purpose

Create a coherent story architecture for new work, approved repairs, continuations, or manga adaptations while preserving existing structure when configured.

## Activation Conditions

Use for high-level story design, structural revision, scene sequencing, or continuation planning after required approvals.

## Compatible Operating Modes

`create_new`, `repair_existing`, `continue_existing`, and `adapt_existing_to_manga`.

## Required Inputs

Project configuration, active canon when present, stable IDs, and either a creative brief or an approved revision plan.

## Optional Inputs

Source snapshots, diagnostics, unresolved plot threads, target length, and chapter-detection preferences.

## Project Discovery

Use shared discovery and stop if missing. Only `manga-creator` may initialize the story workspace.

## Source Of Truth

Approved canon and user decisions constrain architecture. Existing approved manuscript structure is preserved according to project rules. Architecture proposals do not become canon by themselves.

## Owned Outputs

Versioned structural plans, scene maps, plot-thread maps, and setup/payoff maps under `.manga-studio/manuscript/` or `.manga-studio/revisions/` as appropriate.

## Procedure

1. Validate the story profile and relevant approval gates.
2. Resolve chapters, scenes, threads, and events by stable IDs; create IDs through the shared CLI when needed.
3. Model structure appropriate to the story, including a chapterless story when configured.
4. Track scene purpose, causality, escalation, arcs, unresolved threads, and setups/payoffs.
5. Compare against active versions and write a new proposal.
6. Request approval before downstream writing treats it as active.

## Required Schemas

`project.schema.json`, `stable-id-map.schema.json`, provenance schemas, and canon entity schemas relevant to the story.

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

The structure is story-specific, stable-ID based, canon-compatible, versioned, and clear enough for scoped writing without forcing a genre template.
