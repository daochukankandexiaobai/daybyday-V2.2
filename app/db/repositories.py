from __future__ import annotations

import sqlite3
from typing import Any

from app.db.database import DatabaseManager


class BaseRepository:
    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        self._columns_cache: dict[str, set[str]] = {}

    @staticmethod
    def _row_to_dict(row) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def _table_columns(self, table_name: str) -> set[str]:
        cached = self._columns_cache.get(table_name)
        if cached is not None:
            return cached

        with self.db.get_connection() as conn:
            rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        cols = {str(row["name"]) for row in rows}
        self._columns_cache[table_name] = cols
        return cols


class TeamRepository(BaseRepository):
    @staticmethod
    def _identity_matches(
        row: dict[str, Any] | None,
        region: str,
        team_name: str,
        team_manager_name: str,
    ) -> bool:
        if row is None:
            return False
        return (
            str(row.get("region", "")).strip() == region
            and str(row.get("team_name", "")).strip() == team_name
            and str(row.get("team_manager_name", "")).strip() == team_manager_name
        )

    def list_teams(self, include_inactive: bool = False, only_inactive: bool = False) -> list[dict[str, Any]]:
        where = ["1=1"]
        if only_inactive:
            where.append("is_active = 0")
        elif not include_inactive:
            where.append("is_active = 1")

        sql = f"""
            SELECT *
            FROM teams
            WHERE {' AND '.join(where)}
            ORDER BY is_active DESC, updated_at DESC, id DESC
        """
        with self.db.get_connection() as conn:
            rows = conn.execute(sql).fetchall()
            return [dict(row) for row in rows]

    def get_by_id(self, team_id: int, include_inactive: bool = True) -> dict[str, Any] | None:
        where = ["id = ?"]
        params: list[Any] = [team_id]
        if not include_inactive:
            where.append("is_active = 1")

        sql = f"SELECT * FROM teams WHERE {' AND '.join(where)}"
        with self.db.get_connection() as conn:
            row = conn.execute(sql, params).fetchone()
            return self._row_to_dict(row)

    def find_by_identity(
        self,
        region: str,
        team_name: str,
        team_manager_name: str,
        include_inactive: bool = True,
    ) -> dict[str, Any] | None:
        where = ["region = ?", "team_name = ?", "team_manager_name = ?"]
        params: list[Any] = [region, team_name, team_manager_name]
        if not include_inactive:
            where.append("is_active = 1")

        sql = f"""
            SELECT *
            FROM teams
            WHERE {' AND '.join(where)}
            LIMIT 1
        """
        with self.db.get_connection() as conn:
            row = conn.execute(sql, params).fetchone()
            return self._row_to_dict(row)

    def save_team(
        self,
        team_id: int | None,
        region: str,
        team_name: str,
        team_manager_name: str,
        now: str,
    ) -> int:
        with self.db.get_connection() as conn:
            if team_id:
                exists = conn.execute("SELECT id FROM teams WHERE id = ?", (team_id,)).fetchone()
                if exists:
                    conn.execute(
                        """
                        UPDATE teams
                        SET region = ?, team_name = ?, team_manager_name = ?, is_active = 1, updated_at = ?
                        WHERE id = ?
                        """,
                        (region, team_name, team_manager_name, now, team_id),
                    )
                    conn.commit()
                    return int(team_id)

            same = conn.execute(
                """
                SELECT id, is_active
                FROM teams
                WHERE region = ? AND team_name = ? AND team_manager_name = ?
                LIMIT 1
                """,
                (region, team_name, team_manager_name),
            ).fetchone()
            if same:
                if int(same["is_active"] or 1) == 0:
                    conn.execute(
                        "UPDATE teams SET is_active = 1, updated_at = ? WHERE id = ?",
                        (now, int(same["id"])),
                    )
                    conn.commit()
                return int(same["id"])

            cursor = conn.execute(
                """
                INSERT INTO teams (region, team_name, team_manager_name, is_active, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?)
                """,
                (region, team_name, team_manager_name, now, now),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def upsert_import_team(
        self,
        preferred_team_id: int | None,
        region: str,
        team_name: str,
        team_manager_name: str,
        now: str,
    ) -> int:
        region = str(region or "").strip()
        team_name = str(team_name or "").strip()
        team_manager_name = str(team_manager_name or "").strip()
        preferred_id = int(preferred_team_id or 0)

        identity_row = None
        if region and team_name and team_manager_name:
            identity_row = self.find_by_identity(region, team_name, team_manager_name, include_inactive=True)

        if preferred_id <= 0:
            if identity_row is not None:
                with self.db.get_connection() as conn:
                    conn.execute(
                        """
                        UPDATE teams
                        SET is_active = 1,
                            updated_at = ?,
                            region = ?,
                            team_name = ?,
                            team_manager_name = ?
                        WHERE id = ?
                        """,
                        (now, region, team_name, team_manager_name, int(identity_row["id"])),
                    )
                    conn.commit()
                return int(identity_row["id"])
            return self.save_team(None, region, team_name, team_manager_name, now)

        with self.db.get_connection() as conn:
            preferred_row_raw = conn.execute("SELECT * FROM teams WHERE id = ?", (preferred_id,)).fetchone()
            preferred_row = self._row_to_dict(preferred_row_raw)

            if preferred_row is not None:
                if self._identity_matches(preferred_row, region, team_name, team_manager_name):
                    conn.execute(
                        """
                        UPDATE teams
                        SET region = ?, team_name = ?, team_manager_name = ?, is_active = 1, updated_at = ?
                        WHERE id = ?
                        """,
                        (region, team_name, team_manager_name, now, preferred_id),
                    )
                    conn.commit()
                    return preferred_id

                if identity_row is not None and int(identity_row["id"]) != preferred_id:
                    identity_id = int(identity_row["id"])
                    conn.execute(
                        """
                        UPDATE teams
                        SET is_active = 1,
                            updated_at = ?,
                            region = ?,
                            team_name = ?,
                            team_manager_name = ?
                        WHERE id = ?
                        """,
                        (now, region, team_name, team_manager_name, identity_id),
                    )
                    conn.commit()
                    return identity_id

                if region and team_name and team_manager_name:
                    try:
                        cursor = conn.execute(
                            """
                            INSERT INTO teams (region, team_name, team_manager_name, is_active, created_at, updated_at)
                            VALUES (?, ?, ?, 1, ?, ?)
                            """,
                            (region, team_name, team_manager_name, now, now),
                        )
                        conn.commit()
                        return int(cursor.lastrowid)
                    except sqlite3.IntegrityError:
                        fallback = conn.execute(
                            """
                            SELECT id
                            FROM teams
                            WHERE region = ? AND team_name = ? AND team_manager_name = ?
                            LIMIT 1
                            """,
                            (region, team_name, team_manager_name),
                        ).fetchone()
                        if fallback is not None:
                            fallback_id = int(fallback["id"])
                            conn.execute(
                                "UPDATE teams SET is_active = 1, updated_at = ? WHERE id = ?",
                                (now, fallback_id),
                            )
                            conn.commit()
                            return fallback_id

                conn.execute(
                    "UPDATE teams SET is_active = 1, updated_at = ? WHERE id = ?",
                    (now, preferred_id),
                )
                conn.commit()
                return preferred_id

            if identity_row is not None:
                identity_id = int(identity_row["id"])
                conn.execute(
                    """
                    UPDATE teams
                    SET is_active = 1,
                        updated_at = ?,
                        region = ?,
                        team_name = ?,
                        team_manager_name = ?
                    WHERE id = ?
                    """,
                    (now, region, team_name, team_manager_name, identity_id),
                )
                conn.commit()
                return identity_id

            try:
                conn.execute(
                    """
                    INSERT INTO teams (id, region, team_name, team_manager_name, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (preferred_id, region, team_name, team_manager_name, now, now),
                )
                conn.commit()
                return preferred_id
            except sqlite3.IntegrityError:
                cursor = conn.execute(
                    """
                    INSERT INTO teams (region, team_name, team_manager_name, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, 1, ?, ?)
                    """,
                    (region, team_name, team_manager_name, now, now),
                )
                conn.commit()
                return int(cursor.lastrowid)

    def set_active(self, team_id: int, active: bool, now: str, cascade_members: bool = False) -> bool:
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE teams SET is_active = ?, updated_at = ? WHERE id = ?",
                (1 if active else 0, now, team_id),
            )
            if int(cursor.rowcount or 0) > 0 and cascade_members:
                conn.execute(
                    "UPDATE account_managers SET is_active = ?, updated_at = ? WHERE team_id = ?",
                    (1 if active else 0, now, team_id),
                )
            conn.commit()
            return int(cursor.rowcount or 0) > 0

    def hard_delete_team(self, team_id: int) -> bool:
        return False

    def count_related_data(self, team_id: int) -> dict[str, int]:
        team = self.get_by_id(team_id, include_inactive=True) or {}
        team_name = str(team.get("team_name", "")).strip()
        region = str(team.get("region", "")).strip()
        team_manager = str(team.get("team_manager_name", "")).strip()
        final_team_text = f"{region} / {team_name} / {team_manager}"

        with self.db.get_connection() as conn:
            account_managers = int(
                conn.execute(
                    "SELECT COUNT(1) AS c FROM account_managers WHERE team_id = ?",
                    (team_id,),
                ).fetchone()["c"]
            )
            cycle_targets = int(
                conn.execute(
                    "SELECT COUNT(1) AS c FROM cycle_targets WHERE team_id = ?",
                    (team_id,),
                ).fetchone()["c"]
            )
            daily_records = int(
                conn.execute(
                    "SELECT COUNT(1) AS c FROM daily_records WHERE team_id = ?",
                    (team_id,),
                ).fetchone()["c"]
            )
            import_logs = int(
                conn.execute(
                    """
                    SELECT COUNT(1) AS c
                    FROM import_logs
                    WHERE team_name = ?
                       OR final_team = ?
                    """,
                    (team_name, final_team_text),
                ).fetchone()["c"]
            )
            migration_logs = int(
                conn.execute(
                    """
                    SELECT COUNT(1) AS c
                    FROM import_logs
                    WHERE log_type = 'legacy_migration'
                      AND (team_name = ? OR final_team = ?)
                    """,
                    (team_name, final_team_text),
                ).fetchone()["c"]
            )

        return {
            "account_managers": account_managers,
            "cycle_targets": cycle_targets,
            "daily_records": daily_records,
            "import_logs": import_logs,
            "migration_logs": migration_logs,
        }


class AccountManagerRepository(BaseRepository):
    def list_by_team(self, team_id: int, include_inactive: bool = False) -> list[dict[str, Any]]:
        where = ["team_id = ?"]
        params: list[Any] = [team_id]
        if not include_inactive:
            where.append("is_active = 1")

        sql = f"""
            SELECT *
            FROM account_managers
            WHERE {' AND '.join(where)}
            ORDER BY account_manager_name ASC, id ASC
        """
        with self.db.get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def get_by_id(self, manager_id: int) -> dict[str, Any] | None:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM account_managers WHERE id = ?", (manager_id,)).fetchone()
            return self._row_to_dict(row)

    def get_by_name(self, team_id: int, name: str) -> dict[str, Any] | None:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM account_managers
                WHERE team_id = ? AND account_manager_name = ?
                LIMIT 1
                """,
                (team_id, name),
            ).fetchone()
            return self._row_to_dict(row)

    def ensure_member(self, team_id: int, name: str, now: str) -> int:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, is_active
                FROM account_managers
                WHERE team_id = ? AND account_manager_name = ?
                LIMIT 1
                """,
                (team_id, name),
            ).fetchone()
            if row:
                if int(row["is_active"]) != 1:
                    conn.execute(
                        "UPDATE account_managers SET is_active = 1, updated_at = ? WHERE id = ?",
                        (now, row["id"]),
                    )
                    conn.commit()
                return int(row["id"])

            cursor = conn.execute(
                """
                INSERT INTO account_managers
                (team_id, account_manager_name, is_active, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                (team_id, name, now, now),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def upsert_import_member(
        self,
        team_id: int,
        preferred_manager_id: int | None,
        account_manager_name: str,
        now: str,
    ) -> int:
        team_id = int(team_id or 0)
        preferred_id = int(preferred_manager_id or 0)
        name = str(account_manager_name or "").strip()
        if not name and preferred_id > 0:
            name = f"经理{preferred_id}"
        if not name:
            return 0

        name_row = self.get_by_name(team_id, name)
        with self.db.get_connection() as conn:
            if preferred_id > 0:
                preferred_row_raw = conn.execute(
                    "SELECT * FROM account_managers WHERE id = ?",
                    (preferred_id,),
                ).fetchone()
                preferred_row = self._row_to_dict(preferred_row_raw)

                if preferred_row is not None and int(preferred_row.get("team_id", 0) or 0) == team_id:
                    conn.execute(
                        """
                        UPDATE account_managers
                        SET account_manager_name = ?, is_active = 1, updated_at = ?
                        WHERE id = ?
                        """,
                        (name, now, preferred_id),
                    )
                    conn.commit()
                    return preferred_id

                if name_row is not None:
                    name_id = int(name_row["id"])
                    conn.execute(
                        "UPDATE account_managers SET is_active = 1, updated_at = ? WHERE id = ?",
                        (now, name_id),
                    )
                    conn.commit()
                    return name_id

                if preferred_row is None:
                    try:
                        conn.execute(
                            """
                            INSERT INTO account_managers
                            (id, team_id, account_manager_name, is_active, created_at, updated_at)
                            VALUES (?, ?, ?, 1, ?, ?)
                            """,
                            (preferred_id, team_id, name, now, now),
                        )
                        conn.commit()
                        return preferred_id
                    except sqlite3.IntegrityError:
                        pass

            if name_row is not None:
                name_id = int(name_row["id"])
                conn.execute(
                    "UPDATE account_managers SET is_active = 1, updated_at = ? WHERE id = ?",
                    (now, name_id),
                )
                conn.commit()
                return name_id

            cursor = conn.execute(
                """
                INSERT INTO account_managers
                (team_id, account_manager_name, is_active, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                (team_id, name, now, now),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def deactivate_missing(self, team_id: int, keep_ids: list[int], now: str) -> None:
        with self.db.get_connection() as conn:
            if keep_ids:
                placeholders = ",".join(["?" for _ in keep_ids])
                sql = (
                    f"UPDATE account_managers SET is_active = 0, updated_at = ? "
                    f"WHERE team_id = ? AND id NOT IN ({placeholders})"
                )
                conn.execute(sql, [now, team_id, *keep_ids])
            else:
                conn.execute(
                    "UPDATE account_managers SET is_active = 0, updated_at = ? WHERE team_id = ?",
                    (now, team_id),
                )
            conn.commit()


class CycleTargetRepository(BaseRepository):
    def upsert_target(
        self,
        team_id: int,
        account_manager_id: int,
        settlement_cycle_code: str,
        target_amount: float,
        now: str,
    ) -> None:
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cycle_targets
                (team_id, account_manager_id, settlement_cycle_code, target_amount, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(team_id, account_manager_id, settlement_cycle_code)
                DO UPDATE SET target_amount = excluded.target_amount, updated_at = excluded.updated_at
                """,
                (team_id, account_manager_id, settlement_cycle_code, target_amount, now, now),
            )
            conn.commit()

    def list_targets(self, team_id: int, settlement_cycle_code: str) -> list[dict[str, Any]]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    ct.id,
                    ct.team_id,
                    ct.account_manager_id,
                    am.account_manager_name,
                    ct.settlement_cycle_code,
                    ct.target_amount,
                    ct.created_at,
                    ct.updated_at
                FROM cycle_targets ct
                JOIN account_managers am ON am.id = ct.account_manager_id
                WHERE ct.team_id = ? AND ct.settlement_cycle_code = ?
                ORDER BY am.account_manager_name ASC
                """,
                (team_id, settlement_cycle_code),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_target(self, team_id: int, account_manager_id: int, settlement_cycle_code: str) -> float:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT target_amount
                FROM cycle_targets
                WHERE team_id = ? AND account_manager_id = ? AND settlement_cycle_code = ?
                LIMIT 1
                """,
                (team_id, account_manager_id, settlement_cycle_code),
            ).fetchone()
            if row is None:
                return 0.0
            return float(row["target_amount"] or 0.0)

    def team_target_sum(self, team_id: int, settlement_cycle_code: str) -> float:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(target_amount), 0) AS target_sum
                FROM cycle_targets
                WHERE team_id = ? AND settlement_cycle_code = ?
                """,
                (team_id, settlement_cycle_code),
            ).fetchone()
            return float(row["target_sum"] or 0.0)


class DailyRecordRepository(BaseRepository):
    @staticmethod
    def _build_business_key(record: dict[str, Any]) -> str:
        record_date = str(record.get("record_date", "")).strip()
        region = str(record.get("region", "")).strip()
        team_name = str(record.get("team_name_snapshot") or record.get("team_name") or "").strip()
        account_manager = str(
            record.get("account_manager_name_snapshot")
            or record.get("account_manager_name")
            or record.get("manager_name")
            or ""
        ).strip()
        return "|".join([record_date, region, team_name, account_manager])

    @staticmethod
    def _apply_legacy_aliases(data: dict[str, Any], columns: set[str]) -> None:
        """兼容旧版 daily_records 字段约束（date/team/manager_name/business_key）。"""

        if "date" in columns and not str(data.get("date", "")).strip():
            data["date"] = str(data.get("record_date", "")).strip()

        if "team" in columns and not str(data.get("team", "")).strip():
            data["team"] = str(data.get("team_name_snapshot") or data.get("team_name") or "").strip()

        if "manager_name" in columns and not str(data.get("manager_name", "")).strip():
            data["manager_name"] = str(
                data.get("account_manager_name_snapshot")
                or data.get("account_manager_name")
                or data.get("team_manager_name_snapshot")
                or ""
            ).strip()

    def get_by_record_id(self, record_id: str) -> dict[str, Any] | None:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM daily_records WHERE record_id = ?", (record_id,)).fetchone()
            return self._row_to_dict(row)

    def get_by_id(self, row_id: int) -> dict[str, Any] | None:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM daily_records WHERE id = ?", (row_id,)).fetchone()
            return self._row_to_dict(row)

    def get_by_unique(self, record_date: str, team_id: int, account_manager_id: int) -> dict[str, Any] | None:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM daily_records
                WHERE record_date = ? AND team_id = ? AND account_manager_id = ?
                LIMIT 1
                """,
                (record_date, team_id, account_manager_id),
            ).fetchone()
            return self._row_to_dict(row)

    def insert(self, record: dict[str, Any]) -> int:
        columns = self._table_columns("daily_records")
        filtered = {k: v for k, v in record.items() if k in columns}
        self._apply_legacy_aliases(filtered, columns)
        if "business_key" in columns and not str(filtered.get("business_key", "")).strip():
            filtered["business_key"] = self._build_business_key(record)

        fields = list(filtered.keys())
        values = [filtered[key] for key in fields]
        placeholders = ", ".join(["?" for _ in fields])
        sql = f"INSERT INTO daily_records ({', '.join(fields)}) VALUES ({placeholders})"
        with self.db.get_connection() as conn:
            cursor = conn.execute(sql, values)
            conn.commit()
            return int(cursor.lastrowid)

    def update_by_id(self, row_id: int, updates: dict[str, Any]) -> None:
        columns = self._table_columns("daily_records")
        filtered = {k: v for k, v in updates.items() if k in columns}
        if not filtered:
            return
        self._apply_legacy_aliases(filtered, columns)

        keys = list(filtered.keys())
        set_sql = ", ".join([f"{k} = ?" for k in keys])
        values = [filtered[k] for k in keys] + [row_id]
        with self.db.get_connection() as conn:
            conn.execute(f"UPDATE daily_records SET {set_sql} WHERE id = ?", values)
            conn.commit()

    def delete_by_id(self, row_id: int) -> bool:
        with self.db.get_connection() as conn:
            cursor = conn.execute("DELETE FROM daily_records WHERE id = ?", (row_id,))
            conn.commit()
            return int(cursor.rowcount or 0) > 0

    def delete_by_ids(self, row_ids: list[int]) -> int:
        normalized = sorted({int(x) for x in row_ids if int(x) > 0})
        if not normalized:
            return 0
        placeholders = ",".join(["?" for _ in normalized])
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                f"DELETE FROM daily_records WHERE id IN ({placeholders})",
                normalized,
            )
            conn.commit()
            return int(cursor.rowcount or 0)

    def list_team_day_records(self, team_id: int, record_date: str) -> list[dict[str, Any]]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM daily_records
                WHERE team_id = ? AND record_date = ?
                ORDER BY account_manager_name_snapshot ASC, id ASC
                """,
                (team_id, record_date),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_records(
        self,
        start_date: str,
        end_date: str,
        team_id: int | None = None,
        team_ids: list[int] | None = None,
        account_manager_id: int | None = None,
        region: str = "",
        team_name: str = "",
        team_manager_name: str = "",
        source_type: str = "",
    ) -> list[dict[str, Any]]:
        where = ["record_date BETWEEN ? AND ?"]
        params: list[Any] = [start_date, end_date]

        normalized_team_ids: list[int] | None = None
        if team_ids is not None:
            normalized_team_ids = sorted({int(x) for x in team_ids if int(x) > 0})
            if not normalized_team_ids:
                return []

        if normalized_team_ids:
            placeholders = ",".join(["?" for _ in normalized_team_ids])
            where.append(f"team_id IN ({placeholders})")
            params.extend(normalized_team_ids)
        elif team_id is not None and team_id > 0:
            where.append("team_id = ?")
            params.append(team_id)
        if account_manager_id is not None and account_manager_id > 0:
            where.append("account_manager_id = ?")
            params.append(account_manager_id)
        if region.strip():
            where.append("region = ?")
            params.append(region.strip())
        if team_name.strip():
            where.append("team_name_snapshot = ?")
            params.append(team_name.strip())
        if team_manager_name.strip():
            where.append("team_manager_name_snapshot = ?")
            params.append(team_manager_name.strip())
        if source_type.strip():
            where.append("source_type = ?")
            params.append(source_type.strip())

        sql = f"""
            SELECT *
            FROM daily_records
            WHERE {' AND '.join(where)}
            ORDER BY record_date ASC, team_name_snapshot ASC, account_manager_name_snapshot ASC
        """
        with self.db.get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def list_all_records(self, start_date: str, end_date: str, source_type: str = "") -> list[dict[str, Any]]:
        return self.list_records(start_date=start_date, end_date=end_date, source_type=source_type)

    def list_for_export(self, team_id: int, start_date: str, end_date: str) -> list[dict[str, Any]]:
        return self.list_records(start_date=start_date, end_date=end_date, team_id=team_id)

    def get_cycle_codes_in_range(self, start_date: str, end_date: str, team_id: int | None = None) -> list[str]:
        where = ["record_date BETWEEN ? AND ?"]
        params: list[Any] = [start_date, end_date]
        if team_id is not None and team_id > 0:
            where.append("team_id = ?")
            params.append(team_id)

        sql = f"""
            SELECT DISTINCT settlement_cycle_code
            FROM daily_records
            WHERE {' AND '.join(where)}
            ORDER BY settlement_cycle_code ASC
        """
        with self.db.get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [str(row["settlement_cycle_code"] or "") for row in rows if str(row["settlement_cycle_code"] or "")]

    def summarize(
        self,
        start_date: str,
        end_date: str,
        team_id: int | None = None,
        account_manager_id: int | None = None,
    ) -> dict[str, Any]:
        where = ["record_date BETWEEN ? AND ?"]
        params: list[Any] = [start_date, end_date]

        if team_id is not None and team_id > 0:
            where.append("team_id = ?")
            params.append(team_id)
        if account_manager_id is not None and account_manager_id > 0:
            where.append("account_manager_id = ?")
            params.append(account_manager_id)

        sql = f"""
            SELECT
                COUNT(*) AS record_count,
                COALESCE(SUM(repayment_amount_daily), 0) AS repayment_amount_daily,
                COALESCE(SUM(loan_amount_daily), 0) AS loan_amount_daily,
                COALESCE(SUM(intention_daily), 0) AS intention_daily,
                COALESCE(SUM(wechat_count_daily), 0) AS wechat_count_daily,
                COALESCE(SUM(visit_count_daily), 0) AS visit_count_daily,
                COALESCE(SUM(invalid_visit_count_daily), 0) AS invalid_visit_count_daily,
                COALESCE(SUM(signing_count_daily), 0) AS signing_count_daily,
                COALESCE(SUM(quality_visit_count_daily), 0) AS quality_visit_count_daily,
                COALESCE(SUM(approval_customer_count_daily), 0) AS approval_customer_count_daily,
                COALESCE(SUM(repayment_customer_count_daily), 0) AS repayment_customer_count_daily,
                COALESCE(SUM(debt_case_submit_count_daily), 0) AS debt_case_submit_count_daily,
                COALESCE(SUM(debt_case_repayment_count_daily), 0) AS debt_case_repayment_count_daily,
                COALESCE(SUM(debt_case_repayment_amount_daily), 0) AS debt_case_repayment_amount_daily,
                COALESCE(SUM(large_order_repayment_count_daily), 0) AS large_order_repayment_count_daily,
                COALESCE(SUM(large_order_repayment_amount_daily), 0) AS large_order_repayment_amount_daily,
                COALESCE(SUM(four_star_customer_count_daily), 0) AS four_star_customer_count_daily,
                COALESCE(SUM(five_star_customer_count_daily), 0) AS five_star_customer_count_daily
            FROM daily_records
            WHERE {' AND '.join(where)}
        """
        with self.db.get_connection() as conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row)

    def list_distinct_account_manager_names(self, start_date: str, end_date: str) -> list[str]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT account_manager_name_snapshot
                FROM daily_records
                WHERE record_date BETWEEN ? AND ?
                ORDER BY account_manager_name_snapshot ASC
                """,
                (start_date, end_date),
            ).fetchall()
            return [str(row["account_manager_name_snapshot"] or "") for row in rows if str(row["account_manager_name_snapshot"] or "")]


