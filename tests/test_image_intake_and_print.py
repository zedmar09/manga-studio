from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

from helpers import REPO_ROOT, initialize, read_json, write_json
from manga_studio.approvals import record_approval, validate_approval
from manga_studio.profiles import validate_approved_panel_artwork
from manga_studio.print_preflight import preflight_project
from manga_studio.project import ProjectOperationError, discover_project, sha256_file


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def grayscale_png(width: int, height: int) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    rows = b"".join(b"\x00" + bytes([127]) * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", header) + _png_chunk(b"IDAT", zlib.compress(rows)) + _png_chunk(b"IEND", b"")


class GeneratedImageIntakeTests(unittest.TestCase):
    def _prepare(self, root: Path, actual_width: int = 4) -> tuple[Path, Path, Path]:
        context = initialize(root, mode="prepare_visual_production")
        source = read_json(
            REPO_ROOT / "projects/pilot-001/.manga-studio/handoff/pending/pilot-001-panel-page-001-p1-v001.json"
        )
        source["job_id"] = "intake-test-panel-v001"
        source["output_filename"] = ".manga-studio/handoff/generated/panels/intake-test-panel-v001.png"
        source["output_spec"]["width"] = 4
        source["output_spec"]["height"] = 3
        source["revision_history"][-1]["output_filename"] = source["output_filename"]
        source["release_status"] = "ready"
        source["blocking_reasons"] = []
        source["deferred_reference_dependencies"] = []
        source["required_reference_images"] = [{
            "reference_id": "test-character-reference-v001",
            "kind": "character_reference",
            "path": ".manga-studio/handoff/approved/refs/test-character-reference-v001.png",
            "locked": True,
            "usage": "Test fixture reference.",
        }]
        source["reference_priority"] = ["test-character-reference-v001"]
        job_path = context.workspace_path("handoff/pending/intake-test-panel-v001.json")
        image_path = context.project_path(source["output_filename"])
        reference_path = context.project_path(source["required_reference_images"][0]["path"])
        reference_path.parent.mkdir(parents=True, exist_ok=True)
        reference_path.write_bytes(b"reference fixture only; not artwork\n")
        write_json(job_path, source)
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(grayscale_png(actual_width, 3))
        return context.project_root, job_path, image_path

    def test_matching_external_image_creates_technical_intake(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, job, image = self._prepare(Path(temporary) / "story")
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/validate_generated_image.py"), str(job), str(image), "--project", str(project)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            records = list((project / ".manga-studio/continuity/intake").glob("*.json"))
            self.assertEqual(len(records), 1)
            record = read_json(records[0])
            self.assertEqual(record["status"], "technical_valid")
            self.assertTrue(record["approval_required"])
            self.assertEqual(record["file"]["width"], 4)

    def test_dimension_mismatch_is_versioned_and_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, job, image = self._prepare(Path(temporary) / "story", actual_width=5)
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/validate_generated_image.py"), str(job), str(image), "--project", str(project)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            record = read_json(next((project / ".manga-studio/continuity/intake").glob("*.json")))
            self.assertEqual(record["status"], "blocked")
            self.assertIn("width_mismatch", {item["code"] for item in record["findings"]})

    def test_image_at_an_unexpected_path_is_rejected_without_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, job, image = self._prepare(Path(temporary) / "story")
            wrong = project / ".manga-studio/handoff/generated/panels/unexpected.png"
            wrong.write_bytes(image.read_bytes())
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/validate_generated_image.py"), str(job), str(wrong), "--project", str(project)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("must exactly match", result.stdout)
            self.assertEqual(list((project / ".manga-studio/continuity/intake").glob("*.json")), [])

    def test_schema_invalid_job_cannot_create_an_intake_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, job, image = self._prepare(Path(temporary) / "story")
            job_data = read_json(job)
            job_data["unexpected"] = "not allowed"
            write_json(job, job_data)
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/validate_generated_image.py"), str(job), str(image), "--project", str(project)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("unexpected property", result.stdout)
            self.assertEqual(list((project / ".manga-studio/continuity/intake").glob("*.json")), [])

    def test_deferred_job_cannot_accept_a_generated_image(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, job, image = self._prepare(Path(temporary) / "story")
            job_data = read_json(job)
            job_data["release_status"] = "deferred"
            job_data["blocking_reasons"] = ["Not released for external generation."]
            write_json(job, job_data)

            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/validate_generated_image.py"), str(job), str(image), "--project", str(project)],
                text=True, capture_output=True, check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("only for ready, released, or completed jobs", result.stdout)
            self.assertEqual(list((project / ".manga-studio/continuity/intake").glob("*.json")), [])

    def test_production_art_requires_hash_bound_human_visual_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, job, image = self._prepare(Path(temporary) / "story")
            context = discover_project(project)
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/validate_generated_image.py"), str(job), str(image), "--project", str(project)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            intake_path = next(context.workspace_path("continuity/intake").glob("*.json"))
            review_path = context.workspace_path("continuity/intake-test-panel-visual-review-v001.json")
            write_json(review_path, {
                "schema_version": "1.0.0",
                "review_id": "intake-test-panel-visual-review-v001",
                "project_id": context.config["project_id"],
                "review_type": "generated_image",
                "target": intake_path.relative_to(project).as_posix(),
                "target_sha256": sha256_file(intake_path),
                "status": "review_ready", "automated": False, "approval_required": True,
                "metric_scope": "human_visual_assessment", "findings": [],
                "visual_assessment": {
                    "reviewer": "test-reviewer", "reviewed_at": "2026-01-01T00:00:00Z",
                    "story_clarity": 4, "event_readability": 4, "reference_adherence": 4,
                    "character_acting": 4, "composition": 4, "monochrome_finish": 4,
                    "continuity": 4, "lettering_readability": 4,
                    "content_boundary_compliance": 4,
                    "required_elements_present": True,
                    "prohibited_elements_absent": True,
                    "dialogue_safe_zones_usable": True,
                    "artifact_free": True,
                    "notes": [],
                },
            })
            with self.assertRaises(ProjectOperationError):
                record_approval(
                    context, intake_path, artifact_type="generated_image", target_version="v001",
                    actor="test-reviewer", decision="approved",
                )
            low_quality_review = read_json(review_path)
            low_quality_review["visual_assessment"]["composition"] = 3
            write_json(review_path, low_quality_review)
            with self.assertRaisesRegex(ProjectOperationError, "quality scores below 4"):
                record_approval(
                    context, review_path, artifact_type="generated_image", target_version="v001",
                    actor="test-reviewer", decision="approved",
                )
            low_quality_review["visual_assessment"]["composition"] = 4
            write_json(review_path, low_quality_review)
            record_approval(
                context, review_path, artifact_type="generated_image", target_version="v001",
                actor="test-reviewer", decision="approved",
            )
            approved = context.workspace_path("handoff/approved/panels/intake-test-panel-v001.png")
            approved.parent.mkdir(parents=True, exist_ok=True)
            approved.write_bytes(image.read_bytes())
            page = {
                "page_id": "page-001",
                "panels": [{
                    "panel_id": "p1", "source_job_id": "intake-test-panel-v001",
                    "art_path": approved.relative_to(project).as_posix(),
                }],
            }
            self.assertEqual(validate_approved_panel_artwork(context, page), [])
            approved.write_bytes(grayscale_png(5, 3))
            self.assertTrue(any(
                "hash-matching" in error for error in validate_approved_panel_artwork(context, page)
            ))


class PrintPreflightTests(unittest.TestCase):
    def _print_project(self, root: Path):
        context = initialize(root, mode="create_new")
        config = read_json(context.project_file)
        config["target_manga_format"] = {
            "color_mode": "black-and-white",
            "page_width_px": 1575,
            "page_height_px": 2475,
            "output_intent": "print",
            "print_profile": {
                "name": "five-by-eight-with-bleed",
                "unit": "in", "dpi": 300,
                "trim_width": 5, "trim_height": 8,
                "bleed": {"top": 0.125, "right": 0.125, "bottom": 0.125, "left": 0.125},
                "safe_margin": {"top": 0.125, "right": 0.125, "bottom": 0.125, "left": 0.125},
                "binding": "perfect", "inner_gutter": 0.25, "page_side": "single",
                "export_format": "pdf", "crop_marks": True, "color_profile": "Gray Gamma 2.2",
            },
        }
        write_json(context.project_file, config)
        write_json(context.workspace_path("pages/page-001.json"), {
            "page_id": "page-001", "page_number": 1,
            "page_size": {"width": 1575, "height": 2475},
            "layout": {"safe_area": {"x": 75, "y": 75, "width": 1425, "height": 2325}},
        })
        return discover_project(root)

    def test_valid_physical_profile_resolves_exact_pixel_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self._print_project(Path(temporary) / "story")
            errors, findings, summary = preflight_project(context)
            self.assertEqual(errors, [])
            self.assertEqual(summary["expected_canvas_px"], {"width": 1575, "height": 2475})
            self.assertTrue(any(item["code"] == "page_side_resolved" for item in findings))

    def test_wrong_canvas_dimensions_fail_print_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self._print_project(Path(temporary) / "story")
            config = read_json(context.project_file)
            config["target_manga_format"]["page_width_px"] = 1600
            write_json(context.project_file, config)
            context = discover_project(context.project_root)
            errors, _, _ = preflight_project(context)
            self.assertTrue(any("trim plus bleed" in error for error in errors))

    def test_invalid_print_page_number_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self._print_project(Path(temporary) / "story")
            page_path = context.workspace_path("pages/page-001.json")
            page = read_json(page_path)
            page["page_number"] = "first"
            write_json(page_path, page)

            errors, _, _ = preflight_project(context)

            self.assertTrue(any("page_number must be a positive integer" in error for error in errors))

    def test_print_approval_is_bound_to_every_current_page_specification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self._print_project(Path(temporary) / "story")
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/preflight_print.py"), "--project", str(context.project_root)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            review = next(context.workspace_path("production/preflight").glob("*.json"))
            approval = record_approval(
                context, review, artifact_type="print_preflight", target_version="v001",
                actor="test-reviewer", decision="approved",
            )
            page_path = context.workspace_path("pages/page-001.json")
            page = read_json(page_path)
            page["layout"]["safe_area"]["x"] += 1
            page["layout"]["safe_area"]["width"] -= 1
            write_json(page_path, page)

            errors = validate_approval(discover_project(context.project_root), approval)

            self.assertTrue(any("target hashes do not match" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
