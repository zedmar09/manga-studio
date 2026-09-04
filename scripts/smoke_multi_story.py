#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from manga_studio.profiles import validate_profile
from manga_studio.project import import_sources, initialize_project, inventory_sources
from manga_studio.structure import structure_sources
from manga_studio.validation import write_json


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(root: Path, title: str, text: str):
    root.mkdir()
    source = root / "story.md"
    source.write_text(text, encoding="utf-8")
    before = digest(source)
    context, _ = initialize_project(root, title=title)
    inventory = inventory_sources(context)
    inventory["files"][0]["classification_status"] = "approved"
    inventory["files"][0]["usage_role"] = "primary_manuscript"
    write_json(context.workspace_path("source/inventory.json"), inventory)
    import_sources(context)
    structure_sources(context)
    errors = validate_profile(context, "story")
    if errors:
        raise RuntimeError(f"{title} failed validation: {'; '.join(errors)}")
    if digest(source) != before:
        raise RuntimeError(f"{title} original source changed")
    return context


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        first = prepare(base / "first", "First Story", "# Chapter 1: First\n\nFirst story.\n")
        second = prepare(base / "second", "Second Story", "# Chapter 1: Second\n\nSecond story.\n")
        if first.config["project_id"] == second.config["project_id"]:
            raise RuntimeError("disposable stories share a project_id")
        if second.config["project_id"] in first.workspace_path("source/structure.json").read_text(encoding="utf-8"):
            raise RuntimeError("second project leaked into first structure index")
        if first.config["project_id"] in second.workspace_path("source/structure.json").read_text(encoding="utf-8"):
            raise RuntimeError("first project leaked into second structure index")
    print("Disposable multi-story smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
