from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))

from manga_studio.validation import validate_image_job


PANEL_PROHIBITIONS = [
    "dialogue_text",
    "captions",
    "speech_balloons",
    "sound_effect_text",
    "panel_borders",
    "page_numbers",
    "signatures",
    "watermarks",
    "color",
]


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class ValidateImageJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        self.ref_dir = self.project_root / ".manga-studio" / "handoff" / "approved" / "refs"
        self.ref_dir.mkdir(parents=True)
        (self.ref_dir / "character-reference-v001.png").write_text(
            "validation fixture only; not artwork\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def valid_panel_job(self) -> dict:
        return {
            "schema_version": "1.0.0",
            "job_id": "test-panel-page-001-p1-v001",
            "job_type": "manga_panel",
            "output_filename": ".manga-studio/handoff/generated/panels/page-001-panel-01-v001.png",
            "required_reference_images": [
                {
                    "reference_id": "character-reference-v001",
                    "kind": "character_reference",
                    "path": ".manga-studio/handoff/approved/refs/character-reference-v001.png",
                    "locked": True,
                    "usage": "Use as locked character reference."
                }
            ],
            "reference_priority": [
                "character-reference-v001"
            ],
            "scene_state": {
                "page_id": "page-001",
                "panel_id": "p1"
            },
            "character_state": {
                "character-001": "Facing the scene focus."
            },
            "composition": {
                "camera": "medium shot"
            },
            "dialogue_safe_zones": [
                {
                    "x": 20,
                    "y": 20,
                    "width": 300,
                    "height": 160
                }
            ],
            "manga_style": {
                "palette": "black-and-white"
            },
            "required_elements": [
                "primary character"
            ],
            "prohibited_elements": PANEL_PROHIBITIONS,
            "revision_history": [
                {
                    "version": "v001",
                    "output_filename": ".manga-studio/handoff/generated/panels/page-001-panel-01-v001.png",
                    "supersedes_job_id": None,
                    "supersedes_output_filename": None,
                    "notes": "Initial test panel."
                }
            ],
            "release_status": "ready",
            "blocking_reasons": []
        }

    def test_valid_panel_job_passes(self) -> None:
        job_path = self.project_root / "job.json"
        write_json(job_path, self.valid_panel_job())

        errors = validate_image_job(job_path, self.project_root)

        self.assertEqual(errors, [])

    def test_missing_required_reference_fails_clearly(self) -> None:
        job = self.valid_panel_job()
        job["required_reference_images"][0]["path"] = ".manga-studio/handoff/approved/refs/missing-reference-v001.png"
        job_path = self.project_root / "job.json"
        write_json(job_path, job)

        errors = validate_image_job(job_path, self.project_root)

        self.assertTrue(any("required reference 'character-reference-v001' is missing" in error for error in errors))

    def test_panel_job_must_prohibit_text_balloons_borders_and_marks(self) -> None:
        job = self.valid_panel_job()
        job["prohibited_elements"] = ["watermarks"]
        job_path = self.project_root / "job.json"
        write_json(job_path, job)

        errors = validate_image_job(job_path, self.project_root)

        self.assertTrue(any("manga_panel prohibited_elements is missing" in error for error in errors))
        self.assertTrue(any("dialogue_text" in error for error in errors))
        self.assertTrue(any("panel_borders" in error for error in errors))

    def test_deferred_panel_uses_job_dependencies_not_missing_reference_paths(self) -> None:
        job = self.valid_panel_job()
        job["release_status"] = "deferred"
        job["blocking_reasons"] = ["Reference job has not been approved."]
        job["deferred_reference_dependencies"] = [
            {
                "reference_id": "character-reference-v001",
                "source_job_id": "test-character-reference-job-v001",
                "kind": "character_reference",
                "usage": "Resolve to an approved file before release."
            }
        ]
        job["required_reference_images"] = []
        job_path = self.project_root / "deferred.json"
        write_json(job_path, job)

        errors = validate_image_job(job_path, self.project_root, check_reference_existence=False)

        self.assertEqual(errors, [])

    def test_deferred_panel_rejects_invented_missing_reference_path(self) -> None:
        job = self.valid_panel_job()
        job["release_status"] = "deferred"
        job["blocking_reasons"] = ["Reference is not approved."]
        job["required_reference_images"][0]["path"] = ".manga-studio/handoff/approved/refs/not-real.png"
        job_path = self.project_root / "deferred-invalid.json"
        write_json(job_path, job)

        errors = validate_image_job(job_path, self.project_root, check_reference_existence=False)

        self.assertTrue(any("inventing a missing reference path" in error for error in errors))

    def test_locked_reference_replacement_fails(self) -> None:
        previous = self.valid_panel_job()
        previous_path = self.project_root / "previous.json"
        write_json(previous_path, previous)
        (self.ref_dir / "character-reference-v002.png").write_text(
            "replacement fixture only; not artwork\n",
            encoding="utf-8",
        )

        current = copy.deepcopy(previous)
        current["job_id"] = "test-panel-page-001-p1-v002"
        current["output_filename"] = ".manga-studio/handoff/generated/panels/page-001-panel-01-v002.png"
        current["revision_history"][0]["version"] = "v002"
        current["revision_history"][0]["output_filename"] = ".manga-studio/handoff/generated/panels/page-001-panel-01-v002.png"
        current["required_reference_images"][0]["path"] = ".manga-studio/handoff/approved/refs/character-reference-v002.png"
        current_path = self.project_root / "current.json"
        write_json(current_path, current)

        errors = validate_image_job(current_path, self.project_root, previous_job_path=previous_path)

        self.assertTrue(any("locked reference 'character-reference-v001' changed" in error for error in errors))

    def test_correction_cannot_overwrite_old_output(self) -> None:
        job = self.valid_panel_job()
        job["job_id"] = "test-panel-page-001-p1-v002"
        job["job_type"] = "correction"
        job["revision_of_job_id"] = "test-panel-page-001-p1-v001"
        job["output_filename"] = ".manga-studio/handoff/corrections/page-001-panel-01-v001.png"
        job["revision_history"] = [
            {
                "version": "v001",
                "output_filename": ".manga-studio/handoff/corrections/page-001-panel-01-v001.png",
                "supersedes_job_id": None,
                "supersedes_output_filename": None,
                "notes": "Old correction output."
            },
            {
                "version": "v002",
                "output_filename": ".manga-studio/handoff/corrections/page-001-panel-01-v001.png",
                "supersedes_job_id": "test-panel-page-001-p1-v001",
                "supersedes_output_filename": ".manga-studio/handoff/corrections/page-001-panel-01-v001.png",
                "notes": "Invalid overwrite attempt."
            }
        ]
        job_path = self.project_root / "job.json"
        write_json(job_path, job)

        errors = validate_image_job(job_path, self.project_root)

        self.assertTrue(any("new output_filename" in error for error in errors))
        self.assertTrue(any("must differ from supersedes_output_filename" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
