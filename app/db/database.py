import sqlite3
from pathlib import Path
from typing import Optional

from app.utils.paths import app_data_dir


class DatabaseManager:
    def __init__(self, db_path: Optional[str] = None) -> None:
        data_dir = app_data_dir("data")
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path) if db_path else data_dir / "team_report.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def initialize(self) -> None:
        from app.db.migrations import run_migrations

        run_migrations(self)
