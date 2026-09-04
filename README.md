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
    |-- source/                       inventory, stable IDs, snapshots, normalized versions, source maps, provenance
    |-- story/                        story models, chapters, scenes, and arcs
    |-- canon/                        story canon, timelines, relationships, threads, setups/payoffs
    |-- analysis/diagnostics/         structured reports plus optional Markdown companions
    |-- revisions/                    policies, plans, change sets, and deterministic diffs
    |-- manuscript/versions/          non-overwriting manuscript versions
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
python3 scripts/manga_studio.py structure [path]
python3 scripts/manga_studio.py validate-source-map [path]
python3 scripts/manga_studio.py show-structure [path]
python3 scripts/manga_studio.py migrate [path]
python3 scripts/manga_studio.py diagnose <draft.json> --project <path> [--markdown]
python3 scripts/manga_studio.py export-chatgpt-handoff <job.json> --project <path>
python3 scripts/manga_studio.py approve <target> --artifact-type <type> --target-version <version> --actor <actor> --project <path>
python3 scripts/manga_studio.py reject <target> --artifact-type <type> --target-version <version> --actor <actor> --project <path>
python3 scripts/manga_studio.py validate-approval <approval.json> --project <path>
python3 scripts/manga_studio.py set-lock <GATE> --approval <approval.json> --actor <actor> --project <path>
python3 scripts/manga_studio.py clear-lock <GATE> --actor <actor> --project <path>
python3 scripts/manga_studio.py validate-locks [path]
python3 scripts/manga_studio.py apply-change-set <change-set.json> --actor <actor> --project <path>
python3 scripts/manga_studio.py validate [path] --profile story
python3 scripts/manga_studio.py validate [path] --profile preproduction
python3 scripts/manga_studio.py validate [path] --profile production
python3 scripts/manga_studio.py status [path]
python3 scripts/manga_studio.py doctor
```

Additional deterministic helpers provide `hash`, `stable-id`, `version`, `diff`, and `check-locks`. Creative and editorial judgments remain in their owning skills; scripts enforce structure, provenance, schema, approval, and versioning contracts.

## Source Inventory And Import

Run `inventory` before `import`. Inventory records relative path, extension, size, nanosecond modification time, SHA-256 checksum, suggested classification, support status, adapter, and persistent document ID. Import is allowed only when `classification_status` is `approved` or `corrected`, `usage_role` is explicit, and the stable document match is unambiguous. Roles are `primary_manuscript`, `supplementary_manuscript`, `outline`, `author_notes`, `canon_reference`, `research`, and `excluded`; excluded, suggested, unknown, ambiguous, and rejected records do not import.

Core adapters are deterministic UTF-8 plain text (`.txt`) and Markdown (`.md`, `.markdown`). Other files remain in place, are inventoried as unsupported, and receive an actionable message. Import creates a byte-identical immutable snapshot and a versioned normalized derivative. Provenance records normalized SHA-256, adapter name/version, normalization profile, parser version, and source-map checksum. Changed sources, snapshots, normalized derivatives, or maps fail validation; an adapter/profile version change creates a distinct derivative path.

Stable mappings are project-local for source documents, chapters, scenes, source units, characters, locations, organizations, props, timeline events, plot threads, and setups/payoffs. Classification follows `document_id` across a safe move. Checksum matches to multiple absent document records are ambiguous and block import.

## Structural Parsing

`structure` parses approved imported UTF-8 Markdown and plain text without changing originals or normalized derivatives. It recognizes explicit chapter/scene headings, file-per-chapter and single-document modes, chapterless stories, explicit markup boundaries, approved manual boundaries, paragraph order, and deterministic dialogue forms. Duplicate display titles are allowed because stable IDs derive from project-local source positions rather than titles.

Each immutable parser-versioned source map records document/chapter/scene/source-unit IDs, relative source path, heading path, source order, inclusive line ranges, half-open UTF-8 byte ranges, content fingerprint, parser version, and ambiguity status. Generic headings and thematic separators are emitted as `review_required`; `validate-source-map` refuses them until a manual boundary decision resolves the ambiguity.

## Story Engine Contracts

Schema v3 adds source documents/maps, story models/arcs, chapters/scenes, story canon, timeline events, relationships, plot threads, setups/payoffs, character state, voice guides, story issues, diagnostic reports, revision policy/plan/change set, approvals, decisions, and stage locks. Story canon is distinct from visual-production references and never requires an image.

Canon represents confirmed, provisional, inferred, contradictory, deprecated, and unknown facts. Every fact needs mapped source evidence or an approved decision. Continuity artifacts can track knowledge, relationships, injuries/physical state, outfits, carried items, locations, prop ownership/condition, world rules, open threads, setups/payoffs, secrets, and promises.

`manga-story-diagnostician` owns editorial judgment and publishes schema-valid reports through `diagnose`. Findings contain unique IDs, category, severity, confidence, status, why-it-matters, mapped evidence, affected chapter/scene IDs, related entity IDs, alternatives, uncertainty, and manga-adaptation impact. Diagnostics never edit source, canon, or manuscripts. Tests validate contracts and expected fixture coverage; they do not claim to measure creative quality.

Revision policies are `conservative`, `balanced`, or `transformative`. Plans and change sets record targets, triggering issues, evidence, operation, expected result, alternatives, preservation requirements, voice/canon/continuity/structural impact, dependencies, acceptance criteria, and approval status. `apply-change-set` accepts only a separately approved, hash-matching change set aimed at a managed manuscript version. It creates a new manuscript version, unified diff, and decision record; it never overwrites source or prior versions and never changes canon implicitly.

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

`image_generation_enabled` and `IMAGE_READY` default to `false`. Every approval binds project ID, artifact type/path/version, target SHA-256, decision, actor, timestamp, notes, and supersession state. Validation checks that the target exists and still hashes identically. Every active gate has a versioned lock record pointing to valid approvals and prerequisite locks; a loose approval file or boolean cannot satisfy a gate.

IMAGE_READY can pass only when canon, story, and storyboard prerequisites are approved/locked, image generation is explicitly enabled, continuity has a valid hash-bound approval, and provenance checks pass. Deferred image-job examples may be validated structurally before then, but no active job may be released. Skills may propose artifacts but may not approve or lock their own output.

Validation profiles are cumulative:

- `story` validates inventory approval, snapshots, normalized hashes, source maps and stable IDs, present story/canon/continuity/editorial artifacts, manuscript versions and decisions, approvals, diffs, and stage locks without requiring images.
- `preproduction` additionally validates present storyboard versions, page/panel plans, continuity snapshots, and deferred image jobs without requiring generated files.
- `production` additionally requires all image gates, approved references and panels, composed pages, lettering, and export dependencies.

## Codex-To-ChatGPT Handoff

1. Codex creates a versioned JSON job under `.manga-studio/handoff/pending/`.
2. The job remains `deferred` with explicit blockers until IMAGE_READY passes.
3. Before release, Codex validates the job strictly. Every required reference path must name a real file under `.manga-studio/handoff/approved/`; locked references cannot change silently.
4. Codex runs `export-chatgpt-handoff` for a `ready` or `released` job. The deterministic same-name Markdown embeds the canonical JSON, requested output filename, instructions, and an ordered checklist of real approved attachments with SHA-256 hashes.
5. The user attaches exactly the listed files, pastes the entire Markdown into ChatGPT Image Generation, and requests the image. Deferred jobs, missing or unlocked attachments, failed gates, and cross-project paths block export.
6. The returned file is stored at the job's new versioned path under `handoff/generated/`. Older files are never overwritten.
7. Codex validates intake and creates a structured continuity review. Approval is explicit; accepted copies/records are linked under `handoff/approved/`.
8. Corrections are new jobs, Markdown packets, and outputs under `handoff/corrections/`, with revision lineage and a distinct filename.
9. The page compositor accepts only approved panel files. Lettering is added as a separate vector layer after composition.
10. Final continuity review precedes export.

The canonical job remains JSON. The Markdown is a deterministic transport packet, not a second editable source of truth. By default it is written beside the job with the same basename; `--stdout` prints it for direct copying, and `--output` selects another project-relative `.md` path under `handoff/pending/`. An existing different Markdown file is never overwritten.

```bash
python3 scripts/manga_studio.py export-chatgpt-handoff \
  .manga-studio/handoff/pending/<job-id>.json \
  --project <story-directory>
