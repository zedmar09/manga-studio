from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))

from manga_studio.project import ProjectContext, initialize_project


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def initialize(root: Path, mode: str = "import_existing", title: str | None = None) -> ProjectContext:
    context, _ = initialize_project(root, mode=mode, title=title)
    return context


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def approve_inventory(context: ProjectContext, role: str = "primary_manuscript") -> Dict[str, Any]:
    path = context.workspace_path("source/inventory.json")
    inventory = read_json(path)
    for entry in inventory.get("files", []):
        if entry.get("support_status") == "supported":
            entry["classification_status"] = "approved"
            entry["usage_role"] = role
    write_json(path, inventory)
    return inventory
