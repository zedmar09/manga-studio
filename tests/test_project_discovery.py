from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import initialize
from manga_studio.project import ProjectDiscoveryError, discover_project


class ProjectDiscoveryTests(unittest.TestCase):
    def test_nested_invocation_resolves_correct_story_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "nested-story"
            context = initialize(story)
            nested = story / "chapters" / "volume-one" / "drafts"
            nested.mkdir(parents=True)

            discovered = discover_project(nested)

            self.assertEqual(discovered.project_root, story.resolve())
            self.assertEqual(discovered.workspace_root, context.workspace_root)

    def test_explicit_path_selects_requested_story(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first = initialize(base / "first")
            second = initialize(base / "second")

            self.assertEqual(discover_project(first.project_root).config["project_id"], first.config["project_id"])
            self.assertEqual(discover_project(second.project_root).config["project_id"], second.config["project_id"])

    def test_missing_project_never_falls_back_to_pilot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            external = Path(temporary) / "not-a-story" / "nested"
            external.mkdir(parents=True)

            with self.assertRaises(ProjectDiscoveryError) as raised:
                discover_project(external)

            self.assertNotIn("pilot-001", str(raised.exception))
            self.assertIn("manga_studio.py init", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
