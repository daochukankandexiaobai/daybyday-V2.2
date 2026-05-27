from __future__ import annotations

import json
from typing import Any

from app.utils.date_utils import day_end_iso, day_start_iso, now_iso, parse_date


class AdminActionLogService:
    def __init__(self, admin_action_log_repo) -> None:
        self.admin_action_log_repo = admin_action_log_repo

    @staticmethod
    def _dump_snapshot(snapshot: dict[str, Any] | None) -> str:
        if snapshot is None:
            return ""
        return json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def log_action(
        self,
        action_type: str,
        target_type: str,
        target_id: str,
        operator: str,
        before_snapshot: dict[str, Any] | None = None,
        after_snapshot: dict[str, Any] | None = None,
        note: str = "",
    ) -> int:
        row = {
            "action_type": str(action_type or "").strip(),
            "target_type": str(target_type or "").strip(),
            "target_id": str(target_id or "").strip(),
            "operator": str(operator or "admin").strip() or "admin",
            "action_time": now_iso(),
            "before_snapshot": self._dump_snapshot(before_snapshot),
            "after_snapshot": self._dump_snapshot(after_snapshot),
            "note": str(note or "").strip(),
        }
        return self.admin_action_log_repo.insert(row)

    def list_logs(
        self,
        start_date: str = "",
        end_date: str = "",
        action_type: str = "",
        target_type: str = "",
        operator: str = "",
    ) -> list[dict[str, Any]]:
        start_time = day_start_iso(parse_date(start_date)) if start_date else ""
        end_time = day_end_iso(parse_date(end_date)) if end_date else ""
        return self.admin_action_log_repo.list_logs(
            start_time=start_time,
            end_time=end_time,
            action_type=action_type,
            target_type=target_type,
            operator=operator,
        )
