import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional


class DatabaseManager:
    def __init__(self, db_path: Optional[str] = None) -> None:
        base_dir = Path(__file__).resolve().parents[2]
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path) if db_path else data_dir / "team_report.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Provide an explicit atomic write boundary for coordinated services."""
        conn = self.get_connection()
        try:
            conn.execute("BEGIN")
            yield conn
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        from app.db.migrations import run_migrations

        run_migrations(self)
