from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict

from app import APP_NAME


APP_DATA_DIRS = ("data", "logs", "exports", "backups", "config")


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            return Path(str(meipass))
        return Path(sys.executable).resolve().parent
    return project_root()


def resource_path(*parts: str) -> Path:
    return bundle_root().joinpath(*parts)


def app_data_root() -> Path:
    if not is_frozen():
        return project_root()
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / _safe_app_dir_name()
    return Path.home() / _safe_app_dir_name()


def app_data_dir(name: str) -> Path:
    normalized = str(name or "").strip().strip("\\/")
    if not normalized:
        raise ValueError("app data dir name cannot be empty")
    return app_data_root() / normalized


def ensure_app_data_dirs() -> Dict[str, Path]:
    result = {}
    for name in APP_DATA_DIRS:
        path = app_data_dir(name)
        path.mkdir(parents=True, exist_ok=True)
        result[name] = path
    return result


def _safe_app_dir_name() -> str:
    value = str(APP_NAME or "DayByDay").strip() or "DayByDay"
    return "".join(ch for ch in value if ch not in '\\/:*?"<>|') or "DayByDay"