class SettingsRepository(BaseRepository):
    def get(self, key: str, default: str = "") -> str:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
            if row is None:
                return default
            return row["value"] or ""

    def set(self, key: str, value: str) -> None:
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            conn.commit()

    def all_settings(self) -> dict[str, str]:
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
            return {row["key"]: row["value"] for row in rows}


class AdminUserRepository(BaseRepository):
    def get_by_username(self, username: str) -> dict[str, Any] | None:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM admin_users WHERE username = ?", (username,)).fetchone()
            return self._row_to_dict(row)

    def update_password(self, username: str, password_hash: str, salt: str, updated_at: str) -> None:
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE admin_users SET password_hash = ?, salt = ?, updated_at = ? WHERE username = ?",
                (password_hash, salt, updated_at, username),
            )
            conn.commit()


class ImportLogRepository(BaseRepository):
    def insert(self, log_data: dict[str, Any]) -> None:
        fields = list(log_data.keys())
        values = [log_data[k] for k in fields]
        placeholders = ", ".join(["?" for _ in fields])
        sql = f"INSERT INTO import_logs ({', '.join(fields)}) VALUES ({placeholders})"
        with self.db.get_connection() as conn:
            conn.execute(sql, values)
            conn.commit()

    def list_logs(self, start_time: str = "", end_time: str = "", result: str = "") -> list[dict[str, Any]]:
        where = ["1=1"]
        params: list[Any] = []

        if start_time:
            where.append("import_time >= ?")
            params.append(start_time)
        if end_time:
            where.append("import_time <= ?")
            params.append(end_time)
        if result and result not in {"All", "全部"}:
            where.append("result = ?")
            params.append(result)

        sql = f"""
            SELECT *
            FROM import_logs
            WHERE {' AND '.join(where)}
            ORDER BY import_time DESC, id DESC
        """
        with self.db.get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]


