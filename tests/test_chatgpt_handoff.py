from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import initialize, write_json
from manga_studio.handoff import export_chatgpt_handoff, prepare_chatgpt_handoff
from manga_studio.project import ProjectOperationError


PANEL_PROHIBITIONS = [
    "dialogue_text",
    "captions",
    "speech_balloons",
    "sound_effect_text",
    "panel_borders",
    "page_numbers",
    "signatures",
    "watermarks",
]


class ChatGPTHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.context = initialize(Path(self.temporary.name) / "story", mode="prepare_visual_production")
        self.reference_root = self.context.workspace_path("handoff/approved/refs")
        self.reference_root.mkdir(parents=True)
        (self.reference_root / "character-v001.png").write_bytes(b"character reference fixture\n")
        (self.reference_root / "location-v001.png").write_bytes(b"location reference fixture\n")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def panel_job(self) -> dict:
        return {
            "schema_version": "1.0.0",
            "job_id": "test-page-001-panel-01-v001",
            "job_type": "manga_panel",
            "output_filename": ".manga-studio/handoff/generated/panels/page-001-panel-01-v001.png",
            "required_reference_images": [
                {
                    "reference_id": "character-v001",
                    "kind": "character_reference",
                    "path": ".manga-studio/handoff/approved/refs/character-v001.png",
                    "locked": True,
                    "usage": "Preserve the character's face, hair, and wardrobe.",
                },
                {
                    "reference_id": "location-v001",
                    "kind": "location_reference",
                    "path": ".manga-studio/handoff/approved/refs/location-v001.png",
                    "locked": True,
                    "usage": "Preserve the corridor geometry and doors.",
                },
            ],
            "reference_priority": ["location-v001", "character-v001"],
            "scene_state": {"page_id": "page-001", "panel_id": "p1", "time": "afternoon"},
            "character_state": {"hero": "Holding a key in the right hand."},
            "composition": {"camera": "medium vertical shot", "reading_focus": "hero, then doorway"},
            "dialogue_safe_zones": [{"x": 20, "y": 20, "width": 300, "height": 160}],
            "manga_style": {"palette": "black-and-white", "linework": "clean ink"},
            "required_elements": ["hero", "antique key", "empty corridor"],
            "prohibited_elements": PANEL_PROHIBITIONS,
            "revision_history": [
                {
                    "version": "v001",
                    "output_filename": ".manga-studio/handoff/generated/panels/page-001-panel-01-v001.png",
                    "supersedes_job_id": None,
                    "supersedes_output_filename": None,
                    "notes": "Initial panel job.",
                }
            ],
            "release_status": "ready",
            "blocking_reasons": [],
        }

    def write_job(self, job: dict, name: str = "test-page-001-panel-01-v001.json") -> Path:
        path = self.context.workspace_path(f"handoff/pending/{name}")
        write_json(path, job)
        return path

    @patch("manga_studio.handoff._image_generation_gate_errors", return_value=[])
    def test_exports_paste_ready_markdown_with_ordered_attachment_hashes(self, _mock) -> None:
        destination = export_chatgpt_handoff(self.context, self.write_job(self.panel_job()))
        text = destination.read_text(encoding="utf-8")

        self.assertEqual(destination.suffix, ".md")
        self.assertIn("# ChatGPT Image Generation Request", text)
        self.assertIn("Return only the generated image", text)
        self.assertIn("page-001-panel-01-v001.png", text)
        self.assertIn("SHA-256", text)
        self.assertLess(text.index("location-v001.png"), text.index("character-v001.png"))
        self.assertIn("dialogue_text", text)
        self.assertIn('"job_id": "test-page-001-panel-01-v001"', text)

    @patch("manga_studio.handoff._image_generation_gate_errors", return_value=[])
    def test_identical_export_is_idempotent_but_changed_file_is_not_overwritten(self, _mock) -> None:
        job_path = self.write_job(self.panel_job())
        destination = export_chatgpt_handoff(self.context, job_path)
        self.assertEqual(export_chatgpt_handoff(self.context, job_path), destination)

        destination.write_text("manually changed\n", encoding="utf-8")
        with self.assertRaisesRegex(ProjectOperationError, "refusing to overwrite"):
            export_chatgpt_handoff(self.context, job_path)

    @patch("manga_studio.handoff._image_generation_gate_errors", return_value=[])
    def test_missing_attachment_blocks_export(self, _mock) -> None:
        job = self.panel_job()
        job["required_reference_images"][0]["path"] = (
            ".manga-studio/handoff/approved/refs/missing-v001.png"
        )
        with self.assertRaisesRegex(ProjectOperationError, "required reference 'character-v001' is missing"):
            prepare_chatgpt_handoff(self.context, self.write_job(job))

    @patch("manga_studio.handoff._image_generation_gate_errors", return_value=[])
    def test_unlocked_attachment_blocks_export(self, _mock) -> None:
        job = self.panel_job()
        job["required_reference_images"][0]["locked"] = False
        with self.assertRaisesRegex(ProjectOperationError, "must be locked before export"):
            prepare_chatgpt_handoff(self.context, self.write_job(job))

    def test_deferred_job_reports_its_blockers(self) -> None:
        job = self.panel_job()
        job["release_status"] = "deferred"
        job["blocking_reasons"] = ["Storyboard is not locked."]
        with self.assertRaisesRegex(ProjectOperationError, "Storyboard is not locked"):
            prepare_chatgpt_handoff(self.context, self.write_job(job))

    @patch("manga_studio.handoff._image_generation_gate_errors", return_value=[])
    def test_schema_error_blocks_export(self, _mock) -> None:
        job = self.panel_job()
        job["unexpected"] = "not allowed"
        with self.assertRaisesRegex(ProjectOperationError, "unexpected property 'unexpected'"):
            prepare_chatgpt_handoff(self.context, self.write_job(job))

    @patch("manga_studio.handoff._image_generation_gate_errors", return_value=[])
    def test_job_and_output_must_remain_in_managed_handoff_directory(self, _mock) -> None:
        outside_job = self.context.project_root / "outside.json"
        write_json(outside_job, self.panel_job())
        with self.assertRaisesRegex(ProjectOperationError, "must be a JSON file under"):
            prepare_chatgpt_handoff(self.context, outside_job)

        job_path = self.write_job(copy.deepcopy(self.panel_job()))
        with self.assertRaisesRegex(ProjectOperationError, "must be a .md file under"):
            export_chatgpt_handoff(self.context, job_path, self.context.project_root / "outside.md")

    def test_ready_job_still_requires_image_ready_lock(self) -> None:
        with self.assertRaisesRegex(ProjectOperationError, "IMAGE_READY is not true"):
            prepare_chatgpt_handoff(self.context, self.write_job(self.panel_job()))


if __name__ == "__main__":
    unittest.main()
