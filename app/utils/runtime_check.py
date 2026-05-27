from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Dict, List


def _is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        test_file = path / ".write_test.tmp"
        with test_file.open("w", encoding="utf-8") as f:
            f.write("ok")
        test_file.unlink()
        return True
    except Exception:  # noqa: BLE001
        return False


def collect_runtime_report(base_dir: Path) -> Dict[str, object]:
    python_ver = "{}.{}.{}".format(*sys.version_info[:3])
    system_name = platform.system()
    release = platform.release()

    warnings: List[str] = []
    errors: List[str] = []

    # Win7 兼容分支建议固定 Python 3.8
    if not (sys.version_info.major == 3 and sys.version_info.minor == 8):
        warnings.append("建议使用 Python 3.8.x 运行 Win7 兼容分支。")

    if system_name == "Windows":
        if release not in {"7", "10", "11"}:
            warnings.append("未识别的 Windows 版本，建议先做完整冒烟测试。")
    else:
        warnings.append("当前不是 Windows 系统，仅用于开发调试。")

    data_dir = base_dir / "data"
    exports_dir = base_dir / "exports"
    logs_dir = base_dir / "logs"

    for p in (data_dir, exports_dir, logs_dir):
        if not _is_writable(p):
            errors.append("目录不可写: {}".format(p))

    return {
        "python_version": python_ver,
        "system": system_name,
        "release": release,
        "warnings": warnings,
        "errors": errors,
        "cwd": os.getcwd(),
    }
