from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from app.utils.date_utils import (
    day_end_iso,
    day_start_iso,
    now_iso,
    parse_date,
    settlement_cycle_display_code,
)
from app.utils.json_utils import load_json_file
from app.utils.log_utils import get_logger
from app.utils.validators import normalize_record, validate_export_payload


class ImportService:
    """V1.1 JSON 导入服务。"""

    def __init__(
        self,
        record_repo,
        import_log_repo,
        settings_service,
        template_service,
        record_service,
        team_service,
        team_repo=None,
        account_manager_repo=None,
    ) -> None:
        self.logger = get_logger("import_service")
        self.record_repo = record_repo
        self.import_log_repo = import_log_repo
        self.settings_service = settings_service
        self.template_service = template_service
        self.record_service = record_service
        self.team_service = team_service
        self.team_repo = team_repo or getattr(team_service, "team_repo", None)
        self.account_manager_repo = account_manager_repo or getattr(team_service, "account_manager_repo", None)
        self.field_value_service = getattr(record_service, "field_value_service", None)

    def import_files(self, file_paths: list[str], allow_template_mismatch: bool = False) -> list[dict]:
        results: list[dict] = []
        for file_path in file_paths:
            results.extend(self._import_single_file(file_path, allow_template_mismatch))
        return results

    def preview_files(self, file_paths: list[str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        current_template_version = self.template_service.get_active_template_version()
        strict_mode = self.settings_service.is_strict_template_mode()

        for file_path in file_paths:
            path = Path(file_path)
            row: dict[str, Any] = {
                "file_name": path.name,
                "file_path": str(path),
                "export_id": "",
                "template_version": "",
                "team_id": 0,
                "team_name": "",
                "region": "",
                "team_manager_name": "",
                "cycle_code": "",
                "record_count": 0,
                "start_date": "",
                "end_date": "",
                "is_valid": False,
                "template_match": False,
                "message": "",
            }
            try:
                payload = load_json_file(path)
            except Exception as exc:  # noqa: BLE001
                self.logger.exception("导入预览读取失败 file=%s", path)
                row["message"] = f"读取失败: {exc}"
                rows.append(row)
                continue

            valid, message = validate_export_payload(payload)
            if not valid:
                row["message"] = f"结构校验失败: {message}"
                rows.append(row)
                continue

            metadata = payload.get("metadata", {})
            export_info = payload.get("export_info", {})
            cycle_info = payload.get("settlement_cycle_info", {})
            records = payload.get("records", [])
            file_cycle_code = self._resolve_file_cycle_code(cycle_info, export_info, records)
            team_context = self._extract_team_context(payload, records)

            file_template_version = str(metadata.get("template_version") or "")
            template_match = file_template_version == current_template_version
            date_range = self._compute_record_date_range(records)
            msg = "可导入" if (template_match or not strict_mode) else "模板版本不一致，严格模式下将失败"

            row.update(
                {
                    "export_id": str(export_info.get("export_id", "")),
                    "template_version": file_template_version,
                    "team_id": int(team_context.get("team_id", 0) or 0),
                    "team_name": str(team_context.get("team_name", "")),
                    "region": str(team_context.get("region", "")),
                    "team_manager_name": str(team_context.get("team_manager_name", "")),
                    "cycle_code": file_cycle_code,
                    "record_count": len(records),
                    "start_date": str(export_info.get("start_date", "") or date_range[0]),
                    "end_date": str(export_info.get("end_date", "") or date_range[1]),
                    "is_valid": True,
                    "template_match": template_match,
                    "message": msg,
                }
            )
            rows.append(row)

        return rows

    def _import_single_file(self, file_path: str, allow_template_mismatch: bool) -> list[dict]:
        path = Path(file_path)
        file_name = path.name

        try:
            payload = load_json_file(path)
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("导入读取失败 file=%s", path)
            return [
                self._log_and_collect(
                    file_name=file_name,
                    file_path=str(path),
                    export_id="",
                    team_name="",
                    settlement_cycle_code="",
                    template_version="",
                    result="failed",
                    message=f"读取 JSON 失败: {exc}",
                    affected_record_count=0,
                )
            ]

        valid, message = validate_export_payload(payload)
        if not valid:
            self.logger.warning("导入JSON结构校验失败 file=%s reason=%s", path, message)
            return [
                self._log_and_collect(
                    file_name=file_name,
                    file_path=str(path),
                    export_id="",
                    team_name="",
                    settlement_cycle_code="",
                    template_version="",
                    result="failed",
                    message=f"JSON 校验失败: {message}",
                    affected_record_count=0,
                )
            ]

        metadata = payload.get("metadata", {})
        export_info = payload.get("export_info", {})
        records = payload.get("records", [])
        cycle_info = payload.get("settlement_cycle_info", {})
        team_context = self._extract_team_context(payload, records)
        export_id = str(export_info.get("export_id", ""))
        file_template_version = str(metadata.get("template_version") or "")
        file_team_name = str(team_context.get("team_name", "") or export_info.get("team_name", ""))
        file_cycle_code = self._resolve_file_cycle_code(cycle_info, export_info, records)

        if not records:
            self.logger.warning("导入记录为空 file=%s", path)
            return [
                self._log_and_collect(
                    file_name=file_name,
                    file_path=str(path),
                    export_id=export_id,
                    team_name=file_team_name,
                    settlement_cycle_code=file_cycle_code,
                    template_version=file_template_version,
                    result="failed",
                    message="records 为空，拒绝导入",
                    affected_record_count=0,
                )
            ]

        current_template_version = self.template_service.get_active_template_version()
        if self.settings_service.is_strict_template_mode() and not allow_template_mismatch:
            if file_template_version != current_template_version:
                self.logger.warning(
                    "导入模板版本不一致 file=%s current=%s incoming=%s",
                    path,
                    current_template_version,
                    file_template_version,
                )
                return [
                    self._log_and_collect(
                        file_name=file_name,
                        file_path=str(path),
                        export_id=export_id,
                        team_name=file_team_name,
                        settlement_cycle_code=file_cycle_code,
                        template_version=file_template_version,
                        result="failed",
                        message=(
                            f"模板版本不一致，当前={current_template_version}，文件={file_template_version}"
                        ),
                        affected_record_count=0,
                    )
                ]

        master_context = self._sync_master_context(team_context, records)

        file_results: list[dict] = []
        counters = {"success": 0, "updated": 0, "skipped": 0, "conflict": 0, "failed": 0}
        affected_total = 0

        expected_source_team_id = team_context.get("team_id", 0)
        expected_team_name = str(team_context.get("team_name", "")).strip()
        if not expected_team_name:
            expected_team_name = str(export_info.get("team_name", "")).strip()

        for idx, raw_record in enumerate(records, start=1):
            result, action_message, affected = self._upsert_record(
                raw_record=raw_record,
                file_path=str(path),
                file_template_version=file_template_version,
                master_context=master_context,
                expected_source_team_id=expected_source_team_id,
                expected_team_name=expected_team_name,
            )
            counters[result] = counters.get(result, 0) + 1
            affected_total += affected
            file_results.append(
                self._log_and_collect(
                    file_name=file_name,
                    file_path=str(path),
                    export_id=export_id,
                    team_name=file_team_name,
                    settlement_cycle_code=file_cycle_code,
                    template_version=file_template_version,
                    result=result,
                    message=f"第{idx}条: {action_message}",
                    affected_record_count=affected,
                )
            )

        summary_message = (
            f"导入完成: 新增{counters['success']}，更新{counters['updated']}，"
            f"跳过{counters['skipped']}，冲突{counters['conflict']}，失败{counters['failed']}"
        )
        file_results.append(
            self._log_and_collect(
                file_name=file_name,
                file_path=str(path),
                export_id=export_id,
                team_name=file_team_name,
                settlement_cycle_code=file_cycle_code,
                template_version=file_template_version,
                result=self._summary_result(counters),
                message=summary_message,
                affected_record_count=affected_total,
            )
        )
        return file_results

    @staticmethod
    def _summary_result(counters: dict[str, int]) -> str:
        if counters.get("failed", 0) > 0 and counters.get("success", 0) + counters.get("updated", 0) == 0:
            return "failed"
        if counters.get("updated", 0) > 0:
            return "updated"
        if counters.get("success", 0) > 0:
            return "success"
        if counters.get("conflict", 0) > 0:
            return "conflict"
        return "skipped"

    @staticmethod
    def _resolve_file_cycle_code(cycle_info: dict[str, Any], export_info: dict[str, Any], records: list[dict[str, Any]]) -> str:
        cycle_start = str(cycle_info.get("cycle_start", "")).strip()
        cycle_end = str(cycle_info.get("cycle_end", "")).strip()
        if cycle_end:
            return settlement_cycle_display_code(cycle_end=cycle_end)
        if cycle_start:
            return settlement_cycle_display_code(cycle_start=cycle_start)

        start_date = str(export_info.get("start_date", "")).strip()
        if start_date:
            return settlement_cycle_display_code(record_date=start_date)

        for record in records:
            record_date = str(record.get("record_date") or record.get("date") or "").strip()
            if record_date:
                return settlement_cycle_display_code(record_date=record_date)

        raw_code = str(cycle_info.get("cycle_code", "")).strip()
        return settlement_cycle_display_code(cycle_code=raw_code)

    @staticmethod
    def _pick_single_value(values: list[Any]) -> Any:
        normalized = [str(v).strip() for v in values if str(v).strip()]
        uniq = sorted(set(normalized))
        if len(uniq) == 1:
            return uniq[0]
        return ""

    def _extract_team_context(self, payload: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
        export_info = payload.get("export_info", {}) or {}
        team_info = payload.get("team_info", {}) or {}
        if not isinstance(team_info, dict):
            team_info = {}

        record_team_ids = sorted(
            {int(record.get("team_id", 0) or 0) for record in records if int(record.get("team_id", 0) or 0) > 0}
        )
        record_team_id = record_team_ids[0] if len(record_team_ids) == 1 else 0

        region_from_records = self._pick_single_value([record.get("region", "") for record in records])
        team_name_from_records = self._pick_single_value([record.get("team_name_snapshot", "") for record in records])
        manager_from_records = self._pick_single_value([record.get("team_manager_name_snapshot", "") for record in records])

        team_id = int(
            team_info.get("team_id")
            or export_info.get("team_id")
            or record_team_id
            or 0
        )

        region = str(
            team_info.get("region")
            or export_info.get("region")
            or region_from_records
            or ""
        ).strip()
        team_name = str(
            team_info.get("team_name")
            or export_info.get("team_name")
            or team_name_from_records
            or ""
        ).strip()
        team_manager_name = str(
            team_info.get("team_manager_name")
            or export_info.get("team_manager_name")
            or manager_from_records
            or ""
        ).strip()

        return {
            "team_id": team_id,
            "region": region,
            "team_name": team_name,
            "team_manager_name": team_manager_name,
        }

    def _sync_master_context(self, team_context: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
        now = now_iso()
        preferred_team_id = int(team_context.get("team_id", 0) or 0)
        region = str(team_context.get("region", "")).strip()
        team_name = str(team_context.get("team_name", "")).strip()
        team_manager_name = str(team_context.get("team_manager_name", "")).strip()

        local_team_id = 0
        if self.team_repo is not None and region and team_name and team_manager_name:
            local_team_id = int(
                self.team_repo.upsert_import_team(
                    preferred_team_id=preferred_team_id,
                    region=region,
                    team_name=team_name,
                    team_manager_name=team_manager_name,
                    now=now,
                )
                or 0
            )

        team_id_map: dict[int, int] = {}
        if preferred_team_id > 0 and local_team_id > 0:
            team_id_map[preferred_team_id] = local_team_id

        manager_id_by_source: dict[int, int] = {}
        manager_id_by_name: dict[str, int] = {}
        if self.account_manager_repo is not None and local_team_id > 0:
            for raw_record in records:
                normalized = normalize_record(raw_record)
                manager_name = str(normalized.get("account_manager_name_snapshot", "")).strip()
                source_manager_id = int(normalized.get("account_manager_id", 0) or 0)
                if not manager_name and source_manager_id <= 0:
                    continue
                local_manager_id = int(
                    self.account_manager_repo.upsert_import_member(
                        team_id=local_team_id,
                        preferred_manager_id=source_manager_id,
                        account_manager_name=manager_name,
                        now=now,
                    )
                    or 0
                )
                if source_manager_id > 0 and local_manager_id > 0:
                    manager_id_by_source[source_manager_id] = local_manager_id
                if manager_name and local_manager_id > 0:
                    manager_id_by_name[manager_name.casefold()] = local_manager_id

        for raw_record in records:
            source_team_id = int(raw_record.get("team_id", 0) or 0)
            if source_team_id > 0 and local_team_id > 0:
                team_id_map[source_team_id] = local_team_id

        return {
            "local_team_id": local_team_id,
            "region": region,
            "team_name": team_name,
            "team_manager_name": team_manager_name,
            "team_id_map": team_id_map,
            "manager_id_by_source": manager_id_by_source,
            "manager_id_by_name": manager_id_by_name,
        }

    def _prepare_record(
        self,
        raw_record: dict,
        file_template_version: str,
        master_context: dict[str, Any] | None = None,
    ) -> tuple[bool, str, dict[str, Any]]:
        incoming = normalize_record(raw_record)
        incoming["_dynamic_metric_values"] = self._extract_dynamic_metric_values(raw_record)
        incoming["template_version"] = incoming["template_version"] or file_template_version

        if not incoming["record_id"]:
            incoming["record_id"] = str(uuid.uuid4())

        if not incoming["record_date"]:
            return False, "缺少 record_date", incoming

        incoming["settlement_cycle_code"] = settlement_cycle_display_code(record_date=incoming["record_date"])
        source_team_id = int(incoming.get("team_id", 0) or 0)
        source_manager_id = int(incoming.get("account_manager_id", 0) or 0)
        incoming["_source_team_id"] = source_team_id

        ctx = master_context or {}
        local_team_id = int(ctx.get("local_team_id", 0) or 0)
        if local_team_id > 0:
            incoming["team_id"] = int(ctx.get("team_id_map", {}).get(source_team_id, local_team_id))
            if not str(incoming.get("region", "")).strip():
                incoming["region"] = str(ctx.get("region", ""))
            if not str(incoming.get("team_name_snapshot", "")).strip():
                incoming["team_name_snapshot"] = str(ctx.get("team_name", ""))
            if not str(incoming.get("team_manager_name_snapshot", "")).strip():
                incoming["team_manager_name_snapshot"] = str(ctx.get("team_manager_name", ""))

            manager_name = str(incoming.get("account_manager_name_snapshot", "")).strip()
            local_manager_id = int(ctx.get("manager_id_by_source", {}).get(source_manager_id, 0) or 0)
            if local_manager_id <= 0 and manager_name:
                local_manager_id = int(ctx.get("manager_id_by_name", {}).get(manager_name.casefold(), 0) or 0)
            if local_manager_id <= 0 and self.account_manager_repo is not None and manager_name:
                local_manager_id = int(
                    self.account_manager_repo.upsert_import_member(
                        team_id=int(incoming["team_id"]),
                        preferred_manager_id=source_manager_id,
                        account_manager_name=manager_name,
                        now=now_iso(),
                    )
                    or 0
                )
            incoming["account_manager_id"] = local_manager_id

        if (
            int(incoming.get("team_id", 0) or 0) > 0
            and int(incoming.get("account_manager_id", 0) or 0) > 0
            and self.team_repo is not None
            and self.account_manager_repo is not None
        ):
            region = str(incoming.get("region", "")).strip()
            team_name = str(incoming.get("team_name_snapshot", "")).strip()
            team_manager_name = str(incoming.get("team_manager_name_snapshot", "")).strip()
            manager_name = str(incoming.get("account_manager_name_snapshot", "")).strip()
            if region and team_name and team_manager_name and manager_name:
                fixed_team_id = int(
                    self.team_repo.upsert_import_team(
                        preferred_team_id=int(incoming["team_id"]),
                        region=region,
                        team_name=team_name,
                        team_manager_name=team_manager_name,
                        now=now_iso(),
                    )
                    or 0
                )
                if fixed_team_id > 0:
                    incoming["team_id"] = fixed_team_id
                    incoming["account_manager_id"] = int(
                        self.account_manager_repo.upsert_import_member(
                            team_id=fixed_team_id,
                            preferred_manager_id=int(incoming["account_manager_id"]),
                            account_manager_name=manager_name,
                            now=now_iso(),
                        )
                        or 0
                    )

        if not incoming["team_id"] or not incoming["account_manager_id"]:
            region = str(incoming.get("region", "")).strip()
            team_name = str(incoming.get("team_name_snapshot", "")).strip()
            team_manager_name = str(incoming.get("team_manager_name_snapshot", "")).strip()
            account_manager_name = str(incoming.get("account_manager_name_snapshot", "")).strip()
            if not region or not team_name or not team_manager_name or not account_manager_name:
                return False, "缺少 team/account manager 标识字段", incoming
            team_id, account_manager_id = self.team_service.ensure_team_and_member(
                region=region,
                team_name=team_name,
                team_manager_name=team_manager_name,
                account_manager_name=account_manager_name,
            )
            incoming["team_id"] = int(team_id)
            incoming["account_manager_id"] = int(account_manager_id)

        if not incoming["updated_at"]:
            incoming["updated_at"] = now_iso()
        if not incoming["created_at"]:
            incoming["created_at"] = incoming["updated_at"]

        incoming["business_key"] = "|".join(
            [
                incoming["record_date"],
                incoming["region"],
                incoming["team_name_snapshot"],
                incoming["account_manager_name_snapshot"],
            ]
        )

        incoming["source_type"] = "imported"
        if not incoming.get("source_file"):
            incoming["source_file"] = ""

        if not incoming["record_hash"]:
            incoming["record_hash"] = self.record_service.build_record_hash(incoming)

        return True, "ok", incoming

    def _upsert_record(
        self,
        raw_record: dict,
        file_path: str,
        file_template_version: str,
        master_context: dict[str, Any] | None = None,
        expected_source_team_id: Any = None,
        expected_team_name: str = "",
    ) -> tuple[str, str, int]:
        ok, message, incoming = self._prepare_record(
            raw_record=raw_record,
            file_template_version=file_template_version,
            master_context=master_context,
        )
        if not ok:
            self.logger.warning("导入记录预处理失败: %s", message)
            return "failed", message, 0

        incoming["source_file"] = file_path

        if expected_source_team_id not in (None, "", 0, "0"):
            try:
                source_team_id = int(incoming.get("_source_team_id", 0) or 0)
                if source_team_id > 0 and source_team_id != int(expected_source_team_id):
                    self.logger.warning(
                        "导入记录团队ID不一致 source_team_id=%s expected=%s",
                        source_team_id,
                        expected_source_team_id,
                    )
                    return "failed", "record.team_id 与 export_info/team_info.team_id 不一致", 0
            except (TypeError, ValueError):
                return "failed", "export_info/team_info.team_id 非法", 0

        if expected_team_name.strip():
            actual_team_name = str(incoming.get("team_name_snapshot", "")).strip()
            if actual_team_name and actual_team_name != expected_team_name.strip():
                self.logger.warning(
                    "导入记录团队名称不一致 actual=%s expected=%s",
                    actual_team_name,
                    expected_team_name.strip(),
                )
                return "failed", "record.team_name_snapshot 与 export_info/team_info.team_name 不一致", 0

        existing_by_id = self.record_repo.get_by_record_id(incoming["record_id"])
        if existing_by_id:
            return self._resolve_existing(existing_by_id, incoming, "record_id")

        existing_by_unique = self.record_repo.get_by_unique(
            incoming["record_date"],
            int(incoming["team_id"]),
            int(incoming["account_manager_id"]),
        )
        if existing_by_unique:
            return self._resolve_existing(existing_by_unique, incoming, "unique")

        try:
            new_row_id = self.record_repo.insert(incoming)
            self._apply_dynamic_values(new_row_id, incoming)
            self.logger.info(
                "导入新增成功 record_id=%s date=%s team_id=%s account_manager_id=%s",
                incoming.get("record_id"),
                incoming.get("record_date"),
                incoming.get("team_id"),
                incoming.get("account_manager_id"),
            )
            return "success", "新增记录导入成功", 1
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("导入插入失败 record_id=%s", incoming.get("record_id"))
            return "failed", f"插入失败: {exc}", 0

    def _resolve_existing(self, existing: dict, incoming: dict, mode: str) -> tuple[str, str, int]:
        existing_version = int(existing.get("version", 1))
        incoming_version = int(incoming.get("version", 1))

        if incoming_version > existing_version:
            self._apply_update(existing, incoming)
            return "updated", "新版本更高，已覆盖", 1

        if incoming_version < existing_version:
            return "skipped", "导入版本较旧，已跳过", 0

        existing_hash = str(existing.get("record_hash", ""))
        incoming_hash = str(incoming.get("record_hash", ""))
        if existing_hash == incoming_hash:
            if self._dynamic_values_changed(int(existing.get("id", 0) or 0), incoming):
                self._apply_dynamic_values(int(existing.get("id", 0) or 0), incoming)
                return "updated", "动态字段已更新", 1
            return "skipped", "同版本同内容，已跳过", 0

        if mode == "record_id":
            return "conflict", "record_id 相同且同版本内容不同", 0
        return "conflict", "同唯一键记录同版本内容冲突，已跳过", 0

    def _apply_update(self, existing: dict, incoming: dict) -> None:
        updates = {
            "record_id": incoming["record_id"],
            "record_date": incoming["record_date"],
            "region": incoming["region"],
            "team_id": incoming["team_id"],
            "team_name_snapshot": incoming["team_name_snapshot"],
            "team_manager_name_snapshot": incoming["team_manager_name_snapshot"],
            "account_manager_id": incoming["account_manager_id"],
            "account_manager_name_snapshot": incoming["account_manager_name_snapshot"],
            "settlement_cycle_code": incoming["settlement_cycle_code"],
            "business_key": incoming["business_key"],
            "remark": incoming.get("remark", ""),
            "version": incoming["version"],
            "updated_at": incoming["updated_at"],
            "template_version": incoming["template_version"],
            "record_hash": incoming["record_hash"],
            "source_type": "imported",
            "source_file": incoming.get("source_file", ""),
        }
        for key in incoming:
            if key.endswith("_daily"):
                updates[key] = incoming[key]

        self.record_repo.update_by_id(int(existing["id"]), updates)
        self._apply_dynamic_values(int(existing["id"]), incoming)
        self.logger.info(
            "导入更新成功 id=%s record_id=%s version=%s",
            existing.get("id"),
            incoming.get("record_id"),
            incoming.get("version"),
        )

    def _extract_dynamic_metric_values(self, raw_record: dict[str, Any]) -> dict[str, Any]:
        if self.field_value_service is None:
            return {}
        try:
            with self.record_repo.db.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT field_key
                    FROM field_definitions
                    WHERE enabled = 1
                      AND category = 'raw_daily'
                      AND storage_type = 'dynamic_metric'
                    ORDER BY id ASC
                    """
                ).fetchall()
        except Exception:  # noqa: BLE001
            return {}

        values: dict[str, Any] = {}
        for row in rows:
            field_key = str(row["field_key"])
            if field_key in raw_record:
                values[field_key] = raw_record.get(field_key)
        return values

    def _apply_dynamic_values(self, row_id: int, incoming: dict[str, Any]) -> None:
        if self.field_value_service is None:
            return
        values = incoming.get("_dynamic_metric_values", {})
        if not values:
            return
        self.field_value_service.set_values(int(row_id), values)

    def _dynamic_values_changed(self, row_id: int, incoming: dict[str, Any]) -> bool:
        if self.field_value_service is None or int(row_id or 0) <= 0:
            return False
        values = incoming.get("_dynamic_metric_values", {})
        if not values:
            return False
        current = self.field_value_service.get_values(int(row_id), values.keys())
        for field_key, raw_value in values.items():
            try:
                field_def = self.field_value_service._get_field_def(field_key)
                normalized = self.field_value_service.normalize_value(field_def, raw_value)
            except Exception:  # noqa: BLE001
                normalized = raw_value
            if current.get(field_key) != normalized:
                return True
        return False

    def _log_and_collect(
        self,
        file_name: str,
        file_path: str,
        export_id: str,
        team_name: str,
        settlement_cycle_code: str,
        template_version: str,
        result: str,
        message: str,
        affected_record_count: int,
    ) -> dict:
        row = {
            "import_time": now_iso(),
            "file_name": file_name,
            "file_path": file_path,
            "export_id": export_id,
            "team_name": team_name,
            "settlement_cycle_code": settlement_cycle_code,
            "template_version": template_version,
            "result": result,
            "message": message,
            "affected_record_count": affected_record_count,
        }
        self.import_log_repo.insert(row)
        return row

    def list_logs(self, start_date: str = "", end_date: str = "", result: str = "") -> list[dict]:
        start_time = day_start_iso(parse_date(start_date)) if start_date else ""
        end_time = day_end_iso(parse_date(end_date)) if end_date else ""
        return self.import_log_repo.list_logs(start_time=start_time, end_time=end_time, result=result)

    def list_conflict_logs(self, start_date: str = "", end_date: str = "") -> list[dict]:
        return self.list_logs(start_date=start_date, end_date=end_date, result="conflict")

    def check_missing_reports(
        self,
        start_date: str,
        end_date: str,
        expected_managers: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        imported_rows = self.record_repo.list_records(
            start_date=start_date,
            end_date=end_date,
            source_type="imported",
        )

        imported_stats: dict[str, dict[str, Any]] = {}
        for row in imported_rows:
            manager = str(row.get("account_manager_name_snapshot", "")).strip()
            if not manager:
                continue
            stat = imported_stats.setdefault(
                manager,
                {
                    "regions": set(),
                    "teams": set(),
                    "count": 0,
                    "start_date": row.get("record_date", ""),
                    "end_date": row.get("record_date", ""),
                },
            )
            stat["regions"].add(str(row.get("region", "")))
            stat["teams"].add(str(row.get("team_name_snapshot", "")))
            stat["count"] += 1
            current_date = str(row.get("record_date", ""))
            if current_date and (not stat["start_date"] or current_date < stat["start_date"]):
                stat["start_date"] = current_date
            if current_date and (not stat["end_date"] or current_date > stat["end_date"]):
                stat["end_date"] = current_date

        expected = [x.strip() for x in (expected_managers or []) if x.strip()]
        if not expected:
            expected = self.record_repo.list_distinct_account_manager_names(start_date, end_date)

        baseline = set(expected)
        if not baseline:
            baseline = set(imported_stats.keys())

        result_rows: list[dict[str, Any]] = []
        for manager in sorted(baseline):
            stat = imported_stats.get(manager)
            if stat:
                result_rows.append(
                    {
                        "region": " / ".join(sorted(x for x in stat["regions"] if x)),
                        "team": " / ".join(sorted(x for x in stat["teams"] if x)),
                        "account_manager_name": manager,
                        "manager_name": manager,
                        "status": "已收到",
                        "received_record_count": int(stat["count"]),
                        "received_start_date": stat["start_date"],
                        "received_end_date": stat["end_date"],
                        "note": "",
                    }
                )
            else:
                result_rows.append(
                    {
                        "region": "",
                        "team": "",
                        "account_manager_name": manager,
                        "manager_name": manager,
                        "status": "未收到",
                        "received_record_count": 0,
                        "received_start_date": "",
                        "received_end_date": "",
                        "note": "当前时间范围未检测到导入记录",
                    }
                )

        extra = sorted(set(imported_stats.keys()) - baseline)
        for manager in extra:
            stat = imported_stats[manager]
            result_rows.append(
                {
                    "region": " / ".join(sorted(x for x in stat["regions"] if x)),
                    "team": " / ".join(sorted(x for x in stat["teams"] if x)),
                    "account_manager_name": manager,
                    "manager_name": manager,
                    "status": "额外收到",
                    "received_record_count": int(stat["count"]),
                    "received_start_date": stat["start_date"],
                    "received_end_date": stat["end_date"],
                    "note": "不在基线经理列表中",
                }
            )

        return result_rows

    @staticmethod
    def _compute_record_date_range(records: list[dict[str, Any]]) -> tuple[str, str]:
        dates = sorted(
            str(item.get("record_date") or item.get("date") or "").strip()
            for item in records
            if str(item.get("record_date") or item.get("date") or "").strip()
        )
        if not dates:
            return "", ""
        return dates[0], dates[-1]
