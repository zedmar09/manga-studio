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
    |-- story/briefs/                 versioned creative promise, audience, structure, and safety boundaries
    |-- story/success-plans/          versioned goals, audience hypotheses, release strategy, and learning loops
    |-- story/                        story models, chapters, scenes, and arcs
    |-- canon/                        story canon, timelines, relationships, threads, setups/payoffs
    |-- analysis/diagnostics/         structured reports plus optional Markdown companions
    |-- revisions/                    policies, plans, change sets, and deterministic diffs
    |-- manuscript/versions/          non-overwriting manuscript versions
    |-- storyboard/nemu/              structured geometry-only thumbnail plans
    |-- continuity/intake/            technical records for externally returned images
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
    |-- production/preflight/         versioned physical print checks
    |-- fonts/                        optional project-local TTF/OTF assets
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
python3 scripts/manga_studio.py compose-page <page.json> --project <path>
python3 scripts/manga_studio.py add-lettering <page.json> --project <path>
python3 scripts/manga_studio.py review-page <page.json> --project <path>
python3 scripts/manga_studio.py validate-generated-image <job.json> <image> --project <path>
python3 scripts/manga_studio.py preflight-print --project <path>
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

Schema v3 adds source documents/maps, story models/arcs, chapters/scenes, story canon, timeline events, relationships, plot threads, setups/payoffs, character state, voice guides, story issues, diagnostic reports, revision policy/plan/change set, approvals, decisions, and stage locks. Runtime 3.3 adds a versioned creative brief and success plan, structured nemu, richer dramatic character profile, generated-image intake, physical print profile/preflight, and an explicit human visual-assessment contract. Story canon is distinct from visual-production references and never requires an image.

The creative brief records premise, core message, thematic question, reader takeaway, story promise, target audience, content boundaries, genre/tone, target length, opening strategy, optional structural framework, originality boundaries, and show-don't-tell policy. Needle-drop openings and Kishotenketsu are available strategies, not mandatory formulas. Production characters also record external desire, internal need, fear, stakes, flaw, contradiction, moral limits, arc direction, voice principles, and relationship drivers; scene-by-scene state remains a separate contract.

The optional success plan defines what success means for this particular project instead of treating popularity as a guaranteed result. It links to the exact creative brief by checksum and records one to three primary outcomes, intended readers and reader need, genre/demographic/format promises, evidence-labelled market hypotheses, a logline and early hook, sustainable release capacity, distribution status, discoverability and community strategy, collaborator scope/payment/credit/IP requirements, repeatable efficiency practices, rights checks, feedback checkpoints, limited metrics, source-linked observations, bounded experiments, pivot rules, protected creative elements, and risks. Current market/platform claims require dated evidence; legal or contract decisions remain with the author or a qualified professional. Metrics may guide a revision proposal but never outrank canon, author voice, audience boundaries, source immutability, rights, or creator health.

All visual success-plan deliverables keep the architecture boundary. Codex may write a pitch or metadata; covers, thumbnails, promo strips, key images, and reference sheets become gated ChatGPT Image Generation Jobs; video and other non-image media require an explicitly external owner.

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

IMAGE_READY can pass only when canon, story, and storyboard prerequisites are approved/locked, the active creative brief and structured nemu have current hash-bound approvals, image generation is explicitly enabled, continuity has a valid hash-bound approval, and provenance checks pass. Deferred image-job examples may be validated structurally before then, but no active job may be released. Skills may propose artifacts but may not approve or lock their own output.

Validation profiles are cumulative:

- `story` validates inventory approval, snapshots, normalized hashes, source maps and stable IDs, present creative briefs and success plans, story/canon/continuity/editorial artifacts, manuscript versions and decisions, approvals, diffs, and stage locks without requiring images.
- `preproduction` additionally validates the active brief/nemu, production-character dramatic profiles, storyboard versions, page/panel plans, normalized safe-zone/source-canvas alignment, continuity snapshots, and deferred image jobs without requiring generated files.
- `production` additionally requires all image gates, technically inspected and human-reviewed approved panels, composed pages, lettering, export dependencies, and a current approved print preflight when print output is configured.

## Codex-To-ChatGPT Handoff

