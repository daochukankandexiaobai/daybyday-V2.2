from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    from app.db.database import DatabaseManager
    from app.db.repositories import AdminActionLogRepository
    from app.fields.registry import PAGE_PNG_TODAY
    from app.services.admin_action_log_service import AdminActionLogService
    from app.services.field_admin_config_service import FieldAdminConfigService

    tmp_dir = Path(tempfile.mkdtemp(prefix="daybyday_field_config_center_"))
    try:
        db = DatabaseManager(str(tmp_dir / "field_config_center.db"))
        db.initialize()

        admin_log_service = AdminActionLogService(AdminActionLogRepository(db))
        service = FieldAdminConfigService(db, admin_action_log_service=admin_log_service)

        overview = service.get_config_overview()
        _assert(overview["enabled_field_count"] > 0, "overview enabled field count is empty")
        _assert(overview["entry_field_count"] > 0, "overview entry field count is empty")
        _assert(overview["today_field_count"] > 0, "overview today field count is empty")
        _assert(overview["query_field_count"] > 0, "overview query field count is empty")
        _assert(overview["png_template_count"] >= 1, "overview png template count is empty")
        _assert("health" in overview and "status_label" in overview["health"], "overview health summary missing")

        baseline = service.run_config_health_check(operator="tester")
        _assert("summary" in baseline and "items" in baseline, "health check result shape invalid")
        _assert(baseline["items"], "health check should return result items")

        with db.get_connection() as conn:
            conn.execute(
                """
                UPDATE field_definitions
                SET enabled = 0
                WHERE field_key = 'repayment_amount_daily'
                """,
            )
            field_keys = [
                str(row["field_key"])
                for row in conn.execute(
                    "SELECT field_key FROM field_definitions WHERE enabled = 1 ORDER BY field_key LIMIT 15"
                ).fetchall()
            ]
            payload = {
                "sections": [
                    {
                        "key": "health_test",
                        "title": "健康检查测试图",
                        "file_suffix": "health",
                        "field_keys": field_keys + ["missing_health_field"],
                    }
                ]
            }
            conn.execute(
                """
                UPDATE view_templates
                SET config_json = ?
                WHERE template_key = 'png_today_default'
                """,
                (json.dumps(payload, ensure_ascii=False),),
            )
            conn.commit()

        result = service.run_config_health_check(operator="tester")
        titles = [str(item.get("title", "")) for item in result["items"]]
        _assert("页面配置引用了停用字段" in titles, "health check did not catch disabled field reference")
        _assert("PNG 分图字段过多" in titles, "health check did not catch oversized png section")
        _assert("PNG 模板引用不存在字段" in titles, "health check did not catch missing png field reference")

        logs = admin_log_service.list_logs(action_type="check_field_config_health", target_type="field_config")
        _assert(logs, "health check action should be logged")

        overview_after = service.get_config_overview()
        _assert(overview_after["latest_action_type"] == "check_field_config_health", "overview latest action not updated")
        _assert(overview_after["health"]["warning_count"] >= 1, "overview health warning count not updated")

        print("[field_config_center] PASS")
        return 0
    finally:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