```

Panel jobs prohibit dialogue text, captions, speech balloons, sound-effect text, panel borders, page numbers, signatures, and watermarks. Covers, splash pages, references, panels, and corrections follow the same external-generation boundary.

## Skill Source And Installation

`skills-src/` is the canonical source for one master skill and sixteen specialists. `manifests/manga-skills.json` lists exactly those 17 names and versions. Repository-scoped entries in `.agents/skills/` point to the canonical source.

Installation supports user scope plus symlink or copy mode. Both modes install a self-contained shared runtime under `$HOME/.agents/skills/.manga-studio-runtime/versions/3.0.0/` and a stable launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py`. The runtime contains scripts, schemas, templates, manifests, and `VERSION`; `.manga-studio-install.json` records custom destinations. Installation is staged and transactional, refuses non-Manga collisions and broken replacements, backs up prior managed files, and automatically restores them after a partial failure.

This readiness pass does not perform a real user installation. Preview it with:

```bash
python3 scripts/install_skills.py --scope user --mode symlink --dry-run
python3 scripts/uninstall_skills.py --scope user --dry-run
python3 scripts/rollback_install.py --scope user
python3 scripts/doctor.py
```

`doctor.py --mode repository` validates development links, runtime/schema/template availability, manifest/version agreement, Python compilation, skill frontmatter, and invocation from an unrelated directory. `--mode installed` additionally validates the registry, symlink or copy semantics, broken links, duplicate personal skill identities, installed runtime payload, and installed launcher. This completion pass runs temporary installation tests and dry runs only; it does not install user-scoped skills.

## Schema Migration

New workspaces use schema `3.0.0`. `migrate` upgrades a v2 project in place only after copying its managed metadata to `.manga-studio/migrations/v2-to-v3/`. It adds stage-lock record pointers, usage-role fields, normalized provenance metadata, and source-unit IDs without changing original story files or inventing classification approvals. Legacy suggested classifications remain blocked until reviewed, and migrated imports require `structure` to add source-map checksums.

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

The temporary fixtures cover classification gating, safe moves and ambiguous IDs, single-file/chapterless/file-per-chapter/multi-chapter structures, manual ambiguity behavior, provenance tamper detection, diagnostics evidence, malformed editorial artifacts, versioned revision application, approval invalidation, lock prerequisites, simultaneous-story isolation, installer rollback, copy/symlink runtime use, and uninstall isolation.

CI lives at `.github/workflows/ci.yml` and runs unit tests, JSON parsing, pilot schema/profile validation, Python compilation, skill frontmatter/repository doctor checks, installer dry-run, and a disposable multi-story smoke test.

## Current Limitations

Core source adapters intentionally support only UTF-8 Markdown and plain text. Generic headings and separator lines require human boundary review. The deterministic revision executor currently supports exact `replace_text`, `append_text`, and `insert_after` operations; higher-level prose generation remains owned by the writing skills. Diagnostics are structured editorial outputs, not automatic proof of story quality. Image generation stays disabled by default and all artwork remains external to Codex.
