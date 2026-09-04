from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from helpers import REPO_ROOT, approve_inventory, initialize, read_json, write_json
from manga_studio.adapters import ADAPTERS_BY_NAME, MarkdownAdapter
from manga_studio.approvals import (
    invalidate_stale_approvals,
    record_approval,
    set_lock,
    validate_approval,
    validate_locks,
)
from manga_studio.json_schema import validate_json_file
from manga_studio.migration import migrate_project
from manga_studio.profiles import validate_profile
from manga_studio.project import import_sources, inventory_sources, sha256_file
from manga_studio.project import discover_project
import manga_studio.project as project_module
from manga_studio.revisions import apply_change_set
from manga_studio.structure import structure_sources, validate_source_maps


def source_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_story(root: Path):
    root.mkdir(parents=True)
    source = root / "story.md"
    source.write_text(
        "# Chapter 1: Arrival\n\n## Scene 1: Echo\n\nMARA: We made it.\n\n"
        "# Chapter 2: Return\n\n## Scene 2: Echo\n\nThe same title identifies a different scene.\n",
        encoding="utf-8",
    )
    context = initialize(root)
    inventory = inventory_sources(context)
    write_json(context.workspace_path("source/manual-boundaries.json"), {
        "schema_version": "3.0.0",
        "project_id": context.config["project_id"],
        "boundaries": [
            {"document_id": inventory["files"][0]["document_id"], "line": 3, "kind": "scene", "title": "Echo"},
            {"document_id": inventory["files"][0]["document_id"], "line": 9, "kind": "scene", "title": "Echo"},
        ],
    })
    approve_inventory(context)
    import_sources(context)
    structure = structure_sources(context)
    return context, source, structure


def fake_evidence(project_id: str) -> dict:
    return {
        "project_id": project_id,
        "document_id": "doc-evidence",
        "chapter_id": "chapter-evidence",
        "scene_id": "scene-evidence",
        "source_unit_id": "source-unit-evidence",
        "source_relative_path": "story.md",
        "line_start": 1,
        "line_end": 1,
        "byte_start": 0,
        "byte_end": 1,
        "content_fingerprint": "0" * 64,
    }


def change_set(project_id: str, target_rel: str, target_sha: str, status: str = "proposed") -> dict:
    impact = {"level": "low", "notes": "Scoped wording change."}
    return {
        "schema_version": "3.0.0",
        "project_id": project_id,
        "change_set_id": "change-set-ending",
        "version": "v001",
        "revision_policy_id": "policy-balanced",
        "revision_plan_id": "revision-plan-v001",
        "target_stable_ids": ["scene-ending"],
        "triggering_issue_ids": ["issue-ending"],
        "source_evidence": [fake_evidence(project_id)],
        "operation": {
            "type": "replace_text",
            "target_relative_path": target_rel,
            "target_sha256": target_sha,
            "before": "The door closes.",
            "after": "The door closes, and the warning bell rings.",
        },
        "expected_result": "End on a consequential warning beat.",
        "alternatives": ["Move the warning to the next opening."],
        "preserve": ["Point of view", "direct prose voice"],
        "author_voice_impact": impact,
        "canon_impact": {"level": "none", "notes": "No canon change is authorized."},
        "continuity_impact": impact,
        "structural_impact": impact,
        "dependencies": [],
        "acceptance_criteria": ["Original manuscript remains byte-identical.", "A new version and diff exist."],
        "approval_status": status,
    }


