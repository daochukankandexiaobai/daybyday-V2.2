from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.utils.qt_compat import QT_BINDING, QApplication
from app.utils.runtime_check import collect_runtime_report


def main() -> int:
    print("[check] base_dir:", BASE_DIR)
    report = collect_runtime_report(BASE_DIR)
    print("[check] python:", report["python_version"])
    print("[check] system:", report["system"], report["release"])
    print("[check] qt_binding:", QT_BINDING)

    warnings = report.get("warnings", [])
    errors = report.get("errors", [])
    for msg in warnings:
        print("[warn]", msg)
    for msg in errors:
        print("[error]", msg)

    # 离屏初始化 QApplication
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    print("[check] qapp_created:", app is not None)

    if errors:
        return 1
    print("[check] runtime_report: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
