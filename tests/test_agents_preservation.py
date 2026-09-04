from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import initialize
from manga_studio.project import MANAGED_END, MANAGED_START, update_agents_file


class AgentsPreservationTests(unittest.TestCase):
    def test_existing_agents_rules_are_preserved_and_section_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "instructions-story"
            story.mkdir()
            unrelated = "# Existing Rules\n\n- Never rename release files.\n- Use British spelling.\n"
            agents = story / "AGENTS.md"
            agents.write_text(unrelated, encoding="utf-8")

            initialize(story)
            first = agents.read_text(encoding="utf-8")
            update_agents_file(story)
            second = agents.read_text(encoding="utf-8")

            self.assertTrue(first.startswith(unrelated))
            self.assertEqual(first, second)
            self.assertEqual(first.count(MANAGED_START), 1)
            self.assertEqual(first.count(MANAGED_END), 1)
            self.assertIn("Image generation is disabled by default", first)
            self.assertIn("never generate or edit artwork", first)


if __name__ == "__main__":
    unittest.main()
