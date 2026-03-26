#!/usr/bin/env python3
"""Update an installed skill from a GitHub repo path."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass


def _load_installer_module():
    script_dir = os.path.dirname(__file__)
    module_path = os.path.join(script_dir, "install-skill-from-github.py")
    module_name = "skill_installer"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load installer module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


installer = _load_installer_module()
Args = installer.Args
InstallError = installer.InstallError


@dataclass
class UpdateTarget:
    skill_name: str
    skill_src: str
    dest_dir: str
    backup_dir: str


def _parse_args(argv: list[str]) -> Args:
    return installer._parse_args(argv)


def _backup_existing(dest_dir: str) -> str:
    backup_dir = tempfile.mkdtemp(
        prefix=f"{os.path.basename(dest_dir)}-backup-",
        dir=installer._tmp_root(),
    )
    shutil.copytree(dest_dir, os.path.join(backup_dir, "skill"))
    return backup_dir


def _restore_targets(targets: list[UpdateTarget]) -> None:
    for target in targets:
        backup_skill_dir = os.path.join(target.backup_dir, "skill")
        if os.path.isdir(target.dest_dir):
            shutil.rmtree(target.dest_dir, ignore_errors=True)
        if os.path.isdir(backup_skill_dir):
            shutil.copytree(backup_skill_dir, target.dest_dir)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    try:
        source = installer._resolve_source(args)
        source.ref = source.ref or args.ref
        if not source.paths:
            raise InstallError("No skill paths provided.")
        for path in source.paths:
            installer._validate_relative_path(path)

        dest_root = args.dest or installer._default_dest()
        tmp_dir = tempfile.mkdtemp(prefix="skill-update-", dir=installer._tmp_root())
        targets: list[UpdateTarget] = []

        try:
            repo_root = installer._prepare_repo(source, args.method, tmp_dir)
            for path in source.paths:
                skill_name = args.name if len(source.paths) == 1 else None
                skill_name = skill_name or os.path.basename(path.rstrip("/"))
                installer._validate_skill_name(skill_name)
                if not skill_name:
                    raise InstallError("Unable to derive skill name.")

                dest_dir = os.path.join(dest_root, skill_name)
                if not os.path.isdir(dest_dir):
                    raise InstallError(f"Installed skill not found: {dest_dir}")

                skill_src = os.path.join(repo_root, path)
                installer._validate_skill(skill_src)

                targets.append(
                    UpdateTarget(
                        skill_name=skill_name,
                        skill_src=skill_src,
                        dest_dir=dest_dir,
                        backup_dir=_backup_existing(dest_dir),
                    )
                )

            updated_targets: list[UpdateTarget] = []
            try:
                for target in targets:
                    shutil.rmtree(target.dest_dir)
                    installer._copy_skill(target.skill_src, target.dest_dir)
                    updated_targets.append(target)
            except Exception:
                _restore_targets(updated_targets)
                raise
        finally:
            if os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
            for target in targets:
                shutil.rmtree(target.backup_dir, ignore_errors=True)

        for target in targets:
            print(f"Updated {target.skill_name} in {target.dest_dir}")
        return 0
    except InstallError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
