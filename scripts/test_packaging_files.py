from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def _read(path):
    return Path(path).read_text(encoding="utf-8")


def _assert_contains(path, expected):
    content = _read(path)
    _assert(expected in content, "{} should contain {!r}".format(path, expected))


def _set_attr(obj, name, value):
    old_exists = hasattr(obj, name)
    old_value = getattr(obj, name, None)
    setattr(obj, name, value)
    return old_exists, old_value


def _restore_attr(obj, name, old_state):
    old_exists, old_value = old_state
    if old_exists:
        setattr(obj, name, old_value)
    elif hasattr(obj, name):
        delattr(obj, name)


def _test_paths_module():
    from app.utils import paths

    project_root = paths.project_root()
    _assert(project_root == BASE_DIR, "project_root should resolve repository root")
    _assert(paths.resource_path("assets").parent == BASE_DIR, "source resource path should use project root")
    _assert(paths.app_data_dir("data") == BASE_DIR / "data", "source data dir should stay project-local")

    tmp_dir = Path(tempfile.mkdtemp(prefix="daybyday_packaging_paths_"))
    old_frozen = _set_attr(sys, "frozen", True)
    old_meipass = _set_attr(sys, "_MEIPASS", str(tmp_dir / "bundle"))
    old_localappdata = os.environ.get("LOCALAPPDATA")
    os.environ["LOCALAPPDATA"] = str(tmp_dir / "local")
    try:
        _assert(paths.is_frozen(), "is_frozen should detect PyInstaller runtime")
        _assert(paths.resource_path("assets") == tmp_dir / "bundle" / "assets", "frozen resources should use _MEIPASS")
        _assert(paths.app_data_root() == tmp_dir / "local" / "DayByDay", "frozen app data should use LOCALAPPDATA")
        expected_dirs = paths.ensure_app_data_dirs()
        for key in ("data", "logs", "exports", "backups", "config"):
            _assert(key in expected_dirs, "missing app data dir key: {}".format(key))
            _assert(expected_dirs[key].exists(), "app data dir should be created: {}".format(expected_dirs[key]))
    finally:
        _restore_attr(sys, "frozen", old_frozen)
        _restore_attr(sys, "_MEIPASS", old_meipass)
        if old_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = old_localappdata


def _test_packaging_files():
    required_files = [
        "scripts/check_packaging_env.py",
        "scripts/build_exe.ps1",
        "scripts/build_installer.ps1",
        "scripts/build_release.ps1",
        "installer/DayByDay.iss",
        "docs/package_and_install.md",
    ]
    for relative in required_files:
        _assert((BASE_DIR / relative).exists(), "missing packaging file: {}".format(relative))

    _assert_contains(BASE_DIR / "scripts/build_exe.ps1", "python -m PyInstaller")
    _assert_contains(BASE_DIR / "scripts/build_exe.ps1", "--onedir")
    _assert_contains(BASE_DIR / "scripts/build_exe.ps1", "--windowed")
    _assert_contains(BASE_DIR / "scripts/build_exe.ps1", "--noupx")
    _assert_contains(BASE_DIR / "scripts/build_exe.ps1", "--collect-all")
    _assert_contains(BASE_DIR / "scripts/build_exe.ps1", "--exclude-module")
    _assert_contains(BASE_DIR / "scripts/build_installer.ps1", "ISCC.exe")
    _assert_contains(BASE_DIR / "scripts/build_release.ps1", "check_packaging_env.py")
    _assert_contains(BASE_DIR / "installer/DayByDay.iss", "MinVersion=6.1sp1")
    _assert_contains(BASE_DIR / "installer/DayByDay.iss", "installer_output")
    _assert_contains(BASE_DIR / "docs/package_and_install.md", "powershell -ExecutionPolicy Bypass -File scripts/build_release.ps1")


def main():
    _test_paths_module()
    _test_packaging_files()
    print("[packaging_files] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
