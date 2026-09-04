from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .json_schema import validate_json_file
from .project import ProjectContext, ProjectOperationError
from .story import _validate_diagnostic_links


def _next_report_path(context: ProjectContext, report_id: str) -> Tuple[Path, str]:
    safe_id = re.sub(r"[^a-zA-Z0-9._-]+", "-", report_id).strip("-")
    if not safe_id:
        raise ProjectOperationError("diagnostic report_id cannot be converted to a filename")
    directory = context.workspace_path("analysis/diagnostics")
    directory.mkdir(parents=True, exist_ok=True)
    versions: List[int] = []
    for path in directory.glob(f"{safe_id}-v???.json"):
        try:
            versions.append(int(path.stem.rsplit("-v", 1)[1]))
        except (IndexError, ValueError):
            continue
    version = max(versions, default=0) + 1
    label = f"v{version:03d}"
    return directory / f"{safe_id}-{label}.json", label


def _markdown(report: Dict[str, Any]) -> str:
    lines = [f"# {report['title']}", "", f"Scope: {report['scope']}", ""]
    for finding in report["findings"]:
        lines.extend([
            f"## {finding['issue_id']}: {finding['category']}",
            "",
            f"Severity: {finding['severity']} | Confidence: {finding['confidence']} | Status: {finding['status']}",
            "",
            finding["description"],
            "",
            f"Why it matters: {finding['why_it_matters']}",
            "",
            f"Uncertainty: {finding['uncertainty']}",
            "",
            f"Manga adaptation impact: {finding['adaptation_impact']}",
            "",
        ])
    return "\n".join(lines)


def publish_diagnostic_report(
    context: ProjectContext,
    draft_path: Path,
    *,
    markdown_companion: bool = False,
) -> Dict[str, str]:
    draft_path = draft_path.expanduser().resolve()
    if not draft_path.is_file():
        raise ProjectOperationError(f"diagnostic draft does not exist: {draft_path}")
    report = json.loads(draft_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ProjectOperationError("diagnostic draft must be a JSON object")
    if report.get("project_id") != context.config.get("project_id"):
        raise ProjectOperationError("diagnostic draft belongs to another project")
    destination, version = _next_report_path(context, report.get("report_id", "diagnostic"))
    report["report_version"] = version
    encoded = json.dumps(report, indent=2) + "\n"
    destination.write_text(encoded, encoding="utf-8")
    schema_errors = validate_json_file(destination, context.install_root / "schemas" / "diagnostic-report.schema.json")
    link_errors = _validate_diagnostic_links(context)
    if schema_errors or link_errors:
        destination.unlink()
        raise ProjectOperationError("diagnostic report validation failed: " + "; ".join([*schema_errors, *link_errors]))
    outputs = {"json": destination.relative_to(context.project_root).as_posix()}
    if markdown_companion:
        markdown_path = destination.with_suffix(".md")
        markdown_path.write_text(_markdown(report), encoding="utf-8")
        outputs["markdown"] = markdown_path.relative_to(context.project_root).as_posix()
    return outputs
