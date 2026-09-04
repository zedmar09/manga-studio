from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from helpers import approve_inventory, initialize, read_json, write_json
from manga_studio.adapters import adapter_for_extension
from manga_studio.profiles import validate_profile
from manga_studio.project import create_version, import_sources, inventory_sources, sha256_file
from manga_studio.structure import structure_sources


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SourceWorkflowTests(unittest.TestCase):
    def test_core_adapters_are_explicit_and_extensible(self) -> None:
        self.assertEqual(adapter_for_extension(".txt").name, "plain_text")
        self.assertEqual(adapter_for_extension(".md").name, "markdown")
        self.assertIsNone(adapter_for_extension(".docx"))

    def test_single_file_story_and_source_immutability(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "single-file"
            story.mkdir()
            manuscript = story / "story.md"
            manuscript.write_bytes(b"# Chapter 1: A Story\r\n\r\nOriginal bytes.\r\n")
            before = digest(manuscript)

            context = initialize(story)
            self.assertEqual(digest(manuscript), before)
            inventory = inventory_sources(context)
            self.assertEqual(digest(manuscript), before)
            self.assertEqual(next(item for item in inventory["files"] if item["relative_path"] == "story.md")["classification"], "primary_manuscript")
            approve_inventory(context)
            provenance = import_sources(context)
            structure_sources(context)
            self.assertEqual(digest(manuscript), before)
            self.assertEqual(validate_profile(context, "story"), [])
            self.assertEqual(digest(manuscript), before)

            record = next(item for item in provenance["records"] if item["original_path"] == "story.md")
            snapshot = story / record["snapshot_path"]
            normalized = story / record["normalized_path"]
            self.assertEqual(snapshot.read_bytes(), manuscript.read_bytes())
            self.assertEqual(normalized.read_text(encoding="utf-8"), "# Chapter 1: A Story\n\nOriginal bytes.\n")

            (context.workspace_path("analysis/diagnosis-v001.md")).write_text("Proposed diagnosis.\n", encoding="utf-8")
            self.assertEqual(digest(manuscript), before)
            (context.workspace_path("revisions/plan-v001.md")).write_text("Proposed plan.\n", encoding="utf-8")
            self.assertEqual(digest(manuscript), before)

    def test_chapter_per_file_and_notes_are_distinguished(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "chapters-story"
            (story / "book" / "chapters").mkdir(parents=True)
            (story / "notes").mkdir()
            (story / "book" / "chapters" / "chapter-01.md").write_text("# Dawn\n", encoding="utf-8")
            (story / "book" / "chapters" / "chapter-02.txt").write_text("Dusk\n", encoding="utf-8")
            (story / "notes" / "ideas.md").write_text("Maybe later.\n", encoding="utf-8")
            context = initialize(story)

            files = inventory_sources(context)["files"]
            classifications = {item["relative_path"]: item["classification"] for item in files}

            self.assertEqual(classifications["book/chapters/chapter-01.md"], "primary_manuscript")
            self.assertEqual(classifications["book/chapters/chapter-02.txt"], "primary_manuscript")
            self.assertEqual(classifications["notes/ideas.md"], "author_notes")

    def test_unusual_structure_reports_unknown_media_and_unsupported_types(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "unusual"
            (story / "deep" / "drafts").mkdir(parents=True)
            (story / "deep" / "drafts" / "part-a.md").write_text("# Shared Title\n", encoding="utf-8")
            (story / "deep" / "drafts" / "part-b.md").write_text("# Shared Title\n", encoding="utf-8")
            (story / "readme.txt").write_text("Unrelated text.\n", encoding="utf-8")
            (story / "cover.png").write_bytes(b"fixture media, not artwork generation")
            (story / "legacy.docx").write_bytes(b"unsupported fixture")
            context = initialize(story)

            files = {item["relative_path"]: item for item in inventory_sources(context)["files"]}

            self.assertEqual(files["readme.txt"]["classification"], "unknown")
            self.assertEqual(files["cover.png"]["support_status"], "unsupported")
            self.assertEqual(files["legacy.docx"]["support_status"], "unsupported")
            self.assertIn("adapter", files["legacy.docx"]["message"])
            self.assertNotIn(".manga-studio/project.json", files)

    def test_source_document_id_survives_safe_move(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "moving-story"
            story.mkdir()
            original = story / "chapter-old.md"
            original.write_text("# Stable\n", encoding="utf-8")
            context = initialize(story)
            first = inventory_sources(context)
            first_id = next(item for item in first["files"] if item["relative_path"] == "chapter-old.md")["document_id"]
            inventory_path = context.workspace_path("source/inventory.json")
            first["files"][0]["classification_status"] = "corrected"
            first["files"][0]["usage_role"] = "primary_manuscript"
            write_json(inventory_path, first)
            moved = story / "archive" / "chapter-renamed.md"
            moved.parent.mkdir()
            original.rename(moved)

            second = inventory_sources(context)
            moved_record = next(item for item in second["files"] if item["relative_path"] == "archive/chapter-renamed.md")

            self.assertEqual(moved_record["document_id"], first_id)
            self.assertEqual(moved_record["id_match_status"], "matched_checksum_after_move")
            self.assertEqual(moved_record["classification_status"], "corrected")
            self.assertEqual(moved_record["usage_role"], "primary_manuscript")

    def test_user_classification_correction_survives_reinventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "classification-story"
            story.mkdir()
            (story / "material.md").write_text("Reference notes.\n", encoding="utf-8")
            context = initialize(story)
            inventory_sources(context)
            inventory_path = context.workspace_path("source/inventory.json")
            inventory = read_json(inventory_path)
            record = next(item for item in inventory["files"] if item["relative_path"] == "material.md")
            record["classification"] = "reference"
            record["classification_status"] = "corrected"
            record["usage_role"] = "canon_reference"
            write_json(inventory_path, inventory)

            updated = inventory_sources(context)
            corrected = next(item for item in updated["files"] if item["relative_path"] == "material.md")

            self.assertEqual(corrected["classification"], "reference")
            self.assertEqual(corrected["classification_status"], "corrected")
            self.assertEqual(corrected["usage_role"], "canon_reference")

    def test_changed_source_after_inventory_blocks_import(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "changed-story"
            story.mkdir()
            source = story / "story.txt"
            source.write_text("first\n", encoding="utf-8")
            context = initialize(story)
            inventory_sources(context)
            approve_inventory(context)
            source.write_text("changed\n", encoding="utf-8")

            with self.assertRaisesRegex(Exception, "Source changed after inventory"):
                import_sources(context)

    def test_versioning_creates_new_files_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "versioned-story"
            context = initialize(story, mode="create_new")
            draft = story / "draft.md"
            draft.write_text("First draft.\n", encoding="utf-8")

            first = create_version(context, draft, "manuscript")
            draft.write_text("Second draft.\n", encoding="utf-8")
            second = create_version(context, draft, "manuscript")

            self.assertEqual(first.name, "draft-v001.md")
            self.assertEqual(second.name, "draft-v002.md")
            self.assertEqual(first.read_text(encoding="utf-8"), "First draft.\n")
            self.assertEqual(second.read_text(encoding="utf-8"), "Second draft.\n")

    def test_reimport_preserves_historical_snapshot_and_normalized_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            story = Path(temporary) / "source-history"
            story.mkdir()
            source = story / "story.md"
            source.write_text("Version one.\n", encoding="utf-8")
            context = initialize(story)
            inventory_sources(context)
            approve_inventory(context)
            first = import_sources(context)
            structure_sources(context)
            first_record = next(item for item in first["records"] if item["original_path"] == "story.md")
            first_snapshot = story / first_record["snapshot_path"]
            first_normalized = story / first_record["normalized_path"]
            source.write_text("Version two.\n", encoding="utf-8")
            inventory_sources(context)

            second = import_sources(context)
            structure_sources(context)
            records = [item for item in second["records"] if item["original_path"] == "story.md"]

            self.assertEqual(len(records), 2)
            self.assertEqual({item["source_status"] for item in records}, {"active", "superseded"})
            self.assertEqual(first_snapshot.read_text(encoding="utf-8"), "Version one.\n")
            self.assertEqual(first_normalized.read_text(encoding="utf-8"), "Version one.\n")
            self.assertEqual(validate_profile(context, "story"), [])


if __name__ == "__main__":
    unittest.main()
