#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


NAMESPACE_MARKER = "namespace: manga-studio"
RUNTIME_DIRECTORY = ".manga-studio-runtime"
REGISTRY_NAME = ".manga-studio-install.json"
RUNTIME_PAYLOAD = ("scripts", "schemas", "templates", "manifests")


def toolkit_version(install_root: Path) -> str:
    path = install_root / "VERSION"
    version = path.read_text(encoding="utf-8").strip()
    if not version:
        raise ValueError("VERSION must not be empty")
    return version


def load_manifest(install_root: Path) -> Dict[str, Any]:
    path = install_root / "manifests" / "manga-skills.json"
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    skills = manifest.get("skills")
    if not isinstance(skills, list):
        raise ValueError("manifest skills must be an array")
    names = [item.get("name") for item in skills if isinstance(item, dict)]
    if len(names) != len(skills) or not all(isinstance(name, str) and name for name in names):
        raise ValueError("every manifest skill must have a non-empty name")
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"duplicate Manga Studio skill names: {', '.join(duplicates)}")
    if len(names) != 17:
        raise ValueError(f"manifest must list exactly 17 Manga Studio skills; found {len(names)}")
    version = toolkit_version(install_root)
    if manifest.get("runtime_version") != version:
        raise ValueError(
            f"manifest runtime_version {manifest.get('runtime_version')!r} does not match VERSION {version!r}"
        )
    return manifest


def verify_skill(source: Path, expected_name: str, expected_version: str) -> List[str]:
    errors: List[str] = []
    skill_file = source / "SKILL.md"
    if not skill_file.is_file():
        return [f"missing SKILL.md: {skill_file}"]
    skill_text = skill_file.read_text(encoding="utf-8")
    if not skill_text.startswith("---\n"):
        errors.append(f"invalid frontmatter start: {skill_file}")
    if f"name: {expected_name}\n" not in skill_text:
        errors.append(f"frontmatter name does not match manifest: {skill_file}")
    if NAMESPACE_MARKER not in skill_text:
        errors.append(f"missing Manga Studio namespace marker: {skill_file}")
    if f"version: {expected_version}" not in skill_text and f'version: "{expected_version}"' not in skill_text:
        errors.append(f"frontmatter version does not match manifest: {skill_file}")
    if "description:" not in skill_text:
        errors.append(f"missing description: {skill_file}")
    return errors


def is_managed_manga_skill(destination: Path) -> bool:
    if destination.is_symlink() and not destination.exists():
        return False
    skill_file = destination / "SKILL.md"
    return skill_file.is_file() and NAMESPACE_MARKER in skill_file.read_text(encoding="utf-8")


def plan_install(install_root: Path, destination_root: Path, mode: str) -> Tuple[List[Dict[str, str]], List[str]]:
    if mode not in {"symlink", "copy"}:
        return [], [f"unsupported install mode: {mode}"]
    manifest = load_manifest(install_root)
    plan: List[Dict[str, str]] = []
    errors: List[str] = []
    for item in manifest["skills"]:
        name = item["name"]
        version = item["version"]
        source = install_root / "skills-src" / name
        destination = destination_root / name
        errors.extend(verify_skill(source, name, version))
        if destination.exists() or destination.is_symlink():
            if is_managed_manga_skill(destination):
                action = "replace"
            else:
                action = "reject"
                errors.append(f"refusing to overwrite existing non-Manga skill or broken symlink: {destination}")
        else:
            action = "create"
        plan.append({"action": action, "name": name, "source": str(source), "destination": str(destination), "mode": mode})
    return plan, errors


def _copy_runtime(install_root: Path, runtime_root: Path, version: str) -> None:
    version_root = runtime_root / "versions" / version
    version_root.mkdir(parents=True)
    for name in RUNTIME_PAYLOAD:
        source = install_root / name
        if not source.exists():
            raise RuntimeError(f"runtime payload is missing: {source}")
        shutil.copytree(source, version_root / name, ignore=shutil.ignore_patterns("._*", "__pycache__", "*.pyc"))
    shutil.copy2(install_root / "VERSION", version_root / "VERSION")
    shutil.copy2(install_root / "scripts" / "runtime_launcher.py", runtime_root / "manga-studio.py")
    (runtime_root / "manga-studio.py").chmod(0o755)
    (runtime_root / "current.json").write_text(json.dumps({
        "schema_version": "1.0.0", "runtime_version": version, "version_path": f"versions/{version}"
    }, indent=2) + "\n", encoding="utf-8")


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _restore_transaction(
    destination_root: Path,
    backup_root: Path,
    changed_names: List[str],
    *,
    restore_runtime: bool = True,
    restore_registry: bool = True,
) -> None:
    for name in changed_names:
        destination = destination_root / name
        if destination.exists() or destination.is_symlink():
            _remove_path(destination)
    runtime = destination_root / RUNTIME_DIRECTORY
    if restore_runtime and (runtime.exists() or runtime.is_symlink()):
        _remove_path(runtime)
    registry = destination_root / REGISTRY_NAME
    if restore_registry and (registry.exists() or registry.is_symlink()):
        _remove_path(registry)
    backup_skills = backup_root / "skills"
    if backup_skills.is_dir():
        for source in backup_skills.iterdir():
            shutil.move(str(source), str(destination_root / source.name))
    if restore_runtime and (backup_root / "runtime").exists():
        shutil.move(str(backup_root / "runtime"), str(runtime))
    if restore_registry and (backup_root / "registry.json").exists():
        shutil.move(str(backup_root / "registry.json"), str(registry))


