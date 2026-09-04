---
name: manga-creator
description: Orchestrate a portable Manga Studio story workspace, selecting only the specialist skills needed for creation, import, diagnosis, repair, continuation, adaptation, continuity audit, or visual-production preparation.
metadata:
  namespace: manga-studio
  version: "3.3.0"
---

# Manga Creator

## Purpose

Coordinate Manga Studio work for any independent story without assuming its title, genre, characters, structure, chapter count, or location. Codex owns story and production orchestration but never generates or edits artwork.

## Activation Conditions

Use for starting, resuming, routing, or assessing an end-to-end Manga Studio operation. This is the only Manga Studio skill allowed to initialize a missing `.manga-studio/project.json`.

## Compatible Operating Modes

`create_new`, `import_existing`, `diagnose_existing`, `repair_existing`, `continue_existing`, `adapt_existing_to_manga`, `continuity_audit`, and `prepare_visual_production`.

## Required Inputs

The requested operating mode and a story directory or a path inside one. For a new workspace, confirm only details that materially change project configuration.

## Optional Inputs

Title, languages, genre labels, source roots, structure-preservation preferences, reading direction, target audience/content boundaries, opening and structure preferences, screen/print target format, and the author's definition of creative, reader, publication, or commercial success.

## Project Discovery

Use the versioned launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py` for a normal user-scope installation. In repository development mode, use `scripts/manga_studio.py`; `.manga-studio-install.json` records any custom destination and launcher path.

Run the launcher described above with `discover --project <path>`. If discovery fails and the operation needs a project, initialize with `init <story-directory> --mode <mode>`. Never use `projects/pilot-001` as a fallback or infer a project from sample names.

## Source Of Truth

Original files are immutable provenance evidence. Approved canon governs story facts; the active approved manuscript governs prose; the active approved storyboard governs panel planning; approvals, decisions, and locks govern workflow state; approved visual references govern production. An active success plan records goals and testable hypotheses but never outranks canon, the creative brief, author voice, safety boundaries, rights, or creator health.

## Owned Outputs

`.manga-studio/project.json`, initial workspace directories, the managed Manga Studio section in `AGENTS.md`, and orchestration status. Specialists own all editorial and production artifacts.

## Procedure

1. Discover or initialize the project and run `status`.
2. Select the requested operating mode; do not run every specialist automatically.
3. For `create_new`, route to story architecture for a versioned creative brief before long-form architecture. Capture premise, core message, thematic question, reader takeaway, story promise, audience/content boundaries, target length, originality boundaries, show-don't-tell policy, opening strategy, and a story-appropriate structure such as Kishotenketsu only when it serves the concept.
4. When the user asks about success, readership, serialization, publishing, sustainability, marketing, or monetization, create a separate versioned success plan linked by hash to the active creative brief. Define success in the author's terms; label market claims as hypotheses; keep demographic, genre, and format distinct; and never promise popularity, publication, or revenue.
5. For import, diagnosis, repair, or adaptation, inventory, obtain explicit classification/usage-role decisions, import, and structure before diagnosis or revision planning.
6. For continuation, load approved canon, unresolved plot threads, the active manuscript, and any active success plan before routing to writing skills.
7. For continuity audit, choose story consistency review or production continuity review according to the target.
8. Before visual preparation, require an approved creative brief, complete dramatic profiles for production characters, an approved structured nemu, event-driven page intent, explicit reading sequence, motivated camera variation, structured SFX, and a `high` quality profile.
9. Use storyboard, panel, consistency, image-job, compositor, lettering, and continuity skills only when their gates and assets are ready. For each ready image job, provide the deterministic exported ChatGPT Markdown and exact attachment checklist rather than asking the user to reconstruct a prompt.
10. On image return, run `validate-generated-image`, then require a separate human visual assessment and explicit hash-bound approval before the file enters `handoff/approved/` or composition.
11. Run page-quality review plus the appropriate validation profile. Automated page scores are planning indicators only; actual art quality, acting, impact, reference adherence, and artifacts belong to the human visual assessment.
12. For print/both output, run `preflight-print` against trim, bleed, safe margins, binding gutter, DPI, page side, export format, and color profile; require an approved current preflight before print production.

## Required Schemas

`project.schema.json`, `creative-brief.schema.json`, `success-plan.schema.json` when success planning is active, `character.schema.json`, `nemu.schema.json`, `generated-image.schema.json`, source inventory/provenance/map schemas, `stable-id-map.schema.json`, approval/lock schemas, and the contracts owned by selected specialists.

## Next-Skill Handoff

Hand off only the discovered project root, requested deliverable, active versions, relevant approvals, and unresolved blockers to the next specialist.

## Approval Requirements

User approval is required to adopt canon, diagnostics, revision plans, manuscripts, or storyboards and to change stage locks. Image generation remains disabled unless explicitly enabled after story and storyboard locks.

## Failure Behavior

Stop on ambiguous project discovery, malformed configuration, cross-project paths, failed provenance, or unmet gates. Give the exact command or artifact needed to continue.

## Non-Destructive Constraints

Never modify original story files automatically, overwrite versions, replace unrelated `AGENTS.md` instructions, alter unrelated skills, or generate/edit artwork.

## Out Of Scope

Artwork generation, image correction, automatic approval, and speculative execution of specialists unrelated to the chosen mode.

## Representative Example

Example: from a nested prose directory, discover its story root, inventory Markdown chapters, and route only to source ingestion plus diagnosis for `diagnose_existing`.

## Acceptance Criteria

The correct story is isolated, the requested mode is explicit, only necessary specialists are selected, sources remain byte-identical, success criteria are project-specific and non-guaranteeing when present, production jobs use the high-quality contract, technical and visual reviews remain distinct, and validation reports gate state without claiming that artwork was generated or approved.
