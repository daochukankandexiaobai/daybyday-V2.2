from __future__ import annotations

from app.utils.qt_compat import Signal
from app.utils.qt_compat import (
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class TemplateTab(QWidget):
    template_changed = Signal()

    def __init__(self, template_service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.template_service = template_service
        self.current_template_id: int | None = None
        self._build_ui()
        self.reload_templates()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        top_btns = QHBoxLayout()
        self.create_btn = QPushButton("新建模板")
        self.activate_btn = QPushButton("设为当前模板")
        self.reload_btn = QPushButton("刷新")
        top_btns.addWidget(self.create_btn)
        top_btns.addWidget(self.activate_btn)
        top_btns.addWidget(self.reload_btn)
        top_btns.addStretch()

        root.addLayout(top_btns)

        self.templates_table = QTableWidget(0, 5)
        self.templates_table.setHorizontalHeaderLabels(["ID", "模板名称", "模板版本", "是否激活", "创建时间"])
        self.templates_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.templates_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.templates_table.setAlternatingRowColors(True)

        field_group = QGroupBox("模板字段配置")
        field_layout = QVBoxLayout(field_group)

        field_btns = QHBoxLayout()
        self.add_field_btn = QPushButton("新增字段")
        self.remove_field_btn = QPushButton("删除字段")
        self.save_fields_btn = QPushButton("保存字段")
        field_btns.addWidget(self.add_field_btn)
        field_btns.addWidget(self.remove_field_btn)
        field_btns.addWidget(self.save_fields_btn)
        field_btns.addStretch()

        self.fields_table = QTableWidget(0, 5)
        self.fields_table.setHorizontalHeaderLabels(["field_key", "field_label", "field_type", "is_required(0/1)", "display_order"])
        self.fields_table.setAlternatingRowColors(True)

        field_layout.addLayout(field_btns)
        field_layout.addWidget(self.fields_table)

        root.addWidget(QLabel("模板列表"))
        root.addWidget(self.templates_table)
        root.addWidget(field_group)

        self.create_btn.clicked.connect(self.on_create_template)
        self.activate_btn.clicked.connect(self.on_activate_template)
        self.reload_btn.clicked.connect(self.reload_templates)
        self.templates_table.itemSelectionChanged.connect(self.on_template_selected)

        self.add_field_btn.clicked.connect(self.on_add_field)
        self.remove_field_btn.clicked.connect(self.on_remove_field)
        self.save_fields_btn.clicked.connect(self.on_save_fields)

    def reload_templates(self) -> None:
        rows = self.template_service.list_templates()
        self.templates_table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            values = [
                str(row.get("id", "")),
                row.get("template_name", ""),
                row.get("template_version", ""),
                "是" if int(row.get("is_active", 0)) == 1 else "否",
                row.get("created_at", ""),
            ]
            for col_idx, value in enumerate(values):
                self.templates_table.setItem(row_idx, col_idx, QTableWidgetItem(value))

        self.templates_table.resizeColumnsToContents()
        if rows:
            self.templates_table.selectRow(0)
            self.on_template_selected()

    def on_template_selected(self) -> None:
        selected = self.templates_table.selectedItems()
        if not selected:
            self.current_template_id = None
            self.fields_table.setRowCount(0)
            return

        row = selected[0].row()
        item = self.templates_table.item(row, 0)
        if item is None:
            return

        self.current_template_id = int(item.text())
        fields = self.template_service.get_fields(self.current_template_id)
        self.fields_table.setRowCount(len(fields))
        for row_idx, field in enumerate(fields):
            values = [
                field.get("field_key", ""),
                field.get("field_label", ""),
                field.get("field_type", "text"),
                str(int(field.get("is_required", 0))),
                str(int(field.get("display_order", row_idx + 1))),
            ]
            for col_idx, value in enumerate(values):
                self.fields_table.setItem(row_idx, col_idx, QTableWidgetItem(value))

        self.fields_table.resizeColumnsToContents()

    def on_create_template(self) -> None:
        name, ok = QInputDialog.getText(self, "新建模板", "模板名称")
        if not ok or not name.strip():
            return

        version, ok = QInputDialog.getText(self, "新建模板", "模板版本号（如 2026.04.01）")
        if not ok or not version.strip():
            return

        make_active = QMessageBox.question(
            self,
            "设为当前模板",
            "创建后是否立即设为当前模板？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes

        success, message = self.template_service.create_template(
            template_name=name.strip(),
            template_version=version.strip(),
            make_active=make_active,
        )
        if success:
            QMessageBox.information(self, "提示", message)
            self.reload_templates()
            if make_active:
                self.template_changed.emit()
        else:
            QMessageBox.warning(self, "失败", message)

    def on_activate_template(self) -> None:
        if self.current_template_id is None:
            QMessageBox.warning(self, "提示", "请先选择一个模板")
            return

        success, message = self.template_service.set_active_template(self.current_template_id)
        if success:
            QMessageBox.information(self, "提示", message)
            self.reload_templates()
            self.template_changed.emit()
        else:
            QMessageBox.warning(self, "失败", message)

    def on_add_field(self) -> None:
        row = self.fields_table.rowCount()
        self.fields_table.insertRow(row)
        defaults = ["new_field", "新字段", "text", "0", str(row + 1)]
        for col, value in enumerate(defaults):
            self.fields_table.setItem(row, col, QTableWidgetItem(value))

    def on_remove_field(self) -> None:
        row = self.fields_table.currentRow()
        if row >= 0:
            self.fields_table.removeRow(row)

    def on_save_fields(self) -> None:
        if self.current_template_id is None:
            QMessageBox.warning(self, "提示", "请先选择模板")
            return

        fields: list[dict] = []
        valid_types = {"text", "int", "date", "textarea"}

        for row in range(self.fields_table.rowCount()):
            field_key = (self.fields_table.item(row, 0).text() if self.fields_table.item(row, 0) else "").strip()
            field_label = (self.fields_table.item(row, 1).text() if self.fields_table.item(row, 1) else "").strip()
            field_type = (self.fields_table.item(row, 2).text() if self.fields_table.item(row, 2) else "text").strip()
            is_required = (self.fields_table.item(row, 3).text() if self.fields_table.item(row, 3) else "0").strip()
            display_order = (self.fields_table.item(row, 4).text() if self.fields_table.item(row, 4) else str(row + 1)).strip()

            if not field_key or not field_label:
                QMessageBox.warning(self, "校验失败", f"第{row + 1}行 field_key/field_label 不能为空")
                return
            if field_type not in valid_types:
                QMessageBox.warning(self, "校验失败", f"第{row + 1}行 field_type 必须是 text/int/date/textarea")
                return

            try:
                required_int = 1 if int(is_required) else 0
                order_int = int(display_order)
            except ValueError:
                QMessageBox.warning(self, "校验失败", f"第{row + 1}行 is_required/display_order 格式错误")
                return

            fields.append(
                {
                    "field_key": field_key,
                    "field_label": field_label,
                    "field_type": field_type,
                    "is_required": required_int,
                    "display_order": order_int,
                }
            )

        success, message = self.template_service.update_template_fields(self.current_template_id, fields)
        if success:
            QMessageBox.information(self, "提示", message)
            self.template_changed.emit()
        else:
            QMessageBox.warning(self, "失败", message)