def execute_install(plan: List[Dict[str, str]], destination_root: Path, mode: str) -> Path:
    if any(item["action"] == "reject" for item in plan):
        raise RuntimeError("installation plan contains rejected destinations")
    if not plan:
        raise RuntimeError("installation plan is empty")
    install_root = Path(plan[0]["source"]).resolve().parents[1]
    manifest = load_manifest(install_root)
    version = manifest["runtime_version"]
    destination_root.mkdir(parents=True, exist_ok=True)
    transaction_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    staging = destination_root / f".manga-studio-staging-{transaction_id}"
    backup_root = destination_root / ".manga-studio-backups" / transaction_id
    installed_names = [item["name"] for item in plan]
    staging.mkdir(parents=True, exist_ok=False)
    backup_root.mkdir(parents=True, exist_ok=False)
    commit_started = False
    changed_names: List[str] = []
    runtime_changed = False
    registry_changed = False
    try:
        staged_skills = staging / "skills"
        staged_skills.mkdir()
        for item in plan:
            source = Path(item["source"]).resolve()
            destination = staged_skills / item["name"]
            if mode == "symlink":
                destination.symlink_to(source, target_is_directory=True)
            else:
                shutil.copytree(source, destination, ignore=shutil.ignore_patterns("._*", "__pycache__", "*.pyc"))
        staged_runtime = staging / "runtime"
        _copy_runtime(install_root, staged_runtime, version)

        commit_started = True
        backup_skills = backup_root / "skills"
        backup_skills.mkdir()
        for item in plan:
            destination = Path(item["destination"])
            if destination.exists() or destination.is_symlink():
                shutil.move(str(destination), str(backup_skills / item["name"]))
                changed_names.append(item["name"])
        runtime_destination = destination_root / RUNTIME_DIRECTORY
        if runtime_destination.exists() or runtime_destination.is_symlink():
            shutil.move(str(runtime_destination), str(backup_root / "runtime"))
            runtime_changed = True
        registry_path = destination_root / REGISTRY_NAME
        if registry_path.exists() or registry_path.is_symlink():
            shutil.move(str(registry_path), str(backup_root / "registry.json"))
            registry_changed = True

        shutil.move(str(staged_runtime), str(runtime_destination))
        runtime_changed = True
        for item in plan:
            shutil.move(str(staged_skills / item["name"]), str(Path(item["destination"])))
            if item["name"] not in changed_names:
                changed_names.append(item["name"])
        registry = {
            "schema_version": "2.0.0", "namespace": "manga-studio", "mode": mode,
            "destination_root": str(destination_root), "runtime_root": str(runtime_destination),
            "runtime_version": version, "launcher": str(runtime_destination / "manga-studio.py"),
            "skills": installed_names, "backup_root": str(backup_root), "transaction_id": transaction_id,
        }
        registry_changed = True
        registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
        (backup_root / ".rollback.json").write_text(json.dumps({
            "destination_root": str(destination_root), "installed_names": installed_names, "transaction_id": transaction_id,
        }, indent=2) + "\n", encoding="utf-8")
    except Exception:
        if commit_started:
            _restore_transaction(
                destination_root,
                backup_root,
                changed_names,
                restore_runtime=runtime_changed,
                restore_registry=registry_changed,
            )
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return backup_root


def rollback_install(destination_root: Path, backup_root: Path | None = None) -> Path:
    destination_root = destination_root.expanduser().resolve()
    registry_path = destination_root / REGISTRY_NAME
    if backup_root is None:
        if not registry_path.is_file():
            raise RuntimeError("no Manga Studio installation registry is available for rollback")
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        backup_root = Path(registry["backup_root"])
    backup_root = backup_root.expanduser().resolve()
    metadata_path = backup_root / ".rollback.json"
    if not metadata_path.is_file():
        raise RuntimeError(f"rollback metadata is missing: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if Path(metadata["destination_root"]).resolve() != destination_root:
        raise RuntimeError("rollback backup belongs to a different destination root")
    _restore_transaction(destination_root, backup_root, list(metadata["installed_names"]))
    return backup_root


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install manifest-listed Manga Studio skills and versioned runtime.")
    parser.add_argument("--scope", choices=["user"], required=True)
    parser.add_argument("--mode", choices=["symlink", "copy"], required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--destination-root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    install_root = Path(__file__).resolve().parents[1]
    destination_root = (args.destination_root or Path.home() / ".agents" / "skills").expanduser().resolve()
    plan, errors = plan_install(install_root, destination_root, args.mode)
    print(f"Manga Studio installation plan ({'dry-run' if args.dry_run else 'apply'}):")
    print(f"- RUNTIME: {destination_root / RUNTIME_DIRECTORY} <- {install_root} [versioned copy]")
    for item in plan:
        print(f"- {item['action'].upper()}: {item['destination']} <- {item['source']} [{item['mode']}]")
    if errors:
        print("Installation plan rejected:")
        for error in errors:
            print(f"- {error}")
        return 1
    if args.dry_run:
        print("Dry run complete; no files were changed.")
        return 0
    try:
        backup_root = execute_install(plan, destination_root, args.mode)
    except Exception as exc:
        print(f"Installation failed and was rolled back: {exc}", file=sys.stderr)
        return 1
    print(f"Installed {len(plan)} Manga Studio skills under {destination_root}")
    print(f"Runtime launcher: {destination_root / RUNTIME_DIRECTORY / 'manga-studio.py'}")
    print(f"Rollback backup: {backup_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
