from __future__ import annotations

import json
import unittest

from helpers import REPO_ROOT
from doctor import run_doctor
from manga_studio.json_schema import validate_json_file


EXPECTED_SKILLS = {
    "manga-creator",
    "manga-source-ingestor",
    "manga-story-diagnostician",
    "manga-canon-manager",
    "manga-revision-planner",
    "manga-story-architect",
    "manga-character-bible",
    "manga-world-bible",
    "manga-chapter-writer",
    "manga-dialogue-writer",
    "manga-storyboard-director",
    "manga-panel-director",
    "manga-consistency-manager",
    "manga-image-job-builder",
    "manga-lettering",
    "manga-page-compositor",
    "manga-continuity-reviewer",
}


class ManifestAndSchemaTests(unittest.TestCase):
    def test_manifest_lists_exactly_expected_skills(self) -> None:
        manifest = json.loads((REPO_ROOT / "manifests" / "manga-skills.json").read_text(encoding="utf-8"))
        names = [item["name"] for item in manifest["skills"]]
        self.assertEqual(len(names), 17)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), EXPECTED_SKILLS)

    def test_all_json_and_schema_documents_parse(self) -> None:
        json_files = sorted(
            path for path in REPO_ROOT.rglob("*.json")
            if ".git" not in path.parts and not path.name.startswith("._")
        )
        self.assertGreater(len(json_files), 0)
        for path in json_files:
            with self.subTest(path=path):
                parsed = json.loads(path.read_text(encoding="utf-8"))
                if path.name.endswith(".schema.json"):
                    self.assertEqual(parsed["$schema"], "https://json-schema.org/draft/2020-12/schema")
                    self.assertTrue(parsed["$id"])

    def test_doctor_library_checks_pass(self) -> None:
        self.assertEqual(run_doctor(REPO_ROOT), [])

    def test_pilot_artifacts_validate_against_json_schemas(self) -> None:
        pilot = REPO_ROOT / "projects" / "pilot-001" / ".manga-studio"
        schema_root = REPO_ROOT / "schemas"
        cases = [
            (pilot / "project.json", schema_root / "project.schema.json"),
            (pilot / "source" / "inventory.json", schema_root / "source-inventory.schema.json"),
            (pilot / "source" / "provenance.json", schema_root / "provenance.schema.json"),
            (pilot / "source" / "id-map.json", schema_root / "stable-id-map.schema.json"),
            (pilot / "pages" / "page-001.json", schema_root / "page.schema.json"),
        ]
        cases.extend(
            (path, schema_root / "image-job.schema.json")
            for path in sorted((pilot / "handoff" / "pending").glob("*.json"))
        )
        for instance, schema in cases:
            with self.subTest(instance=instance.name, schema=schema.name):
                self.assertEqual(validate_json_file(instance, schema), [])


if __name__ == "__main__":
    unittest.main()
