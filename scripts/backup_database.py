from __future__ import annotations

"""Create a timestamped SQLite backup without stopping the application."""

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = BASE_DIR / "data" / "team_report.db"
DEFAULT_BACKUP_DIR = BASE_DIR / "backups"


def _next_backup_path(backup_dir: Path, database: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = "{}_{}".format(database.stem, timestamp)
    candidate = backup_dir / "{}.db".format(stem)
    index = 1
    while candidate.exists():
        candidate = backup_dir / "{}_{:02d}.db".format(stem, index)
        index += 1
    return candidate


def backup_database(database: Path, backup_dir: Path) -> Path:
    source_path = database.expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError("数据库不存在: {}".format(source_path))

    target_dir = backup_dir.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = _next_backup_path(target_dir, source_path)

    source = sqlite3.connect(str(source_path))
    destination = sqlite3.connect(str(target_path))
    try:
        source.backup(destination)
        result = destination.execute("PRAGMA quick_check").fetchone()
        if result is None or str(result[0]).lower() != "ok":
            raise RuntimeError("备份校验失败: {}".format(result[0] if result else "未知错误"))
    except Exception:
        destination.close()
        target_path.unlink(missing_ok=True)
        raise
    else:
        destination.close()
    finally:
        source.close()
    return target_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="备份团队经理日报系统 SQLite 数据库")
    parser.add_argument("--database", default=str(DEFAULT_DATABASE), help="源数据库路径")
    parser.add_argument("--output-dir", default=str(DEFAULT_BACKUP_DIR), help="备份输出目录")
    args = parser.parse_args(argv)

    try:
        backup_path = backup_database(Path(args.database), Path(args.output_dir))
    except Exception as exc:
        print("[backup] FAILED: {}".format(exc), file=sys.stderr)
        return 1

    print("[backup] PASS")
    print("[backup] path:", backup_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
