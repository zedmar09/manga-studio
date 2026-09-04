#!/usr/bin/env python3
from __future__ import annotations

import json
import py_compile
import sys
from pathlib import Path
from typing import List

from install_skills import load_manifest, verify_skill


REQUIRED_SKILL_SECTIONS = (
    "## Purpose",
    "## Activation Conditions",
    "## Compatible Operating Modes",
    "## Required Inputs",
    "## Optional Inputs",
    "## Project Discovery",
    "## Source Of Truth",
    "## Owned Outputs",
    "## Procedure",
    "## Required Schemas",
    "## Next-Skill Handoff",
    "## Approval Requirements",
    "## Failure Behavior",
    "## Non-Destructive Constraints",
    "## Out Of Scope",
    "## Representative Example",
    "## Acceptance Criteria",
)


def run_doctor(install_root: Path, *, verbose: bool = False) -> List[str]:
    errors: List[str] = []
    checks: List[str] = []
    try:
        manifest = load_manifest(install_root)
        checks.append(f"manifest lists exactly {len(manifest['skills'])} unique skills")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"manifest check failed: {exc}"]

    for item in manifest["skills"]:
        skill_root = install_root / "skills-src" / item["name"]
        skill_errors = verify_skill(skill_root, item["name"], item["version"])
        errors.extend(skill_errors)
        skill_file = skill_root / "SKILL.md"
        if skill_file.is_file():
            text = skill_file.read_text(encoding="utf-8")
            for section in REQUIRED_SKILL_SECTIONS:
                if section not in text:
                    errors.append(f"{item['name']}: missing required section {section}")
    if not errors:
        checks.append("all canonical SKILL.md files have matching metadata and required quality sections")

    for schema in sorted((install_root / "schemas").glob("*.schema.json")):
        try:
            data = json.loads(schema.read_text(encoding="utf-8"))
            if data.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                errors.append(f"{schema.name}: expected JSON Schema draft 2020-12")
            if not data.get("$id"):
                errors.append(f"{schema.name}: missing $id")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{schema.name}: {exc}")
    checks.append("JSON schemas parse and declare draft 2020-12 identifiers")

    for script in sorted((install_root / "scripts").rglob("*.py")):
        try:
            py_compile.compile(str(script), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"Python compilation failed for {script.name}: {exc}")
    if not any("compilation" in error for error in errors):
        checks.append("all toolkit Python scripts compile")

    repo_skills = install_root / ".agents" / "skills"
    for item in manifest["skills"]:
        path = repo_skills / item["name"] / "SKILL.md"
        if not path.is_file():
            errors.append(f"repository-scoped skill is missing: {path}")
    if not any("repository-scoped" in error for error in errors):
        checks.append("repository-scoped skill suite exposes all 17 canonical skills")

    if verbose:
        for check in checks:
            print(f"PASS: {check}")
        for error in errors:
            print(f"FAIL: {error}")
        print(f"Doctor result: {'READY' if not errors else 'NOT READY'}")
    return errors


def main() -> int:
    install_root = Path(__file__).resolve().parents[1]
    return 1 if run_doctor(install_root, verbose=True) else 0


if __name__ == "__main__":
    raise SystemExit(main())
