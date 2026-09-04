---
name: manga-story-diagnostician
description: Diagnose imported story structure, character arcs, pacing, causality, continuity, and manga-adaptation risks without revising the source or declaring new canon.
metadata:
  namespace: manga-studio
  version: "3.3.0"
---

# Manga Story Diagnostician

## Purpose

Produce a schema-valid, evidence-linked diagnostic report for a story of any genre or structure while separating observed facts, interpretations, uncertainties, and alternatives.

## Activation Conditions

Use after supported sources are inventoried and imported, or when an existing diagnosis needs a scoped update.

## Compatible Operating Modes

`diagnose_existing`, `repair_existing`, `continue_existing`, `adapt_existing_to_manga`, and `continuity_audit`.

## Required Inputs

Source inventory, provenance, normalized derivatives, stable source IDs, and the diagnosis question or scope.

## Optional Inputs

Approved creative brief/canon, active success plan, prior diagnostics, reader goals, target audience and content boundaries, feedback or analytics supplied by the user, and adaptation constraints.

## Project Discovery

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Use shared discovery from the invocation path. Stop if no `.manga-studio/project.json` is found; never initialize or consult pilot data.

## Source Of Truth

Original snapshots support textual evidence. Approved canon outranks inferred facts. Active approved manuscripts outrank superseded drafts for current-story diagnosis.

## Owned Outputs

Versioned JSON reports and optional Markdown companions under `.manga-studio/analysis/diagnostics/`. This skill does not create approvals.

## Procedure

1. Validate the story profile and provenance.
2. Scope the diagnosis instead of assuming a full rewrite review.
3. Give every finding a unique issue ID, supported category, severity, confidence, status, description, why-it-matters statement, evidence locators, affected chapter and scene IDs, related entity IDs, relevant external evidence IDs, alternatives, uncertainty, and adaptation impact.
4. Make every evidence locator match a source-map unit and byte/line range in this project.
5. Separate contradictions from intentional ambiguity and unresolved questions.
6. Analyze hook timing, promise/payoff, structure, pacing, causality, character desire/fear/limits, arcs, continuity, voice, setup/payoff, chapter boundaries, show-don't-tell opportunities, audience/content fit, originality risk, and adaptation pressure only where evidence supports it.
7. When a success plan is active, test its craft goals against source evidence and its reader or market hypotheses only against supplied research, feedback, or analytics. Record new external results as source-linked observations in a new success-plan version; diagnostics may reference those observation or evidence IDs but must keep at least one manuscript evidence locator for the story element being assessed. Separate observed retention/readability signals from causal claims, sample bias, platform effects, and taste; never diagnose a story as commercially successful from generic conventions.
8. Publish source-grounded findings with `diagnose`; never modify source, canon, manuscripts, prior reports, approvals, or locks.

## Required Schemas

`project.schema.json`, `creative-brief.schema.json` when active, `success-plan.schema.json` when active, `source-map.schema.json`, `story-issue.schema.json`, and `diagnostic-report.schema.json`.

## Next-Skill Handoff

Pass approved findings and unresolved questions to `manga-revision-planner`; pass canon ambiguities to `manga-canon-manager`.

## Approval Requirements

The user must create a separate hash-bound approval and explicitly run `set-lock DIAGNOSTIC_APPROVED`; this skill may not approve or lock its own report.

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
