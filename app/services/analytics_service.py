from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from app.config.field_registry import DATA_TYPE_AMOUNT, DATA_TYPE_PERCENT, STORAGE_DYNAMIC_METRIC
from app.fields.aggregation_service import (
    AGGREGATION_DERIVED,
    AGGREGATION_FORMULA,
    AGGREGATION_NONE,
    AGGREGATION_SUM,
    AggregationService,
    normalize_aggregation,
)
from app.fields.analysis_config_service import (
    ANALYSIS_TYPE_RANKING,
    ANALYSIS_TYPE_TREND,
    AnalysisConfigService,
)
from app.fields.formula_service import FormulaService
from app.utils.date_utils import parse_date
from app.utils.metrics_utils import ratio_or_none


DAILY_FORMULA_DEPENDENCY_KEYS: Tuple[str, ...] = (
    "repayment_amount_daily",
    "loan_amount_daily",
    "visit_count_daily",
    "invalid_visit_count_daily",
    "signing_count_daily",
    "quality_visit_count_daily",
    "approval_customer_count_daily",
    "repayment_customer_count_daily",
    "four_star_customer_count_daily",
    "five_star_customer_count_daily",
)

TREND_COMPAT_ALIASES = {
    "repayment_amount": "repayment_amount_daily",
    "loan_amount": "loan_amount_daily",
    "visit_count": "visit_count_daily",
    "invalid_visit_count": "invalid_visit_count_daily",
    "signing_count": "signing_count_daily",
    "quality_visit_count": "quality_visit_count_daily",
    "approval_customer_count": "approval_customer_count_daily",
    "repayment_customer_count": "repayment_customer_count_daily",
    "four_star_customer_count": "four_star_customer_count_daily",
    "five_star_customer_count": "five_star_customer_count_daily",
}


