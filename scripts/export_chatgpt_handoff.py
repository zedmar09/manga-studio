#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from manga_studio.handoff import export_chatgpt_handoff, prepare_chatgpt_handoff
from manga_studio.project import ProjectDiscoveryError, ProjectOperationError, discover_project


def _project_path(context, value: Path) -> Path:
    return value.expanduser().resolve() if value.is_absolute() else context.project_path(value.as_posix())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a paste-ready ChatGPT image-generation handoff.")
    parser.add_argument("job", type=Path, help="Image-job JSON under .manga-studio/handoff/pending/.")
    parser.add_argument("--project", type=Path, help="Story directory or nested project path.")
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument("--output", type=Path, help="Project-relative .md destination under handoff/pending/.")
    destination.add_argument("--stdout", action="store_true", help="Print the Markdown instead of writing a file.")
    args = parser.parse_args(argv)

    probe = args.project or (args.job if args.job.is_absolute() else Path.cwd())
    try:
        context = discover_project(probe)
        job_path = _project_path(context, args.job)
        if args.stdout:
            print(prepare_chatgpt_handoff(context, job_path), end="")
        else:
            output_path = _project_path(context, args.output) if args.output else None
            print(export_chatgpt_handoff(context, job_path, output_path))
    except (ProjectDiscoveryError, ProjectOperationError, OSError, ValueError) as exc:
        print(f"ChatGPT handoff export failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
