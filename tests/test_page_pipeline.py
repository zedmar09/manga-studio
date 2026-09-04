from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))

from compose_page import compose_svg
from manga_studio.json_schema import validate_instance
from manga_studio.page_pipeline import lettering_svg, next_version_path, page_quality_review, polygons_overlap
from manga_studio.validation import validate_page_spec


class PagePipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temporary.name)
        self.page = json.loads(
            (REPO_ROOT / "projects" / "pilot-001" / ".manga-studio" / "pages" / "page-001.json").read_text(
                encoding="utf-8"
            )
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_page(self, page: dict) -> Path:
        path = self.project_root / ".manga-studio" / "pages" / "page-001.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(page, indent=2) + "\n", encoding="utf-8")
        return path

    def test_dynamic_four_panel_page_passes_schema_and_geometry_validation(self) -> None:
        page_path = self.write_page(self.page)

        schema_errors = validate_instance(self.page, REPO_ROOT / "schemas" / "page.schema.json")
        validation_errors = validate_page_spec(page_path, self.project_root)

        self.assertEqual(schema_errors, [])
        self.assertEqual(validation_errors, [])

    def test_self_intersecting_polygon_and_unapproved_overlap_are_rejected(self) -> None:
        page = copy.deepcopy(self.page)
        page["panels"][0]["clip_polygon"] = [
            {"x": 780, "y": 100},
            {"x": 1500, "y": 1180},
            {"x": 1500, "y": 100},
            {"x": 780, "y": 1180},
        ]
        page["panels"][2]["frame"] = {"x": 200, "y": 1300, "width": 500, "height": 800}
        page["panels"][2]["clip_polygon"] = [
            {"x": 200, "y": 1300},
            {"x": 700, "y": 1300},
            {"x": 700, "y": 2100},
            {"x": 200, "y": 2100},
        ]
        page_path = self.write_page(page)

        errors = validate_page_spec(page_path, self.project_root)

        self.assertTrue(any("must not self-intersect" in error for error in errors))
        self.assertTrue(any("overlap without permission" in error for error in errors))

    def test_compositor_uses_polygon_clips_focus_and_z_order(self) -> None:
        page = copy.deepcopy(self.page)
        approved = self.project_root / ".manga-studio" / "handoff" / "approved" / "panels"
        approved.mkdir(parents=True)
        for index, panel in enumerate(page["panels"], start=1):
            path = approved / f"panel-{index}-v001.png"
            path.write_bytes(b"panel fixture only; not artwork\n")
            panel["art_path"] = path.relative_to(self.project_root).as_posix()
        page["panels"][0]["z_index"] = 3
        page["panels"][1]["z_index"] = 1

        svg = compose_svg(page, self.project_root, self.project_root / "composed.svg")

        self.assertIn('<clipPath id="clip-p1"><polygon', svg)
        self.assertIn('preserveAspectRatio="xMidYMid slice"', svg)
        self.assertLess(svg.index('id="panel-p2"'), svg.index('id="panel-p1"'))
        self.assertIn('data-z-index="3"', svg)

    def test_lettering_renders_sfx_ellipse_and_thought_cloud_as_vector_shapes(self) -> None:
        page = copy.deepcopy(self.page)
        page["lettering"].append({
            "lettering_id": "page-001-thought-01",
            "panel_id": "p2",
            "reading_order": 6,
            "kind": "thought",
            "text": "Where is it?",
            "box": {"x": 230, "y": 820, "width": 320, "height": 160},
            "shape": "cloud",
            "tail_to": {"x": 500, "y": 1040},
        })

        svg = lettering_svg(page)

        self.assertIn('data-kind="sfx"', svg)
        self.assertIn('paint-order="stroke fill"', svg)
        self.assertIn('rotate(-8 ', svg)
        self.assertIn('data-kind="speech"', svg)
        self.assertIn('data-kind="thought"', svg)
        self.assertIn("<circle", svg)

    def test_quality_review_flags_unmarked_action_axis_reversal(self) -> None:
        page = copy.deepcopy(self.page)
        page["panels"][0]["event"]["event_type"] = "action"
        page["panels"][0]["event"]["action_direction"] = "left_to_right"
        page["panels"][1]["event"]["event_type"] = "action"
        page["panels"][1]["event"]["action_direction"] = "right_to_left"
        page["panels"][1]["event"]["axis_break"] = False

        review = page_quality_review(
            page,
            project_id="test-project",
            target=".manga-studio/pages/page-001.json",
            review_id="page-001-quality-v001",
        )

        self.assertEqual(review["status"], "changes_requested")
        self.assertTrue(any(finding.get("code") == "UNMARKED_AXIS_REVERSAL" for finding in review["findings"]))
        self.assertLess(review["metrics"]["continuity"], 100)

    def test_high_quality_pilot_is_ready_for_human_review_not_auto_approved(self) -> None:
        review = page_quality_review(
            self.page,
            project_id="pilot-001",
            target=".manga-studio/pages/page-001.json",
            review_id="page-001-quality-v001",
        )

        self.assertEqual(review["status"], "review_ready")
        self.assertTrue(review["approval_required"])
        self.assertEqual(review["metrics"]["overall"], 100)

    def test_versioned_output_path_never_reuses_an_existing_version(self) -> None:
        directory = self.project_root / "outputs"
        directory.mkdir()
        (directory / "page-001-composed-v001.svg").write_text("fixture\n", encoding="utf-8")
        (directory / "page-001-composed-v003.svg").write_text("fixture\n", encoding="utf-8")

        destination = next_version_path(directory, "page-001-composed", ".svg")

        self.assertEqual(destination.name, "page-001-composed-v004.svg")

    def test_identical_panel_polygons_count_as_overlap(self) -> None:
        polygon = [(10.0, 10.0), (90.0, 10.0), (90.0, 90.0), (10.0, 90.0)]

        self.assertTrue(polygons_overlap(polygon, list(polygon)))

    def test_source_safe_zone_cropped_by_panel_polygon_is_rejected(self) -> None:
        page = copy.deepcopy(self.page)
        page["panels"][0]["dialogue_safe_zones"] = [
            {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
        ]
        page_path = self.write_page(page)

        errors = validate_page_spec(page_path, self.project_root)

        self.assertTrue(any("is cropped or leaves the panel" in error for error in errors))

    def test_invalid_project_font_fails_clearly_instead_of_silent_fallback(self) -> None:
        page = copy.deepcopy(self.page)
        font_path = self.project_root / ".manga-studio/fonts/not-a-font.ttf"
        font_path.parent.mkdir(parents=True, exist_ok=True)
        font_path.write_bytes(b"not a font")
        page["lettering_style"]["font_file"] = font_path.relative_to(self.project_root).as_posix()
        page_path = self.write_page(page)

        errors = validate_page_spec(page_path, self.project_root)

        self.assertTrue(any("cannot provide usable metrics" in error for error in errors))

    def test_boolean_geometry_is_rejected_as_non_numeric_page_data(self) -> None:
        page = copy.deepcopy(self.page)
        page["page_size"]["width"] = True
        page["panels"][0]["frame"]["x"] = False
        page_path = self.write_page(page)

        errors = validate_page_spec(page_path, self.project_root)

        self.assertTrue(any("page_size.width must be a positive integer" in error for error in errors))
        self.assertTrue(any("panels[0].frame.x must be an integer" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