class AdminActionLogRepository(BaseRepository):
    def insert(self, payload: dict[str, Any]) -> int:
        fields = list(payload.keys())
        placeholders = ", ".join(["?" for _ in fields])
        sql = f"INSERT INTO admin_action_logs ({', '.join(fields)}) VALUES ({placeholders})"
        with self.db.get_connection() as conn:
            cursor = conn.execute(sql, [payload[k] for k in fields])
            conn.commit()
            return int(cursor.lastrowid)

    def list_logs(
        self,
        start_time: str = "",
        end_time: str = "",
        action_type: str = "",
        target_type: str = "",
        operator: str = "",
    ) -> list[dict[str, Any]]:
        where = ["1=1"]
        params: list[Any] = []

        if start_time:
            where.append("action_time >= ?")
            params.append(start_time)
        if end_time:
            where.append("action_time <= ?")
            params.append(end_time)
        if action_type and action_type not in {"All", "全部"}:
            where.append("action_type = ?")
            params.append(action_type)
        if target_type and target_type not in {"All", "全部"}:
            where.append("target_type = ?")
            params.append(target_type)
        if operator.strip():
            where.append("operator = ?")
            params.append(operator.strip())

        sql = f"""
            SELECT *
            FROM admin_action_logs
            WHERE {' AND '.join(where)}
            ORDER BY action_time DESC, id DESC
        """
        with self.db.get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]


