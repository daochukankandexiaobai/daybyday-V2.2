from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any

from app.config.field_profiles import PROFILE_ANALYSIS_METRICS, get_profile_field_keys
from app.config.field_registry import DATA_TYPE_AMOUNT, get_field_spec
from app.config.field_rules import supports_chart
from app.utils.date_utils import parse_date
from app.utils.metrics_utils import ratio_or_none


class AnalyticsService:
    """查询汇总分析服务：复用既有查询口径，输出分析数据。"""

    TREND_CHART_KEY = "trend"

    def __init__(self, record_service) -> None:
        self.record_service = record_service

    @staticmethod
    def _normalize_team_ids(team_ids: list[int] | None) -> list[int]:
        if not team_ids:
            return []
        return sorted({int(item) for item in team_ids if int(item) > 0})

    @classmethod
    def trend_metric_keys(cls) -> tuple[str, ...]:
        return tuple(
            key
            for key in get_profile_field_keys(PROFILE_ANALYSIS_METRICS)
            if supports_chart(key, cls.TREND_CHART_KEY)
        )

    @staticmethod
    def _trend_default_value(field_key: str) -> float | int:
        spec = get_field_spec(field_key)
        return 0.0 if spec.data_type == DATA_TYPE_AMOUNT else 0

    @classmethod
    def _empty_trend_point(cls, date_key: str) -> dict[str, Any]:
        point: dict[str, Any] = {"date": date_key}
        for field_key in cls.trend_metric_keys():
            point[field_key] = cls._trend_default_value(field_key)
        return point

    def get_summary_kpis(self, query_result: dict[str, Any]) -> dict[str, Any]:
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
        team_ids: list[int] | None,
    ) -> list[dict[str, Any]]:
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

        bucket: dict[str, dict[str, Any]] = {}
        day = parse_date(start_date)
        day_end = parse_date(end_date)
        while day <= day_end:
            date_key = day.isoformat()
            bucket[date_key] = self._empty_trend_point(date_key)
            day += timedelta(days=1)

        for row in rows:
            date_key = str(row.get("record_date", "")).strip()
            if not date_key:
                continue
            item = bucket.setdefault(
                date_key,
                self._empty_trend_point(date_key),
            )
            item["repayment_amount_daily"] += float(row.get("repayment_amount_daily", 0) or 0)
            item["loan_amount_daily"] += float(row.get("loan_amount_daily", 0) or 0)
            item["visit_count_daily"] += int(row.get("visit_count_daily", 0) or 0)
            item["signing_count_daily"] += int(row.get("signing_count_daily", 0) or 0)
            item["repayment_customer_count_daily"] += int(row.get("repayment_customer_count_daily", 0) or 0)
            item["four_star_customer_count_daily"] += int(row.get("four_star_customer_count_daily", 0) or 0)
            item["five_star_customer_count_daily"] += int(row.get("five_star_customer_count_daily", 0) or 0)

            # 兼容旧的趋势 metric_key，避免外部仍传旧 key 时取不到值。
            item["repayment_amount"] = item["repayment_amount_daily"]
            item["loan_amount"] = item["loan_amount_daily"]
            item["visit_count"] = item["visit_count_daily"]
            item["signing_count"] = item["signing_count_daily"]
            item["repayment_customer_count"] = item["repayment_customer_count_daily"]

        return [bucket[key] for key in sorted(bucket.keys())]

    def get_ranking_by_account_manager(
        self,
        query_rows: list[dict[str, Any]],
        metric_key: str,
        top_n: int = 10,
    ) -> list[dict[str, Any]]:
        metric_map = {
            "repayment_amount": ("repayment_amount", False),
            "signing_count": ("signing_count", False),
            "visit_count": ("visit_count", False),
            "quality_visit_count": ("quality_visit_count", False),
            "sales_conversion_rate": ("sales_conversion_rate", True),
            "warrant_conversion_rate": ("warrant_conversion_rate", True),
        }
        field, is_rate = metric_map.get(metric_key, ("repayment_amount", False))

        rows: list[dict[str, Any]] = []
        for row in query_rows:
            value = row.get(field)
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

    def get_funnel_metrics(self, query_rows: list[dict[str, Any]]) -> dict[str, Any]:
        visit_count = sum(int(row.get("visit_count", 0) or 0) for row in query_rows)
        invalid_visit_count = sum(int(row.get("invalid_visit_count", 0) or 0) for row in query_rows)
        signing_count = sum(int(row.get("signing_count", 0) or 0) for row in query_rows)
        repayment_customer_count = sum(int(row.get("repayment_customer_count", 0) or 0) for row in query_rows)

        valid_visit_count = max(visit_count - invalid_visit_count, 0)

        signing_rate = ratio_or_none(signing_count, valid_visit_count)
        sales_conversion_rate = ratio_or_none(signing_count, visit_count)
        warrant_conversion_rate = ratio_or_none(repayment_customer_count, signing_count)

        return {
            "visit_count": visit_count,
            "valid_visit_count": valid_visit_count,
            "signing_count": signing_count,
            "repayment_customer_count": repayment_customer_count,
            "signing_rate": signing_rate,
            "sales_conversion_rate": sales_conversion_rate,
            "warrant_conversion_rate": warrant_conversion_rate,
        }

    def get_summary_by_team(self, query_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = defaultdict(
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

        result: list[dict[str, Any]] = []
        for item in grouped.values():
            visit = int(item["visit_count"])
            invalid = int(item["invalid_visit_count"])
            signing = int(item["signing_count"])
            quality = int(item["quality_visit_count"])
            repayment_customer = int(item["repayment_customer_count"])
            result.append(
                {
                    **item,
                    "signing_rate": ratio_or_none(signing, visit - invalid),
                    "quality_visit_rate": ratio_or_none(quality, visit),
                    "sales_conversion_rate": ratio_or_none(signing, visit),
                    "warrant_conversion_rate": ratio_or_none(repayment_customer, signing),
                }
            )

        result.sort(key=lambda row: str(row.get("team_name", "")))
        return result

    def build_analysis_bundle(
        self,
        mode: str,
        base_date: str,
        team_ids: list[int] | None,
        custom_start: str = "",
        custom_end: str = "",
        ranking_metric: str = "repayment_amount",
        top_n: int = 10,
        query_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
