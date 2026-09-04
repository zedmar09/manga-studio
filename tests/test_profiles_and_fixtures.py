from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import REPO_ROOT, approve_inventory, initialize, read_json, write_json
from manga_studio.profiles import validate_profile
from manga_studio.project import discover_project, import_sources, inventory_sources, project_status
from manga_studio.structure import structure_sources


class ProfileAndFixtureTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
