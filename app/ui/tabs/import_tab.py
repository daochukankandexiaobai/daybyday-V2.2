from __future__ import annotations

from app.utils.qt_compat import Signal
from app.utils.qt_compat import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.utils.date_utils import settlement_cycle_display_code


class ImportTab(QWidget):
    import_finished = Signal()
    view_import_data_requested = Signal(dict)

    def __init__(self, import_service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.import_service = import_service
        self.preview_rows: list[dict] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        self.select_btn = QPushButton("选择JSON文件")
        self.preview_btn = QPushButton("导入预览")
        self.clear_btn = QPushButton("清空列表")
        self.import_btn = QPushButton("确认导入")
        self.allow_mismatch = QCheckBox("允许模板版本不一致导入（管理员）")

        top.addWidget(self.select_btn)
        top.addWidget(self.preview_btn)
        top.addWidget(self.clear_btn)
        top.addWidget(self.import_btn)
        top.addWidget(self.allow_mismatch)
        top.addStretch()

        self.file_list = QListWidget()

        self.preview_table = QTableWidget(0, 11)
        self.preview_table.setHorizontalHeaderLabels(
            [
                "文件名",
                "export_id",
                "模板版本",
                "团队",
                "结算周期",
                "记录数",
                "开始日期",
                "结束日期",
                "版本匹配",
                "状态",
                "消息",
            ]
        )

        self.result_table = QTableWidget(0, 6)
        self.result_table.setHorizontalHeaderLabels(["导入时间", "文件名", "模板版本", "结果", "影响记录数", "消息"])

        root.addLayout(top)
        root.addWidget(QLabel("待导入文件"))
        root.addWidget(self.file_list)
        root.addWidget(QLabel("导入预览"))
        root.addWidget(self.preview_table)
        root.addWidget(QLabel("导入结果"))
        root.addWidget(self.result_table)

        self.select_btn.clicked.connect(self.on_select_files)
        self.preview_btn.clicked.connect(self.on_preview)
        self.clear_btn.clicked.connect(self.on_clear)
        self.import_btn.clicked.connect(self.on_import)

    def on_select_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "选择 JSON 文件", "", "JSON Files (*.json)")
        for file_path in files:
            if not self._exists(file_path):
                self.file_list.addItem(file_path)

    def _exists(self, file_path: str) -> bool:
        for i in range(self.file_list.count()):
            if self.file_list.item(i).text() == file_path:
                return True
        return False

    def _paths(self) -> list[str]:
        return [self.file_list.item(i).text() for i in range(self.file_list.count())]

    def on_preview(self) -> None:
        paths = self._paths()
        if not paths:
            QMessageBox.warning(self, "提示", "请先选择文件")
            return

        self.preview_rows = self.import_service.preview_files(paths)
        self._render_preview(self.preview_rows)

        valid = sum(1 for x in self.preview_rows if x.get("is_valid"))
        mismatch = sum(1 for x in self.preview_rows if x.get("is_valid") and not x.get("template_match"))
        QMessageBox.information(self, "预览完成", f"文件总数：{len(paths)}\n可导入：{valid}\n模板不匹配：{mismatch}")

    def on_clear(self) -> None:
        self.file_list.clear()
        self.preview_rows.clear()
        self.preview_table.setRowCount(0)
        self.result_table.setRowCount(0)

    def on_import(self) -> None:
        paths = self._paths()
        if not paths:
            QMessageBox.warning(self, "提示", "请先选择文件")
            return

        if not self.preview_rows or len(self.preview_rows) != len(paths):
            self.preview_rows = self.import_service.preview_files(paths)
            self._render_preview(self.preview_rows)

        valid_rows = [x for x in self.preview_rows if x.get("is_valid")]
        valid_paths = [x.get("file_path", "") for x in valid_rows if x.get("file_path")]
        if not valid_paths:
            QMessageBox.warning(self, "提示", "无可导入文件，请先修复预览错误")
            return

        mismatch = sum(1 for x in valid_rows if not x.get("template_match"))
        answer = QMessageBox.question(
            self,
            "确认导入",
            f"将导入 {len(valid_paths)} 个文件\n模板不匹配文件：{mismatch}\n是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        results = self.import_service.import_files(
            file_paths=valid_paths,
            allow_template_mismatch=self.allow_mismatch.isChecked(),
        )
        self._render_results(results)
        self.import_finished.emit()

        detail = [x for x in results if str(x.get("message", "")).startswith("第")]
        success = sum(1 for x in detail if x.get("result") in {"success", "updated"})
        failed = sum(1 for x in detail if x.get("result") == "failed")
        conflict = sum(1 for x in detail if x.get("result") == "conflict")
        skipped = sum(1 for x in detail if x.get("result") == "skipped")
        QMessageBox.information(
            self,
            "导入完成",
            f"明细条数：{len(detail)}\n成功/更新：{success}\n跳过：{skipped}\n失败：{failed}\n冲突：{conflict}",
        )

        if success > 0:
            context = self._build_view_context(valid_rows)
            if context["team_names"]:
                answer = QMessageBox.question(
                    self,
                    "查看导入数据",
                    "是否切换到查询汇总页查看本次导入数据？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if answer == QMessageBox.Yes:
                    self.view_import_data_requested.emit(context)

    def _render_preview(self, rows: list[dict]) -> None:
        self.preview_table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            if not row.get("is_valid"):
                status = "不可导入"
            elif row.get("template_match"):
                status = "可导入"
            else:
                status = "模板不匹配"

            values = [
                row.get("file_name", ""),
                row.get("export_id", ""),
                row.get("template_version", ""),
                row.get("team_name", ""),
                settlement_cycle_display_code(cycle_code=str(row.get("cycle_code", ""))),
                str(row.get("record_count", 0)),
                row.get("start_date", ""),
                row.get("end_date", ""),
                "是" if row.get("template_match") else "否",
                status,
                row.get("message", ""),
            ]
            for col_idx, value in enumerate(values):
                self.preview_table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))
        self.preview_table.resizeColumnsToContents()

    def _render_results(self, rows: list[dict]) -> None:
        self.result_table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            values = [
                row.get("import_time", ""),
                row.get("file_name", ""),
                row.get("template_version", ""),
                row.get("result", ""),
                str(row.get("affected_record_count", 0)),
                row.get("message", ""),
            ]
            for col_idx, value in enumerate(values):
                self.result_table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))
        self.result_table.resizeColumnsToContents()

    @staticmethod
    def _build_view_context(valid_rows: list[dict]) -> dict:
        team_names = sorted(
            {str(row.get("team_name", "")).strip() for row in valid_rows if str(row.get("team_name", "")).strip()}
        )
        start_dates = sorted(
            [str(row.get("start_date", "")).strip() for row in valid_rows if str(row.get("start_date", "")).strip()]
        )
        end_dates = sorted(
            [str(row.get("end_date", "")).strip() for row in valid_rows if str(row.get("end_date", "")).strip()]
        )
        return {
            "team_names": team_names,
            "start_date": start_dates[0] if start_dates else "",
            "end_date": end_dates[-1] if end_dates else "",
        }
