---
name: manga-revision-planner
description: Convert approved diagnostics into versioned, dependency-aware revision proposals while preserving source text, author voice, canon authority, and approval boundaries.
metadata:
  namespace: manga-studio
  version: "2.0.0"
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

Target length, adaptation format, priority constraints, prior revision plans, and user decisions.

## Project Discovery

Use shared discovery and stop if missing. This specialist never initializes or selects the pilot implicitly.

## Source Of Truth

Approved canon and source evidence constrain the plan; the approved diagnosis supplies accepted problems; user decisions resolve tradeoffs.

## Owned Outputs

Versioned plans under `.manga-studio/revisions/` and related decision or approval proposals.

## Procedure

1. Verify `DIAGNOSTIC_APPROVED` and story-profile validity.
2. Convert each accepted finding into a scoped revision objective linked to stable IDs.
3. Record dependencies, affected artifacts, canon risk, voice risk, and acceptance checks.
4. Order work without assuming chapters exist or that the source is already manga.
5. Produce a deterministic diff plan; do not edit source or manuscript files.
6. Request approval before activating the plan.

## Required Schemas

`project.schema.json`, `stable-id-map.schema.json`, `review.schema.json`, and provenance schemas.

## Next-Skill Handoff

Pass an approved plan to `manga-story-architect`, `manga-chapter-writer`, `manga-dialogue-writer`, or `manga-canon-manager` according to ownership.

## Approval Requirements

The complete plan and material plan revisions require approval before `REVISION_PLAN_APPROVED` changes or implementation begins.

## Failure Behavior

Stop if diagnostics are unapproved, canon is contradictory, stable targets are ambiguous, or the request would silently rewrite source.

## Non-Destructive Constraints

Write new plan versions only. Preserve author voice requirements and all original files byte-for-byte.

## Out Of Scope

Executing prose revisions, approving canon, storyboarding, and image jobs.

## Representative Example

Example: propose consolidating two repetitive scenes while preserving both original files and referring to each by stable scene ID.

## Acceptance Criteria

Every proposed change has evidence, scope, dependencies, risks, owner, and acceptance checks, and no authoritative file changes before approval.
