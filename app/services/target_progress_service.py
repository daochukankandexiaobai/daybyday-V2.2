from __future__ import annotations

from typing import Any

from app.utils.date_utils import parse_date
from app.utils.validators import safe_decimal


class TargetProgressService:
    STATUS_NO_TARGET = "no_target"
    STATUS_LAGGING = "lagging"
    STATUS_WARNING = "warning"
    STATUS_OK = "ok"
    STATUS_EXCELLENT = "excellent"

    STATUS_LABELS = {
        STATUS_NO_TARGET: "未设置目标",
        STATUS_LAGGING: "落后",
        STATUS_WARNING: "预警",
        STATUS_OK: "达标",
        STATUS_EXCELLENT: "超常",
    }

    def calc_time_progress(self, week_start_date: str, week_end_date: str, current_date: str) -> float:
        week_start = parse_date(str(week_start_date or "").strip())
        week_end = parse_date(str(week_end_date or "").strip())
        current = parse_date(str(current_date or "").strip())
        if week_end < week_start:
            raise ValueError("week_end_date 不能早于 week_start_date")

        total_days = (week_end - week_start).days + 1
        if current < week_start:
            return 0.0
        if current > week_end:
            return 1.0
        elapsed_days = (current - week_start).days + 1
        return round(elapsed_days / total_days, 4)

    def calc_daily_target_status(
        self,
        actual_to_date: float,
        week_target: float,
        week_start_date: str,
        week_end_date: str,
        current_date: str,
    ) -> dict[str, Any]:
        actual = safe_decimal(actual_to_date)
        target = safe_decimal(week_target)
        time_progress = self.calc_time_progress(week_start_date, week_end_date, current_date)
        if target <= 0:
            return self._no_target_result(actual, target, time_progress=time_progress)

        completion_rate = actual / target
        progress_ratio = completion_rate / time_progress if time_progress > 0 else None
        status_code = self._status_for_rate(progress_ratio if progress_ratio is not None else completion_rate)
        return self._result(
            actual=actual,
            target=target,
            completion_rate=completion_rate,
            status_rate=progress_ratio,
            status_code=status_code,
            time_progress=time_progress,
            progress_ratio=progress_ratio,
        )

    def calc_week_target_status(self, actual: float, week_target: float) -> dict[str, Any]:
        return self._calc_simple_status(actual, week_target)

    def calc_cycle_target_status(self, actual: float, cycle_target: float) -> dict[str, Any]:
        return self._calc_simple_status(actual, cycle_target)

    def _calc_simple_status(self, actual: float, target: float) -> dict[str, Any]:
        normalized_actual = safe_decimal(actual)
        normalized_target = safe_decimal(target)
        if normalized_target <= 0:
            return self._no_target_result(normalized_actual, normalized_target)

        completion_rate = normalized_actual / normalized_target
        status_code = self._status_for_rate(completion_rate)
        return self._result(
            actual=normalized_actual,
            target=normalized_target,
            completion_rate=completion_rate,
            status_rate=completion_rate,
            status_code=status_code,
        )

    def _status_for_rate(self, rate: float) -> str:
        if rate < 0.8:
            return self.STATUS_LAGGING
        if rate < 1.0:
            return self.STATUS_WARNING
        if rate < 1.2:
            return self.STATUS_OK
        return self.STATUS_EXCELLENT

    def _no_target_result(
        self,
        actual: float,
        target: float,
        time_progress: float | None = None,
    ) -> dict[str, Any]:
        return self._result(
            actual=actual,
            target=target,
            completion_rate=None,
            status_rate=None,
            status_code=self.STATUS_NO_TARGET,
            time_progress=time_progress,
            progress_ratio=None,
        )

    def _result(
        self,
        *,
        actual: float,
        target: float,
        completion_rate: float | None,
        status_rate: float | None,
        status_code: str,
        time_progress: float | None = None,
        progress_ratio: float | None = None,
    ) -> dict[str, Any]:
        return {
            "actual": round(actual, 2),
            "target": round(target, 2),
            "completion_rate": None if completion_rate is None else round(completion_rate, 4),
            "status_rate": None if status_rate is None else round(status_rate, 4),
            "time_progress": time_progress,
            "progress_ratio": None if progress_ratio is None else round(progress_ratio, 4),
            "status_code": status_code,
            "status_label": self.STATUS_LABELS.get(status_code, status_code),
        }
