from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.utils.date_utils import parse_date
from app.utils.validators import safe_int


class StarCustomerAlertService:
    FOUR_STAR_FIELD = "four_star_customer_count_daily"
    FIVE_STAR_FIELD = "five_star_customer_count_daily"

    def __init__(self, record_repo, account_manager_repo=None, team_repo=None) -> None:
        self.record_repo = record_repo
        self.account_manager_repo = account_manager_repo
        self.team_repo = team_repo

    @staticmethod
    def is_workday(target_date: Any) -> bool:
        day = parse_date(target_date) if isinstance(target_date, str) else target_date
        return day.weekday() < 5

    def get_previous_workdays(self, end_date: str, count: int = 3) -> list[str]:
        remaining = max(1, int(count or 1))
        current = parse_date(str(end_date or "").strip())
        result: list[str] = []
        while len(result) < remaining:
            if self.is_workday(current):
                result.append(current.isoformat())
            current = current - timedelta(days=1)
        return result

    def get_star_values_for_workdays(
        self,
        team_id: int,
        account_manager_id: int,
        dates: list[str],
    ) -> dict[str, Any]:
        normalized_dates = [str(item or "").strip() for item in dates if str(item or "").strip()]
        records = self.record_repo.list_manager_records_by_dates(
            team_id=int(team_id or 0),
            account_manager_id=int(account_manager_id or 0),
            dates=normalized_dates,
        )
        record_map = {str(row.get("record_date", "")): row for row in records}
        four_values: list[int] = []
        five_values: list[int] = []
        has_record: list[bool] = []
        for item_date in normalized_dates:
            row = record_map.get(item_date)
            has_record.append(row is not None)
            four_values.append(safe_int(row.get(self.FOUR_STAR_FIELD) if row is not None else 0))
            five_values.append(safe_int(row.get(self.FIVE_STAR_FIELD) if row is not None else 0))
        return {
            "checked_dates": normalized_dates,
            "four_star_values": four_values,
            "five_star_values": five_values,
            "has_record": has_record,
        }

    def get_star_alert_status_for_date(
        self,
        team_id: int,
        account_manager_id: int,
        record_date: str,
        threshold: int = 2,
        streak_days: int = 3,
    ) -> dict[str, Any]:
        checked_dates = self.get_previous_workdays(record_date, streak_days)
        values = self.get_star_values_for_workdays(
            team_id=team_id,
            account_manager_id=account_manager_id,
            dates=checked_dates,
        )
        four_values = list(values.get("four_star_values", []))
        five_values = list(values.get("five_star_values", []))
        normalized_threshold = int(threshold or 0)
        normalized_streak_days = int(streak_days or 0)

        return {
            "team_id": int(team_id or 0),
            "account_manager_id": int(account_manager_id or 0),
            "as_of_date": str(record_date or "").strip(),
            "checked_dates": checked_dates,
            "recent_dates": checked_dates,
            "threshold": normalized_threshold,
            "streak_days": normalized_streak_days,
            "workday_rule": "skip_weekends_missing_workdays_as_zero",
            "has_record": values.get("has_record", []),
            "four_star_values": four_values,
            "five_star_values": five_values,
            "four_star_alert": bool(len(four_values) >= normalized_streak_days and all(value < normalized_threshold for value in four_values)),
            "five_star_alert": bool(len(five_values) >= normalized_streak_days and all(value < normalized_threshold for value in five_values)),
        }

    def get_star_alert_status_for_range(
        self,
        team_id: int,
        account_manager_id: int,
        start_date: str,
        end_date: str,
        threshold: int = 2,
        streak_days: int = 3,
    ) -> dict[str, Any]:
        scan_dates = self._workdays_between(start_date, end_date)
        if not scan_dates:
            scan_dates = [str(end_date or "").strip()]

        daily_statuses: list[dict[str, Any]] = []
        four_alert_dates: list[str] = []
        five_alert_dates: list[str] = []
        for item_date in scan_dates:
            status = self.get_star_alert_status_for_date(
                team_id=team_id,
                account_manager_id=account_manager_id,
                record_date=item_date,
                threshold=threshold,
                streak_days=streak_days,
            )
            daily_statuses.append(status)
            if status.get("four_star_alert"):
                four_alert_dates.append(item_date)
            if status.get("five_star_alert"):
                five_alert_dates.append(item_date)

        latest_status = daily_statuses[-1] if daily_statuses else {}
        return {
            "team_id": int(team_id or 0),
            "account_manager_id": int(account_manager_id or 0),
            "start_date": str(start_date or "").strip(),
            "end_date": str(end_date or "").strip(),
            "scan_dates": scan_dates,
            "checked_dates": latest_status.get("checked_dates", []),
            "recent_dates": latest_status.get("checked_dates", []),
            "threshold": int(threshold or 0),
            "streak_days": int(streak_days or 0),
            "workday_rule": "skip_weekends_missing_workdays_as_zero",
            "four_star_values": latest_status.get("four_star_values", []),
            "five_star_values": latest_status.get("five_star_values", []),
            "four_star_alert": bool(four_alert_dates),
            "five_star_alert": bool(five_alert_dates),
            "four_star_alert_dates": four_alert_dates,
            "five_star_alert_dates": five_alert_dates,
            "daily_statuses": daily_statuses,
        }

    def is_four_star_low_streak(
        self,
        team_id: int,
        account_manager_id: int,
        end_date: str,
        threshold: int = 2,
        streak_days: int = 3,
    ) -> bool:
        return bool(
            self.get_star_alert_status_for_date(
                team_id=team_id,
                account_manager_id=account_manager_id,
                record_date=end_date,
                threshold=threshold,
                streak_days=streak_days,
            ).get("four_star_alert")
        )

    def is_five_star_low_streak(
        self,
        team_id: int,
        account_manager_id: int,
        end_date: str,
        threshold: int = 2,
        streak_days: int = 3,
    ) -> bool:
        return bool(
            self.get_star_alert_status_for_date(
                team_id=team_id,
                account_manager_id=account_manager_id,
                record_date=end_date,
                threshold=threshold,
                streak_days=streak_days,
            ).get("five_star_alert")
        )

    def get_recent_recorded_dates_for_manager(
        self,
        team_id: int,
        account_manager_id: int,
        end_date: str,
        limit: int = 3,
    ) -> list[str]:
        return self.get_previous_workdays(end_date, limit)

    def get_star_alert_summary_for_range(
        self,
        start_date: str,
        end_date: str,
        team_id: int | None = None,
        team_ids: list[int] | None = None,
        threshold: int = 2,
        streak_days: int = 3,
    ) -> dict[str, Any]:
        normalized_start = str(start_date or "").strip()
        normalized_end = str(end_date or "").strip()
        normalized_team_ids = self._resolve_team_ids(
            start_date=normalized_start,
            end_date=normalized_end,
            team_id=team_id,
            team_ids=team_ids,
        )

        details: list[dict[str, Any]] = []
        four_alert_count = 0
        five_alert_count = 0
        checked_manager_count = 0

        for current_team_id in normalized_team_ids:
            manager_ids = self._resolve_manager_ids_for_team(
                team_id=current_team_id,
                start_date=normalized_start,
                end_date=normalized_end,
            )
            for manager_id in manager_ids:
                status = self.get_star_alert_status_for_range(
                    team_id=current_team_id,
                    account_manager_id=manager_id,
                    start_date=normalized_start,
                    end_date=normalized_end,
                    threshold=threshold,
                    streak_days=streak_days,
                )
                checked_manager_count += 1
                if status["four_star_alert"]:
                    four_alert_count += 1
                if status["five_star_alert"]:
                    five_alert_count += 1
                details.append(status)

        return {
            "start_date": normalized_start,
            "end_date": normalized_end,
            "team_ids": normalized_team_ids,
            "threshold": int(threshold or 0),
            "streak_days": int(streak_days or 0),
            "workday_rule": "skip_weekends_missing_workdays_as_zero",
            "checked_manager_count": checked_manager_count,
            "four_star_alert_count": four_alert_count,
            "five_star_alert_count": five_alert_count,
            "details": details,
        }

    def _workdays_between(self, start_date: str, end_date: str) -> list[str]:
        start = parse_date(str(start_date or "").strip())
        end = parse_date(str(end_date or "").strip())
        if start > end:
            return []
        result: list[str] = []
        current = start
        while current <= end:
            if self.is_workday(current):
                result.append(current.isoformat())
            current = current + timedelta(days=1)
        return result

    def _resolve_team_ids(
        self,
        start_date: str,
        end_date: str,
        team_id: int | None,
        team_ids: list[int] | None,
    ) -> list[int]:
        if team_ids is not None:
            return sorted({int(item) for item in team_ids if int(item or 0) > 0})
        if team_id is not None and int(team_id or 0) > 0:
            return [int(team_id)]
        return self.record_repo.list_team_ids_with_records(start_date, end_date)

    def _resolve_manager_ids_for_team(self, team_id: int, start_date: str, end_date: str) -> list[int]:
        manager_ids: set[int] = set()
        if self.account_manager_repo is not None:
            members = self.account_manager_repo.list_by_team(team_id, include_inactive=False)
            manager_ids.update(int(item["id"]) for item in members)
        manager_ids.update(self.record_repo.list_team_manager_ids_with_records(team_id, start_date, end_date))
        return sorted(manager_ids)