class SourceApprovalAndStructureTests(unittest.TestCase):
    def test_v2_migration_preserves_original_source_and_metadata_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "legacy"
            root.mkdir()
            source = root / "story.md"
            source.write_text("Legacy source.\n", encoding="utf-8")
            before = source.read_bytes()
            context = initialize(root)
            config = read_json(context.project_file)
            config["schema_version"] = "2.0.0"
            config.pop("stage_lock_records")
            write_json(context.project_file, config)
            id_map = read_json(context.workspace_path("source/id-map.json"))
            id_map["schema_version"] = "2.0.0"
            id_map["namespaces"].pop("source_units")
            write_json(context.workspace_path("source/id-map.json"), id_map)
            context = discover_project(root)

            actions = migrate_project(context)

            self.assertTrue(any("3.0.0" in action for action in actions))
            self.assertEqual(source.read_bytes(), before)
            self.assertTrue(context.workspace_path("migrations/v2-to-v3/project.json").is_file())
            self.assertEqual(read_json(context.project_file)["schema_version"], "3.0.0")

    def test_suggested_and_rejected_sources_are_not_imported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "story"
            root.mkdir()
            source = root / "story.md"
            source.write_text("# Chapter 1: Draft\n", encoding="utf-8")
            before = source_digest(source)
            context = initialize(root)
            inventory = inventory_sources(context)

            suggested = import_sources(context)
            self.assertEqual(suggested["import_summary"]["imported"], 0)
            self.assertTrue(suggested["import_summary"]["blocked"])
            inventory["files"][0]["classification_status"] = "rejected"
            inventory["files"][0]["usage_role"] = "excluded"
            write_json(context.workspace_path("source/inventory.json"), inventory)
            rejected = import_sources(context)

            self.assertEqual(rejected["import_summary"]["imported"], 0)
            self.assertEqual(rejected["import_summary"]["blocked"], [])
            self.assertEqual(source_digest(source), before)
            self.assertFalse(context.workspace_path("source/snapshots").exists())

    def test_approved_source_imports_and_duplicate_titles_keep_distinct_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, source, structure = prepare_story(Path(temporary) / "story")
            map_path = context.project_path(structure["documents"][0]["source_map_path"])
            source_map = read_json(map_path)

            self.assertEqual(validate_source_maps(context), [])
            self.assertEqual(len(source_map["chapters"]), 2)
            self.assertEqual([scene["display_title"] for scene in source_map["scenes"]], ["Echo", "Echo"])
            self.assertEqual(len({scene["scene_id"] for scene in source_map["scenes"]}), 2)
            self.assertTrue(any(unit["unit_type"] == "dialogue" for unit in source_map["source_units"]))
            first_ids = structure["documents"][0]["source_unit_ids"]
            self.assertEqual(structure_sources(context)["documents"][0]["source_unit_ids"], first_ids)
            self.assertEqual(validate_profile(context, "story"), [])
            self.assertTrue(source.is_file())

    def test_chapterless_plain_text_receives_an_implicit_chapter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "chapterless"
            root.mkdir()
            (root / "novel.txt").write_text("A beginning without headings.\n\nA second paragraph.\n", encoding="utf-8")
            context = initialize(root)
            inventory_sources(context)
            approve_inventory(context)
            import_sources(context)
            result = structure_sources(context)
            source_map = read_json(context.project_path(result["documents"][0]["source_map_path"]))

            self.assertEqual(len(source_map["chapters"]), 1)
            self.assertEqual(source_map["chapters"][0]["boundary"]["origin"], "implicit_chapterless")
            self.assertEqual(source_map["source_units"][0]["line_start"], 1)
            self.assertEqual(source_map["structure_status"], "parsed")

    def test_leading_prose_before_explicit_chapter_is_retained_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "leading-prose"
            root.mkdir()
            source = root / "story.md"
            source.write_text(
                "A note before the numbered chapters.\n\n# Chapter 1: Arrival\n\nThe story begins.\n",
                encoding="utf-8",
            )
            before = source.read_bytes()
            context = initialize(root)
            inventory_sources(context)
            approve_inventory(context)
            import_sources(context)
            result = structure_sources(context)
            source_map = read_json(context.project_path(result["documents"][0]["source_map_path"]))

            self.assertEqual(source_map["chapters"][0]["boundary"]["origin"], "implicit_leading_content")
            self.assertEqual(source_map["chapters"][0]["display_title"], "Front Matter")
            self.assertEqual(source_map["source_units"][0]["line_start"], 1)
            self.assertEqual(source_map["source_units"][0]["chapter_id"], source_map["chapters"][0]["chapter_id"])
            self.assertEqual(source_map["structure_status"], "review_required")
            self.assertEqual(source.read_bytes(), before)

    def test_filename_pattern_supports_file_per_chapter_without_title_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "file-chapters"
            root.mkdir()
            (root / "chapter-01.md").write_text("# Dawn\n\nOpening.\n", encoding="utf-8")
            context = initialize(root)
            inventory_sources(context)
            approve_inventory(context)
            import_sources(context)
            result = structure_sources(context)
            source_map = read_json(context.project_path(result["documents"][0]["source_map_path"]))

            self.assertEqual(source_map["structure_status"], "parsed")
            self.assertEqual(source_map["chapters"][0]["display_title"], "Dawn")
            self.assertEqual(source_map["chapters"][0]["boundary"]["origin"], "implicit_file_chapter")

    def test_generic_heading_ambiguity_blocks_source_map_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "ambiguous-headings"
            root.mkdir()
            (root / "story.md").write_text("# Dawn\n\nText.\n\n# Dusk\n\nMore.\n", encoding="utf-8")
            context = initialize(root)
            inventory_sources(context)
            approve_inventory(context)
            import_sources(context)
            result = structure_sources(context)

            self.assertEqual(result["documents"][0]["structure_status"], "review_required")
            self.assertTrue(any("ambiguous boundaries require review" in error for error in validate_source_maps(context)))

            first_map = context.project_path(result["documents"][0]["source_map_path"])
            write_json(context.workspace_path("source/manual-boundaries.json"), {
                "schema_version": "3.0.0",
                "project_id": context.config["project_id"],
                "boundaries": [
                    {"document_id": result["documents"][0]["document_id"], "line": 1, "kind": "chapter", "title": "Dawn"},
                    {"document_id": result["documents"][0]["document_id"], "line": 5, "kind": "chapter", "title": "Dusk"},
                ],
            })
            resolved = structure_sources(context)
            second_map = context.project_path(resolved["documents"][0]["source_map_path"])
            self.assertNotEqual(first_map, second_map)
            self.assertTrue(first_map.is_file())
            self.assertEqual(validate_source_maps(context), [])

    def test_ambiguous_document_match_cannot_import(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "ambiguous-id"
            root.mkdir()
            source = root / "new.md"
            source.write_text("same bytes\n", encoding="utf-8")
            context = initialize(root)
            checksum = sha256_file(source)
            id_map = read_json(context.workspace_path("source/id-map.json"))
            id_map["namespaces"]["source_documents"] = [
                {"id": "doc-old-a", "path": "missing-a.md", "checksum": checksum, "aliases": []},
                {"id": "doc-old-b", "path": "missing-b.md", "checksum": checksum, "aliases": []},
            ]
            write_json(context.workspace_path("source/id-map.json"), id_map)
            inventory = inventory_sources(context)
            entry = inventory["files"][0]

            self.assertEqual(entry["id_match_status"], "ambiguous")
            self.assertIsNone(entry["document_id"])
            entry["classification_status"] = "approved"
            entry["usage_role"] = "primary_manuscript"
            write_json(context.workspace_path("source/inventory.json"), inventory)
            imported = import_sources(context)
            self.assertEqual(imported["import_summary"]["imported"], 0)
            self.assertIn("ambiguous", imported["import_summary"]["blocked"][0]["reason"])

    def test_modified_normalized_derivative_and_source_map_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, _, structure = prepare_story(Path(temporary) / "story")
            provenance = read_json(context.workspace_path("source/provenance.json"))
            normalized = context.project_path(provenance["records"][0]["normalized_path"])
            normalized.write_text("tampered\n", encoding="utf-8")
            self.assertTrue(any("normalized derivative checksum changed" in error for error in validate_profile(context, "story")))

            normalized.write_text(
                "# Chapter 1: Arrival\n\n## Scene 1: Echo\n\nMARA: We made it.\n\n"
                "# Chapter 2: Return\n\n## Scene 2: Echo\n\nThe same title identifies a different scene.\n",
                encoding="utf-8",
            )
            source_map = context.project_path(structure["documents"][0]["source_map_path"])
            source_map.write_text(source_map.read_text(encoding="utf-8") + " ", encoding="utf-8")
            self.assertTrue(any("source map checksum changed" in error for error in validate_profile(context, "story")))

    def test_adapter_version_change_creates_a_new_derivative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, _, _ = prepare_story(Path(temporary) / "story")
            first_provenance = read_json(context.workspace_path("source/provenance.json"))
            first_record = first_provenance["records"][0]
            first_path = context.project_path(first_record["normalized_path"])
            first_bytes = first_path.read_bytes()
            original_adapter = ADAPTERS_BY_NAME["markdown"]
            try:
                ADAPTERS_BY_NAME["markdown"] = MarkdownAdapter(version="1.1.0")
                updated = import_sources(context)
            finally:
                ADAPTERS_BY_NAME["markdown"] = original_adapter

            self.assertEqual(len(updated["records"]), 2)
            self.assertEqual(first_path.read_bytes(), first_bytes)
            active = next(record for record in updated["records"] if record["source_status"] == "active")
            self.assertIn("markdown-v1.1.0", active["normalized_path"])
            self.assertNotEqual(active["normalized_path"], first_record["normalized_path"])

    def test_parser_version_change_creates_a_new_derivative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, _, _ = prepare_story(Path(temporary) / "story")
            first = read_json(context.workspace_path("source/provenance.json"))["records"][0]
            first_path = context.project_path(first["normalized_path"])
            first_bytes = first_path.read_bytes()
            original_version = project_module.PARSER_COMPATIBILITY_VERSION
            try:
                project_module.PARSER_COMPATIBILITY_VERSION = "1.1.0"
                updated = import_sources(context)
            finally:
                project_module.PARSER_COMPATIBILITY_VERSION = original_version

            self.assertEqual(first_path.read_bytes(), first_bytes)
            active = next(record for record in updated["records"] if record["source_status"] == "active")
            self.assertIn("parser-v1.1.0", active["normalized_path"])
            self.assertNotEqual(active["normalized_path"], first["normalized_path"])


class ApprovalAndRevisionTests(unittest.TestCase):
    def test_loose_approval_file_cannot_satisfy_a_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = initialize(Path(temporary) / "story", mode="create_new")
            write_json(context.workspace_path("approvals/source.json"), {"status": "approved"})
            config = read_json(context.project_file)
            config["stage_locks"]["SOURCE_LOCKED"] = True
            write_json(context.project_file, config)

            errors = validate_locks(context)
            self.assertTrue(any("stage_lock_records.SOURCE_LOCKED" in error for error in errors))

    def test_lock_requires_real_hash_bound_approvals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, _, _ = prepare_story(Path(temporary) / "story")
            inventory_approval = record_approval(
                context, context.workspace_path("source/inventory.json"), artifact_type="source_inventory",
                target_version="v001", actor="fixture-user", decision="approved",
            )
            structure_approval = record_approval(
                context, context.workspace_path("source/structure.json"), artifact_type="source_structure",
                target_version="v001", actor="fixture-user", decision="approved",
            )
            lock = set_lock(
                context, "SOURCE_LOCKED", approval_paths=[inventory_approval, structure_approval], actor="fixture-user"
            )

            self.assertTrue(lock.is_file())
            self.assertEqual(validate_locks(context), [])
            context.workspace_path("source/structure.json").write_text("{}\n", encoding="utf-8")
            self.assertTrue(any("checksum changed" in error for error in validate_locks(context)))

    def test_source_lock_rejects_mislabeled_approval_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, _, _ = prepare_story(Path(temporary) / "story")
            inventory_approval = record_approval(
                context, context.workspace_path("source/inventory.json"), artifact_type="source_inventory",
                target_version="v001", actor="fixture-user", decision="approved",
            )
            forged_structure_approval = record_approval(
                context, context.workspace_path("source/inventory.json"), artifact_type="source_inventory",
                target_version="v001", actor="fixture-user", decision="approved",
            )
            forged = read_json(forged_structure_approval)
            forged["artifact_type"] = "source_structure"
            write_json(forged_structure_approval, forged)

            with self.assertRaisesRegex(Exception, "source_structure approval must target"):
                set_lock(
                    context,
                    "SOURCE_LOCKED",
                    approval_paths=[inventory_approval, forged_structure_approval],
                    actor="fixture-user",
                )

            self.assertFalse(read_json(context.project_file)["stage_locks"]["SOURCE_LOCKED"])

    def test_gate_rejects_approval_record_outside_managed_store(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, _, _ = prepare_story(Path(temporary) / "story")
            inventory_approval = record_approval(
                context, context.workspace_path("source/inventory.json"), artifact_type="source_inventory",
                target_version="v001", actor="fixture-user", decision="approved",
            )
            structure_approval = record_approval(
                context, context.workspace_path("source/structure.json"), artifact_type="source_structure",
                target_version="v001", actor="fixture-user", decision="approved",
            )
            loose_approval = context.project_root / "loose-approval.json"
            write_json(loose_approval, read_json(structure_approval))

            with self.assertRaisesRegex(Exception, "must live under .manga-studio/approvals"):
                set_lock(
                    context,
                    "SOURCE_LOCKED",
                    approval_paths=[inventory_approval, loose_approval],
                    actor="fixture-user",
                )

    def test_canon_gate_requires_approval_for_active_canon_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, _, _ = prepare_story(Path(temporary) / "story")
            inventory_approval = record_approval(
                context, context.workspace_path("source/inventory.json"), artifact_type="source_inventory",
                target_version="v001", actor="fixture-user", decision="approved",
            )
            structure_approval = record_approval(
                context, context.workspace_path("source/structure.json"), artifact_type="source_structure",
                target_version="v001", actor="fixture-user", decision="approved",
            )
            set_lock(
                context,
                "SOURCE_LOCKED",
                approval_paths=[inventory_approval, structure_approval],
                actor="fixture-user",
            )
            canon_v1 = context.workspace_path("canon/story/canon-v001.json")
            canon_v2 = context.workspace_path("canon/story/canon-v002.json")
            for path, version in ((canon_v1, "v001"), (canon_v2, "v002")):
                write_json(path, {
                    "schema_version": "3.0.0",
                    "project_id": context.config["project_id"],
                    "canon_id": f"canon-{version}",
                    "version": version,
                    "status": "approved",
                    "confirmed_facts": [],
                    "provisional_facts": [],
                    "inferred_facts": [],
                    "contradictions": [],
                    "deprecated_facts": [],
                    "unknowns": [],
                })
            config = read_json(context.project_file)
            config["active_canon_version"] = canon_v2.relative_to(context.project_root).as_posix()
            write_json(context.project_file, config)
            stale_approval = record_approval(
                context, canon_v1, artifact_type="canon", target_version="v001",
                actor="fixture-user", decision="approved",
            )

            with self.assertRaisesRegex(Exception, "not current active_canon_version"):
                set_lock(
                    context,
                    "CANON_APPROVED",
                    approval_paths=[stale_approval],
                    actor="fixture-user",
                )

    def test_approval_invalidates_when_target_changes_and_rejection_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = initialize(Path(temporary) / "story", mode="create_new")
            target = context.workspace_path("manuscript/versions/story-v001.md")
            target.write_text("Version one.\n", encoding="utf-8")
            approved = record_approval(
                context, target, artifact_type="manuscript", target_version="v001",
                actor="fixture-user", decision="approved",
            )
            rejected = record_approval(
                context, target, artifact_type="manuscript", target_version="v001",
                actor="fixture-user", decision="rejected", notes="Keep the earlier ending.",
            )
            target.write_text("Changed after approval.\n", encoding="utf-8")

            self.assertTrue(any("checksum changed" in error for error in validate_approval(context, approved)))
            self.assertIn(read_json(rejected)["status"], {"rejected"})
            self.assertIn(read_json(rejected)["approval_id"], [path.stem for path in context.workspace_path("approvals").glob("*.json")])
            self.assertIn(read_json(approved)["approval_id"], invalidate_stale_approvals(context))
            self.assertEqual(read_json(approved)["status"], "invalidated")

    def test_change_set_needs_approval_and_creates_version_diff_and_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = initialize(Path(temporary) / "story", mode="create_new")
            original = context.workspace_path("manuscript/versions/story-v001.md")
            original.write_text("The door closes.\n", encoding="utf-8")
            before = original.read_bytes()
            change_path = context.workspace_path("revisions/change-sets/change-set-ending-v001.json")
            write_json(change_path, change_set(context.config["project_id"], original.relative_to(context.project_root).as_posix(), sha256_file(original)))

            with self.assertRaisesRegex(Exception, "not marked approved"):
                apply_change_set(context, change_path, actor="fixture-user")
            proposal = read_json(change_path)
            proposal["approval_status"] = "approved"
            write_json(change_path, proposal)
            record_approval(
                context, change_path, artifact_type="change_set", target_version="v001",
                actor="fixture-user", decision="approved",
            )
            outputs = apply_change_set(context, change_path, actor="fixture-user")

            self.assertEqual(original.read_bytes(), before)
            self.assertIn("warning bell", context.project_path(outputs["manuscript_version"]).read_text(encoding="utf-8"))
            self.assertTrue(context.project_path(outputs["diff"]).is_file())
            self.assertTrue(context.project_path(outputs["decision"]).is_file())

            rejected_path = context.workspace_path("revisions/change-sets/change-set-rejected-v001.json")
            rejected_change = change_set(
                context.config["project_id"], original.relative_to(context.project_root).as_posix(), sha256_file(original), "rejected"
            )
            rejected_change["change_set_id"] = "change-set-rejected"
            write_json(rejected_path, rejected_change)
            rejected_record = record_approval(
                context, rejected_path, artifact_type="change_set", target_version="v001",
                actor="fixture-user", decision="rejected",
            )
            with self.assertRaisesRegex(Exception, "not marked approved"):
                apply_change_set(context, rejected_path, actor="fixture-user")
            self.assertTrue(rejected_path.is_file())
            self.assertEqual(read_json(rejected_record)["status"], "rejected")

    def test_change_set_rejects_non_versioned_manuscript_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = initialize(Path(temporary) / "story", mode="create_new")
            target = context.workspace_path("manuscript/draft.md")
            target.write_text("The door closes.\n", encoding="utf-8")
            change_path = context.workspace_path("revisions/change-sets/change-set-ending-v001.json")
            write_json(
                change_path,
                change_set(
                    context.config["project_id"],
                    target.relative_to(context.project_root).as_posix(),
                    sha256_file(target),
                    "approved",
                ),
            )
            record_approval(
                context,
                change_path,
                artifact_type="change_set",
                target_version="v001",
                actor="fixture-user",
                decision="approved",
            )

            with self.assertRaisesRegex(Exception, "managed versions"):
                apply_change_set(context, change_path, actor="fixture-user")

            self.assertEqual(target.read_text(encoding="utf-8"), "The door closes.\n")


class DiagnosticFixtureTests(unittest.TestCase):
    def test_expected_diagnostics_cover_all_deliberate_categories_with_valid_evidence(self) -> None:
        fixture = REPO_ROOT / "tests" / "fixtures" / "story-engine" / "three-chapter"
        source = fixture / "source.md"
        source_before = source_digest(source)
        source_map_path = fixture / "expected-source-map.json"
        report_path = fixture / "expected-diagnostic-report.json"
        source_map = read_json(source_map_path)
        report = read_json(report_path)
        units = {item["source_unit_id"]: item for item in source_map["source_units"]}
        chapter_ids = {item["chapter_id"] for item in source_map["chapters"]}
        scene_ids = {item["scene_id"] for item in source_map["scenes"]}
        expected = {
            "timeline", "character_knowledge", "injury_physical_state_continuity", "prop_continuity",
            "relationship_continuity", "setup_payoff", "unresolved_plot_thread",
            "duplicated_scene_purpose", "chapter_ending", "dialogue_voice",
        }

        self.assertEqual(validate_json_file(source_map_path, REPO_ROOT / "schemas" / "source-map.schema.json"), [])
        self.assertEqual(validate_json_file(report_path, REPO_ROOT / "schemas" / "diagnostic-report.schema.json"), [])
        self.assertEqual({finding["category"] for finding in report["findings"]}, expected)
        self.assertEqual(report["source_map_checksums"], [sha256_file(source_map_path)])
        for finding in report["findings"]:
            self.assertTrue(set(finding["affected_chapter_ids"]) <= chapter_ids)
            self.assertTrue(set(finding["affected_scene_ids"]) <= scene_ids)
            for evidence in finding["evidence"]:
                self.assertEqual(evidence["project_id"], report["project_id"])
                unit = units[evidence["source_unit_id"]]
                self.assertGreaterEqual(evidence["line_start"], unit["line_start"])
                self.assertLessEqual(evidence["line_end"], unit["line_end"])
                self.assertEqual(evidence["content_fingerprint"], unit["content_fingerprint"])
        self.assertEqual(source_digest(source), source_before)

    def test_story_profile_rejects_incomplete_editorial_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = initialize(Path(temporary) / "malformed", mode="create_new")
            write_json(context.workspace_path("analysis/diagnostics/bad.json"), {
                "schema_version": "3.0.0", "project_id": context.config["project_id"], "findings": [{}]
            })
            errors = validate_profile(context, "story")
            self.assertTrue(any("missing required property" in error for error in errors))

    def test_canon_fact_requires_evidence_or_an_approved_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "canon.json"
            canon = {
                "schema_version": "3.0.0", "project_id": "project-canon", "canon_id": "canon-v001",
                "version": "v001", "status": "draft",
                "confirmed_facts": [{
                    "fact_id": "fact-one", "subject_id": "character-one", "predicate": "goal",
                    "value": "Reach the gate", "status": "confirmed", "basis": {"basis_type": "source_evidence"},
                }],
                "provisional_facts": [], "inferred_facts": [], "contradictions": [],
                "deprecated_facts": [], "unknowns": [],
            }
            write_json(path, canon)
            schema = REPO_ROOT / "schemas" / "canon.schema.json"
            self.assertTrue(validate_json_file(path, schema))

            canon["confirmed_facts"][0]["basis"] = {
                "basis_type": "approved_decision",
                "decision": {"decision_id": "decision-one", "approval_id": "approval-one"},
            }
            write_json(path, canon)
            self.assertEqual(validate_json_file(path, schema), [])

            context = initialize(Path(temporary) / "story", mode="create_new")
            canon["project_id"] = context.config["project_id"]
            managed = context.workspace_path("canon/story/canon-v001.json")
            write_json(managed, canon)
            errors = validate_profile(context, "story")
            self.assertTrue(any("approved decision record is missing" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
