#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    runtime_root = Path(__file__).resolve().parent
    current_path = runtime_root / "current.json"
    if not current_path.is_file():
        print(f"Manga Studio runtime error: missing {current_path}", file=sys.stderr)
        return 2
    current = json.loads(current_path.read_text(encoding="utf-8"))
    version_path = current.get("version_path")
    if not isinstance(version_path, str):
        print("Manga Studio runtime error: current.json lacks version_path", file=sys.stderr)
        return 2
    cli = runtime_root / version_path / "scripts" / "manga_studio.py"
    if not cli.is_file():
        print(f"Manga Studio runtime error: missing CLI {cli}", file=sys.stderr)
        return 2
    os.execv(sys.executable, [sys.executable, str(cli), *sys.argv[1:]])
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
