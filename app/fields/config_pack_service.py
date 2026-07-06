from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app import APP_VERSION
from app.fields.formula_service import FormulaService
from app.fields.registry import (
    PAGE_ANALYSIS,
    PAGE_DATA_ENTRY,
    PAGE_EXCEL_EXPORT,
    PAGE_JSON_EXPORT,
    PAGE_PNG_TODAY,
    PAGE_QUERY_SUMMARY,
    PAGE_TODAY_DISPLAY,
    build_default_field_rows,
    build_default_page_visibility_rows,
    build_default_view_template_rows,
)
from app.services.field_config_health_service import FieldConfigHealthService


PACK_TYPE = "field_report_config_pack"
IMPORT_MODE_ADD_MISSING = "add_missing"
IMPORT_MODE_MERGE_UPDATE = "merge_update"
IMPORT_MODE_REPLACE = "replace"

FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
DATA_TYPES = {"int", "amount", "money", "decimal", "percent", "text", "textarea", "date"}
AGGREGATIONS = {"none", "sum", "avg", "max", "min", "latest", "count", "derived", "formula"}
PAGE_KEYS = {
    PAGE_DATA_ENTRY,
    PAGE_TODAY_DISPLAY,
    PAGE_QUERY_SUMMARY,
    PAGE_ANALYSIS,
    PAGE_PNG_TODAY,
    PAGE_EXCEL_EXPORT,
    PAGE_JSON_EXPORT,
}
CONFIG_ARRAY_KEYS = (
    "field_definitions",
    "field_page_visibility",
    "view_templates",
    "png_templates",
    "analysis_config",
    "export_config",
    "monitoring_config",
    "field_package_states",
)
ALLOWED_TOP_LEVEL_KEYS = {
    "pack_type",
    "pack_id",
    "pack_version",
    "app_min_version",
    "app_max_version",
    "created_at",
    "created_by",
    "description",
    "checksum",
}
ALLOWED_TOP_LEVEL_KEYS.update(CONFIG_ARRAY_KEYS)

FIELD_COLUMNS = (
    "field_key",
    "label",
    "data_type",
    "category",
    "group_key",
    "editable",
    "required",
    "default_value",
    "aggregation",
    "formula_id",
    "enabled",
    "system_field",
    "storage_type",
    "storage_column",
)
FIELD_COMPARE_COLUMNS = (
    "label",
    "data_type",
    "category",
    "group_key",
    "editable",
    "required",
    "default_value",
    "aggregation",
    "formula_id",
    "enabled",
    "storage_type",
    "storage_column",
)
VISIBILITY_COLUMNS = ("field_key", "page_key", "visible", "group_key", "display_order")
TEMPLATE_COLUMNS = ("template_key", "template_name", "page_key", "config_json", "is_default", "enabled")


@dataclass
class ConfigPackValidationResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    checksum_expected: str = ""
    checksum_actual: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class ConfigPackConflict:
    label: str
    local_field_key: str
    pack_field_key: str
    conflict_type: str = "same_label_different_key"


@dataclass
class ConfigPackPreviewResult:
    metadata: Dict[str, Any]
    validation: ConfigPackValidationResult
    local_field_count: int
    pack_field_count: int
    add_fields: List[Dict[str, Any]] = field(default_factory=list)
    update_fields: List[Dict[str, Any]] = field(default_factory=list)
    disable_fields: List[Dict[str, Any]] = field(default_factory=list)
    conflicts: List[ConfigPackConflict] = field(default_factory=list)
    template_changes: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def add_count(self) -> int:
        return len(self.add_fields)

    @property
    def update_count(self) -> int:
        return len(self.update_fields)

    @property
    def disable_count(self) -> int:
        return len(self.disable_fields)

    @property
    def conflict_count(self) -> int:
        return len(self.conflicts)


@dataclass
class ConfigPackImportResult:
    success: bool
    message: str
    mode: str
    backup_path: str = ""
    added_count: int = 0
    updated_count: int = 0
    disabled_count: int = 0
    templates_updated_count: int = 0
    skipped_count: int = 0
    conflict_count: int = 0
    health_result: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_text(value: Any) -> str:
    return "" if value is None else str(value)


