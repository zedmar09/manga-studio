# Manga Studio

Manga Studio is a portable, story-local workflow for adapting or creating manga while keeping all artwork generation outside Codex. The toolkit discovers any independent story through its `.manga-studio/project.json`; it never assumes a title, genre, cast, directory layout, chapter model, or pilot project.

## Architecture Boundary

Codex may inventory and preserve sources, manage canon and versions, diagnose and revise story material, plan storyboards and panels, construct structured image jobs, receive and review external outputs, add lettering, compose pages, and export approved work.

Codex must never generate or edit manga artwork. Character, location, organization, prop, panel, cover, splash-page, and correction visuals are represented as structured ChatGPT Image Generation Jobs. ChatGPT Image Generation is reserved for eventual external execution after the production gates pass.

No image was generated or edited while building this repository.

## Portable Story Workspace

Original story files remain where the author keeps them. Manga Studio writes only its managed metadata and versioned derivatives beneath `.manga-studio/`, except for its clearly delimited, idempotent section in `AGENTS.md`.

```text
<story-directory>/
|-- original story files
|-- AGENTS.md                         optional; unrelated instructions are preserved
`-- .manga-studio/
    |-- project.json
    |-- source/                       inventory, stable IDs, snapshots, normalized derivatives, provenance
    |-- canon/
    |-- analysis/
    |-- revisions/
    |-- manuscript/
    |-- storyboard/
    |-- continuity/
    |-- approvals/
    |-- decisions/
    |-- locks/
    |-- handoff/
    |   |-- pending/
    |   |-- generated/
    |   |-- approved/
    |   `-- corrections/
    |-- panels/
    |-- lettering/
    |-- pages/
    `-- exports/