class AnalyticsService:
    """查询汇总分析服务。

    Data-analysis metric choices are now read from field configuration. Formula
    metrics still follow the established rule: aggregate raw numerators and
    denominators first, then calculate the formula.
    """

    TREND_CHART_KEY = ANALYSIS_TYPE_TREND

    def __init__(self, record_service) -> None:
        self.record_service = record_service
        self.db_manager = getattr(getattr(record_service, "record_repo", None), "db", None)
        self.field_value_service = getattr(record_service, "field_value_service", None)
        self.formula_service = FormulaService()
        self.aggregation_service = AggregationService(self.formula_service)
        self.analysis_config_service = AnalysisConfigService(self.db_manager)

    @staticmethod
    def _normalize_team_ids(team_ids: Optional[List[int]]) -> List[int]:
        if not team_ids:
            return []
        return sorted({int(item) for item in team_ids if int(item) > 0})

    def trend_metric_keys(self) -> Tuple[str, ...]:
        return tuple(
            str(row.get("field_key", ""))
            for row in self.analysis_config_service.get_fields_for_analysis_type(ANALYSIS_TYPE_TREND)
            if str(row.get("field_key", "")).strip()
        )

    def get_analysis_metric_options(self, analysis_type: str) -> List[Tuple[str, str]]:
        return self.analysis_config_service.get_metric_options(analysis_type)

    def get_metric_label(self, field_key: str) -> str:
        return self.analysis_config_service.label_for_field(field_key)

    def is_percent_metric(self, field_key: str) -> bool:
        return self.analysis_config_service.is_percent_field(field_key)

    @staticmethod
    def _trend_default_value(field_def: Mapping[str, Any]) -> Any:
        data_type = str(field_def.get("data_type", ""))
        return 0.0 if data_type in {DATA_TYPE_AMOUNT, DATA_TYPE_PERCENT, "money", "decimal"} else 0

    def _empty_trend_point(self, date_key: str, field_defs: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        point: Dict[str, Any] = {"date": date_key}
        for field_def in field_defs:
            field_key = str(field_def.get("field_key", ""))
            if field_key:
                point[field_key] = self._trend_default_value(field_def)
        self._apply_trend_compat_aliases(point)
        return point

    def get_summary_kpis(self, query_result: Dict[str, Any]) -> Dict[str, Any]:
        rows = query_result.get("rows", []) or []
        summary = query_result.get("summary", {}) or {}
        cross_cycle = bool(query_result.get("cross_cycle"))

        repayment_amount_total = float(summary.get("repayment_amount_cumulative", 0) or 0)
        loan_amount_total = float(summary.get("loan_amount_cumulative", 0) or 0)
        visit_total = int(summary.get("invitation_cumulative", 0) or 0)
        signing_total = int(summary.get("signing_count_cumulative", 0) or 0)
        quality_visit_total = int(summary.get("quality_visit_count_cumulative", 0) or 0)

        invalid_visit_total = sum(int(row.get("invalid_visit_count", 0) or 0) for row in rows)
        repayment_customer_total = sum(int(row.get("repayment_customer_count", 0) or 0) for row in rows)

        signing_rate = ratio_or_none(signing_total, visit_total - invalid_visit_total)
        quality_visit_rate = ratio_or_none(quality_visit_total, visit_total)
        sales_conversion_rate = ratio_or_none(signing_total, visit_total)
        warrant_conversion_rate = ratio_or_none(repayment_customer_total, signing_total)

        return {
            "repayment_amount_total": repayment_amount_total,
            "loan_amount_total": loan_amount_total,
            "visit_total": visit_total,
            "signing_total": signing_total,
            "repayment_customer_total": repayment_customer_total,
            "signing_rate": signing_rate,
            "quality_visit_rate": quality_visit_rate,
            "sales_conversion_rate": sales_conversion_rate,
            "warrant_conversion_rate": warrant_conversion_rate,
            "target_progress": None if cross_cycle else summary.get("target_progress"),
            "cross_cycle": cross_cycle,
        }

    def get_trend_by_day(
        self,
        start_date: str,
        end_date: str,
        team_ids: Optional[List[int]],
    ) -> List[Dict[str, Any]]:
        team_ids_normalized = self._normalize_team_ids(team_ids)
        if not team_ids_normalized:
            return []

        single_team_id = team_ids_normalized[0] if len(team_ids_normalized) == 1 else None
        multi_team_ids = team_ids_normalized if len(team_ids_normalized) > 1 else None
        rows = self.record_service.record_repo.list_records(
            start_date=start_date,
            end_date=end_date,
            team_id=single_team_id,
            team_ids=multi_team_ids,
        )

        field_defs = self.analysis_config_service.get_fields_for_analysis_type(ANALYSIS_TYPE_TREND)
        rows = self._enrich_rows_with_dynamic_values(rows, field_defs)

        rows_by_date: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            date_key = str(row.get("record_date", "")).strip()
            if date_key:
                rows_by_date[date_key].append(row)

        bucket: Dict[str, Dict[str, Any]] = {}
        day = parse_date(start_date)
        day_end = parse_date(end_date)
        while day <= day_end:
            date_key = day.isoformat()
            bucket[date_key] = self._empty_trend_point(date_key, field_defs)
            day += timedelta(days=1)

        for date_key, day_rows in rows_by_date.items():
            item = bucket.setdefault(date_key, self._empty_trend_point(date_key, field_defs))
            totals = self._aggregate_daily_totals(day_rows, field_defs)
            for field_def in field_defs:
                field_key = str(field_def.get("field_key", ""))
                if not field_key:
                    continue
                if self._is_formula_field(field_def):
                    item[field_key] = self._calculate_formula_field(field_def, totals)
                    continue

                aggregation = normalize_aggregation(str(field_def.get("aggregation") or AGGREGATION_SUM))
                value = self.aggregation_service.aggregate_field(day_rows, field_key, aggregation)
                item[field_key] = value if value is not None else self._trend_default_value(field_def)
            self._apply_trend_compat_aliases(item)

        return [bucket[key] for key in sorted(bucket.keys())]

    def get_ranking_by_account_manager(
        self,
        query_rows: List[Dict[str, Any]],
        metric_key: str,
        top_n: int = 10,
    ) -> List[Dict[str, Any]]:
        metric_field = self.analysis_config_service.summary_key_for_metric(metric_key)
        metric_def = self.analysis_config_service.row_for_field(metric_field)
        is_rate = self.is_percent_metric(metric_field)

        rows: List[Dict[str, Any]] = []
        for row in query_rows:
            value = row.get(metric_field)
            if value is None and self._is_formula_field(metric_def):
                value = self._calculate_formula_field(metric_def, row)
            if is_rate and value is None:
                continue
            rows.append(
                {
                    "account_manager_name": str(row.get("account_manager_name", "")),
                    "team_name": str(row.get("team_name", "")),
                    "value": float(value or 0),
                }
            )

        rows.sort(key=lambda item: (item["value"], item["account_manager_name"]), reverse=True)
        limit = max(1, int(top_n))
        return rows[:limit]

    def get_funnel_metrics(self, query_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        visit_count = sum(int(row.get("visit_count", 0) or 0) for row in query_rows)
        invalid_visit_count = sum(int(row.get("invalid_visit_count", 0) or 0) for row in query_rows)
        signing_count = sum(int(row.get("signing_count", 0) or 0) for row in query_rows)
        repayment_customer_count = sum(int(row.get("repayment_customer_count", 0) or 0) for row in query_rows)

        valid_visit_count = max(visit_count - invalid_visit_count, 0)
        values = {
            "visit_count": visit_count,
            "invalid_visit_count": invalid_visit_count,
            "signing_count": signing_count,
            "repayment_customer_count": repayment_customer_count,
        }

        signing_rate = self.formula_service.calculate("signing_rate", values)
        sales_conversion_rate = self.formula_service.calculate("sales_conversion_rate", values)
        warrant_conversion_rate = self.formula_service.calculate("warrant_conversion_rate", values)

        return {
            "visit_count": visit_count,
            "valid_visit_count": valid_visit_count,
            "signing_count": signing_count,
            "repayment_customer_count": repayment_customer_count,
            "signing_rate": signing_rate,
            "sales_conversion_rate": sales_conversion_rate,
            "warrant_conversion_rate": warrant_conversion_rate,
        }

    def get_summary_by_team(self, query_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "team_name": "",
                "repayment_amount": 0.0,
                "loan_amount": 0.0,
                "visit_count": 0,
                "invalid_visit_count": 0,
                "signing_count": 0,
                "quality_visit_count": 0,
                "repayment_customer_count": 0,
            }
        )

        for row in query_rows:
            team_name = str(row.get("team_name", "")).strip() or "未归属团队"
            item = grouped[team_name]
            item["team_name"] = team_name
            item["repayment_amount"] += float(row.get("repayment_amount", 0) or 0)
            item["loan_amount"] += float(row.get("loan_amount", 0) or 0)
            item["visit_count"] += int(row.get("visit_count", 0) or 0)
            item["invalid_visit_count"] += int(row.get("invalid_visit_count", 0) or 0)
            item["signing_count"] += int(row.get("signing_count", 0) or 0)
            item["quality_visit_count"] += int(row.get("quality_visit_count", 0) or 0)
            item["repayment_customer_count"] += int(row.get("repayment_customer_count", 0) or 0)

        result: List[Dict[str, Any]] = []
        for item in grouped.values():
            formulas = {
                "signing_rate": self.formula_service.calculate("signing_rate", item),
                "quality_visit_rate": self.formula_service.calculate("quality_visit_rate", item),
                "sales_conversion_rate": self.formula_service.calculate("sales_conversion_rate", item),
                "warrant_conversion_rate": self.formula_service.calculate("warrant_conversion_rate", item),
            }
            result.append({**item, **formulas})

        result.sort(key=lambda row: str(row.get("team_name", "")))
        return result

    def build_analysis_bundle(
        self,
        mode: str,
        base_date: str,
        team_ids: Optional[List[int]],
        custom_start: str = "",
        custom_end: str = "",
        ranking_metric: str = "repayment_amount",
        top_n: int = 10,
        query_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = query_result or self.record_service.get_query_summary_grouped_by_account_manager(
            mode=mode,
            base_date=base_date,
            team_id=None,
            team_ids=team_ids,
            custom_start=custom_start,
            custom_end=custom_end,
        )
        rows = context.get("rows", []) or []
        normalized_team_ids = self._normalize_team_ids(team_ids)

        return {
            "query_result": context,
            "kpis": self.get_summary_kpis(context),
            "trend": self.get_trend_by_day(
                start_date=str(context.get("start_date", "")),
                end_date=str(context.get("end_date", "")),
                team_ids=normalized_team_ids,
            ),
            "ranking": self.get_ranking_by_account_manager(
                query_rows=rows,
                metric_key=ranking_metric,
                top_n=top_n,
            ),
            "funnel": self.get_funnel_metrics(rows),
            "summary_by_team": self.get_summary_by_team(rows),
        }

    def _enrich_rows_with_dynamic_values(
        self,
        rows: Iterable[Dict[str, Any]],
        field_defs: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        dynamic_keys = [
            str(field_def.get("field_key", ""))
            for field_def in field_defs
            if str(field_def.get("storage_type", "")) == STORAGE_DYNAMIC_METRIC
            and str(field_def.get("field_key", "")).strip()
        ]
        if not dynamic_keys or self.field_value_service is None:
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

    def _aggregate_daily_totals(
        self,
        rows: Iterable[Mapping[str, Any]],
        field_defs: Iterable[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        row_list = list(rows)
        keys = set(DAILY_FORMULA_DEPENDENCY_KEYS)
        for field_def in field_defs:
            field_key = str(field_def.get("field_key", ""))
            if field_key.endswith("_daily"):
                keys.add(field_key)

        totals: Dict[str, Any] = {}
        for field_key in sorted(keys):
            totals[field_key] = self.aggregation_service.aggregate_field(row_list, field_key, AGGREGATION_SUM) or 0

        self._apply_trend_compat_aliases(totals)
        totals["invitation_cumulative"] = totals.get("visit_count", 0)
        totals["signing_count_cumulative"] = totals.get("signing_count", 0)
        totals["quality_visit_count_cumulative"] = totals.get("quality_visit_count", 0)
        totals["approval_customer_count_cumulative"] = totals.get("approval_customer_count", 0)
        totals["repayment_customer_count_cumulative"] = totals.get("repayment_customer_count", 0)
        totals["repayment_amount_cumulative"] = totals.get("repayment_amount", 0)
        totals["loan_amount_cumulative"] = totals.get("loan_amount", 0)
        return totals

    def _calculate_formula_field(self, field_def: Mapping[str, Any], values: Mapping[str, Any]) -> Optional[float]:
        field_key = str(field_def.get("field_key", ""))
        formula_id = str(field_def.get("formula_id") or field_key)
        if not self.formula_service.is_formula_known(formula_id):
            return None
        return self.formula_service.calculate(formula_id, dict(values))

    @staticmethod
    def _is_formula_field(field_def: Mapping[str, Any]) -> bool:
        aggregation = normalize_aggregation(str(field_def.get("aggregation") or AGGREGATION_NONE))
        data_type = str(field_def.get("data_type", ""))
        return aggregation in {AGGREGATION_FORMULA, AGGREGATION_DERIVED} or data_type == DATA_TYPE_PERCENT

    @staticmethod
    def _apply_trend_compat_aliases(values: Dict[str, Any]) -> None:
        for alias_key, source_key in TREND_COMPAT_ALIASES.items():
            if source_key in values:
                values[alias_key] = values.get(source_key)