1. Codex creates a versioned image-job `1.3.0` JSON under `.manga-studio/handoff/pending/`. It declares exact output format/dimensions/mode/alpha, the approved audience and content boundaries, source-normalized safe zones, event/staging, black-and-white line/black/tone/contrast/depth/motion strategy, and job-type-specific reference-sheet requirements. Active production jobs require a `high` profile with locked continuity, explicit quality goals, and a self-check.
2. The job remains `deferred` with explicit blockers until IMAGE_READY passes.
3. Before release, Codex validates the job strictly. Every required reference path must name a real file under `.manga-studio/handoff/approved/`; locked references cannot change silently.
4. Codex runs `export-chatgpt-handoff` for a `ready` or `released` job. The deterministic same-name Markdown embeds the canonical JSON, requested output filename, instructions, and an ordered checklist of real approved attachments with SHA-256 hashes.
5. The user attaches exactly the listed files, pastes the entire Markdown into ChatGPT Image Generation, and requests the image. Deferred jobs, missing or unlocked attachments, failed gates, and cross-project paths block export.
6. The returned file is stored at the job's exact new versioned path under `handoff/generated/`. Older files are never overwritten.
7. Codex runs `validate-generated-image`. The versioned intake records SHA-256, signature-derived format, dimensions, color container, bit depth, alpha, and size. Path, format, size, or forbidden-alpha failures block intake; a color-capable container triggers visual review rather than pretending to prove visible color.
8. A person inspects the actual image and records story clarity, event readability, reference adherence, acting, composition, monochrome finish, continuity, lettering-space usability, audience/content compliance, required/prohibited-element checks, and artifacts in a `human_visual_assessment`. Approval requires every scored dimension to reach 4/5, all binary checks to pass, no unresolved error finding, and a hash-current intake; production then verifies that approved panel bytes match the intake hash.
9. Corrections are new jobs, Markdown packets, and outputs under `handoff/corrections/`, with revision lineage, a source review, bounded requested changes, preservation requirements, and a distinct filename.
10. The page compositor accepts only approved panel files. Lettering is added as a separate vector layer after composition.
11. Final continuity review and any required approved print preflight precede export.

The canonical job remains JSON. The Markdown is a deterministic transport packet, not a second editable source of truth. By default it is written beside the job with the same basename; `--stdout` prints it for direct copying, and `--output` selects another project-relative `.md` path under `handoff/pending/`. An existing different Markdown file is never overwritten.

```bash
python3 scripts/manga_studio.py export-chatgpt-handoff \
  .manga-studio/handoff/pending/<job-id>.json \
  --project <story-directory>
```

After ChatGPT returns the file at the requested path:

```bash
python3 scripts/manga_studio.py validate-generated-image \
  .manga-studio/handoff/pending/<job-id>.json \
  .manga-studio/handoff/generated/<returned-file> \
  --project <story-directory>
```

Panel jobs prohibit dialogue text, captions, speech balloons, sound-effect text, panel borders, page numbers, signatures, watermarks, and color. Covers, splash pages, references, thumbnails, panels, and corrections follow the same external-generation boundary.

## Professional Page Pipeline

Page specifications can describe an event-driven manga page without embedding any artwork. Each panel carries a source canvas, source-normalized dialogue-safe zones, one dominant event, intensity, importance, emotional beat, show-don't-tell cue, shot size, camera angle and motion, screen direction, transition, and continuity anchors. A structured nemu records normalized panel blocks, balloon placeholders, reading sequence, focus, pacing, and page-turn logic before panel jobs are released.

The compositor supports rectangular or polygon-clipped panels, focus-aware cover/contain placement, diagonal frames, insets, controlled overlap, z-index ordering, bleed intent, and per-panel borders. The same image transform projects normalized safe zones into page coordinates, so focus crops cannot silently remove lettering space. It links only hash-matching approved images and writes a new SVG version instead of changing artwork or overwriting an earlier composition.

Lettering remains a separate vector layer. It supports speech, captions, thoughts, whispers, shouts, radio dialogue, narration, and structured SFX; multiple balloon treatments; horizontal or vertical writing; ruby/furigana; rotation; tails; project-local TTF/OTF metrics and optional embedding; Latin or Japanese line breaking with kinsoku constraints; automatic fitting; safe-zone/collision checks; and unique reading order. SFX records source, meaning, intensity, language, and translation context so sound remains understandable rather than decorative.

`review_page.py` creates a versioned report covering geometry, safe zones, reading order, text fit, lettering collisions, shot/camera variety, action-axis changes, continuity handoffs, pacing, and page-impact planning indicators. These numbers have `metric_scope: planning_indicators`; they never claim to score rendered drawing quality. Actual art uses a separate `human_visual_assessment`. A clean report is `review_ready`, never automatically `approved`.

For print or dual output, `preflight-print` converts trim, per-edge bleed, safe margins, binding gutter, page side, and DPI into exact canvas and safe-area requirements. Its report is bound to the current project checksum, and print production requires explicit approval. The deterministic export package remains SVG in this release; printer-specific PDF/PNG/TIFF rendering is an explicit downstream limitation.

```bash
python3 scripts/manga_studio.py review-page \
  .manga-studio/pages/<page-id>.json \
  --project <story-directory>
```

## Skill Source And Installation

`skills-src/` is the canonical source for one master skill and sixteen specialists. `manifests/manga-skills.json` lists exactly those 17 names and versions. Repository-scoped entries in `.agents/skills/` point to the canonical source.

