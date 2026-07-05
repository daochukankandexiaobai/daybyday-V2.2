from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import timedelta
from typing import Any, Dict, List

from app.config.field_profiles import PROFILE_PREVIEW_TABLE, PROFILE_QUERY_SUMMARY_TABLE
from app.config.field_rules import CONFIGURED_DAILY_AMOUNT_FIELD_KEYS, CONFIGURED_DAILY_INT_FIELD_KEYS
from app.config.field_registry import (
    STORAGE_DYNAMIC_METRIC,
    STORAGE_FIXED_COLUMN,
    get_entry_fields,
)
from app.fields.aggregation_service import AggregationService
from app.fields.display_config_service import DisplayFieldConfigService
from app.fields.field_value_service import FieldValueService
from app.fields.formula_service import (
    FORMULA_APPROVAL_RATE,
    FORMULA_DAILY_SIGN_RATE,
    FORMULA_QUALITY_VISIT_RATE,
    FORMULA_REPAYMENT_CONVERSION_RATE,
    FORMULA_SALES_CONVERSION_RATE,
    FORMULA_SIGN_RATE,
    FORMULA_TARGET_COMPLETION_RATE,
    FORMULA_WARRANT_CONVERSION_RATE,
    FormulaService,
)
from app.fields.registry import PAGE_QUERY_SUMMARY, PAGE_TODAY_DISPLAY
from app.utils.date_utils import (
    canonical_cycle_codes_from_dates,
    cycle_week_for_date,
    now_iso,
    normalize_cycle_code_text,
    parse_date,
    range_crosses_cycles,
    resolve_report_range,
    settlement_cycle_display_code,
    settlement_cycle_for_date,
)
from app.utils.hash_utils import hash_record_payload
from app.utils.log_utils import get_logger
from app.utils.metrics_utils import aggregate_daily_rows, ratio_or_none
from app.utils.validators import DAILY_AMOUNT_FIELDS, DAILY_INT_FIELDS, safe_decimal, safe_int


