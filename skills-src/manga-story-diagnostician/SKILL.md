---
name: manga-story-diagnostician
description: Diagnose imported story structure, character arcs, pacing, causality, continuity, and manga-adaptation risks without revising the source or declaring new canon.
metadata:
  namespace: manga-studio
  version: "2.0.0"
---

# Manga Story Diagnostician

## Purpose

Produce evidence-linked editorial diagnosis for a story of any genre or structure while separating observed facts, interpretations, uncertainties, and recommendations.

## Activation Conditions

Use after supported sources are inventoried and imported, or when an existing diagnosis needs a scoped update.

## Compatible Operating Modes

`diagnose_existing`, `repair_existing`, `continue_existing`, `adapt_existing_to_manga`, and `continuity_audit`.

## Required Inputs

Source inventory, provenance, normalized derivatives, stable source IDs, and the diagnosis question or scope.

## Optional Inputs

Approved canon, prior diagnostics, reader goals, target demographic, and adaptation constraints.

## Project Discovery

Use shared discovery from the invocation path. Stop if no `.manga-studio/project.json` is found; never initialize or consult pilot data.

## Source Of Truth

Original snapshots support textual evidence. Approved canon outranks inferred facts. Active approved manuscripts outrank superseded drafts for current-story diagnosis.

## Owned Outputs

Versioned reports under `.manga-studio/analysis/` and proposed diagnostic approvals under `.manga-studio/approvals/`.

## Procedure

1. Validate the story profile and provenance.
2. Scope the diagnosis instead of assuming a full rewrite review.
3. Cite stable document, chapter, scene, and entity IDs for findings.
4. Separate contradictions from intentional ambiguity and unresolved questions.
5. Analyze structure, pacing, causality, arcs, continuity, and adaptation pressure only where evidence supports it.
6. Write a new versioned report; never modify source or prior reports.

## Required Schemas

`project.schema.json`, `source-inventory.schema.json`, `provenance.schema.json`, `stable-id-map.schema.json`, and `review.schema.json` where structured findings are used.

## Next-Skill Handoff

Pass approved findings and unresolved questions to `manga-revision-planner`; pass canon ambiguities to `manga-canon-manager`.

## Approval Requirements

The user must approve a diagnosis before `DIAGNOSTIC_APPROVED` changes or a revision plan treats findings as accepted.

## Failure Behavior

Stop on missing provenance, unsupported required sources, ambiguous IDs, or insufficient evidence. Label uncertainty instead of inventing story facts.

## Non-Destructive Constraints

Do not edit source, canon, manuscripts, approvals, or locks. Do not generate or prepare artwork.

## Out Of Scope

Implementing revisions, writing chapters, deciding canon, storyboarding, and visual production.

## Representative Example

Example: identify two scenes with duplicate display titles by stable scene IDs and flag a causal gap without renaming either source chapter.

## Acceptance Criteria

Findings are evidence-linked, story-independent, versioned, explicit about uncertainty, and ready for approval without changing any authoritative artifact.
