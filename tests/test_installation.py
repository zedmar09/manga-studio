from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import REPO_ROOT, initialize
from install_skills import execute_install, plan_install
from uninstall_skills import main as uninstall_main


class InstallationTests(unittest.TestCase):
    def test_manifest_install_plan_contains_exact_suite_and_dry_run_changes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "user-skills"
            plan, errors = plan_install(REPO_ROOT, destination, "symlink")

            self.assertEqual(errors, [])
            self.assertEqual(len(plan), 17)
            self.assertEqual({item["action"] for item in plan}, {"create"})
            self.assertFalse(destination.exists())

    def test_existing_non_manga_skill_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "user-skills"
            collision = destination / "manga-creator"
            collision.mkdir(parents=True)
            (collision / "SKILL.md").write_text("---\nname: manga-creator\ndescription: Personal skill.\n---\n", encoding="utf-8")

            plan, errors = plan_install(REPO_ROOT, destination, "copy")

            self.assertTrue(any(item["name"] == "manga-creator" and item["action"] == "reject" for item in plan))
            self.assertTrue(any("non-Manga skill" in error for error in errors))
            self.assertIn("Personal skill", (collision / "SKILL.md").read_text(encoding="utf-8"))

    def test_temporary_install_and_uninstall_never_touch_story_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            destination = base / "user-skills"
            story = base / "story"
            context = initialize(story, mode="create_new")
            marker = context.workspace_path("decisions/keep.json")
            marker.write_text("{}\n", encoding="utf-8")
            plan, errors = plan_install(REPO_ROOT, destination, "copy")
            self.assertEqual(errors, [])
            execute_install(plan, destination, "copy")

            result = uninstall_main(["--scope", "user", "--destination-root", str(destination)])

            self.assertEqual(result, 0)
            self.assertTrue(context.project_file.exists())
            self.assertTrue(marker.exists())
            self.assertFalse((destination / "manga-creator").exists())

    def test_replacement_creates_rollback_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "user-skills"
            existing = destination / "manga-creator"
            existing.mkdir(parents=True)
            (existing / "SKILL.md").write_text(
                "---\nname: manga-creator\ndescription: Old.\nmetadata:\n  namespace: manga-studio\n  version: \"1.0.0\"\n---\n",
                encoding="utf-8",
            )
            plan, errors = plan_install(REPO_ROOT, destination, "copy")
            self.assertEqual(errors, [])

            backup = execute_install(plan, destination, "copy")

            self.assertIsNotNone(backup)
            self.assertTrue((backup / "manga-creator" / "SKILL.md").exists())
            self.assertIn('version: "2.0.0"', (destination / "manga-creator" / "SKILL.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
