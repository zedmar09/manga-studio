from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import initialize, write_json
from manga_studio.project import get_or_create_entity_id, import_sources, inventory_sources


class MultiStoryIsolationTests(unittest.TestCase):
    def test_two_simultaneous_stories_do_not_share_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first_root = base / "quiet-drama"
            second_root = base / "space-comedy"
            first_root.mkdir()
            second_root.mkdir()
            (first_root / "chapter.md").write_text("# Opening\nAlex waits.\n", encoding="utf-8")
            (second_root / "chapter.md").write_text("# Opening\nAlex launches.\n", encoding="utf-8")
            first = initialize(first_root, title="Quiet Drama")
            second = initialize(second_root, title="Space Comedy")

            first_character = get_or_create_entity_id(first, "characters", "alex", "Alex")
            second_character = get_or_create_entity_id(second, "characters", "alex", "Alex")
            first_chapter = get_or_create_entity_id(first, "chapters", "source-doc#heading-1", "Opening")
            second_chapter = get_or_create_entity_id(second, "chapters", "source-doc#heading-1", "Opening")
            inventory_sources(first)
            inventory_sources(second)
            import_sources(first)
            import_sources(second)

            write_json(first.workspace_path("canon/story-v001.json"), {"character_id": first_character, "genre": "drama"})
            write_json(second.workspace_path("canon/story-v001.json"), {"character_id": second_character, "genre": "comedy"})
            write_json(first.workspace_path("approvals/canon.json"), {"status": "approved"})
            (first.workspace_path("analysis/diagnosis-v001.md")).write_text("First story only.\n", encoding="utf-8")

            self.assertNotEqual(first.config["project_id"], second.config["project_id"])
            self.assertNotEqual(first_character, second_character)
            self.assertNotEqual(first_chapter, second_chapter)
            renamed_first_chapter = get_or_create_entity_id(first, "chapters", "source-doc#heading-1", "A New Opening")
            self.assertEqual(first_chapter, renamed_first_chapter)
            self.assertFalse(second.workspace_path("approvals/canon.json").exists())
            self.assertFalse(second.workspace_path("analysis/diagnosis-v001.md").exists())
            self.assertNotEqual(
                first.workspace_path("canon/story-v001.json").read_text(encoding="utf-8"),
                second.workspace_path("canon/story-v001.json").read_text(encoding="utf-8"),
            )

            first_map = first.workspace_path("source/id-map.json").read_text(encoding="utf-8")
            second_map = second.workspace_path("source/id-map.json").read_text(encoding="utf-8")
            self.assertNotIn(str(second_root.resolve()), first_map)
            self.assertNotIn(str(first_root.resolve()), second_map)
            self.assertNotIn(str(second_root.resolve()), first.workspace_path("source/inventory.json").read_text(encoding="utf-8"))
            self.assertNotIn(str(first_root.resolve()), second.workspace_path("source/inventory.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
