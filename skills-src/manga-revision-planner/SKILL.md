---
name: manga-revision-planner
description: Convert approved diagnostics into versioned, dependency-aware revision proposals while preserving source text, author voice, canon authority, and approval boundaries.
metadata:
  namespace: manga-studio
  version: "3.3.0"
---

# Manga Revision Planner

## Purpose

Plan repairs or adaptation changes as explicit proposals before manuscript writing begins.

## Activation Conditions

Use when approved diagnostic findings require ordered revisions, tradeoff decisions, or a repair scope.

## Compatible Operating Modes

`repair_existing`, `continue_existing`, and `adapt_existing_to_manga`.

## Required Inputs

Approved diagnosis, active canon, source provenance, stable IDs, revision mode, and author-voice rules.

## Optional Inputs

Target length, adaptation format, priority constraints, active success plan, reader feedback or analytics, prior revision plans, and user decisions.

## Project Discovery

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Use shared discovery and stop if missing. This specialist never initializes or selects the pilot implicitly.

## Source Of Truth

Approved canon and source evidence constrain the plan; the approved diagnosis supplies accepted problems; user decisions resolve tradeoffs.

## Owned Outputs

Versioned policies, plans, change sets, and deterministic diffs under `.manga-studio/revisions/`. This skill proposes but does not apply, approve, or lock revisions.

## Procedure

1. Verify `DIAGNOSTIC_APPROVED` and story-profile validity.
2. Convert each accepted finding into a scoped revision objective linked to stable IDs.
3. Record target stable IDs, triggering issue IDs, source evidence, operation, expected result, alternatives, preserved elements, voice/canon/continuity/structural impact, creative-brief and audience/content impact, success-plan hypothesis or metric impact when relevant, dependencies, risks, rollback notes, and acceptance criteria.
4. Order work without assuming chapters exist or that the source is already manga.
5. Refuse metric-chasing changes that lack sufficient evidence or violate protected canon, author voice, content boundaries, rights, or sustainability limits. Prefer a bounded single-variable experiment when causality is uncertain.
6. Produce a deterministic diff plan; do not edit source or manuscript files.
7. Request approval before activating the plan.

## Required Schemas

`revision-policy.schema.json`, `revision-plan.schema.json`, `change-set.schema.json`, `success-plan.schema.json` when active, `approval.schema.json`, and `decision-log.schema.json`.

## Next-Skill Handoff

Pass an approved plan to `manga-story-architect`, `manga-chapter-writer`, `manga-dialogue-writer`, or `manga-canon-manager` according to ownership.

## Approval Requirements

The plan requires a separate hash-bound approval before its lock changes. Applying prose requires a separately approved change set and creates a new manuscript version, diff, and decision record; canon changes remain separately approved.

## Failure Behavior

Stop if diagnostics are unapproved, canon is contradictory, stable targets are ambiguous, or the request would silently rewrite source.

## Non-Destructive Constraints

Write new plan versions only. Preserve author voice requirements and all original files byte-for-byte.

## Out Of Scope

Executing prose revisions, approving canon, storyboarding, and image jobs.

## Representative Example

Example: propose consolidating two repetitive scenes while preserving both original files and referring to each by stable scene ID.

## Acceptance Criteria

Every proposed change has evidence, scope, dependencies, risks, creative-promise impact, owner, rollback guidance, and acceptance checks, and no authoritative file changes before approval.
