---
name: manga-consistency-manager
description: Check source, canon, manuscript, revision, and storyboard artifacts for cross-stage story consistency before approvals or locks; it does not review rendered images.
metadata:
  namespace: manga-studio
  version: "3.0.0"
---

# Manga Consistency Manager

## Purpose

Review textual and planned story artifacts across stages so contradictions are resolved before expensive production work.

## Activation Conditions

Use before manuscript/storyboard approval or lock, during continuation, or for a story-level continuity audit.

## Compatible Operating Modes

`diagnose_existing`, `repair_existing`, `continue_existing`, `adapt_existing_to_manga`, `continuity_audit`, and `prepare_visual_production`.

## Required Inputs

Active or proposed canon, manuscript, storyboard, stable IDs, provenance, and the approval or lock being evaluated.

## Optional Inputs

Diagnostics, revision plan, decision records, dialogue variants, and continuity snapshots.

## Project Discovery

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Use shared discovery and stop if missing. Keep all comparisons inside one project root.

## Source Of Truth

Approved canon outranks drafts and plans; active approved manuscript outranks storyboard paraphrases; explicit decisions and stage locks define accepted state; source remains provenance authority.

## Owned Outputs

Versioned consistency reports under `.manga-studio/analysis/` or `.manga-studio/continuity/` and proposed approval blockers.

## Procedure

1. Validate story provenance and active-version paths.
2. Compare entities and events by stable IDs rather than names or positions.
3. Check canon facts, causal order, character state, timeline, plot threads, setup/payoff status, dialogue facts, and storyboard fidelity.
4. Separate errors, warnings, intentional changes, and unresolved decisions.
5. Write a structured report without changing the reviewed artifacts.
6. Clear a gate only through the appropriate approval workflow.

## Required Schemas

`project.schema.json`, `stable-id-map.schema.json`, `continuity-state.schema.json`, `review.schema.json`, and schemas for reviewed entities/pages.

## Next-Skill Handoff

Send story defects to their owning writing/bible skill; send approved preproduction material to storyboard locking or image-job preparation.

## Approval Requirements

Consistency reports inform but do not grant approval. Users decide whether warnings are acceptable and whether locks may change.

## Failure Behavior

Stop on cross-project references, missing active versions, corrupt provenance, or ambiguous identity. Do not guess which artifact should win.

## Non-Destructive Constraints

Review only. Never rewrite source, canon, manuscripts, storyboards, approvals, locks, or images.

## Out Of Scope

Rendered-image continuity, page export QA, prose rewriting, and artwork correction.

## Representative Example

Example: detect that a storyboard resolves a plot thread before the active manuscript does, using the plot-thread ID despite different display labels.

## Acceptance Criteria

The report is project-isolated, stable-ID based, source-aware, actionable by artifact owner, and safe to use for an explicit gate decision.