class RecordService:
    """日报服务（客户经理 x 日期粒度）。"""
    _AMOUNT_FIELDS = list(CONFIGURED_DAILY_AMOUNT_FIELD_KEYS)
    _COUNT_FIELDS = list(CONFIGURED_DAILY_INT_FIELD_KEYS)

    def __init__(
        self,
        record_repo,
        team_repo,
        account_manager_repo,
        cycle_target_repo,
        template_service,
        field_value_service=None,
    ) -> None:
        self.logger = get_logger("record_service")
        self.record_repo = record_repo
        self.team_repo = team_repo
        self.account_manager_repo = account_manager_repo
        self.cycle_target_repo = cycle_target_repo
        self.template_service = template_service
        self.field_value_service = field_value_service or FieldValueService(record_repo.db)
        self.display_config_service = DisplayFieldConfigService(record_repo.db)
        self.formula_service = FormulaService()
        self.aggregation_service = AggregationService(self.formula_service)

    def get_today_display_field_definitions(self) -> List[Dict[str, Any]]:
        return self.display_config_service.get_page_fields(
            page_key=PAGE_TODAY_DISPLAY,
            fallback_profile_key=PROFILE_PREVIEW_TABLE,
            template_key="today_display_default",
        )

    def get_query_summary_field_definitions(self) -> List[Dict[str, Any]]:
        return self.display_config_service.get_page_fields(
            page_key=PAGE_QUERY_SUMMARY,
            fallback_profile_key=PROFILE_QUERY_SUMMARY_TABLE,
            template_key="query_summary_default",
        )

    def get_entry_field_definitions(self) -> List[Dict[str, Any]]:
        rows = self._entry_field_rows_from_visibility()
        if rows:
            return rows
        rows = self._entry_field_rows_from_template()
        if rows:
            return rows
        return self._entry_field_rows_from_registry()

    def _entry_field_rows_from_visibility(self) -> List[Dict[str, Any]]:
        sql = """
            SELECT fd.*, fpv.visible, fpv.display_order, fpv.page_key
            FROM field_page_visibility fpv
            JOIN field_definitions fd ON fd.field_key = fpv.field_key
            WHERE fpv.page_key = ?
              AND fpv.visible = 1
              AND fd.enabled = 1
              AND fd.editable = 1
              AND fd.category = 'raw_daily'
            ORDER BY fpv.display_order ASC, fd.id ASC
        """
        try:
            with self.record_repo.db.get_connection() as conn:
                for page_key in ("entry", "data_entry"):
                    rows = [dict(row) for row in conn.execute(sql, (page_key,)).fetchall()]
                    if rows:
                        return rows
                return []
        except Exception:  # noqa: BLE001
            return []

    def _entry_field_rows_from_template(self) -> List[Dict[str, Any]]:
        try:
            import json

            with self.record_repo.db.get_connection() as conn:
                template = conn.execute(
                    """
                    SELECT config_json
                    FROM view_templates
                    WHERE template_key = 'entry_default'
                      AND enabled = 1
                    LIMIT 1
                    """
                ).fetchone()
                if template is None:
                    return []
                payload = json.loads(str(template["config_json"] or "{}"))
                field_keys = [str(item) for item in payload.get("field_keys", []) if str(item).strip()]
                if not field_keys:
                    return []
                placeholders = ",".join(["?" for _ in field_keys])
                rows = {
                    str(row["field_key"]): dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT *
                        FROM field_definitions
                        WHERE field_key IN ({placeholders})
                          AND enabled = 1
                          AND editable = 1
                          AND category = 'raw_daily'
                        """,
                        field_keys,
                    ).fetchall()
                }
                return [rows[key] for key in field_keys if key in rows]
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _entry_field_rows_from_registry() -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for spec in get_entry_fields():
            if spec.category != "raw_daily" or not spec.enabled or not spec.editable:
                continue
            rows.append(
                {
                    "field_key": spec.field_key,
                    "label": spec.label,
                    "data_type": spec.data_type,
                    "category": spec.category,
                    "editable": 1 if spec.editable else 0,
                    "required": 1 if spec.required else 0,
                    "default_value": str(spec.default_value if spec.default_value is not None else ""),
                    "storage_type": spec.storage_type,
                    "storage_column": spec.storage_column,
                    "enabled": 1 if spec.enabled else 0,
                }
            )
        return rows

    def _entry_field_map(self) -> Dict[str, Dict[str, Any]]:
        return {str(row["field_key"]): row for row in self.get_entry_field_definitions()}

    def _all_daily_metric_field_definitions(self) -> List[Dict[str, Any]]:
        try:
            with self.record_repo.db.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM field_definitions
                    WHERE enabled = 1
                      AND category = 'raw_daily'
                      AND field_key <> 'remark'
                    ORDER BY id ASC
                    """
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _is_numeric_field_def(field_def: Dict[str, Any]) -> bool:
        return str(field_def.get("data_type", "")).lower() in {"int", "amount", "money", "decimal", "percent"}

    @staticmethod
    def _zero_for_field_def(field_def: Dict[str, Any]) -> Any:
        data_type = str(field_def.get("data_type", "")).lower()
        if data_type == "int":
            return 0
        if data_type in {"amount", "money", "decimal", "percent"}:
            return 0.0
        return ""

    def _enrich_dynamic_metric_rows(
        self,
        rows: List[Dict[str, Any]],
        field_definitions: List[Dict[str, Any]] | None = None,
    ) -> List[Dict[str, Any]]:
        field_definitions = field_definitions if field_definitions is not None else self._all_daily_metric_field_definitions()
        dynamic_keys = [
            str(row.get("field_key", ""))
            for row in field_definitions
            if str(row.get("storage_type", "")) == STORAGE_DYNAMIC_METRIC
        ]
        if not dynamic_keys:
            return [dict(row) for row in rows]

        result = []
        for row in rows:
            enriched = dict(row)
            record_id = int(enriched.get("id") or 0)
            if record_id > 0:
                try:
                    enriched.update(self.field_value_service.get_values(record_id, dynamic_keys))
                except Exception:  # noqa: BLE001
                    pass
            result.append(enriched)
        return result

    def _append_raw_daily_values(self, output: Dict[str, Any], source_row: Dict[str, Any]) -> None:
        for field_def in self._all_daily_metric_field_definitions():
            field_key = str(field_def.get("field_key", ""))
            if not field_key or field_key in output:
                continue
            try:
                output[field_key] = self.field_value_service.get_value(source_row, field_key)
            except Exception:  # noqa: BLE001
                output[field_key] = self._zero_for_field_def(field_def)

    def _empty_daily_metrics(self) -> dict[str, Any]:
        metrics: dict[str, Any] = {}
        for field_key, field_def in self._entry_field_map().items():
            if field_key == "remark":
                metrics[field_key] = ""
                continue
            metrics[field_key] = self.field_value_service.normalize_value(field_def, None)
        return metrics

    def _normalize_entry_values(self, payload: dict[str, Any]) -> dict[str, Any]:
        metrics: dict[str, Any] = {}
        for field_key, field_def in self._entry_field_map().items():
            metrics[field_key] = self.field_value_service.normalize_value(field_def, payload.get(field_key))
        return metrics

    def _split_storage_values(self, values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        field_map = self._entry_field_map()
        fixed_values: dict[str, Any] = {}
        dynamic_values: dict[str, Any] = {}
        for field_key, value in values.items():
            field_def = field_map.get(field_key, {})
            storage_type = str(field_def.get("storage_type") or "")
            storage_column = str(field_def.get("storage_column") or field_key)
            if storage_type == STORAGE_DYNAMIC_METRIC:
                dynamic_values[field_key] = value
            elif storage_type == STORAGE_FIXED_COLUMN or field_key in DAILY_INT_FIELDS or field_key in DAILY_AMOUNT_FIELDS or field_key == "remark":
                fixed_values[storage_column] = value
        return fixed_values, dynamic_values

    def _dynamic_values_changed(self, record_id: int, dynamic_values: dict[str, Any]) -> bool:
        if not dynamic_values:
            return False
        current = self.field_value_service.get_values(int(record_id), dynamic_values.keys())
        for key, value in dynamic_values.items():
            if current.get(key) != value:
                return True
        return False

    @classmethod
    def _sum_rows(cls, rows: list[dict[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key in cls._AMOUNT_FIELDS:
            result[key] = sum(float(row.get(key, 0) or 0) for row in rows)
        for key in cls._COUNT_FIELDS:
            result[key] = sum(int(row.get(key, 0) or 0) for row in rows)
        return result

    @staticmethod
    def _legacy_cycle_code(code: str) -> str:
        normalized = normalize_cycle_code_text(code)
        clean = normalized.replace("期", "")
        if len(clean) != 7 or clean[4] != "-":
            return normalized
        try:
            year = int(clean[:4])
            month = int(clean[5:7])
        except (TypeError, ValueError):
            return normalized
        idx = year * 12 + (month - 1) - 1
        legacy_year = idx // 12
        legacy_month = idx % 12 + 1
        return f"{legacy_year:04d}-{legacy_month:02d}期"

    def _manager_target(self, team_id: int, account_manager_id: int, cycle_code: str) -> float:
        normalized = normalize_cycle_code_text(cycle_code)
        target = self.cycle_target_repo.get_target(team_id, account_manager_id, normalized)
        if target > 0:
            return target
        legacy = self._legacy_cycle_code(normalized)
        if legacy != normalized:
            legacy_target = self.cycle_target_repo.get_target(team_id, account_manager_id, legacy)
            if legacy_target > 0:
                return legacy_target
        return target

    def _team_target(self, team_id: int, cycle_code: str) -> float:
        normalized = normalize_cycle_code_text(cycle_code)
        target = self.cycle_target_repo.team_target_sum(team_id, normalized)
        if target > 0:
            return target
        legacy = self._legacy_cycle_code(normalized)
        if legacy != normalized:
            legacy_target = self.cycle_target_repo.team_target_sum(team_id, legacy)
            if legacy_target > 0:
                return legacy_target
        return target

    def build_record_hash(self, payload: dict[str, Any]) -> str:
        hash_payload = {
            "record_date": payload["record_date"],
            "team_id": int(payload["team_id"]),
            "account_manager_id": int(payload["account_manager_id"]),
            "settlement_cycle_code": payload["settlement_cycle_code"],
            "team_name_snapshot": payload.get("team_name_snapshot", ""),
            "team_manager_name_snapshot": payload.get("team_manager_name_snapshot", ""),
            "account_manager_name_snapshot": payload.get("account_manager_name_snapshot", ""),
            "remark": str(payload.get("remark", "")),
            **{k: payload.get(k, 0) for k in sorted(DAILY_INT_FIELDS)},
            **{k: payload.get(k, 0.0) for k in sorted(DAILY_AMOUNT_FIELDS)},
        }
        return hash_record_payload(hash_payload)

    def _aggregate(self, rows: list[dict[str, Any]], team_target: float = 0.0, include_progress: bool = True) -> dict[str, Any]:
        return aggregate_daily_rows(rows, team_target=team_target, include_progress=include_progress)

    def _aggregate_daily_metric_totals(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        field_definitions = self._all_daily_metric_field_definitions()
        rows = self._enrich_dynamic_metric_rows(rows, field_definitions)
        raw_rules: Dict[str, str] = {}
        for key in self._AMOUNT_FIELDS:
            raw_rules[key] = "sum"
        for key in self._COUNT_FIELDS:
            raw_rules[key] = "sum"
        data_type_by_key: Dict[str, str] = {}
        for field_def in field_definitions:
            field_key = str(field_def.get("field_key", ""))
            if not field_key or not self._is_numeric_field_def(field_def):
                continue
            aggregation = str(field_def.get("aggregation", "sum") or "sum")
            if aggregation in {"derived", "formula", "none", "latest"}:
                continue
            raw_rules[field_key] = aggregation
            data_type_by_key[field_key] = str(field_def.get("data_type", "")).lower()
        totals = self.aggregation_service.aggregate_fields(rows, raw_rules)
        for key in self._AMOUNT_FIELDS:
            totals[key] = float(totals.get(key) or 0)
        for key in self._COUNT_FIELDS:
            totals[key] = int(totals.get(key) or 0)
        for key, data_type in data_type_by_key.items():
            if data_type == "int":
                totals[key] = int(totals.get(key) or 0)
            else:
                totals[key] = float(totals.get(key) or 0)
        return totals

    def _today_formula_values(self, values: dict[str, Any]) -> dict[str, Any]:
        result = dict(values)
        result["target_progress"] = self.formula_service.calculate(FORMULA_TARGET_COMPLETION_RATE, result)
        result["daily_signing_rate"] = self.formula_service.calculate(FORMULA_DAILY_SIGN_RATE, result)
        result["daily_quality_visit_rate"] = self.formula_service.calculate(FORMULA_QUALITY_VISIT_RATE, result)
        result["daily_approval_rate"] = self.formula_service.calculate(FORMULA_APPROVAL_RATE, result)
        result["daily_sales_conversion_rate"] = self.formula_service.calculate(FORMULA_SALES_CONVERSION_RATE, result)
        result["warrant_conversion_rate"] = self.formula_service.calculate(FORMULA_WARRANT_CONVERSION_RATE, result)
        return result

    def _query_formula_values(self, values: dict[str, Any], cross_cycle: bool) -> dict[str, Any]:
        result = dict(values)
        result["target_progress"] = None if cross_cycle else self.formula_service.calculate(
            FORMULA_TARGET_COMPLETION_RATE,
            result,
        )
        result["signing_rate"] = self.formula_service.calculate(FORMULA_SIGN_RATE, result)
        result["quality_visit_rate"] = self.formula_service.calculate(FORMULA_QUALITY_VISIT_RATE, result)
        result["approval_rate"] = self.formula_service.calculate(FORMULA_APPROVAL_RATE, result)
        result["repayment_conversion_rate"] = self.formula_service.calculate(FORMULA_REPAYMENT_CONVERSION_RATE, result)
        result["sales_conversion_rate"] = self.formula_service.calculate(FORMULA_SALES_CONVERSION_RATE, result)
        result["warrant_conversion_rate"] = self.formula_service.calculate(FORMULA_WARRANT_CONVERSION_RATE, result)
        return result

    def build_today_display_summary_row(
        self,
        rows: list[dict[str, Any]],
        record_date: str,
        summary_label: str = "团队汇总",
    ) -> dict[str, Any]:
        values = self.aggregation_service.aggregate_fields(
            rows,
            {
                "cycle_target": "sum",
                "repayment_amount_cumulative": "sum",
                "loan_amount_cumulative": "sum",
                "repayment_amount_daily": "sum",
                "loan_amount_daily": "sum",
                "intention_daily": "sum",
                "wechat_count_daily": "sum",
                "visit_count_daily": "sum",
                "invitation_cumulative": "sum",
                "invalid_visit_count_daily": "sum",
                "four_star_customer_count_daily": "sum",
                "five_star_customer_count_daily": "sum",
                "signing_count_daily": "sum",
                "signing_count_cumulative": "sum",
                "quality_visit_count_daily": "sum",
                "quality_visit_count_cumulative": "sum",
                "approval_customer_count_daily": "sum",
                "repayment_customer_count_daily": "sum",
                "debt_case_submit_count_daily": "sum",
                "debt_case_repayment_count_daily": "sum",
                "debt_case_repayment_amount_daily": "sum",
                "large_order_repayment_count_daily": "sum",
                "large_order_repayment_amount_daily": "sum",
            },
        )
        values.update(
            {
                "record_date": summary_label,
                "account_manager_name": "",
                "is_summary_row": True,
            }
        )
        totals = self._aggregate_daily_metric_totals(rows)
        for field_key, value in totals.items():
            if field_key not in values:
                values[field_key] = value
        values = self._today_formula_values(values)
        return values

    def _build_query_summary_aggregate(
        self,
        rows: list[dict[str, Any]],
        team_target: float,
        cross_cycle: bool,
    ) -> dict[str, Any]:
        totals = self._aggregate_daily_metric_totals(rows)
        values = {
            "record_count": len(rows),
            "repayment_amount_cumulative": float(totals.get("repayment_amount_daily", 0) or 0),
            "loan_amount_cumulative": float(totals.get("loan_amount_daily", 0) or 0),
            "invitation_cumulative": int(totals.get("visit_count_daily", 0) or 0),
            "visit_count_cumulative": int(totals.get("visit_count_daily", 0) or 0),
            "invalid_visit_count_cumulative": int(totals.get("invalid_visit_count_daily", 0) or 0),
            "four_star_customer_count": int(totals.get("four_star_customer_count_daily", 0) or 0),
            "five_star_customer_count": int(totals.get("five_star_customer_count_daily", 0) or 0),
            "signing_count_cumulative": int(totals.get("signing_count_daily", 0) or 0),
            "quality_visit_count_cumulative": int(totals.get("quality_visit_count_daily", 0) or 0),
            "approval_customer_count_cumulative": int(totals.get("approval_customer_count_daily", 0) or 0),
            "repayment_customer_count_cumulative": int(totals.get("repayment_customer_count_daily", 0) or 0),
            "cycle_target": float(team_target or 0),
            "cycle_repayment_target": float(team_target or 0),
            "team_cycle_target": float(team_target or 0),
            "repayment_amount": float(totals.get("repayment_amount_daily", 0) or 0),
            "loan_amount": float(totals.get("loan_amount_daily", 0) or 0),
            "visit_count": int(totals.get("visit_count_daily", 0) or 0),
            "invalid_visit_count": int(totals.get("invalid_visit_count_daily", 0) or 0),
            "signing_count": int(totals.get("signing_count_daily", 0) or 0),
            "quality_visit_count": int(totals.get("quality_visit_count_daily", 0) or 0),
            "approval_customer_count": int(totals.get("approval_customer_count_daily", 0) or 0),
            "repayment_customer_count": int(totals.get("repayment_customer_count_daily", 0) or 0),
        }
        values = self._query_formula_values(values, cross_cycle)
        return {
            "record_count": values["record_count"],
            "repayment_amount_cumulative": values["repayment_amount_cumulative"],
            "loan_amount_cumulative": values["loan_amount_cumulative"],
            "invitation_cumulative": values["invitation_cumulative"],
            "visit_count_cumulative": values["visit_count_cumulative"],
            "invalid_visit_count_cumulative": values["invalid_visit_count_cumulative"],
            "four_star_customer_count": values["four_star_customer_count"],
            "five_star_customer_count": values["five_star_customer_count"],
            "signing_count_cumulative": values["signing_count_cumulative"],
            "quality_visit_count_cumulative": values["quality_visit_count_cumulative"],
            "approval_customer_count_cumulative": values["approval_customer_count_cumulative"],
            "repayment_customer_count_cumulative": values["repayment_customer_count_cumulative"],
            "signing_rate": values["signing_rate"],
            "quality_visit_rate": values["quality_visit_rate"],
            "approval_rate": values["approval_rate"],
            "repayment_conversion_rate": values["repayment_conversion_rate"],
            "sales_conversion_rate": values["sales_conversion_rate"],
            "warrant_conversion_rate": values["warrant_conversion_rate"],
            "target_progress": values["target_progress"],
            "team_cycle_target": float(team_target or 0),
        }

    def get_team_day_sheet(self, team_id: int, record_date: str) -> dict[str, Any]:
        team = self.team_repo.get_by_id(team_id)
        if team is None:
            return {"ok": False, "message": "团队不存在"}

        date_obj = parse_date(record_date)
        cycle = settlement_cycle_for_date(date_obj)
        week_info = cycle_week_for_date(date_obj)

        members = self.account_manager_repo.list_by_team(team_id)
        existing = self.record_repo.list_team_day_records(team_id, record_date)
        existing_map = {int(item["account_manager_id"]): item for item in existing}

        rows: list[dict[str, Any]] = []
        for member in members:
            manager_id = int(member["id"])
            row = {
                "account_manager_id": manager_id,
                "account_manager_name": member["account_manager_name"],
                "remark": "",
                **self._empty_daily_metrics(),
            }
            old = existing_map.get(manager_id)
            if old:
                old_with_dynamic = self.field_value_service.read_record_with_dynamic_values(int(old["id"]))
                for field_key in self._entry_field_map():
                    row[field_key] = old_with_dynamic.get(field_key, row.get(field_key, 0))
                row["remark"] = old_with_dynamic.get("remark", "")
            rows.append(row)

        cycle_rows = self.record_repo.list_records(
            start_date=cycle.start.isoformat(),
            end_date=cycle.end_inclusive.isoformat(),
            team_id=team_id,
        )
        team_target = self._team_target(team_id, cycle.code)
        summary = self._aggregate(cycle_rows, team_target=team_target, include_progress=True)

        return {
            "ok": True,
            "team": team,
            "record_date": record_date,
            "cycle_code": settlement_cycle_display_code(record_date=record_date),
            "cycle_start": cycle.start.isoformat(),
            "cycle_end": cycle.end_inclusive.isoformat(),
            "week_label": week_info["week_label"],
            "rows": rows,
            "summary": summary,
        }

    def save_team_day_sheet(
        self,
        team_id: int,
        record_date: str,
        rows: list[dict[str, Any]],
        source_type: str = "local",
        source_file: str | None = None,
    ) -> tuple[bool, str, dict[str, int]]:
        team = self.team_repo.get_by_id(team_id)
        if team is None:
            return False, "团队不存在", {"inserted": 0, "updated": 0, "skipped": 0}

        template_version = self.template_service.get_active_template_version()
        now = now_iso()

        inserted = 0
        updated = 0
        skipped = 0

        for row in rows:
            account_manager_id = safe_int(row.get("account_manager_id"))
            if account_manager_id <= 0:
                continue

            member = self.account_manager_repo.get_by_id(account_manager_id)
            if member is None:
                continue

            entry_values = self._normalize_entry_values(row)
            fixed_values, dynamic_values = self._split_storage_values(entry_values)
            metrics_for_hash = {
                **{key: fixed_values.get(key, entry_values.get(key, 0)) for key in DAILY_INT_FIELDS},
                **{key: fixed_values.get(key, entry_values.get(key, 0.0)) for key in DAILY_AMOUNT_FIELDS},
            }
            payload = {
                "record_date": record_date,
                "region": str(team["region"]),
                "team_id": int(team["id"]),
                "team_name_snapshot": str(team["team_name"]),
                "team_manager_name_snapshot": str(team["team_manager_name"]),
                "account_manager_id": account_manager_id,
                "account_manager_name_snapshot": str(member["account_manager_name"]),
                "settlement_cycle_code": settlement_cycle_display_code(record_date=record_date),
                "business_key": "|".join(
                    [
                        record_date,
                        str(team["region"]),
                        str(team["team_name"]),
                        str(member["account_manager_name"]),
                    ]
                ),
                "remark": str(entry_values.get("remark", row.get("remark", ""))).strip(),
                "template_version": template_version,
                "source_type": source_type,
                "source_file": source_file,
                **fixed_values,
                **metrics_for_hash,
            }

            existing = self.record_repo.get_by_unique(record_date, int(team["id"]), account_manager_id)
            if existing:
                next_hash = self.build_record_hash(payload)
                dynamic_changed = self._dynamic_values_changed(int(existing["id"]), dynamic_values)
                if str(existing.get("record_hash", "")) == next_hash and not dynamic_changed:
                    skipped += 1
                    continue

                self.record_repo.update_by_id(
                    int(existing["id"]),
                    {
                        **fixed_values,
                        **metrics_for_hash,
                        "remark": payload["remark"],
                        "region": payload["region"],
                        "team_name_snapshot": payload["team_name_snapshot"],
                        "team_manager_name_snapshot": payload["team_manager_name_snapshot"],
                        "account_manager_name_snapshot": payload["account_manager_name_snapshot"],
                        "settlement_cycle_code": payload["settlement_cycle_code"],
                        "business_key": payload["business_key"],
                        "version": int(existing.get("version", 1)) + 1,
                        "updated_at": now,
                        "template_version": template_version,
                        "record_hash": next_hash,
                        "source_type": source_type,
                        "source_file": source_file,
                    },
                )
                if dynamic_values:
                    self.field_value_service.set_values(int(existing["id"]), dynamic_values)
                updated += 1
                continue

            new_payload = {
                "record_id": str(uuid.uuid4()),
                **payload,
                "version": 1,
                "created_at": now,
                "updated_at": now,
            }
            new_payload["record_hash"] = self.build_record_hash(new_payload)
            new_record_id = self.record_repo.insert(new_payload)
            if dynamic_values:
                self.field_value_service.set_values(new_record_id, dynamic_values)
            inserted += 1

        message = f"保存完成：新增{inserted}，更新{updated}，跳过{skipped}"
        self.logger.info(
            "保存日报 team_id=%s date=%s source=%s result inserted=%s updated=%s skipped=%s",
            team_id,
            record_date,
            source_type,
            inserted,
            updated,
            skipped,
        )
        return True, message, {"inserted": inserted, "updated": updated, "skipped": skipped}

    def copy_yesterday_member_order(self, team_id: int, record_date: str) -> list[int]:
        prev_day = parse_date(record_date) - timedelta(days=1)
        rows = self.record_repo.list_team_day_records(team_id, prev_day.isoformat())
        return [int(item["account_manager_id"]) for item in rows]

    def query_records(
        self,
        start_date: str,
        end_date: str,
        team_id: int | None = None,
        account_manager_id: int | None = None,
    ) -> list[dict[str, Any]]:
        return self.record_repo.list_records(
            start_date=start_date,
            end_date=end_date,
            team_id=team_id,
            account_manager_id=account_manager_id,
        )

    def get_day_records(self, team_id: int, record_date: str) -> list[dict[str, Any]]:
        return self.query_records(record_date, record_date, team_id=team_id)

    def has_team_day_data(self, team_id: int, record_date: str) -> bool:
        return len(self.record_repo.list_team_day_records(team_id, record_date)) > 0

    def build_report(
        self,
        mode: str,
        base_date: str,
        team_id: int,
        custom_start: str = "",
        custom_end: str = "",
    ) -> dict[str, Any]:
        date_obj = parse_date(base_date)
        custom_start_obj = parse_date(custom_start) if custom_start else None
        custom_end_obj = parse_date(custom_end) if custom_end else None

        start_date, end_date = resolve_report_range(
            mode,
            base_date=date_obj,
            custom_start=custom_start_obj,
            custom_end=custom_end_obj,
        )

        rows = self.record_repo.list_records(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            team_id=team_id,
        )

        cross_cycle = range_crosses_cycles(start_date, end_date)
        team_target = 0.0
        if not cross_cycle:
            team_target = self._team_target(team_id, settlement_cycle_for_date(start_date).code)

        summary = self._aggregate(rows, team_target=team_target, include_progress=not cross_cycle)
        cycle_codes = canonical_cycle_codes_from_dates([str(row.get("record_date", "")) for row in rows])
        if not cycle_codes and not cross_cycle:
            cycle_codes = [settlement_cycle_for_date(start_date).code]

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "rows": rows,
            "summary": summary,
            "cross_cycle": cross_cycle,
            "cycle_codes": cycle_codes,
        }

    def list_week_options(self, record_date: str) -> list[dict[str, str]]:
        cycle = settlement_cycle_for_date(parse_date(record_date))
        from app.utils.date_utils import cycle_week_segments

        return cycle_week_segments(cycle)

    def group_by_account_manager(self, rows: list[dict[str, Any]], team_target_map: dict[int, float] | None = None) -> list[dict[str, Any]]:
        grouped: dict[int, dict[str, Any]] = {}
        for row in rows:
            manager_id = int(row.get("account_manager_id", 0) or 0)
            item = grouped.setdefault(
                manager_id,
                {
                    "group_name": row.get("account_manager_name_snapshot", ""),
                    "account_manager_id": manager_id,
                    "rows": [],
                },
            )
            item["rows"].append(row)

        result: list[dict[str, Any]] = []
        for manager_id, item in grouped.items():
            target = 0.0
            if team_target_map:
                target = float(team_target_map.get(manager_id, 0.0))
            agg = self._aggregate(item["rows"], team_target=target, include_progress=True)
            result.append({"group_name": item["group_name"], **agg})

        result.sort(key=lambda x: str(x.get("group_name", "")))
        return result

    def get_preview_rows(self, team_id: int, record_date: str) -> list[dict[str, Any]]:
        """今日展示：一人一行，包含当日值与截至当日的周期累计。"""
        day = parse_date(record_date)
        cycle = settlement_cycle_for_date(day)

        members = self.account_manager_repo.list_by_team(team_id)
        today_rows = self.record_repo.list_team_day_records(team_id, record_date)
        today_rows = self._enrich_dynamic_metric_rows(today_rows)
        today_map = {int(row.get("account_manager_id", 0) or 0): row for row in today_rows}

        cycle_rows = self.record_repo.list_records(
            start_date=cycle.start.isoformat(),
            end_date=record_date,
            team_id=team_id,
        )
        cycle_rows = self._enrich_dynamic_metric_rows(cycle_rows)
        cumulative_grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in cycle_rows:
            manager_id = int(row.get("account_manager_id", 0) or 0)
            cumulative_grouped[manager_id].append(row)

        result: list[dict[str, Any]] = []
        for member in members:
            manager_id = int(member["id"])
            manager_name = str(member.get("account_manager_name", ""))
            today_row = today_map.get(manager_id, {})
            cumulative = self._aggregate_daily_metric_totals(cumulative_grouped.get(manager_id, []))

            cycle_target = self._manager_target(team_id, manager_id, cycle.code)
            daily_visit = int(today_row.get("visit_count_daily", 0) or 0)
            daily_invalid = int(today_row.get("invalid_visit_count_daily", 0) or 0)
            daily_signing = int(today_row.get("signing_count_daily", 0) or 0)
            daily_quality = int(today_row.get("quality_visit_count_daily", 0) or 0)
            daily_approval = int(today_row.get("approval_customer_count_daily", 0) or 0)
            daily_repayment_customer = int(today_row.get("repayment_customer_count_daily", 0) or 0)
            daily_four_star = int(today_row.get("four_star_customer_count_daily", 0) or 0)
            daily_five_star = int(today_row.get("five_star_customer_count_daily", 0) or 0)

            row = {
                "team_id": int(team_id),
                "account_manager_id": manager_id,
                "record_date": record_date,
                "account_manager_name": manager_name,
                "settlement_cycle_code": settlement_cycle_display_code(record_date=record_date),
                "cycle_target": cycle_target,
                "repayment_amount_cumulative": float(cumulative.get("repayment_amount_daily", 0) or 0),
                "loan_amount_cumulative": float(cumulative.get("loan_amount_daily", 0) or 0),
                "repayment_amount_daily": float(today_row.get("repayment_amount_daily", 0) or 0),
                "loan_amount_daily": float(today_row.get("loan_amount_daily", 0) or 0),
                "intention_daily": int(today_row.get("intention_daily", 0) or 0),
                "wechat_count_daily": int(today_row.get("wechat_count_daily", 0) or 0),
                "visit_count_daily": daily_visit,
                "invitation_cumulative": int(cumulative.get("visit_count_daily", 0) or 0),
                "invalid_visit_count_daily": daily_invalid,
                "four_star_customer_count_daily": daily_four_star,
                "five_star_customer_count_daily": daily_five_star,
                "signing_count_daily": daily_signing,
                "signing_count_cumulative": int(cumulative.get("signing_count_daily", 0) or 0),
                "quality_visit_count_daily": daily_quality,
                "quality_visit_count_cumulative": int(cumulative.get("quality_visit_count_daily", 0) or 0),
                "approval_customer_count_daily": daily_approval,
                "repayment_customer_count_daily": daily_repayment_customer,
                "debt_case_submit_count_daily": int(today_row.get("debt_case_submit_count_daily", 0) or 0),
                "debt_case_repayment_count_daily": int(today_row.get("debt_case_repayment_count_daily", 0) or 0),
                "debt_case_repayment_amount_daily": float(today_row.get("debt_case_repayment_amount_daily", 0) or 0),
                "large_order_repayment_count_daily": int(today_row.get("large_order_repayment_count_daily", 0) or 0),
                "large_order_repayment_amount_daily": float(today_row.get("large_order_repayment_amount_daily", 0) or 0),
            }
            self._append_raw_daily_values(row, today_row)
            result.append(self._today_formula_values(row))

        result.sort(key=lambda x: str(x.get("account_manager_name", "")))
        return result

    def get_query_summary_grouped_by_account_manager(
        self,
        mode: str,
        base_date: str,
        team_id: int | None,
        team_ids: list[int] | None = None,
        custom_start: str = "",
        custom_end: str = "",
    ) -> dict[str, Any]:
        """查询汇总：先过滤，再按客户经理聚合，一人一行。"""
        base = parse_date(base_date)
        custom_start_obj = parse_date(custom_start) if custom_start else None
        custom_end_obj = parse_date(custom_end) if custom_end else None
        start_date, end_date = resolve_report_range(mode, base, custom_start_obj, custom_end_obj)

        explicit_team_ids: list[int] = []
        if team_ids is not None:
            explicit_team_ids = sorted({int(x) for x in team_ids if int(x) > 0})
        elif team_id and int(team_id) > 0:
            explicit_team_ids = [int(team_id)]

        if team_ids is not None and not explicit_team_ids:
            cross_cycle = range_crosses_cycles(start_date, end_date)
            cycle_code = settlement_cycle_for_date(start_date).code
            query_range = f"{start_date.isoformat()} ~ {end_date.isoformat()}"
            return {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "query_range": query_range,
                "cross_cycle": cross_cycle,
                "cycle_code": "" if cross_cycle else settlement_cycle_display_code(cycle_code=cycle_code),
                "queried_all_teams": False,
                "rows": [],
                "summary": self._build_query_summary_aggregate([], team_target=0.0, cross_cycle=cross_cycle),
            }

        single_team_filter: int | None = explicit_team_ids[0] if len(explicit_team_ids) == 1 else None
        team_ids_filter: list[int] | None = explicit_team_ids if len(explicit_team_ids) >= 2 else None
        rows = self.record_repo.list_records(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            team_id=single_team_filter,
            team_ids=team_ids_filter,
        )

        cross_cycle = range_crosses_cycles(start_date, end_date)
        cycle_code = settlement_cycle_for_date(start_date).code
        query_range = f"{start_date.isoformat()} ~ {end_date.isoformat()}"

        grouped: dict[str, dict[str, Any]] = {}
        for prefill_team_id in explicit_team_ids:
            team = self.team_repo.get_by_id(prefill_team_id) or {}
            team_name = str(team.get("team_name", ""))
            members = self.account_manager_repo.list_by_team(prefill_team_id)
            for member in members:
                manager_id = int(member.get("id", 0) or 0)
                manager_name = str(member.get("account_manager_name", "")).strip()
                key = f"team:{prefill_team_id}|id:{manager_id}"
                grouped[key] = {
                    "team_id": prefill_team_id,
                    "team_name": team_name,
                    "account_manager_id": manager_id,
                    "account_manager_name": manager_name,
                    "rows": [],
                }

        for row in rows:
            manager_id = int(row.get("account_manager_id", 0) or 0)
            team_id_in_row = int(row.get("team_id", 0) or 0)
            manager_name = str(row.get("account_manager_name_snapshot", "")).strip()
            team_name = str(row.get("team_name_snapshot", "")).strip()
            key = f"team:{team_id_in_row}|id:{manager_id}" if manager_id != 0 else f"team:{team_id_in_row}|name:{manager_name}"
            bucket = grouped.setdefault(
                key,
                {
                    "team_id": team_id_in_row,
                    "team_name": team_name,
                    "account_manager_id": manager_id,
                    "account_manager_name": manager_name,
                    "rows": [],
                },
            )
            bucket["rows"].append(row)

        result_rows: list[dict[str, Any]] = []
        summary_source_rows: list[dict[str, Any]] = []

        for item in grouped.values():
            manager_id = int(item.get("account_manager_id", 0) or 0)
            manager_name = str(item.get("account_manager_name", ""))
            manager_team_id = int(item.get("team_id", 0) or 0)
            manager_team_name = str(item.get("team_name", ""))
            manager_rows = item.get("rows", [])
            totals = self._aggregate_daily_metric_totals(manager_rows)

            visit = int(totals.get("visit_count_daily", 0) or 0)
            invalid_visit = int(totals.get("invalid_visit_count_daily", 0) or 0)
            signing = int(totals.get("signing_count_daily", 0) or 0)
            quality_visit = int(totals.get("quality_visit_count_daily", 0) or 0)
            approval = int(totals.get("approval_customer_count_daily", 0) or 0)
            repayment_customer = int(totals.get("repayment_customer_count_daily", 0) or 0)
            four_star_customer = int(totals.get("four_star_customer_count_daily", 0) or 0)
            five_star_customer = int(totals.get("five_star_customer_count_daily", 0) or 0)

            cycle_target = None
            if not cross_cycle and manager_id > 0 and manager_team_id > 0:
                cycle_target = self._manager_target(manager_team_id, manager_id, cycle_code)
            repayment_amount = float(totals.get("repayment_amount_daily", 0) or 0)
            loan_amount = float(totals.get("loan_amount_daily", 0) or 0)

            display_name = manager_name
            if len(explicit_team_ids) != 1 and manager_team_name:
                display_name = f"{manager_team_name} / {manager_name}"

            row = {
                "query_range": query_range,
                "team_id": manager_team_id,
                "team_name": manager_team_name,
                "account_manager_id": manager_id,
                "account_manager_name": display_name,
                "settlement_cycle_code": "" if cross_cycle else settlement_cycle_display_code(cycle_code=cycle_code),
                "cycle_target": cycle_target,
                "cycle_repayment_target": cycle_target,
                "repayment_amount_cumulative": repayment_amount,
                "loan_amount_cumulative": loan_amount,
                "repayment_amount": repayment_amount,
                "loan_amount": loan_amount,
                "intention": int(totals.get("intention_daily", 0) or 0),
                "wechat_count": int(totals.get("wechat_count_daily", 0) or 0),
                "visit_count": visit,
                "invitation_cumulative": visit,
                "invalid_visit_count": invalid_visit,
                "four_star_customer_count": four_star_customer,
                "five_star_customer_count": five_star_customer,
                "signing_count": signing,
                "signing_count_cumulative": signing,
                "quality_visit_count": quality_visit,
                "quality_visit_count_cumulative": quality_visit,
                "approval_customer_count": approval,
                "repayment_customer_count": repayment_customer,
                "debt_case_submit_count": int(totals.get("debt_case_submit_count_daily", 0) or 0),
                "debt_case_repayment_count": int(totals.get("debt_case_repayment_count_daily", 0) or 0),
                "debt_case_repayment_amount": float(totals.get("debt_case_repayment_amount_daily", 0) or 0),
                "large_order_repayment_count": int(totals.get("large_order_repayment_count_daily", 0) or 0),
                "large_order_repayment_amount": float(totals.get("large_order_repayment_amount_daily", 0) or 0),
            }
            for field_key, value in totals.items():
                if field_key not in row:
                    row[field_key] = value
            row = self._query_formula_values(row, cross_cycle)
            result_rows.append(row)
            summary_source_rows.extend(manager_rows)

        result_rows.sort(key=lambda x: str(x.get("account_manager_name", "")))

        total_target = 0.0
        if not cross_cycle:
            if len(explicit_team_ids) == 1:
                total_target = self._team_target(explicit_team_ids[0], cycle_code)
            elif explicit_team_ids:
                total_target = sum(self._team_target(tid, cycle_code) for tid in explicit_team_ids)
            else:
                team_ids = {int(row.get("team_id", 0) or 0) for row in rows if int(row.get("team_id", 0) or 0) > 0}
                total_target = sum(self._team_target(tid, cycle_code) for tid in team_ids)
        summary = self._build_query_summary_aggregate(
            summary_source_rows,
            team_target=total_target,
            cross_cycle=cross_cycle,
        )

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "query_range": query_range,
            "cross_cycle": cross_cycle,
            "cycle_code": "" if cross_cycle else settlement_cycle_display_code(cycle_code=cycle_code),
            "queried_all_teams": not explicit_team_ids,
            "rows": result_rows,
            "summary": summary,
        }
