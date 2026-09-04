from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import REPO_ROOT, initialize
from doctor import run_doctor
from install_skills import execute_install, plan_install, rollback_install
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
            self.assertTrue((backup / "skills" / "manga-creator" / "SKILL.md").exists())
            self.assertIn('version: "3.0.0"', (destination / "manga-creator" / "SKILL.md").read_text(encoding="utf-8"))

    def test_copy_and_symlink_installs_have_self_contained_runtime(self) -> None:
        for mode in ("copy", "symlink"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary) / "user-skills"
                plan, errors = plan_install(REPO_ROOT, destination, mode)
                self.assertEqual(errors, [])
                execute_install(plan, destination, mode)

                self.assertTrue((destination / ".manga-studio-runtime" / "manga-studio.py").is_file())
                self.assertEqual(run_doctor(REPO_ROOT, mode="installed", destination_root=destination), [])

    def test_transaction_can_be_rolled_back(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "user-skills"
            plan, errors = plan_install(REPO_ROOT, destination, "copy")
            self.assertEqual(errors, [])
            backup = execute_install(plan, destination, "copy")

            rollback_install(destination, backup)

            self.assertFalse((destination / "manga-creator").exists())
            self.assertFalse((destination / ".manga-studio-runtime").exists())

    def test_staging_failure_leaves_existing_install_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "user-skills"
            existing = destination / "manga-creator"
            existing.mkdir(parents=True)
            original = (
                "---\nname: manga-creator\ndescription: Old.\nmetadata:\n"
                "  namespace: manga-studio\n  version: \"1.0.0\"\n---\n"
            )
            (existing / "SKILL.md").write_text(original, encoding="utf-8")
            plan, errors = plan_install(REPO_ROOT, destination, "copy")
            self.assertEqual(errors, [])

            with patch("install_skills._copy_runtime", side_effect=RuntimeError("fixture failure")):
                with self.assertRaisesRegex(RuntimeError, "fixture failure"):
                    execute_install(plan, destination, "copy")

            self.assertEqual((existing / "SKILL.md").read_text(encoding="utf-8"), original)
            self.assertFalse((destination / ".manga-studio-runtime").exists())

    def test_partial_backup_failure_preserves_every_existing_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "user-skills"
            originals = {}
            for name in ("manga-creator", "manga-source-ingestor"):
                skill = destination / name
                skill.mkdir(parents=True)
                content = (
                    f"---\nname: {name}\ndescription: Existing {name}.\nmetadata:\n"
                    "  namespace: manga-studio\n  version: \"2.0.0\"\n---\n"
                )
                (skill / "SKILL.md").write_text(content, encoding="utf-8")
                originals[name] = content

            plan, errors = plan_install(REPO_ROOT, destination, "copy")
            self.assertEqual(errors, [])
            second = destination / "manga-source-ingestor"
            real_move = shutil.move

            def fail_on_second_backup(source, target, *args, **kwargs):
                if Path(source) == second:
                    raise RuntimeError("partial backup failure")
                return real_move(source, target, *args, **kwargs)

            with patch("install_skills.shutil.move", side_effect=fail_on_second_backup):
                with self.assertRaisesRegex(RuntimeError, "partial backup failure"):
                    execute_install(plan, destination, "copy")

            for name, content in originals.items():
                self.assertEqual((destination / name / "SKILL.md").read_text(encoding="utf-8"), content)
            self.assertFalse((destination / ".manga-studio-runtime").exists())

    def test_doctor_detects_duplicate_personal_skill_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "user-skills"
            plan, errors = plan_install(REPO_ROOT, destination, "copy")
            self.assertEqual(errors, [])
            execute_install(plan, destination, "copy")
            duplicate = destination / "duplicate-creator"
            duplicate.mkdir()
            (duplicate / "SKILL.md").write_text(
                "---\nname: manga-creator\ndescription: Duplicate.\n---\n", encoding="utf-8"
            )

            errors = run_doctor(REPO_ROOT, mode="installed", destination_root=destination)
            self.assertTrue(any("duplicate personal skill" in error for error in errors))

    def test_installed_doctor_detects_missing_runtime_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "user-skills"
            plan, errors = plan_install(REPO_ROOT, destination, "copy")
            self.assertEqual(errors, [])
            execute_install(plan, destination, "copy")
            runtime_schema = (
                destination
                / ".manga-studio-runtime"
                / "versions"
                / "3.0.0"
                / "schemas"
                / "approval.schema.json"
            )
            runtime_schema.unlink()

            errors = run_doctor(REPO_ROOT, mode="installed", destination_root=destination)

            self.assertTrue(any("approval.schema.json" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