Installation supports user scope plus symlink or copy mode. Both modes install a self-contained shared runtime under `$HOME/.agents/skills/.manga-studio-runtime/versions/3.3.0/` and a stable launcher at `$HOME/.agents/skills/.manga-studio-runtime/manga-studio.py`. The runtime contains scripts, schemas, templates, manifests, and `VERSION`; `.manga-studio-install.json` records custom destinations. Installation is staged and transactional, refuses non-Manga collisions and broken replacements, backs up prior managed files, and automatically restores them after a partial failure.

Preview or install it with:

```bash
python3 scripts/install_skills.py --scope user --mode symlink --dry-run
python3 scripts/install_skills.py --scope user --mode copy
python3 scripts/uninstall_skills.py --scope user --dry-run
python3 scripts/rollback_install.py --scope user
python3 scripts/doctor.py
```

`doctor.py --mode repository` validates development links, runtime/schema/template availability, manifest/version agreement, Python compilation, skill frontmatter, and invocation from an unrelated directory. `--mode installed` additionally validates the registry, symlink or copy semantics, broken links, duplicate personal skill identities, installed runtime payload, and installed launcher. This completion pass runs temporary installation tests and dry runs only; it does not install user-scoped skills.

## Schema Migration

New workspaces use schema `3.0.0`. `migrate` upgrades a v2 project in place only after copying its managed metadata to `.manga-studio/migrations/v2-to-v3/`. For an existing v3 workspace, the same command adds missing runtime-3.3 directories and compatible default fields without touching story sources. It adds stage-lock record pointers, usage-role fields, normalized provenance metadata, source-unit IDs, and the optional active-success-plan field without inventing classification approvals. Legacy suggested classifications remain blocked until reviewed, and migrated imports require `structure` to add source-map checksums.

## Pilot Fixture

`projects/pilot-001/` is an isolated compatibility fixture, not a default or template. Its title, characters, location, prop, four-panel page plan, success plan, and eight sample image jobs are examples only. Its workflow phase is `story_foundation`, image generation is disabled, IMAGE_READY is false, all jobs are deferred, and story/preproduction validation does not require absent images.

## Production Commands

These commands remain blocked until approved production dependencies and gates exist:

```bash
python3 scripts/manga_studio.py compose-page .manga-studio/pages/page-001.json --project <story-directory>
python3 scripts/manga_studio.py add-lettering .manga-studio/pages/page-001.json --project <story-directory>
python3 scripts/manga_studio.py review-page .manga-studio/pages/page-001.json --project <story-directory>
python3 scripts/manga_studio.py validate-generated-image .manga-studio/handoff/pending/<job>.json .manga-studio/handoff/generated/<image> --project <story-directory>
python3 scripts/manga_studio.py preflight-print --project <story-directory>
python3 scripts/export_chapter.py --project <story-directory> [--chapter-id chapter-id]
```

Composition, lettering, reviews, and export packages use new `-v###` outputs and refuse overwrite. The export script supports projects with or without chapters.

## Tests

```bash
python3 -m unittest discover -s tests
find . -name '*.json' -not -path './.git/*' -print0 | xargs -0 -n1 python3 -m json.tool >/dev/null
python3 -m compileall -q scripts tests
```

The temporary fixtures cover classification gating, safe moves and ambiguous IDs, single-file/chapterless/file-per-chapter/multi-chapter structures, manual ambiguity behavior, provenance tamper detection, diagnostics evidence, malformed editorial artifacts, versioned revision application, approval invalidation, lock prerequisites, success-plan schema limits and creative-brief hash drift, normalized page geometry, external-image intake success/failure, physical print preflight, simultaneous-story isolation, installer rollback, copy/symlink runtime use, and uninstall isolation.

CI lives at `.github/workflows/ci.yml` and runs unit tests, JSON parsing, pilot schema/profile validation, Python compilation, skill frontmatter/repository doctor checks, installer dry-run, and a disposable multi-story smoke test.

## Current Limitations

Core source adapters intentionally support only UTF-8 Markdown and plain text. Generic headings and separator lines require human boundary review. The deterministic revision executor supports exact `replace_text`, `append_text`, and `insert_after`; higher-level prose generation remains owned by writing skills. Success planning does not fetch platform analytics, conduct live audience research, provide legal advice, or predict publication, readership, or revenue; those inputs remain external and must be evidence-labelled. Page scores are planning indicators, not proof of artistic or narrative quality. Font parsing covers common SFNT TrueType/OpenType horizontal metrics, while complex shaping, vertical glyph substitution, and full language-specific typography still require a dedicated layout engine. Technical intake reads PNG/JPEG/WebP/TIFF headers but cannot prove visible monochrome content or artistic quality. Print preflight validates geometry and profile state, while the export package is still SVG rather than printer-rendered PDF/PNG/TIFF. External image results remain variable and require human review against locked references. Image generation stays disabled by default and all artwork remains external to Codex.
