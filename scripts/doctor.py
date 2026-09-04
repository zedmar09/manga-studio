#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from install_skills import REGISTRY_NAME, RUNTIME_DIRECTORY, load_manifest, toolkit_version, verify_skill


REQUIRED_SKILL_SECTIONS = (
    "## Purpose", "## Activation Conditions", "## Compatible Operating Modes", "## Required Inputs",
    "## Optional Inputs", "## Project Discovery", "## Source Of Truth", "## Owned Outputs",
    "## Procedure", "## Required Schemas", "## Next-Skill Handoff", "## Approval Requirements",
    "## Failure Behavior", "## Non-Destructive Constraints", "## Out Of Scope",
    "## Representative Example", "## Acceptance Criteria",
)

REQUIRED_STORY_SCHEMAS = {
    "source-document.schema.json", "source-map.schema.json", "story-model.schema.json",
    "story-arc.schema.json", "chapter.schema.json", "scene.schema.json", "canon.schema.json",
    "timeline-event.schema.json", "relationship.schema.json", "plot-thread.schema.json",
    "setup-payoff.schema.json", "character-state.schema.json", "voice-guide.schema.json",
    "story-issue.schema.json", "diagnostic-report.schema.json", "revision-policy.schema.json",
    "revision-plan.schema.json", "change-set.schema.json", "approval.schema.json",
    "decision-log.schema.json", "stage-lock.schema.json",
    "success-plan.schema.json",
}


def _check_skill_suite(skill_root: Path, manifest: dict, errors: List[str]) -> None:
    for item in manifest["skills"]:
        root = skill_root / item["name"]
        errors.extend(verify_skill(root, item["name"], item["version"]))
        skill_file = root / "SKILL.md"
        if skill_file.is_file():
            text = skill_file.read_text(encoding="utf-8")
            for section in REQUIRED_SKILL_SECTIONS:
                if section not in text:
                    errors.append(f"{item['name']}: missing required section {section}")


def _check_runtime(runtime_root: Path, expected_version: str, errors: List[str]) -> Optional[Path]:
    current_path = runtime_root / "current.json"
    if not current_path.is_file():
        errors.append(f"installed runtime current.json is missing: {current_path}")
        return None
    try:
        current = json.loads(current_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"installed runtime current.json is unreadable: {exc}")
        return None
    if current.get("runtime_version") != expected_version:
        errors.append("installed runtime version does not match manifest")
    version_path = current.get("version_path")
    if not isinstance(version_path, str):
        errors.append("installed runtime version_path is missing")
        return None
    version_root = runtime_root / version_path
    for required in (
        "scripts/manga_studio.py",
        "scripts/compose_page.py",
        "scripts/add_lettering.py",
        "scripts/review_page.py",
        "scripts/validate_generated_image.py",
        "scripts/preflight_print.py",
        "scripts/lib/manga_studio/page_pipeline.py",
        "scripts/lib/manga_studio/image_intake.py",
        "scripts/lib/manga_studio/print_preflight.py",
        "schemas/project.schema.json",
        "schemas/page.schema.json",
        "schemas/panel.schema.json",
        "schemas/review.schema.json",
        "schemas/generated-image.schema.json",
        "schemas/creative-brief.schema.json",
        "schemas/success-plan.schema.json",
        "schemas/nemu.schema.json",
        "templates/success-plan.template.json",
        "templates/story-model.template.json",
        "manifests/manga-skills.json",
        "VERSION",
    ):
        if not (version_root / required).is_file():
            errors.append(f"installed runtime payload is missing: {version_root / required}")
    if (version_root / "VERSION").is_file():
        try:
            installed_manifest = load_manifest(version_root)
            if installed_manifest.get("runtime_version") != expected_version:
                errors.append("installed runtime manifest version does not match repository manifest")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"installed runtime manifest/version check failed: {exc}")
    if not (runtime_root / "manga-studio.py").is_file():
        errors.append("installed runtime launcher is missing")
    return version_root


def _check_unrelated_invocation(command: List[str], errors: List[str]) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        result = subprocess.run(command, cwd=temporary, text=True, capture_output=True, check=False)
    if result.returncode != 0 or "usage:" not in result.stdout.lower():
        errors.append("runtime cannot be invoked from an unrelated story directory")


def _check_duplicate_skill_names(skill_root: Path, errors: List[str]) -> None:
    locations: dict[str, List[Path]] = {}
    if not skill_root.is_dir():
        return
    for candidate in skill_root.iterdir():
        if candidate.name.startswith(".") or not candidate.is_dir():
            continue
        skill_file = candidate / "SKILL.md"
        if not skill_file.is_file():
            continue
        for line in skill_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("name: "):
                locations.setdefault(line.removeprefix("name: ").strip(), []).append(candidate)
                break
    for name, paths in sorted(locations.items()):
        if len(paths) > 1:
            errors.append(f"duplicate personal skill name '{name}': " + ", ".join(str(path) for path in paths))