class ConfigPackService:
    """Export, preview, import, backup, and restore field/report config packs."""

    def __init__(
        self,
        db_manager: Any,
        admin_action_log_service: Optional[Any] = None,
        settings_service: Optional[Any] = None,
    ) -> None:
        self.db_manager = db_manager
        self.admin_action_log_service = admin_action_log_service
        self.settings_service = settings_service
        self.formula_service = FormulaService()
        self.health_service = FieldConfigHealthService(db_manager, self.formula_service)

    def export_config_pack(self, path: str, metadata: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        metadata = dict(metadata or {})
        target = Path(path)
        try:
            pack = self._build_current_pack(metadata)
            pack["checksum"] = self.calculate_checksum(pack)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            self._log("export_config_pack_failed", str(target), metadata.get("created_by", "admin"), result=str(exc))
            return False, "配置包导出失败: {}".format(exc)

        self._log(
            "export_config_pack",
            str(target),
            metadata.get("created_by", "admin"),
            after={"path": str(target), "pack_id": pack.get("pack_id", "")},
            result="success",
        )
        return True, str(target)

    def load_config_pack(self, path: str) -> Dict[str, Any]:
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return {"_load_error": "读取 JSON 失败: {}".format(exc), "_source_file": str(source)}
        if not isinstance(payload, dict):
            return {"_load_error": "配置包 JSON 根节点必须是对象", "_source_file": str(source)}
        payload["_source_file"] = str(source)
        return payload

    def validate_config_pack(self, pack: Dict[str, Any]) -> ConfigPackValidationResult:
        result = ConfigPackValidationResult()
        if not isinstance(pack, dict):
            result.errors.append("配置包 JSON 根节点必须是对象")
            return result
        if pack.get("_load_error"):
            result.errors.append(str(pack.get("_load_error")))
            return result

        pack_type = str(pack.get("pack_type", "") or "")
        if pack_type != PACK_TYPE:
            result.errors.append("该文件不是字段与报表配置包")
            return result

        for key in ("pack_version", "app_min_version"):
            if not str(pack.get(key, "") or "").strip():
                result.errors.append("配置包格式不完整: 缺少 {}".format(key))

        for key in CONFIG_ARRAY_KEYS:
            if key not in pack:
                result.errors.append("配置包格式不完整: 缺少 {}".format(key))
                continue
            if not isinstance(pack.get(key), list):
                result.errors.append("配置包格式错误: {} 必须是数组".format(key))

        unknown_keys = sorted(str(key) for key in pack.keys() if str(key) not in ALLOWED_TOP_LEVEL_KEYS and not str(key).startswith("_"))
        if unknown_keys:
            result.warnings.append("配置包包含未知结构: {}".format(", ".join(unknown_keys)))

        self._validate_version(pack, result)
        self._validate_checksum(pack, result)
        self._validate_fields(pack, result)
        self._validate_visibility(pack, result)
        self._validate_templates(pack, result)
        self._validate_local_label_conflicts(pack, result)
        return result

    def preview_config_pack(self, pack: Dict[str, Any], operator: str = "") -> ConfigPackPreviewResult:
        validation = self.validate_config_pack(pack)
        local_fields = self._list_current_field_definitions()
        local_by_key = {str(row.get("field_key", "")): row for row in local_fields}
        local_by_label = self._fields_by_label(local_fields)
        pack_fields = self._pack_fields(pack)
        pack_by_key = {str(row.get("field_key", "")): row for row in pack_fields}
        conflicts = self._detect_label_conflicts(pack_fields, local_by_label, local_by_key)
        conflict_keys = {conflict.pack_field_key for conflict in conflicts}

        add_fields: List[Dict[str, Any]] = []
        update_fields: List[Dict[str, Any]] = []
        for row in pack_fields:
            field_key = str(row.get("field_key", "") or "")
            if not field_key:
                continue
            if field_key not in local_by_key:
                if field_key not in conflict_keys:
                    add_fields.append(row)
                continue
            changes = self._field_changes(local_by_key[field_key], row)
            if changes:
                update_row = dict(row)
                update_row["changes"] = changes
                update_fields.append(update_row)

        disable_fields = [
            row for key, row in sorted(local_by_key.items())
            if key and key not in pack_by_key and _safe_int(row.get("enabled"), 0) == 1
        ]
        metadata = self._pack_metadata(pack)
        template_changes = self._preview_template_changes(pack)
        warnings = list(validation.warnings)
        for conflict in conflicts:
            warnings.append(
                "发现同名不同编码字段: 本机 {} / {}; 配置包 {} / {}".format(
                    conflict.label,
                    conflict.local_field_key,
                    conflict.label,
                    conflict.pack_field_key,
                )
            )

        preview = ConfigPackPreviewResult(
            metadata=metadata,
            validation=validation,
            local_field_count=len(local_fields),
            pack_field_count=len(pack_fields),
            add_fields=add_fields,
            update_fields=update_fields,
            disable_fields=disable_fields,
            conflicts=conflicts,
            template_changes=template_changes,
            warnings=warnings,
            errors=list(validation.errors),
        )
        if operator:
            self._log(
                "preview_config_pack",
                str(pack.get("_source_file", "")),
                operator,
                after={
                    "pack_id": metadata.get("pack_id", ""),
                    "add_count": preview.add_count,
                    "update_count": preview.update_count,
                    "conflict_count": preview.conflict_count,
                    "errors": preview.errors,
                    "warnings": preview.warnings,
                },
                result="success" if not preview.errors else "validation_failed",
            )
        return preview

    def import_config_pack(
        self,
        pack: Dict[str, Any],
        mode: str = IMPORT_MODE_MERGE_UPDATE,
        operator: str = "admin",
        source_file: str = "",
    ) -> ConfigPackImportResult:
        normalized_mode = self._normalize_import_mode(mode)
        validation = self.validate_config_pack(pack)
        if validation.errors:
            self._log(
                "import_config_pack_failed",
                source_file or str(pack.get("_source_file", "")),
                operator,
                after={"errors": validation.errors},
                result="validation_failed",
            )
            return ConfigPackImportResult(
                success=False,
                message="配置包校验失败",
                mode=normalized_mode,
                errors=list(validation.errors),
                warnings=list(validation.warnings),
            )

        backup_path = self.backup_current_config("before_import", operator=operator)
        if not backup_path:
            return ConfigPackImportResult(
                success=False,
                message="导入前备份失败，已拒绝继续导入",
                mode=normalized_mode,
                errors=["导入前备份失败"],
                warnings=list(validation.warnings),
            )

        preview = self.preview_config_pack(pack)
        conflict_keys = {conflict.pack_field_key for conflict in preview.conflicts}
        counts = {
            "added": 0,
            "updated": 0,
            "disabled": 0,
            "templates": 0,
            "skipped": 0,
        }
        try:
            with self.db_manager.get_connection() as conn:
                if normalized_mode == IMPORT_MODE_ADD_MISSING:
                    counts.update(self._apply_add_missing(conn, pack, conflict_keys))
                elif normalized_mode == IMPORT_MODE_MERGE_UPDATE:
                    counts.update(self._apply_merge_update(conn, pack, conflict_keys))
                elif normalized_mode == IMPORT_MODE_REPLACE:
                    counts.update(self._apply_replace(conn, pack, conflict_keys))
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            self._log(
                "import_config_pack_failed",
                source_file or str(pack.get("_source_file", "")),
                operator,
                after={"error": str(exc), "mode": normalized_mode, "backup_path": backup_path},
                result="failed",
            )
            return ConfigPackImportResult(
                success=False,
                message="配置包导入失败: {}".format(exc),
                mode=normalized_mode,
                backup_path=backup_path,
                errors=[str(exc)],
                warnings=list(validation.warnings),
            )

        health = self.health_service.run_checks()
        self.update_config_pack_state(
            current_pack_id=str(pack.get("pack_id", "") or ""),
            current_pack_version=str(pack.get("pack_version", "") or ""),
            imported_at=_now_str(),
            imported_by=operator,
            import_mode=normalized_mode,
            source_file=source_file or str(pack.get("_source_file", "")),
            health_status=str(health.get("summary", {}).get("status_label", "")),
            notes="配置包导入成功",
        )
        self._log(
            "import_config_pack",
            source_file or str(pack.get("_source_file", "")),
            operator,
            after={
                "pack_id": pack.get("pack_id", ""),
                "mode": normalized_mode,
                "backup_path": backup_path,
                "counts": counts,
                "health": health.get("summary", {}),
            },
            result="success",
        )
        return ConfigPackImportResult(
            success=True,
            message="配置包导入成功",
            mode=normalized_mode,
            backup_path=backup_path,
            added_count=counts["added"],
            updated_count=counts["updated"],
            disabled_count=counts["disabled"],
            templates_updated_count=counts["templates"],
            skipped_count=counts["skipped"],
            conflict_count=len(preview.conflicts),
            health_result=health,
            warnings=list(validation.warnings) + list(preview.warnings),
        )

    def backup_current_config(self, reason: str, operator: str = "admin") -> str:
        backup_dir = self._backup_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = backup_dir / "config_backup_before_import_{}.json".format(timestamp)
        metadata = {
            "pack_id": "backup-{}".format(timestamp),
            "pack_version": datetime.now().strftime("%Y.%m.%d.%H%M%S.%f"),
            "created_by": operator,
            "description": "自动备份: {}".format(reason),
            "app_min_version": self._current_app_version(),
        }
        try:
            pack = self._build_current_pack(metadata)
            pack["checksum"] = self.calculate_checksum(pack)
            backup_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            self._log("backup_config_pack_failed", str(path), operator, after={"error": str(exc)}, result="failed")
            return ""

        self._log("backup_config_pack", str(path), operator, after={"reason": reason, "path": str(path)}, result="success")
        return str(path)

    def latest_backup_path(self) -> str:
        backup_dir = self._backup_dir()
        if not backup_dir.exists():
            return ""
        backups = sorted(backup_dir.glob("config_backup_before_import_*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        return str(backups[0]) if backups else ""

    def restore_config_from_backup(self, path: str, operator: str = "admin") -> Tuple[bool, str]:
        pack = self.load_config_pack(path)
        validation = self.validate_config_pack(pack)
        if validation.errors:
            self._log("restore_config_backup_failed", path, operator, after={"errors": validation.errors}, result="validation_failed")
            return False, "备份配置校验失败: {}".format("; ".join(validation.errors))
        try:
            with self.db_manager.get_connection() as conn:
                self._apply_replace(conn, pack, conflict_keys=set())
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            self._log("restore_config_backup_failed", path, operator, after={"error": str(exc)}, result="failed")
            return False, "恢复导入前配置失败: {}".format(exc)

        health = self.health_service.run_checks()
        self.update_config_pack_state(
            current_pack_id=str(pack.get("pack_id", "") or ""),
            current_pack_version=str(pack.get("pack_version", "") or ""),
            imported_at=_now_str(),
            imported_by=operator,
            import_mode="restore_backup",
            source_file=path,
            health_status=str(health.get("summary", {}).get("status_label", "")),
            notes="恢复导入前配置",
        )
        self._log("restore_config_backup", path, operator, after={"health": health.get("summary", {})}, result="success")
        return True, "已恢复导入前配置"

    def restore_last_import_backup(self, operator: str = "admin") -> Tuple[bool, str]:
        path = self.latest_backup_path()
        if not path:
            return False, "未找到可恢复的导入前配置备份。"
        return self.restore_config_from_backup(path, operator=operator)

    def restore_default_config(self, operator: str = "admin") -> Tuple[bool, str]:
        backup_path = self.backup_current_config("before_restore_default", operator=operator)
        if not backup_path:
            return False, "恢复默认配置前备份失败，已拒绝继续恢复"
        now = _now_str()
        try:
            with self.db_manager.get_connection() as conn:
                conn.execute("UPDATE field_definitions SET enabled = 0, updated_at = ? WHERE system_field = 0", (now,))
                for row in build_default_field_rows():
                    self._upsert_field(conn, row, now, count_update=False)
                conn.execute("DELETE FROM field_page_visibility")
                for row in build_default_page_visibility_rows():
                    self._insert_visibility(conn, row, now)
                conn.execute("DELETE FROM view_templates")
                for row in build_default_view_template_rows():
                    self._insert_template(conn, row, now, replace=False)
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            self._log("restore_default_config_failed", "default", operator, after={"error": str(exc)}, result="failed")
            return False, "恢复系统默认配置失败: {}".format(exc)

        health = self.health_service.run_checks()
        self.update_config_pack_state(
            current_pack_id="system_default",
            current_pack_version=self._current_app_version(),
            imported_at=_now_str(),
            imported_by=operator,
            import_mode="restore_default",
            source_file="",
            health_status=str(health.get("summary", {}).get("status_label", "")),
            notes="恢复系统默认配置; backup={}".format(backup_path),
        )
        self._log("restore_default_config", "default", operator, after={"backup_path": backup_path, "health": health.get("summary", {})}, result="success")
        return True, "已恢复系统默认配置"

    def run_health_check(self, operator: str = "admin") -> Dict[str, Any]:
        result = self.health_service.run_checks()
        summary = result.get("summary", {})
        self.update_config_pack_state(
            current_pack_id=str(self.get_current_config_pack_state().get("current_pack_id", "")),
            current_pack_version=str(self.get_current_config_pack_state().get("current_pack_version", "")),
            imported_at=str(self.get_current_config_pack_state().get("imported_at", "")),
            imported_by=str(self.get_current_config_pack_state().get("imported_by", "")),
            import_mode=str(self.get_current_config_pack_state().get("import_mode", "")),
            source_file=str(self.get_current_config_pack_state().get("source_file", "")),
            health_status=str(summary.get("status_label", "")),
            notes=str(self.get_current_config_pack_state().get("notes", "")),
        )
        self._log("config_pack_health_check", "current", operator, after={"summary": summary}, result="success")
        return result

    def get_current_config_pack_state(self) -> Dict[str, Any]:
        self._ensure_config_pack_state_table()
        with self.db_manager.get_connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM config_pack_state
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            health = self.health_service.run_checks()
            return {
                "current_pack_id": "",
                "current_pack_version": "",
                "imported_at": "",
                "imported_by": "",
                "import_mode": "",
                "source_file": "",
                "health_status": str(health.get("summary", {}).get("status_label", "")),
                "notes": "",
            }
        return dict(row)

    def update_config_pack_state(
        self,
        current_pack_id: str,
        current_pack_version: str,
        imported_at: str,
        imported_by: str,
        import_mode: str,
        source_file: str,
        health_status: str,
        notes: str = "",
    ) -> None:
        self._ensure_config_pack_state_table()
        with self.db_manager.get_connection() as conn:
            conn.execute("DELETE FROM config_pack_state")
            conn.execute(
                """
                INSERT INTO config_pack_state (
                    current_pack_id, current_pack_version, imported_at, imported_by,
                    import_mode, source_file, health_status, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    current_pack_id,
                    current_pack_version,
                    imported_at,
                    imported_by,
                    import_mode,
                    source_file,
                    health_status,
                    notes,
                ),
            )
            conn.commit()

    def calculate_checksum(self, pack: Dict[str, Any]) -> str:
        payload = copy.deepcopy(pack)
        payload.pop("_source_file", None)
        payload.pop("_load_error", None)
        payload["checksum"] = ""
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def format_preview_report(self, preview: ConfigPackPreviewResult) -> str:
        lines = [
            "配置包预览报告",
            "配置包编号: {}".format(preview.metadata.get("pack_id", "")),
            "配置包版本: {}".format(preview.metadata.get("pack_version", "")),
            "创建时间: {}".format(preview.metadata.get("created_at", "")),
            "创建人: {}".format(preview.metadata.get("created_by", "")),
            "描述: {}".format(preview.metadata.get("description", "")),
            "",
            "字段统计:",
            "本机字段数: {}".format(preview.local_field_count),
            "配置包字段数: {}".format(preview.pack_field_count),
            "将新增: {}".format(preview.add_count),
            "将更新: {}".format(preview.update_count),
            "完全替换时将停用: {}".format(preview.disable_count),
            "冲突字段: {}".format(preview.conflict_count),
        ]
        if preview.add_fields:
            lines.append("")
            lines.append("新增字段:")
            for row in preview.add_fields:
                lines.append("- {label} / {field_key} / {data_type} / {group_key} / {aggregation}".format(**self._field_report_row(row)))
        if preview.update_fields:
            lines.append("")
            lines.append("更新字段:")
            for row in preview.update_fields:
                lines.append("- {} / {}: {}".format(row.get("label", ""), row.get("field_key", ""), "; ".join(row.get("changes", []))))
        if preview.warnings:
            lines.append("")
            lines.append("风险提示:")
            lines.extend("- {}".format(item) for item in preview.warnings)
        if preview.errors:
            lines.append("")
            lines.append("错误:")
            lines.extend("- {}".format(item) for item in preview.errors)
        return "\n".join(lines)

    def format_import_report(self, result: ConfigPackImportResult) -> str:
        lines = [
            "配置包导入结果: {}".format("成功" if result.success else "失败"),
            "消息: {}".format(result.message),
            "导入模式: {}".format(result.mode),
            "备份文件: {}".format(result.backup_path),
            "新增字段: {}".format(result.added_count),
            "更新字段: {}".format(result.updated_count),
            "停用字段: {}".format(result.disabled_count),
            "更新模板: {}".format(result.templates_updated_count),
            "跳过字段: {}".format(result.skipped_count),
            "冲突字段: {}".format(result.conflict_count),
        ]
        summary = result.health_result.get("summary", {}) if isinstance(result.health_result, dict) else {}
        if summary:
            lines.append("健康检查: {}".format(summary.get("status_label", "")))
        if result.warnings:
            lines.append("")
            lines.append("警告:")
            lines.extend("- {}".format(item) for item in result.warnings)
        if result.errors:
            lines.append("")
            lines.append("错误:")
            lines.extend("- {}".format(item) for item in result.errors)
        return "\n".join(lines)

    def _build_current_pack(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        with self.db_manager.get_connection() as conn:
            field_rows = self._rows_without_id(conn.execute("SELECT * FROM field_definitions ORDER BY id").fetchall())
            visibility_rows = self._rows_without_id(
                conn.execute("SELECT * FROM field_page_visibility ORDER BY page_key, display_order, id").fetchall()
            )
            template_rows = self._rows_without_id(
                conn.execute("SELECT * FROM view_templates ORDER BY page_key, is_default DESC, id").fetchall()
            )
        pack = {
            "pack_type": PACK_TYPE,
            "pack_id": str(metadata.get("pack_id") or "field_config_pack_{}".format(datetime.now().strftime("%Y%m%d_%H%M%S"))),
            "pack_version": str(metadata.get("pack_version") or datetime.now().strftime("%Y.%m.%d")),
            "app_min_version": str(metadata.get("app_min_version") or self._current_app_version()),
            "app_max_version": str(metadata.get("app_max_version") or ""),
            "created_at": str(metadata.get("created_at") or _now_str()),
            "created_by": str(metadata.get("created_by") or "admin"),
            "description": str(metadata.get("description") or ""),
            "checksum": "",
            "field_definitions": field_rows,
            "field_page_visibility": visibility_rows,
            "view_templates": template_rows,
            "png_templates": [row for row in template_rows if str(row.get("page_key", "")) == PAGE_PNG_TODAY],
            "analysis_config": self._derived_page_config(visibility_rows, template_rows, PAGE_ANALYSIS),
            "export_config": self._derived_export_config(visibility_rows),
            "monitoring_config": self._derived_monitoring_config(),
            "field_package_states": self._derived_field_package_states(field_rows),
        }
        return pack

    @staticmethod
    def _rows_without_id(rows: Iterable[Any]) -> List[Dict[str, Any]]:
        result = []
        for row in rows:
            data = dict(row)
            data.pop("id", None)
            result.append(data)
        return result

    @staticmethod
    def _derived_page_config(visibility_rows: List[Dict[str, Any]], template_rows: List[Dict[str, Any]], page_key: str) -> List[Dict[str, Any]]:
        return [
            {
                "page_key": page_key,
                "field_visibility": [row for row in visibility_rows if str(row.get("page_key", "")) == page_key],
                "templates": [row for row in template_rows if str(row.get("page_key", "")) == page_key],
            }
        ]

    @staticmethod
    def _derived_export_config(visibility_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "page_key": page_key,
                "field_visibility": [row for row in visibility_rows if str(row.get("page_key", "")) == page_key],
            }
            for page_key in (PAGE_EXCEL_EXPORT, PAGE_JSON_EXPORT)
        ]

    @staticmethod
    def _derived_monitoring_config() -> List[Dict[str, Any]]:
        return [
            {"rule_key": "weekly_target_progress", "source": "code_default", "configurable": 0},
            {"rule_key": "star_customer_low_streak", "source": "code_default", "configurable": 0},
        ]

    @staticmethod
    def _derived_field_package_states(field_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        enabled_by_key = {str(row.get("field_key", "")): _safe_int(row.get("enabled"), 0) == 1 for row in field_rows}
        packages = {
            "star_customer": ("four_star_customer_count_daily", "five_star_customer_count_daily"),
            "debt_big_order": (
                "debt_case_submit_count_daily",
                "debt_case_repayment_count_daily",
                "debt_case_repayment_amount_daily",
                "large_order_repayment_count_daily",
                "large_order_repayment_amount_daily",
            ),
        }
        return [
            {
                "package_key": package_key,
                "field_keys": list(field_keys),
                "enabled": 1 if all(enabled_by_key.get(field_key, False) for field_key in field_keys) else 0,
            }
            for package_key, field_keys in packages.items()
        ]

    def _validate_version(self, pack: Dict[str, Any], result: ConfigPackValidationResult) -> None:
        app_version = self._current_app_version()
        min_version = str(pack.get("app_min_version", "") or "").strip()
        max_version = str(pack.get("app_max_version", "") or "").strip()
        if min_version and self._compare_versions(app_version, min_version) < 0:
            result.errors.append("程序版本不兼容: 当前版本 {} 低于配置包最低版本 {}".format(app_version, min_version))
            self._log("config_pack_version_rejected", str(pack.get("_source_file", "")), "system", after={"app_version": app_version, "app_min_version": min_version}, result="rejected")
        if max_version and self._compare_versions(app_version, max_version) > 0:
            result.warnings.append("当前程序版本 {} 高于配置包最高建议版本 {}".format(app_version, max_version))

    def _validate_checksum(self, pack: Dict[str, Any], result: ConfigPackValidationResult) -> None:
        expected = str(pack.get("checksum", "") or "").strip()
        actual = self.calculate_checksum(pack)
        result.checksum_expected = expected
        result.checksum_actual = actual
        if not expected:
            result.warnings.append("配置包缺少 checksum")
            return
        if expected != actual:
            result.warnings.append("checksum 不匹配，配置包内容可能已被修改")
            self._log("config_pack_checksum_warning", str(pack.get("_source_file", "")), "system", after={"expected": expected, "actual": actual}, result="warning")

    def _validate_fields(self, pack: Dict[str, Any], result: ConfigPackValidationResult) -> None:
        rows = pack.get("field_definitions", [])
        if not isinstance(rows, list):
            return
        seen: Dict[str, int] = {}
        labels: Dict[str, str] = {}
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                result.errors.append("field_definitions 第 {} 项必须是对象".format(index))
                continue
            field_key = str(row.get("field_key", "") or "").strip()
            label = str(row.get("label", "") or "").strip()
            data_type = str(row.get("data_type", "") or "").strip()
            aggregation = str(row.get("aggregation", "") or "none").strip() or "none"
            category = str(row.get("category", "") or "").strip()
            formula_id = str(row.get("formula_id", "") or "").strip()
            if not field_key:
                result.errors.append("field_definitions 第 {} 项 field_key 不能为空".format(index))
            elif not FIELD_KEY_RE.match(field_key):
                result.errors.append("field_key 格式错误: {}".format(field_key))
            if field_key:
                seen[field_key] = seen.get(field_key, 0) + 1
            if not label:
                result.errors.append("字段 {} label 不能为空".format(field_key or index))
            elif label in labels and labels[label] != field_key:
                result.warnings.append("配置包内部存在同名不同 field_key 字段: {} / {}, {}".format(label, labels[label], field_key))
            else:
                labels[label] = field_key
            if data_type not in DATA_TYPES:
                result.errors.append("字段 {} data_type 不合法: {}".format(field_key, data_type))
            if aggregation not in AGGREGATIONS:
                result.errors.append("字段 {} aggregation 不合法: {}".format(field_key, aggregation))
            if aggregation == "formula":
                formula_key = formula_id or field_key
                if not self.formula_service.is_formula_known(formula_key):
                    result.errors.append("字段 {} formula_id 不合法或缺失".format(field_key))
            elif formula_id and not self.formula_service.is_formula_known(formula_id):
                result.errors.append("字段 {} formula_id 不合法: {}".format(field_key, formula_id))
            elif category == "formula" and not self.formula_service.is_formula_known(field_key):
                result.warnings.append("字段 {} 是派生字段但未声明可识别 formula_id".format(field_key))
        for field_key, count in sorted(seen.items()):
            if count > 1:
                result.errors.append("field_key 重复: {}".format(field_key))

    def _validate_visibility(self, pack: Dict[str, Any], result: ConfigPackValidationResult) -> None:
        fields = {str(row.get("field_key", "")) for row in self._pack_fields(pack)}
        rows = pack.get("field_page_visibility", [])
        if not isinstance(rows, list):
            return
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                result.errors.append("field_page_visibility 第 {} 项必须是对象".format(index))
                continue
            field_key = str(row.get("field_key", "") or "").strip()
            page_key = str(row.get("page_key", "") or "").strip()
            if field_key and field_key not in fields:
                result.errors.append("页面配置引用不存在字段: {}@{}".format(field_key, page_key))
            if page_key and page_key not in PAGE_KEYS:
                result.warnings.append("页面配置包含未知 page_key: {}".format(page_key))

    def _validate_templates(self, pack: Dict[str, Any], result: ConfigPackValidationResult) -> None:
        fields = {str(row.get("field_key", "")) for row in self._pack_fields(pack)}
        rows = pack.get("view_templates", [])
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                result.errors.append("view_templates 存在非对象项")
                continue
            template_key = str(row.get("template_key", "") or "").strip()
            raw = str(row.get("config_json", "{}") or "{}")
            try:
                payload = json.loads(raw)
            except ValueError as exc:
                result.errors.append("模板 {} config_json 非法: {}".format(template_key, exc))
                continue
            for field_key in self._field_keys_from_template_payload(payload):
                if field_key not in fields:
                    result.errors.append("模板 {} 引用不存在字段: {}".format(template_key, field_key))
            if str(row.get("page_key", "") or "") == PAGE_PNG_TODAY:
                for section in payload.get("sections", []) if isinstance(payload.get("sections", []), list) else []:
                    if isinstance(section, dict) and isinstance(section.get("field_keys"), list) and len(section.get("field_keys", [])) > 14:
                        result.warnings.append("PNG 模板 {} 单图字段超过 14 个".format(template_key))

    def _validate_local_label_conflicts(self, pack: Dict[str, Any], result: ConfigPackValidationResult) -> None:
        local_fields = self._list_current_field_definitions()
        local_by_key = {str(row.get("field_key", "")): row for row in local_fields}
        local_by_label = self._fields_by_label(local_fields)
        for conflict in self._detect_label_conflicts(self._pack_fields(pack), local_by_label, local_by_key):
            result.warnings.append(
                "发现同名不同编码字段: 本机 {} / {}; 配置包 {} / {}".format(
                    conflict.label,
                    conflict.local_field_key,
                    conflict.label,
                    conflict.pack_field_key,
                )
            )

    def _apply_add_missing(self, conn: Any, pack: Dict[str, Any], conflict_keys: set) -> Dict[str, int]:
        now = _now_str()
        counts = {"added": 0, "updated": 0, "disabled": 0, "templates": 0, "skipped": 0}
        local_keys = self._local_field_keys(conn)
        for row in self._pack_fields(pack):
            field_key = str(row.get("field_key", "") or "")
            if not field_key:
                continue
            if field_key in conflict_keys:
                counts["skipped"] += 1
                continue
            if field_key in local_keys:
                continue
            self._insert_field(conn, row, now)
            counts["added"] += 1
        return counts

    def _apply_merge_update(self, conn: Any, pack: Dict[str, Any], conflict_keys: set) -> Dict[str, int]:
        now = _now_str()
        counts = {"added": 0, "updated": 0, "disabled": 0, "templates": 0, "skipped": 0}
        local_keys = self._local_field_keys(conn)
        imported_keys = []
        for row in self._pack_fields(pack):
            field_key = str(row.get("field_key", "") or "")
            if not field_key:
                continue
            if field_key in conflict_keys and field_key not in local_keys:
                counts["skipped"] += 1
                continue
            if field_key in local_keys:
                self._upsert_field(conn, row, now)
                counts["updated"] += 1
            else:
                self._insert_field(conn, row, now)
                counts["added"] += 1
            imported_keys.append(field_key)

        if imported_keys:
            placeholders = ",".join(["?" for _ in imported_keys])
            conn.execute("DELETE FROM field_page_visibility WHERE field_key IN ({})".format(placeholders), imported_keys)
        for row in self._pack_visibility(pack):
            if str(row.get("field_key", "")) in conflict_keys:
                continue
            self._insert_visibility(conn, row, now)

        for row in self._pack_templates(pack):
            self._insert_template(conn, row, now, replace=True)
            counts["templates"] += 1
        return counts

    def _apply_replace(self, conn: Any, pack: Dict[str, Any], conflict_keys: set) -> Dict[str, int]:
        now = _now_str()
        counts = {"added": 0, "updated": 0, "disabled": 0, "templates": 0, "skipped": 0}
        local_keys = self._local_field_keys(conn)
        pack_keys = set()
        for row in self._pack_fields(pack):
            field_key = str(row.get("field_key", "") or "")
            if not field_key:
                continue
            if field_key in conflict_keys and field_key not in local_keys:
                counts["skipped"] += 1
                continue
            pack_keys.add(field_key)
            if field_key in local_keys:
                self._upsert_field(conn, row, now)
                counts["updated"] += 1
            else:
                self._insert_field(conn, row, now)
                counts["added"] += 1
        extra_keys = sorted(key for key in local_keys if key not in pack_keys)
        for field_key in extra_keys:
            cursor = conn.execute("UPDATE field_definitions SET enabled = 0, updated_at = ? WHERE field_key = ? AND enabled != 0", (now, field_key))
            counts["disabled"] += int(cursor.rowcount or 0)

        conn.execute("DELETE FROM field_page_visibility")
        for row in self._pack_visibility(pack):
            if str(row.get("field_key", "")) in conflict_keys:
                continue
            self._insert_visibility(conn, row, now)
        conn.execute("DELETE FROM view_templates")
        for row in self._pack_templates(pack):
            self._insert_template(conn, row, now, replace=False)
            counts["templates"] += 1
        return counts

    def _insert_field(self, conn: Any, row: Dict[str, Any], now: str) -> None:
        normalized = self._normalize_field_row(row)
        conn.execute(
            """
            INSERT INTO field_definitions (
                field_key, label, data_type, category, group_key,
                editable, required, default_value, aggregation, formula_id,
                enabled, system_field, storage_type, storage_column, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["field_key"],
                normalized["label"],
                normalized["data_type"],
                normalized["category"],
                normalized["group_key"],
                normalized["editable"],
                normalized["required"],
                normalized["default_value"],
                normalized["aggregation"],
                normalized["formula_id"],
                normalized["enabled"],
                normalized["system_field"],
                normalized["storage_type"],
                normalized["storage_column"],
                now,
                now,
            ),
        )

    def _upsert_field(self, conn: Any, row: Dict[str, Any], now: str, count_update: bool = True) -> None:
        normalized = self._normalize_field_row(row)
        conn.execute(
            """
            INSERT INTO field_definitions (
                field_key, label, data_type, category, group_key,
                editable, required, default_value, aggregation, formula_id,
                enabled, system_field, storage_type, storage_column, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(field_key) DO UPDATE SET
                label = excluded.label,
                data_type = CASE WHEN field_definitions.system_field = 1 THEN field_definitions.data_type ELSE excluded.data_type END,
                category = excluded.category,
                group_key = excluded.group_key,
                editable = excluded.editable,
                required = excluded.required,
                default_value = excluded.default_value,
                aggregation = excluded.aggregation,
                formula_id = excluded.formula_id,
                enabled = excluded.enabled,
                system_field = CASE WHEN field_definitions.system_field = 1 THEN 1 ELSE excluded.system_field END,
                storage_type = CASE WHEN field_definitions.system_field = 1 THEN field_definitions.storage_type ELSE excluded.storage_type END,
                storage_column = CASE WHEN field_definitions.system_field = 1 THEN field_definitions.storage_column ELSE excluded.storage_column END,
                updated_at = excluded.updated_at
            """,
            (
                normalized["field_key"],
                normalized["label"],
                normalized["data_type"],
                normalized["category"],
                normalized["group_key"],
                normalized["editable"],
                normalized["required"],
                normalized["default_value"],
                normalized["aggregation"],
                normalized["formula_id"],
                normalized["enabled"],
                normalized["system_field"],
                normalized["storage_type"],
                normalized["storage_column"],
                now,
                now,
            ),
        )

    @staticmethod
    def _normalize_field_row(row: Dict[str, Any]) -> Dict[str, Any]:
        aggregation = _normalize_text(row.get("aggregation") or "none").strip() or "none"
        storage_type = _normalize_text(row.get("storage_type") or "dynamic_metric").strip() or "dynamic_metric"
        return {
            "field_key": _normalize_text(row.get("field_key")).strip(),
            "label": _normalize_text(row.get("label")).strip(),
            "data_type": _normalize_text(row.get("data_type") or "text").strip(),
            "category": _normalize_text(row.get("category") or "raw_daily").strip(),
            "group_key": _normalize_text(row.get("group_key")).strip(),
            "editable": 1 if _safe_int(row.get("editable"), 0) else 0,
            "required": 1 if _safe_int(row.get("required"), 0) else 0,
            "default_value": _normalize_text(row.get("default_value")),
            "aggregation": aggregation,
            "formula_id": _normalize_text(row.get("formula_id")).strip(),
            "enabled": 1 if _safe_int(row.get("enabled"), 1) else 0,
            "system_field": 1 if _safe_int(row.get("system_field"), 0) else 0,
            "storage_type": storage_type,
            "storage_column": _normalize_text(row.get("storage_column")).strip(),
        }

    def _insert_visibility(self, conn: Any, row: Dict[str, Any], now: str) -> None:
        normalized = {
            "field_key": _normalize_text(row.get("field_key")).strip(),
            "page_key": _normalize_text(row.get("page_key")).strip(),
            "visible": 1 if _safe_int(row.get("visible"), 1) else 0,
            "group_key": _normalize_text(row.get("group_key")).strip(),
            "display_order": _safe_int(row.get("display_order"), 0),
        }
        if not normalized["field_key"] or not normalized["page_key"]:
            return
        conn.execute(
            """
            INSERT INTO field_page_visibility (
                field_key, page_key, visible, group_key, display_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(field_key, page_key) DO UPDATE SET
                visible = excluded.visible,
                group_key = excluded.group_key,
                display_order = excluded.display_order,
                updated_at = excluded.updated_at
            """,
            (
                normalized["field_key"],
                normalized["page_key"],
                normalized["visible"],
                normalized["group_key"],
                normalized["display_order"],
                now,
                now,
            ),
        )

    def _insert_template(self, conn: Any, row: Dict[str, Any], now: str, replace: bool) -> None:
        normalized = {
            "template_key": _normalize_text(row.get("template_key")).strip(),
            "template_name": _normalize_text(row.get("template_name") or row.get("template_key")).strip(),
            "page_key": _normalize_text(row.get("page_key")).strip(),
            "config_json": _normalize_text(row.get("config_json") or "{}"),
            "is_default": 1 if _safe_int(row.get("is_default"), 0) else 0,
            "enabled": 1 if _safe_int(row.get("enabled"), 1) else 0,
        }
        if not normalized["template_key"]:
            return
        if replace:
            conn.execute(
                """
                INSERT INTO view_templates (
                    template_key, template_name, page_key, config_json,
                    is_default, enabled, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(template_key) DO UPDATE SET
                    template_name = excluded.template_name,
                    page_key = excluded.page_key,
                    config_json = excluded.config_json,
                    is_default = excluded.is_default,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized["template_key"],
                    normalized["template_name"],
                    normalized["page_key"],
                    normalized["config_json"],
                    normalized["is_default"],
                    normalized["enabled"],
                    now,
                    now,
                ),
            )
            return
        conn.execute(
            """
            INSERT INTO view_templates (
                template_key, template_name, page_key, config_json,
                is_default, enabled, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["template_key"],
                normalized["template_name"],
                normalized["page_key"],
                normalized["config_json"],
                normalized["is_default"],
                normalized["enabled"],
                now,
                now,
            ),
        )

    def _pack_metadata(self, pack: Dict[str, Any]) -> Dict[str, Any]:
        return {key: pack.get(key, "") for key in ("pack_id", "pack_version", "created_at", "created_by", "description", "app_min_version", "app_max_version")}

    @staticmethod
    def _pack_fields(pack: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows = pack.get("field_definitions", [])
        return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    @staticmethod
    def _pack_visibility(pack: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows = pack.get("field_page_visibility", [])
        return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    @staticmethod
    def _pack_templates(pack: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows = pack.get("view_templates", [])
        return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    def _list_current_field_definitions(self) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            rows = conn.execute("SELECT * FROM field_definitions ORDER BY id").fetchall()
        return self._rows_without_id(rows)

    @staticmethod
    def _local_field_keys(conn: Any) -> set:
        rows = conn.execute("SELECT field_key FROM field_definitions").fetchall()
        return {str(row["field_key"]) for row in rows}

    @staticmethod
    def _fields_by_label(fields: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        result: Dict[str, List[Dict[str, Any]]] = {}
        for row in fields:
            label = str(row.get("label", "") or "").strip()
            if not label:
                continue
            result.setdefault(label, []).append(row)
        return result

    @staticmethod
    def _detect_label_conflicts(
        pack_fields: List[Dict[str, Any]],
        local_by_label: Dict[str, List[Dict[str, Any]]],
        local_by_key: Dict[str, Dict[str, Any]],
    ) -> List[ConfigPackConflict]:
        conflicts = []
        for row in pack_fields:
            field_key = str(row.get("field_key", "") or "")
            label = str(row.get("label", "") or "").strip()
            if not field_key or not label:
                continue
            if field_key in local_by_key:
                continue
            for local in local_by_label.get(label, []):
                local_key = str(local.get("field_key", "") or "")
                if local_key and local_key != field_key:
                    conflicts.append(ConfigPackConflict(label=label, local_field_key=local_key, pack_field_key=field_key))
                    break
        return conflicts

    @staticmethod
    def _field_changes(local: Dict[str, Any], incoming: Dict[str, Any]) -> List[str]:
        changes = []
        normalized = ConfigPackService._normalize_field_row(incoming)
        for key in FIELD_COMPARE_COLUMNS:
            old = _normalize_text(local.get(key))
            new = _normalize_text(normalized.get(key))
            if old != new:
                changes.append("{}: {} -> {}".format(key, old, new))
        return changes

    def _preview_template_changes(self, pack: Dict[str, Any]) -> Dict[str, Any]:
        with self.db_manager.get_connection() as conn:
            local_templates = {
                str(row["template_key"]): dict(row)
                for row in conn.execute("SELECT * FROM view_templates").fetchall()
            }
        changes = {"updated": [], "added": [], "by_page": {}}
        for row in self._pack_templates(pack):
            key = str(row.get("template_key", "") or "")
            page_key = str(row.get("page_key", "") or "")
            local = local_templates.get(key)
            if local is None:
                changes["added"].append(key)
                changes["by_page"][page_key] = True
                continue
            changed = any(_normalize_text(local.get(column)) != _normalize_text(row.get(column)) for column in TEMPLATE_COLUMNS)
            if changed:
                changes["updated"].append(key)
                changes["by_page"][page_key] = True
        for page_key in (PAGE_DATA_ENTRY, PAGE_TODAY_DISPLAY, PAGE_QUERY_SUMMARY, PAGE_PNG_TODAY, PAGE_ANALYSIS):
            changes["by_page"].setdefault(page_key, False)
        return changes

    @staticmethod
    def _field_keys_from_template_payload(payload: Dict[str, Any]) -> List[str]:
        result = []
        for key in ("field_keys", "metric_field_keys"):
            raw = payload.get(key, [])
            if isinstance(raw, list):
                result.extend(str(item) for item in raw if str(item).strip())
        sections = payload.get("sections", [])
        if isinstance(sections, list):
            for section in sections:
                if not isinstance(section, dict):
                    continue
                raw_keys = section.get("field_keys", [])
                if isinstance(raw_keys, list):
                    result.extend(str(item) for item in raw_keys if str(item).strip())
        groups = payload.get("groups", [])
        if isinstance(groups, list):
            for group in groups:
                if not isinstance(group, dict):
                    continue
                raw_keys = group.get("field_keys", [])
                if isinstance(raw_keys, list):
                    result.extend(str(item) for item in raw_keys if str(item).strip())
        return result

    def _current_app_version(self) -> str:
        if self.settings_service is not None:
            getter = getattr(self.settings_service, "get", None)
            if callable(getter):
                value = str(getter("app_version", "") or "").strip()
                if value:
                    return value
        return str(APP_VERSION or "1.0.0")

    @staticmethod
    def _compare_versions(left: str, right: str) -> int:
        def parts(value: str) -> List[int]:
            found = re.findall(r"\d+", str(value or ""))
            return [int(item) for item in found[:4]] or [0]

        l_parts = parts(left)
        r_parts = parts(right)
        max_len = max(len(l_parts), len(r_parts))
        l_parts.extend([0] * (max_len - len(l_parts)))
        r_parts.extend([0] * (max_len - len(r_parts)))
        if l_parts < r_parts:
            return -1
        if l_parts > r_parts:
            return 1
        return 0

    @staticmethod
    def _normalize_import_mode(mode: str) -> str:
        normalized = str(mode or "").strip()
        if normalized in {IMPORT_MODE_ADD_MISSING, IMPORT_MODE_MERGE_UPDATE, IMPORT_MODE_REPLACE}:
            return normalized
        return IMPORT_MODE_MERGE_UPDATE

    def _backup_dir(self) -> Path:
        db_path = getattr(self.db_manager, "db_path", None)
        if db_path:
            return Path(db_path).resolve().parent / "backups" / "config"
        return Path.cwd() / "backups" / "config"

    @staticmethod
    def _field_report_row(row: Dict[str, Any]) -> Dict[str, str]:
        return {
            "field_key": _normalize_text(row.get("field_key")),
            "label": _normalize_text(row.get("label")),
            "data_type": _normalize_text(row.get("data_type")),
            "group_key": _normalize_text(row.get("group_key")),
            "aggregation": _normalize_text(row.get("aggregation")),
        }

    def _ensure_config_pack_state_table(self) -> None:
        with self.db_manager.get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS config_pack_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    current_pack_id TEXT,
                    current_pack_version TEXT,
                    imported_at TEXT,
                    imported_by TEXT,
                    import_mode TEXT,
                    source_file TEXT,
                    health_status TEXT,
                    notes TEXT
                );
                """
            )
            conn.commit()

    def _log(
        self,
        action_type: str,
        target_id: str,
        operator: str,
        before: Optional[Dict[str, Any]] = None,
        after: Optional[Dict[str, Any]] = None,
        result: str = "",
    ) -> None:
        if self.admin_action_log_service is None:
            return
        try:
            note = str(result or "")
            self.admin_action_log_service.log_action(
                action_type=action_type,
                target_type="config_pack",
                target_id=str(target_id or ""),
                operator=str(operator or "admin"),
                before_snapshot=before,
                after_snapshot=after,
                note=note,
            )
        except Exception:
            return