class TemplateRepository(BaseRepository):
    def list_templates(self) -> list[dict[str, Any]]:
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT * FROM templates ORDER BY created_at DESC, id DESC").fetchall()
            return [dict(row) for row in rows]

    def get_active_template(self) -> dict[str, Any] | None:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM templates WHERE is_active = 1 LIMIT 1").fetchone()
            return self._row_to_dict(row)

    def get_by_version(self, template_version: str) -> dict[str, Any] | None:
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM templates WHERE template_version = ?",
                (template_version,),
            ).fetchone()
            return self._row_to_dict(row)

    def get_fields(self, template_id: int) -> list[dict[str, Any]]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM template_fields
                WHERE template_id = ?
                ORDER BY display_order ASC, id ASC
                """,
                (template_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_template(self, template_name: str, template_version: str, is_active: int, created_at: str) -> int:
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO templates (template_name, template_version, is_active, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (template_name, template_version, is_active, created_at),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def set_active(self, template_id: int) -> None:
        with self.db.get_connection() as conn:
            conn.execute("UPDATE templates SET is_active = 0")
            conn.execute("UPDATE templates SET is_active = 1 WHERE id = ?", (template_id,))
            conn.commit()

    def replace_fields(self, template_id: int, fields: list[dict[str, Any]]) -> None:
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM template_fields WHERE template_id = ?", (template_id,))
            for field in fields:
                conn.execute(
                    """
                    INSERT INTO template_fields
                    (template_id, field_key, field_label, field_type, is_required, display_order)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        template_id,
                        field["field_key"],
                        field["field_label"],
                        field["field_type"],
                        int(field.get("is_required", 0)),
                        int(field.get("display_order", 0)),
                    ),
                )
            conn.commit()
