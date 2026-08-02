from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict

from app.fields.config_pack_service import (
    IMPORT_MODE_ADD_MISSING,
    IMPORT_MODE_MERGE_UPDATE,
    IMPORT_MODE_REPLACE,
)
from app.utils.qt_compat import (
    QButtonGroup,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    Qt,
    Signal,
)


class ConfigPackTab(QWidget):
    config_changed = Signal()

    def __init__(self, config_pack_service, operator_getter=None, parent=None) -> None:
        super().__init__(parent)
        self.config_pack_service = config_pack_service
        self.operator_getter = operator_getter
        self.state_labels: Dict[str, QLabel] = {}
        self.mode_group = QButtonGroup(self)
        self._build_ui()
        self.reload_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Vertical)
        splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(splitter, 1)

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(6)

        top_layout.addWidget(self._build_state_group())
        top_layout.addWidget(self._build_operation_group())
        top_layout.addWidget(self._build_mode_group())
        top_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(top)
        splitter.addWidget(scroll)

        report_group = QGroupBox("结果报告")
        report_layout = QVBoxLayout(report_group)
        self.report_edit = QTextEdit()
        self.report_edit.setReadOnly(True)
        self.report_edit.setLineWrapMode(QTextEdit.NoWrap)
        self.report_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        report_layout.addWidget(self.report_edit)
        splitter.addWidget(report_group)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    def _build_state_group(self) -> QGroupBox:
        group = QGroupBox("当前配置状态")
        grid = QGridLayout(group)
        items = [
            ("current_pack_id", "当前配置包编号"),
            ("current_pack_version", "当前配置包版本"),
            ("imported_at", "最近导入时间"),
            ("imported_by", "最近导入人"),
            ("import_mode", "导入模式"),
            ("health_status", "配置健康状态"),
        ]
        for index, (key, label) in enumerate(items):
            row = index // 2
            col = (index % 2) * 2
            name_label = QLabel(label)
            value_label = QLabel("-")
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value_label.setWordWrap(True)
            self.state_labels[key] = value_label
            grid.addWidget(name_label, row, col)
            grid.addWidget(value_label, row, col + 1)
        return group

    def _build_operation_group(self) -> QGroupBox:
        group = QGroupBox("配置包操作")
        grid = QGridLayout(group)
        buttons = [
            ("导出当前配置包", self.on_export_pack),
            ("预览配置包", self.on_preview_pack),
            ("导入配置包", self.on_import_pack),
            ("恢复上次导入前配置", self.on_restore_backup),
            ("恢复系统默认配置", self.on_restore_default),
            ("运行配置健康检查", self.on_health_check),
        ]
        for index, (text, handler) in enumerate(buttons):
            button = QPushButton(text)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            if "恢复系统默认" in text:
                button.setProperty("buttonRole", "danger")
            elif "导入" in text or "恢复" in text:
                button.setProperty("buttonRole", "secondary")
            button.clicked.connect(handler)
            grid.addWidget(button, index // 3, index % 3)
        return group

    def _build_mode_group(self) -> QGroupBox:
        group = QGroupBox("导入模式选择")
        layout = QHBoxLayout(group)
        modes = [
            (IMPORT_MODE_ADD_MISSING, "仅新增缺失字段"),
            (IMPORT_MODE_MERGE_UPDATE, "合并更新配置（推荐）"),
            (IMPORT_MODE_REPLACE, "完全替换字段配置"),
        ]
        for index, (mode, label) in enumerate(modes):
            radio = QRadioButton(label)
            radio.setProperty("importMode", mode)
            radio.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.mode_group.addButton(radio, index)
            layout.addWidget(radio)
            if mode == IMPORT_MODE_MERGE_UPDATE:
                radio.setChecked(True)
        layout.addStretch()
        return group

    def reload_state(self) -> None:
        state = self.config_pack_service.get_current_config_pack_state()
        for key, label in self.state_labels.items():
            label.setText(str(state.get(key, "") or "-"))

    def on_export_pack(self) -> None:
        operator = self._operator()
        default_pack_id = "field_config_pack_{}".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
        pack_id, ok = QInputDialog.getText(self, "配置包编号", "请输入配置包编号：", text=default_pack_id)
        if not ok or not str(pack_id).strip():
            return
        description, ok = QInputDialog.getText(self, "配置包描述", "请输入配置包描述：", text="")
        if not ok:
            return
        created_by, ok = QInputDialog.getText(self, "创建人", "请输入创建人：", text=operator)
        if not ok or not str(created_by).strip():
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出当前配置包",
            "{}.json".format(str(pack_id).strip()),
            "JSON Files (*.json)",
        )
        if not file_path:
            return
        ok, message = self.config_pack_service.export_config_pack(
            file_path,
            {
                "pack_id": str(pack_id).strip(),
                "pack_version": datetime.now().strftime("%Y.%m.%d"),
                "created_by": str(created_by).strip(),
                "description": str(description),
            },
        )
        if not ok:
            QMessageBox.warning(self, "导出失败", message)
            self.report_edit.setPlainText(message)
            return
        QMessageBox.information(self, "导出成功", "配置包已导出：\n{}".format(message))
        self.report_edit.setPlainText("配置包已导出：\n{}".format(message))

    def on_preview_pack(self) -> None:
        file_path = self._select_json_file("预览配置包")
        if not file_path:
            return
        pack = self.config_pack_service.load_config_pack(file_path)
        preview = self.config_pack_service.preview_config_pack(pack, operator=self._operator())
        self.report_edit.setPlainText(self.config_pack_service.format_preview_report(preview))
        if preview.errors:
            QMessageBox.warning(self, "预览发现错误", "配置包存在错误，不能导入。")

    def on_import_pack(self) -> None:
        file_path = self._select_json_file("导入配置包")
        if not file_path:
            return
        pack = self.config_pack_service.load_config_pack(file_path)
        preview = self.config_pack_service.preview_config_pack(pack, operator=self._operator())
        self.report_edit.setPlainText(self.config_pack_service.format_preview_report(preview))
        if preview.errors:
            QMessageBox.warning(self, "导入失败", "配置包校验失败，不能导入。")
            return
        if preview.warnings:
            if QMessageBox.question(
                self,
                "确认导入",
                "配置包存在警告，建议先查看预览报告。是否继续导入？",
            ) != QMessageBox.Yes:
                return
        mode = self._selected_mode()
        if mode == IMPORT_MODE_REPLACE:
            if QMessageBox.question(
                self,
                "强确认",
                "完全替换字段配置会按配置包重置字段显示顺序、页面模板和导出模板，但不会删除历史日报数据。是否继续？",
            ) != QMessageBox.Yes:
                return
        result = self.config_pack_service.import_config_pack(
            pack,
            mode=mode,
            operator=self._operator(),
            source_file=file_path,
        )
        self.report_edit.setPlainText(self.config_pack_service.format_import_report(result))
        self.reload_state()
        if not result.success:
            QMessageBox.warning(self, "导入失败", result.message)
            return
        QMessageBox.information(self, "导入完成", result.message)
        self.config_changed.emit()

    def on_restore_backup(self) -> None:
        path = self.config_pack_service.latest_backup_path()
        if not path:
            QMessageBox.information(self, "提示", "未找到可恢复的导入前配置备份。")
            return
        if QMessageBox.question(
            self,
            "确认恢复",
            "将恢复最近一次导入前配置：\n{}\n\n不会删除历史日报数据。是否继续？".format(path),
        ) != QMessageBox.Yes:
            return
        ok, message = self.config_pack_service.restore_config_from_backup(path, operator=self._operator())
        self.report_edit.setPlainText(message)
        self.reload_state()
        if not ok:
            QMessageBox.warning(self, "恢复失败", message)
            return
        QMessageBox.information(self, "恢复完成", message)
        self.config_changed.emit()

    def on_restore_default(self) -> None:
        if QMessageBox.question(
            self,
            "强确认",
            "恢复默认配置会覆盖当前字段显示顺序、页面模板和导出模板，但不会删除历史日报数据。是否继续？",
        ) != QMessageBox.Yes:
            return
        ok, message = self.config_pack_service.restore_default_config(operator=self._operator())
        self.report_edit.setPlainText(message)
        self.reload_state()
        if not ok:
            QMessageBox.warning(self, "恢复失败", message)
            return
        QMessageBox.information(self, "恢复完成", message)
        self.config_changed.emit()

    def on_health_check(self) -> None:
        result = self.config_pack_service.run_health_check(operator=self._operator())
        summary = result.get("summary", {})
        lines = [
            "配置健康检查",
            "状态: {}".format(summary.get("status_label", "")),
            "错误: {}".format(summary.get("error_count", 0)),
            "警告: {}".format(summary.get("warning_count", 0)),
            "",
        ]
        for item in result.get("items", []):
            lines.append("[{level}] {title}: {detail}".format(**item))
        self.report_edit.setPlainText("\n".join(lines))
        self.reload_state()

    def _selected_mode(self) -> str:
        button = self.mode_group.checkedButton()
        if button is None:
            return IMPORT_MODE_MERGE_UPDATE
        return str(button.property("importMode") or IMPORT_MODE_MERGE_UPDATE)

    def _select_json_file(self, title: str) -> str:
        file_path, _ = QFileDialog.getOpenFileName(self, title, "", "JSON Files (*.json)")
        return str(Path(file_path)) if file_path else ""

    def _operator(self) -> str:
        if callable(self.operator_getter):
            return str(self.operator_getter() or "admin")
        return "admin"