```

Paths stored in project data are relative to `project_root`, the story directory. `workspace_root` is `<project_root>/.manga-studio`; configured source roots point to original material; `manga_studio_install_root` is this toolkit or its installed copy.

## Discovery

Every skill and script uses the same discovery algorithm:

1. Use an explicit `--project` path when supplied.
2. Otherwise start at the current working directory.
3. Search upward for `.manga-studio/project.json`.
4. Use its parent story directory as `project_root`.
5. Only `manga-creator` may initialize a missing project.
6. Specialists stop with an actionable error when discovery fails.

There is no fallback to `projects/pilot-001`, and sample names never influence discovery.

## Shared CLI

```bash
python3 scripts/manga_studio.py discover [path]
python3 scripts/manga_studio.py init [path] --mode import_existing
python3 scripts/manga_studio.py inventory [path]
python3 scripts/manga_studio.py import [path]
python3 scripts/manga_studio.py validate [path] --profile story
python3 scripts/manga_studio.py validate [path] --profile preproduction
python3 scripts/manga_studio.py validate [path] --profile production
python3 scripts/manga_studio.py status [path]
python3 scripts/manga_studio.py doctor
```

Additional deterministic helpers provide `hash`, `stable-id`, `version`, `diff`, and `check-locks`. Creative and editorial judgments remain in their owning skills.

## Source Inventory And Import

Run `inventory` before `import`. Inventory records relative path, extension, size, nanosecond modification time, SHA-256 checksum, suggested classification, support status, adapter, and persistent document ID. Classifications are `manuscript`, `outline`, `notes`, `reference`, or `unknown`; a user can mark them `approved`, `corrected`, or `rejected` before import.

Core adapters are deterministic UTF-8 plain text (`.txt`) and Markdown (`.md`, `.markdown`). Other files remain in place, are inventoried as unsupported, and receive an actionable message. Import creates a byte-identical immutable snapshot and a separate normalized derivative. A changed source checksum blocks import or validation rather than being silently accepted.

Stable mappings are project-local for source documents, chapters, scenes, characters, locations, organizations, props, timeline events, plot threads, and setups/payoffs. Safe moves retain IDs through checksum-plus-path-history matching; ambiguous matches require review.

## Stage Gates

The project records these explicit gates:

```text
SOURCE_LOCKED
CANON_APPROVED
DIAGNOSTIC_APPROVED
REVISION_PLAN_APPROVED
MANUSCRIPT_APPROVED
STORY_LOCKED
STORYBOARD_APPROVED
STORYBOARD_LOCKED
IMAGE_READY
```

`image_generation_enabled` and `IMAGE_READY` default to `false`. IMAGE_READY can pass only when canon, story, and storyboard prerequisites are approved/locked, image generation is explicitly enabled, continuity is approved, and provenance checks pass. Deferred image-job examples may be validated structurally before then, but no active job may be released.

Validation profiles are cumulative:

- `story` validates configuration, source inventory, snapshots, provenance, active story versions, approvals, and locks without requiring images.
- `preproduction` adds storyboards, page/panel plans, continuity structures, and deferred image-job validation without requiring generated files.
- `production` additionally requires all image gates, approved references and panels, composed pages, lettering, and export dependencies.

## Codex-To-ChatGPT Handoff

1. Codex creates a versioned JSON job under `.manga-studio/handoff/pending/`.
2. The job remains `deferred` with explicit blockers until IMAGE_READY passes.
3. Before release, Codex validates the job strictly. Every required reference path must name a real file under `.manga-studio/handoff/approved/`; locked references cannot change silently.
4. The user submits the released job to ChatGPT Image Generation outside Codex.
5. The returned file is stored at the job's new versioned path under `handoff/generated/`. Older files are never overwritten.
6. Codex validates intake and creates a structured continuity review. Approval is explicit; accepted copies/records are linked under `handoff/approved/`.
7. Corrections are new jobs and outputs under `handoff/corrections/`, with revision lineage and a distinct filename.
8. The page compositor accepts only approved panel files. Lettering is added as a separate vector layer after composition.
9. Final continuity review precedes export.

Panel jobs prohibit dialogue text, captions, speech balloons, sound-effect text, panel borders, page numbers, signatures, and watermarks. Covers, splash pages, references, panels, and corrections follow the same external-generation boundary.

## Skill Source And Installation

`skills-src/` is the canonical source for one master skill and sixteen specialists. `manifests/manga-skills.json` lists exactly those 17 names and versions. Repository-scoped entries in `.agents/skills/` point to the canonical source.

Installation supports user scope plus symlink or copy mode. It validates every skill, reports create/replace/preserve/reject decisions, refuses non-Manga collisions, and backs up managed replacements for rollback. It only targets `$HOME/.agents/skills/` in normal use.

This readiness pass does not perform a real user installation. Preview it with:

```bash
python3 scripts/install_skills.py --scope user --mode symlink --dry-run
python3 scripts/uninstall_skills.py --scope user --dry-run
python3 scripts/doctor.py
```

## Pilot Fixture

`projects/pilot-001/` is an isolated compatibility fixture, not a default or template. Its title, characters, location, prop, four-panel page plan, and eight sample image jobs are examples only. Its workflow phase is `story_foundation`, image generation is disabled, IMAGE_READY is false, all jobs are deferred, and story/preproduction validation does not require absent images.

## Production Commands

These commands remain blocked until approved production dependencies and gates exist:

```bash
python3 scripts/compose_page.py .manga-studio/pages/page-001.json --project <story-directory>
python3 scripts/add_lettering.py .manga-studio/pages/page-001.json --project <story-directory>
python3 scripts/export_chapter.py --project <story-directory> [--chapter-id chapter-id]
```

The export script supports projects with or without chapters.

## Tests

```bash
python3 -m unittest discover -s tests
find . -name '*.json' -not -path './.git/*' -print0 | xargs -0 -n1 python3 -m json.tool >/dev/null
python3 -m compileall -q scripts tests
```

The temporary fixtures cover single-file stories, nested chapter files, existing AGENTS instructions, unusual/unsupported layouts, new stories, continuations, simultaneous stories, nested discovery, pilot isolation, original-file safety, installer rollback, and uninstall isolation.
