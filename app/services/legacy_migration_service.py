from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from app.utils.date_utils import now_iso, parse_date, settlement_cycle_display_code
from app.utils.json_utils import load_json_file
from app.utils.log_utils import get_logger
from app.utils.validators import (
    DAILY_AMOUNT_FIELDS,
    DAILY_INT_FIELDS,
    normalize_record,
    safe_decimal,
    safe_int,
    validate_export_payload,
)


class LegacyMigrationService:
    """管理员专属：旧版 JSON 识别 + 预加载 + 替换式迁移。"""

    _INT_ALIAS = {
        "intention_daily": ("intention_daily", "new_customers", "intentions"),
        "wechat_count_daily": ("wechat_count_daily", "appointments", "wechat_count"),
        "visit_count_daily": ("visit_count_daily", "visits"),
        "invalid_visit_count_daily": ("invalid_visit_count_daily", "invalid_visits"),
        "signing_count_daily": ("signing_count_daily", "signings"),
        "quality_visit_count_daily": ("quality_visit_count_daily", "quality_visits"),
        "approval_customer_count_daily": ("approval_customer_count_daily", "approval_count", "approvals"),
        "repayment_customer_count_daily": (
            "repayment_customer_count_daily",
            "repayments",
            "repayment_customers",
        ),
        "debt_case_submit_count_daily": ("debt_case_submit_count_daily",),
        "debt_case_repayment_count_daily": ("debt_case_repayment_count_daily",),
        "large_order_repayment_count_daily": ("large_order_repayment_count_daily",),
    }

    _AMOUNT_ALIAS = {
        "repayment_amount_daily": ("repayment_amount_daily", "repayment_amount"),
        "loan_amount_daily": ("loan_amount_daily", "loan_amount"),
        "debt_case_repayment_amount_daily": ("debt_case_repayment_amount_daily",),
        "large_order_repayment_amount_daily": ("large_order_repayment_amount_daily",),
    }

    def __init__(self, db_manager, template_service, record_service) -> None:
        self.db_manager = db_manager
        self.template_service = template_service
        self.record_service = record_service
        self.logger = get_logger("legacy_migration_service")

    @staticmethod
    def _first_value(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            if key in data and data.get(key) not in (None, ""):
                return data.get(key)
        return None

    @staticmethod
    def _ordered_unique(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            clean = str(item or "").strip()
            if not clean:
                continue
            key = clean.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(clean)
        return result

    @staticmethod
    def _looks_like_legacy(payload: dict[str, Any]) -> tuple[bool, list[str]]:
        if not isinstance(payload, dict):
            return False, []

        records = payload.get("records")
        export_info = payload.get("export_info")
        if not isinstance(records, list) or not isinstance(export_info, dict):
            return False, []
        if not records:
            return False, []

        first = records[0] if isinstance(records[0], dict) else {}
        markers: list[str] = []

        if "settlement_cycle_info" not in payload:
            markers.append("missing_settlement_cycle_info")
        if "export_type" in export_info:
            markers.append("export_info.export_type")
        if "team" in export_info and "team_name" not in export_info:
            markers.append("export_info.team")
        if "manager" in export_info and "team_manager_name" not in export_info:
            markers.append("export_info.manager")

        if "date" in first and "record_date" not in first:
            markers.append("record.date")
        if "team" in first and "team_name_snapshot" not in first:
            markers.append("record.team")
        if "manager_name" in first and "account_manager_name_snapshot" not in first:
            markers.append("record.manager_name")

        for k in ("new_customers", "appointments", "visits", "signings", "repayments"):
            if k in first:
                markers.append(f"record.{k}")

        return bool(markers), markers

    @staticmethod
    def _normalize_cycle_code(value: Any, fallback_record_date: str = "") -> str:
        text = str(value or "").strip()
        if text:
            return settlement_cycle_display_code(cycle_code=text)
        if fallback_record_date:
            try:
                return settlement_cycle_display_code(record_date=fallback_record_date)
            except Exception:  # noqa: BLE001
                return ""
        return ""

    def _normalize_legacy_record(
        self,
        raw: dict[str, Any],
        default_region: str,
        default_team_name: str,
        default_team_manager_name: str,
        default_cycle_code: str,
    ) -> dict[str, Any] | None:
        now = now_iso()
        record_date = str(raw.get("record_date") or raw.get("date") or "").strip()
        if not record_date:
            return None

        try:
            parse_date(record_date)
        except Exception:  # noqa: BLE001
            return None

        account_manager_name = str(
            raw.get("account_manager_name_snapshot")
            or raw.get("account_manager_name")
            or raw.get("manager_name")
            or ""
        ).strip()
        if not account_manager_name:
            return None

        row: dict[str, Any] = {
            "legacy_record_id": str(raw.get("record_id") or "").strip(),
            "record_date": record_date,
            "region": str(raw.get("region") or default_region or "").strip(),
            "team_name": str(raw.get("team_name_snapshot") or raw.get("team") or default_team_name or "").strip(),
            "team_manager_name": str(
                raw.get("team_manager_name_snapshot")
                or raw.get("team_manager_name")
                or default_team_manager_name
                or ""
            ).strip(),
            "account_manager_name": account_manager_name,
            "settlement_cycle_code": self._normalize_cycle_code(
                raw.get("settlement_cycle_code") or default_cycle_code,
                fallback_record_date=record_date,
            ),
            "remark": str(raw.get("remark") or raw.get("note") or ""),
            "version": max(1, safe_int(raw.get("version", 1))),
            "created_at": str(raw.get("created_at") or "").strip() or now,
            "updated_at": str(raw.get("updated_at") or "").strip() or now,
        }

        for key, aliases in self._INT_ALIAS.items():
            row[key] = safe_int(self._first_value(raw, aliases))

        for key, aliases in self._AMOUNT_ALIAS.items():
            row[key] = safe_decimal(self._first_value(raw, aliases))

        return row

    def _extract_targets(
        self,
        payload: dict[str, Any],
        export_info: dict[str, Any],
        cycle_hint: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []

        def append_target(raw_name: Any, raw_cycle: Any, raw_amount: Any) -> None:
            name = str(raw_name or "").strip()
            if not name:
                return
            amount = safe_decimal(raw_amount)
            cycle_code = self._normalize_cycle_code(raw_cycle, "") or cycle_hint
            rows.append(
                {
                    "account_manager_name": name,
                    "settlement_cycle_code": cycle_code,
                    "target_amount": amount,
                }
            )

        members_sources = []
        team_config = payload.get("team_config")
        if isinstance(team_config, dict):
            members_sources.append(team_config.get("members"))
        members_sources.extend(
            [
                payload.get("members"),
                payload.get("team_members"),
                payload.get("account_managers"),
                export_info.get("members"),
            ]
        )

        for source in members_sources:
            if not isinstance(source, list):
                continue
            for item in source:
                if isinstance(item, str):
                    append_target(item, cycle_hint, 0)
                    continue
                if not isinstance(item, dict):
                    continue
                append_target(
                    item.get("account_manager_name") or item.get("manager_name") or item.get("name"),
                    item.get("settlement_cycle_code") or item.get("cycle_code") or item.get("cycle"),
                    item.get("target_amount") or item.get("target") or 0,
                )

        target_sources = [
            payload.get("targets"),
            payload.get("cycle_targets"),
            payload.get("target_info"),
            export_info.get("targets"),
        ]
        for source in target_sources:
            if isinstance(source, dict):
                for name, amount in source.items():
                    append_target(name, cycle_hint, amount)
                continue
            if not isinstance(source, list):
                continue
            for item in source:
                if isinstance(item, dict):
                    append_target(
                        item.get("account_manager_name")
                        or item.get("manager_name")
                        or item.get("name"),
                        item.get("settlement_cycle_code") or item.get("cycle_code") or item.get("cycle"),
                        item.get("target_amount") or item.get("target") or 0,
                    )

        dedup: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            key = (
                str(row.get("account_manager_name", "")).strip().casefold(),
                str(row.get("settlement_cycle_code", "")).strip(),
            )
            if not key[0]:
                continue
            dedup[key] = row
        result = list(dedup.values())
        result.sort(key=lambda x: (str(x.get("account_manager_name", "")), str(x.get("settlement_cycle_code", ""))))
        return result

    def preview_legacy_file(self, file_path: str) -> dict[str, Any]:
        path = Path(file_path)
        try:
            payload = load_json_file(path)
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("旧版迁移读取失败 file=%s", path)
            return {
                "ok": False,
                "is_legacy": False,
                "message": f"读取失败: {exc}",
                "file_name": path.name,
                "file_path": str(path),
            }

        is_current, _ = validate_export_payload(payload if isinstance(payload, dict) else {})
        if is_current:
            return {
                "ok": False,
                "is_legacy": False,
                "message": "该文件已是当前版本 JSON，请使用“JSON导入”功能",
                "file_name": path.name,
                "file_path": str(path),
            }

        looks_legacy, markers = self._looks_like_legacy(payload if isinstance(payload, dict) else {})
        if not looks_legacy:
            return {
                "ok": False,
                "is_legacy": False,
                "message": "未识别为可迁移的旧版 JSON 结构",
                "file_name": path.name,
                "file_path": str(path),
            }

        export_info = payload.get("export_info") if isinstance(payload.get("export_info"), dict) else {}
        cycle_info = payload.get("settlement_cycle_info") if isinstance(payload.get("settlement_cycle_info"), dict) else {}
        raw_records = payload.get("records") if isinstance(payload.get("records"), list) else []

        region = str(export_info.get("region") or payload.get("region") or "").strip()
        team_name = str(
            export_info.get("team_name")
            or export_info.get("team")
            or payload.get("team_name")
            or payload.get("team")
            or ""
        ).strip()
        team_manager_name = str(
            export_info.get("team_manager_name")
            or export_info.get("manager")
            or payload.get("team_manager_name")
            or payload.get("manager")
            or ""
        ).strip()

        records: list[dict[str, Any]] = []
        for raw in raw_records:
            if not isinstance(raw, dict):
                continue
            row = self._normalize_legacy_record(
                raw,
                default_region=region,
                default_team_name=team_name,
                default_team_manager_name=team_manager_name,
                default_cycle_code=self._normalize_cycle_code(cycle_info.get("cycle_code", ""), ""),
            )
            if row is not None:
                records.append(row)

        if not records:
            return {
                "ok": False,
                "is_legacy": False,
                "message": "识别失败：未找到可用的旧版 records",
                "file_name": path.name,
                "file_path": str(path),
            }

        if not region:
            region = str(records[0].get("region", "")).strip()
        if not team_name:
            team_name = str(records[0].get("team_name", "")).strip()
        if not team_manager_name:
            team_manager_name = str(records[0].get("team_manager_name", "")).strip()

        cycle_hint = self._normalize_cycle_code(
            cycle_info.get("cycle_code") or export_info.get("cycle_code") or "",
            fallback_record_date=str(records[0].get("record_date", "")),
        )

        target_rows = self._extract_targets(payload, export_info, cycle_hint=cycle_hint)

        member_names = self._ordered_unique(
            [str(x.get("account_manager_name", "")) for x in records]
            + [str(x.get("account_manager_name", "")) for x in target_rows]
        )

        member_rows: list[dict[str, Any]] = []
        for member in member_names:
            related = [x for x in target_rows if str(x.get("account_manager_name", "")).strip() == member]
            if related:
                member_rows.extend(related)
            else:
                member_rows.append(
                    {
                        "account_manager_name": member,
                        "settlement_cycle_code": cycle_hint,
                        "target_amount": 0.0,
                    }
                )

        records.sort(key=lambda x: (str(x.get("record_date", "")), str(x.get("account_manager_name", ""))))
        dates = [str(x.get("record_date", "")) for x in records]
        start_date = min(dates)
        end_date = max(dates)

        recognized_summary = (
            f"markers={','.join(markers)}; raw_records={len(raw_records)}; "
            f"valid_records={len(records)}; members={len(member_names)}; targets={len(target_rows)}"
        )

        return {
            "ok": True,
            "is_legacy": True,
            "message": "识别成功",
            "file_name": path.name,
            "file_path": str(path),
            "team": {
                "region": region,
                "team_name": team_name,
                "team_manager_name": team_manager_name,
            },
            "members": member_rows,
            "records": records,
            "recognized_range": {
                "start_date": start_date,
                "end_date": end_date,
            },
            "recognized_summary": recognized_summary,
            "source_export_id": str(export_info.get("export_id") or ""),
            "recognized_identity": {
                "legacy_team_id": safe_int(export_info.get("team_id")),
                "region": region,
                "team_name": team_name,
                "team_manager_name": team_manager_name,
            },
            "markers": markers,
        }

    @staticmethod
    def _record_rank(row: dict[str, Any]) -> tuple[int, str]:
        return int(row.get("version", 1) or 1), str(row.get("updated_at", "") or "")

    def _deduplicate_records(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mapping: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            key = (
                str(row.get("record_date", "")).strip(),
                str(row.get("account_manager_name", "")).strip().casefold(),
            )
            if not key[0] or not key[1]:
                continue
            existing = mapping.get(key)
            if existing is None or self._record_rank(row) >= self._record_rank(existing):
                mapping[key] = row
        result = list(mapping.values())
        result.sort(key=lambda x: (str(x.get("record_date", "")), str(x.get("account_manager_name", ""))))
        return result

    @staticmethod
    def _final_team_text(team_info: dict[str, Any]) -> str:
        region = str(team_info.get("region", "")).strip()
        team_name = str(team_info.get("team_name", "")).strip()
        manager = str(team_info.get("team_manager_name", "")).strip()
        return f"{region} / {team_name} / {manager}"

    @staticmethod
    def _insert_log(conn, row: dict[str, Any]) -> None:
        fields = list(row.keys())
        placeholders = ", ".join(["?" for _ in fields])
        sql = f"INSERT INTO import_logs ({', '.join(fields)}) VALUES ({placeholders})"
        conn.execute(sql, [row[k] for k in fields])

    @staticmethod
    def _safe_team_name(team: dict[str, Any]) -> str:
        return str(team.get("team_name") or "").strip()

    def _resolve_target_team_id(
        self,
        conn,
        final_team: dict[str, Any],
        recognized_identity: dict[str, Any],
        now: str,
    ) -> int:
        legacy_team_id = safe_int(recognized_identity.get("legacy_team_id"))
        if legacy_team_id > 0:
            row = conn.execute("SELECT id FROM teams WHERE id = ?", (legacy_team_id,)).fetchone()
            if row is not None:
                return int(row["id"])

        region = str(recognized_identity.get("region") or "").strip()
        team_name = str(recognized_identity.get("team_name") or "").strip()
        team_manager_name = str(recognized_identity.get("team_manager_name") or "").strip()

        if region and team_name and team_manager_name:
            row = conn.execute(
                """
                SELECT id
                FROM teams
                WHERE region = ? AND team_name = ? AND team_manager_name = ?
                LIMIT 1
                """,
                (region, team_name, team_manager_name),
            ).fetchone()
            if row is not None:
                return int(row["id"])

        final_team_name = self._safe_team_name(final_team)
        if final_team_name:
            rows = conn.execute(
                "SELECT id FROM teams WHERE team_name = ? ORDER BY id ASC",
                (final_team_name,),
            ).fetchall()
            if len(rows) == 1:
                return int(rows[0]["id"])

        cursor = conn.execute(
            """
            INSERT INTO teams (region, team_name, team_manager_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(final_team.get("region", "")).strip(),
                str(final_team.get("team_name", "")).strip(),
                str(final_team.get("team_manager_name", "")).strip(),
                now,
                now,
            ),
        )
        return int(cursor.lastrowid)

    def _normalize_confirmed_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for raw in records:
            if not isinstance(raw, dict):
                continue
            row = normalize_record(raw)
            record_date = str(raw.get("record_date") or row.get("record_date") or "").strip()
            manager_name = str(
                raw.get("account_manager_name")
                or raw.get("account_manager_name_snapshot")
                or row.get("account_manager_name_snapshot")
                or ""
            ).strip()
            if not record_date or not manager_name:
                continue
            try:
                parse_date(record_date)
            except Exception:  # noqa: BLE001
                continue

            normalized_row = {
                "record_date": record_date,
                "account_manager_name": manager_name,
                "remark": str(raw.get("remark") or row.get("remark") or ""),
                "version": max(1, safe_int(raw.get("version") or row.get("version") or 1)),
                "created_at": str(raw.get("created_at") or row.get("created_at") or "").strip() or now_iso(),
                "updated_at": str(raw.get("updated_at") or row.get("updated_at") or "").strip() or now_iso(),
                "settlement_cycle_code": self._normalize_cycle_code(
                    raw.get("settlement_cycle_code") or row.get("settlement_cycle_code") or "",
                    fallback_record_date=record_date,
                ),
            }

            for key in DAILY_INT_FIELDS:
                normalized_row[key] = safe_int(raw.get(key, row.get(key, 0)))
            for key in DAILY_AMOUNT_FIELDS:
                normalized_row[key] = safe_decimal(raw.get(key, row.get(key, 0)))

            result.append(normalized_row)

        return self._deduplicate_records(result)

    def _normalize_confirmed_targets(self, rows: list[dict[str, Any]], cycle_hint: str) -> list[dict[str, Any]]:
        dedup: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("account_manager_name") or "").strip()
            if not name:
                continue
            cycle_code = self._normalize_cycle_code(row.get("settlement_cycle_code") or "", "") or cycle_hint
            target_amount = safe_decimal(row.get("target_amount"))
            key = (name.casefold(), cycle_code)
            dedup[key] = {
                "account_manager_name": name,
                "settlement_cycle_code": cycle_code,
                "target_amount": target_amount,
            }

        result = list(dedup.values())
        result.sort(key=lambda x: (str(x.get("account_manager_name", "")), str(x.get("settlement_cycle_code", ""))))
        return result

    def apply_migration(self, payload: dict[str, Any], operator: str = "admin") -> tuple[bool, str, dict[str, Any]]:
        file_name = str(payload.get("file_name") or "")
        file_path = str(payload.get("file_path") or "")
        recognized_summary = str(payload.get("recognized_summary") or "")
        source_export_id = str(payload.get("source_export_id") or "")

        team = payload.get("team") if isinstance(payload.get("team"), dict) else {}
        final_team = {
            "region": str(team.get("region") or "").strip(),
            "team_name": str(team.get("team_name") or "").strip(),
            "team_manager_name": str(team.get("team_manager_name") or "").strip(),
        }

        if not final_team["region"] or not final_team["team_name"] or not final_team["team_manager_name"]:
            return False, "迁移失败：团队基础信息不完整（区域/团队/团队经理不能为空）", {}

        confirmed_records = self._normalize_confirmed_records(payload.get("records") or [])
        if not confirmed_records:
            return False, "迁移失败：没有可迁移的日报记录", {}

        cycle_hint = ""
        if confirmed_records:
            cycle_hint = self._normalize_cycle_code("", confirmed_records[0]["record_date"])

        confirmed_targets = self._normalize_confirmed_targets(payload.get("members") or [], cycle_hint)

        member_names = self._ordered_unique(
            [str(x.get("account_manager_name", "")) for x in (payload.get("members") or [])]
            + [str(x.get("account_manager_name", "")) for x in confirmed_records]
        )
        if not member_names:
            return False, "迁移失败：未识别到客户经理名单", {}

        date_values = [str(x.get("record_date", "")) for x in confirmed_records]
        start_date = min(date_values)
        end_date = max(date_values)

        recognized_identity = payload.get("recognized_identity") if isinstance(payload.get("recognized_identity"), dict) else {}
        now = now_iso()
        template_version = self.template_service.get_active_template_version()

        conn = self.db_manager.get_connection()
        try:
            conn.execute("BEGIN")

            team_id = self._resolve_target_team_id(
                conn,
                final_team=final_team,
                recognized_identity=recognized_identity,
                now=now,
            )

            conn.execute(
                """
                UPDATE teams
                SET region = ?, team_name = ?, team_manager_name = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    final_team["region"],
                    final_team["team_name"],
                    final_team["team_manager_name"],
                    now,
                    team_id,
                ),
            )

            existing_members = conn.execute(
                """
                SELECT id, account_manager_name
                FROM account_managers
                WHERE team_id = ?
                """,
                (team_id,),
            ).fetchall()
            existing_map = {
                str(row["account_manager_name"]).strip().casefold(): {
                    "id": int(row["id"]),
                    "name": str(row["account_manager_name"]).strip(),
                }
                for row in existing_members
            }

            keep_ids: list[int] = []
            manager_id_map: dict[str, int] = {}
            for member_name in member_names:
                key = member_name.casefold()
                row = existing_map.get(key)
                if row is None:
                    cursor = conn.execute(
                        """
                        INSERT INTO account_managers (team_id, account_manager_name, is_active, created_at, updated_at)
                        VALUES (?, ?, 1, ?, ?)
                        """,
                        (team_id, member_name, now, now),
                    )
                    manager_id = int(cursor.lastrowid)
                else:
                    manager_id = int(row["id"])
                    conn.execute(
                        "UPDATE account_managers SET is_active = 1, updated_at = ? WHERE id = ?",
                        (now, manager_id),
                    )
                keep_ids.append(manager_id)
                manager_id_map[key] = manager_id

            if keep_ids:
                placeholders = ",".join(["?" for _ in keep_ids])
                conn.execute(
                    f"UPDATE account_managers SET is_active = 0, updated_at = ? WHERE team_id = ? AND id NOT IN ({placeholders})",
                    [now, team_id, *keep_ids],
                )
            else:
                conn.execute(
                    "UPDATE account_managers SET is_active = 0, updated_at = ? WHERE team_id = ?",
                    (now, team_id),
                )

            if confirmed_targets:
                target_cycles = sorted(
                    {
                        str(x.get("settlement_cycle_code", "")).strip()
                        for x in confirmed_targets
                        if str(x.get("settlement_cycle_code", "")).strip()
                    }
                )
                if target_cycles:
                    placeholders = ",".join(["?" for _ in target_cycles])
                    conn.execute(
                        f"DELETE FROM cycle_targets WHERE team_id = ? AND settlement_cycle_code IN ({placeholders})",
                        [team_id, *target_cycles],
                    )

                for target in confirmed_targets:
                    name_key = str(target.get("account_manager_name", "")).strip().casefold()
                    manager_id = manager_id_map.get(name_key)
                    if not manager_id:
                        continue
                    conn.execute(
                        """
                        INSERT INTO cycle_targets
                        (team_id, account_manager_id, settlement_cycle_code, target_amount, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(team_id, account_manager_id, settlement_cycle_code)
                        DO UPDATE SET target_amount = excluded.target_amount, updated_at = excluded.updated_at
                        """,
                        (
                            team_id,
                            manager_id,
                            str(target.get("settlement_cycle_code", "")).strip(),
                            safe_decimal(target.get("target_amount", 0)),
                            now,
                            now,
                        ),
                    )

            deleted_cursor = conn.execute(
                "DELETE FROM daily_records WHERE team_id = ? AND record_date BETWEEN ? AND ?",
                (team_id, start_date, end_date),
            )
            deleted_count = int(deleted_cursor.rowcount or 0)

            inserted_count = 0
            for row in confirmed_records:
                manager_name = str(row.get("account_manager_name", "")).strip()
                manager_id = manager_id_map.get(manager_name.casefold())
                if manager_id is None:
                    continue

                record_date = str(row.get("record_date", "")).strip()
                settlement_cycle_code = self._normalize_cycle_code(
                    row.get("settlement_cycle_code") or "",
                    fallback_record_date=record_date,
                )
                business_key = "|".join(
                    [
                        record_date,
                        final_team["region"],
                        final_team["team_name"],
                        manager_name,
                    ]
                )

                save_payload = {
                    "record_id": f"legacy-{uuid.uuid4()}",
                    "record_date": record_date,
                    "region": final_team["region"],
                    "team_id": team_id,
                    "team_name_snapshot": final_team["team_name"],
                    "team_manager_name_snapshot": final_team["team_manager_name"],
                    "account_manager_id": manager_id,
                    "account_manager_name_snapshot": manager_name,
                    "settlement_cycle_code": settlement_cycle_code,
                    "business_key": business_key,
                    "remark": str(row.get("remark") or ""),
                    "version": max(1, safe_int(row.get("version", 1))),
                    "created_at": str(row.get("created_at") or now),
                    "updated_at": now,
                    "template_version": template_version,
                    "source_type": "legacy_migration",
                    "source_file": file_path,
                }
                for key in DAILY_INT_FIELDS:
                    save_payload[key] = safe_int(row.get(key, 0))
                for key in DAILY_AMOUNT_FIELDS:
                    save_payload[key] = safe_decimal(row.get(key, 0))

                save_payload["record_hash"] = self.record_service.build_record_hash(save_payload)

                columns = [
                    "record_id",
                    "business_key",
                    "record_date",
                    "region",
                    "team_id",
                    "team_name_snapshot",
                    "team_manager_name_snapshot",
                    "account_manager_id",
                    "account_manager_name_snapshot",
                    "settlement_cycle_code",
                    "repayment_amount_daily",
                    "loan_amount_daily",
                    "intention_daily",
                    "wechat_count_daily",
                    "visit_count_daily",
                    "invalid_visit_count_daily",
                    "signing_count_daily",
                    "quality_visit_count_daily",
                    "approval_customer_count_daily",
                    "repayment_customer_count_daily",
                    "debt_case_submit_count_daily",
                    "debt_case_repayment_count_daily",
                    "debt_case_repayment_amount_daily",
                    "large_order_repayment_count_daily",
                    "large_order_repayment_amount_daily",
                    "remark",
                    "version",
                    "created_at",
                    "updated_at",
                    "template_version",
                    "record_hash",
                    "source_type",
                    "source_file",
                ]
                placeholders = ", ".join(["?" for _ in columns])
                conn.execute(
                    f"INSERT INTO daily_records ({', '.join(columns)}) VALUES ({placeholders})",
                    [save_payload[c] for c in columns],
                )
                inserted_count += 1

            cycle_code_for_log = self._normalize_cycle_code(
                "",
                fallback_record_date=start_date,
            )
            success_message = (
                f"旧版迁移完成：团队={self._final_team_text(final_team)}，"
                f"时间范围={start_date}~{end_date}，替换成员={len(member_names)}，"
                f"清理旧记录={deleted_count}，写入新记录={inserted_count}"
            )
            self._insert_log(
                conn,
                {
                    "import_time": now,
                    "file_name": file_name,
                    "file_path": file_path,
                    "export_id": source_export_id,
                    "team_name": final_team["team_name"],
                    "settlement_cycle_code": cycle_code_for_log,
                    "template_version": template_version,
                    "result": "success",
                    "message": success_message,
                    "affected_record_count": inserted_count,
                    "log_type": "legacy_migration",
                    "operator": operator or "admin",
                    "recognized_summary": recognized_summary,
                    "final_team": self._final_team_text(final_team),
                    "range_start": start_date,
                    "range_end": end_date,
                    "replaced_member_count": len(member_names),
                    "replaced_record_count": inserted_count,
                },
            )

            conn.commit()
            self.logger.info(
                "旧版迁移成功 team_id=%s team=%s range=%s~%s members=%s inserted=%s deleted=%s file=%s",
                team_id,
                final_team["team_name"],
                start_date,
                end_date,
                len(member_names),
                inserted_count,
                deleted_count,
                file_path,
            )
            return (
                True,
                "迁移成功",
                {
                    "team_id": team_id,
                    "team_name": final_team["team_name"],
                    "range_start": start_date,
                    "range_end": end_date,
                    "member_count": len(member_names),
                    "deleted_count": deleted_count,
                    "inserted_count": inserted_count,
                },
            )
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            self.logger.exception("旧版迁移失败 file=%s", file_path)

            failure_row = {
                "import_time": now_iso(),
                "file_name": file_name,
                "file_path": file_path,
                "export_id": source_export_id,
                "team_name": final_team.get("team_name", ""),
                "settlement_cycle_code": "",
                "template_version": self.template_service.get_active_template_version(),
                "result": "failed",
                "message": f"旧版迁移失败: {exc}",
                "affected_record_count": 0,
                "log_type": "legacy_migration",
                "operator": operator or "admin",
                "recognized_summary": recognized_summary,
                "final_team": self._final_team_text(final_team),
                "range_start": "",
                "range_end": "",
                "replaced_member_count": 0,
                "replaced_record_count": 0,
            }
            fail_conn = self.db_manager.get_connection()
            try:
                self._insert_log(fail_conn, failure_row)
                fail_conn.commit()
            finally:
                fail_conn.close()
            return False, f"迁移失败: {exc}", {}
        finally:
            conn.close()