def run_doctor(
    install_root: Path,
    *,
    verbose: bool = False,
    mode: str = "repository",
    destination_root: Optional[Path] = None,
) -> List[str]:
    errors: List[str] = []
    checks: List[str] = []
    install_root = install_root.expanduser().resolve()
    runtime_validation_root = install_root
    try:
        manifest = load_manifest(install_root)
        version = toolkit_version(install_root)
        checks.append(f"manifest lists exactly {len(manifest['skills'])} unique skills at runtime {version}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"manifest check failed: {exc}"]

    if mode == "repository":
        _check_skill_suite(install_root / "skills-src", manifest, errors)
        repo_skills = install_root / ".agents" / "skills"
        for item in manifest["skills"]:
            path = repo_skills / item["name"]
            if path.is_symlink() and not path.exists():
                errors.append(f"broken repository-scoped skill symlink: {path}")
            if not (path / "SKILL.md").is_file():
                errors.append(f"repository-scoped skill is missing: {path}")
        for required in ("scripts/manga_studio.py", "templates/story-model.template.json", "VERSION"):
            if not (install_root / required).is_file():
                errors.append(f"repository runtime payload is missing: {required}")
        _check_unrelated_invocation(
            [sys.executable, os.fspath(install_root / "scripts" / "manga_studio.py"), "--help"],
            errors,
        )
        checks.append("repository development mode and unrelated-directory invocation checked")
    elif mode == "installed":
        destination = (destination_root or Path.home() / ".agents" / "skills").expanduser().resolve()
        registry_path = destination / REGISTRY_NAME
        if not registry_path.is_file():
            return [f"installation registry is missing: {registry_path}"]
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        if registry.get("namespace") != "manga-studio":
            errors.append("installation registry namespace is not manga-studio")
        if registry.get("runtime_version") != version:
            errors.append("installation registry runtime version does not match repository manifest")
        install_mode = registry.get("mode")
        if install_mode not in {"symlink", "copy"}:
            errors.append(f"installation registry has unsupported mode: {install_mode}")
        _check_skill_suite(destination, manifest, errors)
        _check_duplicate_skill_names(destination, errors)
        for item in manifest["skills"]:
            path = destination / item["name"]
            if path.is_symlink() and not path.exists():
                errors.append(f"broken installed skill symlink: {path}")
            if install_mode == "symlink" and not path.is_symlink():
                errors.append(f"symlink-mode skill is not a symlink: {path}")
            if install_mode == "copy" and path.is_symlink():
                errors.append(f"copy-mode skill must not be a symlink: {path}")
        runtime_root = destination / RUNTIME_DIRECTORY
        installed_version_root = _check_runtime(runtime_root, version, errors)
        if installed_version_root is not None:
            runtime_validation_root = installed_version_root
        _check_unrelated_invocation([os.fspath(runtime_root / "manga-studio.py"), "--help"], errors)
        checks.append(f"actual {install_mode} installation and shared runtime checked")
    else:
        return [f"unknown doctor mode: {mode}"]

    schema_root = runtime_validation_root / "schemas"
    available_schemas = {
        path.name for path in schema_root.glob("*.schema.json")
        if not path.name.startswith("._")
    }
    expected_schemas = {
        path.name for path in (install_root / "schemas").glob("*.schema.json")
        if not path.name.startswith("._")
    } | REQUIRED_STORY_SCHEMAS
    missing_schemas = sorted(expected_schemas - available_schemas)
    if missing_schemas:
        errors.append("story schemas are missing: " + ", ".join(missing_schemas))
    for schema in sorted(schema_root.glob("*.schema.json")):
        if schema.name.startswith("._"):
            continue
        try:
            data = json.loads(schema.read_text(encoding="utf-8"))
            if data.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                errors.append(f"{schema.name}: expected JSON Schema draft 2020-12")
            if not data.get("$id"):
                errors.append(f"{schema.name}: missing $id")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{schema.name}: {exc}")
    checks.append("schema availability and JSON Schema identifiers checked")

    for script in sorted((runtime_validation_root / "scripts").rglob("*.py")):
        if script.name.startswith("._"):
            continue
        try:
            py_compile.compile(str(script), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"Python compilation failed for {script}: {exc}")
    checks.append("toolkit Python compilation checked")

    if verbose:
        for check in checks:
            print(f"PASS: {check}")
        for error in errors:
            print(f"FAIL: {error}")
        print(f"Doctor result: {'READY' if not errors else 'NOT READY'}")
    return errors


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Manga Studio repository or installation readiness.")
    parser.add_argument("--mode", choices=["repository", "installed"], default="repository")
    parser.add_argument("--destination-root", type=Path)
    args = parser.parse_args(argv)
    install_root = Path(__file__).resolve().parents[1]
    return 1 if run_doctor(
        install_root, verbose=True, mode=args.mode, destination_root=args.destination_root
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
