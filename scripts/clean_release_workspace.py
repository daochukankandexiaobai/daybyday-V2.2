from __future__ import annotations

"""Remove only regenerable source-workspace files before a release build."""

import argparse
import os
import shutil
from pathlib import Path
from typing import Iterable, List


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRECTORY_NAMES = {
    ".agents",
    ".git",
    ".venv",
    "backups",
    "build",
    "data",
    "dist",
    "exports",
    "logs",
    "tmp",
    "tmp_exports",
}


def _within_workspace(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(WORKSPACE_ROOT)
    except ValueError:
        raise ValueError("refusing to clean outside workspace: {}".format(resolved))
    return resolved


def find_cache_directories() -> List[Path]:
    """Find Python and static-analysis caches without traversing release data."""
    targets = []
    for relative_path in (".ruff_cache", "__pycache__"):
        candidate = WORKSPACE_ROOT / relative_path
        if candidate.is_dir():
            targets.append(_within_workspace(candidate))

    for current, directory_names, _file_names in os.walk(str(WORKSPACE_ROOT), topdown=True):
        directory_names[:] = [
            name for name in directory_names if name not in EXCLUDED_DIRECTORY_NAMES
        ]
        current_path = Path(current)
        for name in list(directory_names):
            if name != "__pycache__":
                continue
            candidate = current_path / name
            targets.append(_within_workspace(candidate))
            directory_names.remove(name)
    return sorted(set(targets), key=lambda path: str(path).lower())


def find_source_log_files() -> List[Path]:
    log_dir = WORKSPACE_ROOT / "logs"
    if not log_dir.is_dir():
        return []
    return sorted(
        _within_workspace(path)
        for path in log_dir.iterdir()
        if path.is_file()
    )


def _print_targets(title: str, paths: Iterable[Path]) -> None:
    print(title)
    for path in paths:
        print(" - {}".format(path.relative_to(WORKSPACE_ROOT)))


def clean_workspace(apply_changes: bool = False) -> int:
    cache_directories = find_cache_directories()
    log_files = find_source_log_files()
    _print_targets("Cache directories:", cache_directories)
    _print_targets("Source log files:", log_files)

    if not apply_changes:
        print("Preview only. Run with --apply to remove the listed files.")
        return 0

    for directory in cache_directories:
        shutil.rmtree(str(directory))
    for log_file in log_files:
        log_file.unlink()
    print(
        "Removed {} cache directories and {} source log files.".format(
            len(cache_directories),
            len(log_files),
        )
    )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Clean regenerable source-workspace files before a release build."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="remove the previewed cache directories and source log files",
    )
    args = parser.parse_args(argv)
    return clean_workspace(apply_changes=bool(args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
