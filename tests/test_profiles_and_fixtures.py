from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import REPO_ROOT, approve_inventory, initialize, read_json, write_json
from manga_studio.profiles import validate_profile
from manga_studio.migration import migrate_project
from manga_studio.project import discover_project, import_sources, inventory_sources, project_status
from manga_studio.structure import structure_sources


class ProfileAndFixtureTests(unittest.TestCase):
    def test_current_schema_migration_refreshes_runtime_layout_without_touching_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = initialize(Path(temporary) / "existing-v3", mode="create_new")
            source = context.project_root / "story.md"
            source.write_text("Original source stays unchanged.\n", encoding="utf-8")
            original = source.read_bytes()
            config = read_json(context.project_file)
            config.pop("active_creative_brief_version")
            config.pop("active_success_plan_version")
            config.pop("active_nemu_version")
            config["target_manga_format"].pop("output_intent")
            config["target_manga_format"].pop("print_profile")
            write_json(context.project_file, config)
            context.workspace_path("production/preflight").rmdir()
            context.workspace_path("production").rmdir()
            context.workspace_path("story/success-plans").rmdir()

            actions = migrate_project(discover_project(context.project_root))
            refreshed = read_json(context.project_file)

            self.assertTrue(any("3.3" in action for action in actions))
            self.assertTrue(context.workspace_path("production/preflight").is_dir())
            self.assertTrue(context.workspace_path("story/success-plans").is_dir())
            self.assertEqual(refreshed["target_manga_format"]["output_intent"], "screen")
            self.assertIsNone(refreshed["active_creative_brief_version"])
            self.assertIsNone(refreshed["active_success_plan_version"])
            self.assertEqual(source.read_bytes(), original)

    def test_new_story_without_manuscript_passes_story_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = initialize(Path(temporary) / "new-story", mode="create_new")

            self.assertEqual(validate_profile(context, "story"), [])
            self.assertFalse(context.config["image_generation_enabled"])
            self.assertFalse(context.config["stage_locks"]["IMAGE_READY"])

    def test_continuation_project_supports_existing_chapters_and_open_threads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "continuation"
            (story / "chapters").mkdir(parents=True)
            (story / "chapters" / "chapter-01.md").write_text("# Chapter 1: Return\nExisting chapter.\n", encoding="utf-8")
            context = initialize(story, mode="continue_existing")
            inventory_sources(context)
            approve_inventory(context)
            import_sources(context)
            structure_sources(context)
            manuscript_rel = ".manga-studio/manuscript/manuscript-v001.md"
            (story / manuscript_rel).write_text("# Return\nExisting chapter.\n", encoding="utf-8")
            write_json(context.workspace_path("canon/plot-threads.json"), {
                "threads": [{"plot_thread_id": "plot-thread-local", "status": "unresolved"}]
            })
            config = read_json(context.project_file)
            config["active_manuscript_version"] = manuscript_rel
            write_json(context.project_file, config)
            context = discover_project(story)

            self.assertEqual(validate_profile(context, "story"), [])
            self.assertEqual(project_status(context)["operating_mode"], "continue_existing")
            self.assertTrue(context.workspace_path("canon/plot-threads.json").exists())

    def test_pilot_story_and_preproduction_pass_but_production_fails_without_images(self) -> None:
        pilot = discover_project(REPO_ROOT / "projects" / "pilot-001")

        story_errors = validate_profile(pilot, "story")
        preproduction_errors = validate_profile(pilot, "preproduction")
        production_errors = validate_profile(pilot, "production")

        self.assertEqual(story_errors, [])
        self.assertEqual(preproduction_errors, [])
        self.assertTrue(any("IMAGE_READY" in error for error in production_errors))
        self.assertTrue(any("no approved artwork" in error for error in production_errors))

    def test_image_ready_cannot_be_true_without_all_prerequisites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = initialize(Path(temporary) / "bad-gates", mode="create_new")
            config = read_json(context.project_file)
            config["stage_locks"]["IMAGE_READY"] = True
            write_json(context.project_file, config)
            context = discover_project(context.project_root)

            errors = validate_profile(context, "story")

            self.assertTrue(any("IMAGE_READY is true" in error for error in errors))
            self.assertTrue(any("image_generation_enabled is false" in error for error in errors))

    def test_preproduction_rejects_missing_deferred_reference_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "pilot"
            shutil.copytree(REPO_ROOT / "projects/pilot-001", story)
            context = discover_project(story)
            job_path = context.workspace_path("handoff/pending/pilot-001-panel-page-001-p1-v001.json")
            job = read_json(job_path)
            job["deferred_reference_dependencies"][0]["source_job_id"] = "missing-reference-job-v001"
            write_json(job_path, job)

            errors = validate_profile(discover_project(story), "preproduction")

            self.assertTrue(any("deferred reference source job is missing" in error for error in errors))

    def test_preproduction_rejects_image_job_content_drift_from_active_brief(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "pilot"
            shutil.copytree(REPO_ROOT / "projects/pilot-001", story)
            context = discover_project(story)
            job_path = context.workspace_path("handoff/pending/pilot-001-panel-page-001-p1-v001.json")
            job = read_json(job_path)
            job["content_constraints"]["content_rating"] = "mature"
            write_json(job_path, job)

            errors = validate_profile(discover_project(story), "preproduction")

            self.assertTrue(any("must exactly match the active creative brief" in error for error in errors))

    def test_story_profile_rejects_success_plan_with_stale_creative_brief_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "pilot"
            shutil.copytree(REPO_ROOT / "projects/pilot-001", story)
            context = discover_project(story)
            brief_path = context.project_path(context.config["active_creative_brief_version"])
            brief = read_json(brief_path)
            brief["story_promise"] += " Changed after the success plan was authored."
            write_json(brief_path, brief)

            errors = validate_profile(discover_project(story), "story")

            self.assertTrue(any("success plan creative brief checksum changed" in error for error in errors))

    def test_story_profile_rejects_duplicate_success_metric_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "pilot"
            shutil.copytree(REPO_ROOT / "projects/pilot-001", story)
            context = discover_project(story)
            plan_path = context.project_path(context.config["active_success_plan_version"])
            plan = read_json(plan_path)
            plan["measurement_and_iteration"]["primary_metrics"][1]["name"] = plan[
                "measurement_and_iteration"
            ]["primary_metrics"][0]["name"]
            write_json(plan_path, plan)

            errors = validate_profile(discover_project(story), "story")

            self.assertTrue(any("primary metric names must be unique" in error for error in errors))

    def test_story_profile_rejects_visual_success_deliverable_owned_outside_chatgpt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "pilot"
            shutil.copytree(REPO_ROOT / "projects/pilot-001", story)
            context = discover_project(story)
            plan_path = context.project_path(context.config["active_success_plan_version"])
            plan = read_json(plan_path)
            plan["publishing_strategy"]["discoverability_deliverables"][1]["owner"] = "human"
            write_json(plan_path, plan)

            errors = validate_profile(discover_project(story), "story")

            self.assertTrue(any("must be owned by chatgpt_image_generation" in error for error in errors))

    def test_story_profile_rejects_market_evidence_claim_without_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "pilot"
            shutil.copytree(REPO_ROOT / "projects/pilot-001", story)
            context = discover_project(story)
            plan_path = context.project_path(context.config["active_success_plan_version"])
            plan = read_json(plan_path)
            hypothesis = plan["audience_and_positioning"]["market_hypotheses"][0]
            hypothesis["evidence_status"] = "researched"
            write_json(plan_path, plan)

            errors = validate_profile(discover_project(story), "story")

            self.assertTrue(any("requires evidence_source_ids" in error for error in errors))

    def test_story_profile_accepts_source_linked_success_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "pilot"
            shutil.copytree(REPO_ROOT / "projects/pilot-001", story)
            context = discover_project(story)
            plan_path = context.project_path(context.config["active_success_plan_version"])
            plan = read_json(plan_path)
            plan["basis"]["research_sources"].append({
                "source_id": "pilot-reader-feedback-round-one",
                "kind": "reader_feedback",
                "citation": "Anonymized pilot comprehension questionnaire, round one",
                "accessed_on": "2026-09-04",
                "notes": "Fixture evidence only."
            })
            plan["measurement_and_iteration"]["observations"].append({
                "observation_id": "pilot-clarity-observation-one",
                "metric_name": "unaided event comprehension",
                "observed_at": "2026-09-04",
                "sample_description": "Two first-time fixture readers.",
                "value": "Both readers identified all four dominant events.",
                "evidence_source_ids": ["pilot-reader-feedback-round-one"],
                "interpretation": "The tested page version met its narrow comprehension target.",
                "confidence": "low",
                "decision": "no_change"
            })
            write_json(plan_path, plan)

            self.assertEqual(validate_profile(discover_project(story), "story"), [])

    def test_preproduction_ignores_macos_sidecar_json_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "pilot"
            shutil.copytree(REPO_ROOT / "projects/pilot-001", story)
            context = discover_project(story)
            context.workspace_path("canon/characters/._mira.json").write_bytes(b"sidecar")
            context.workspace_path("approvals/._approval.json").write_bytes(b"sidecar")

            self.assertEqual(validate_profile(discover_project(story), "preproduction"), [])


if __name__ == "__main__":
    unittest.main()
