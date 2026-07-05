from __future__ import annotations

from pathlib import Path

from app.utils.qt_compat import Qt
from app.utils.qt_compat import QAction, QFont, QIcon, QPixmap, dialog_exec
from app.utils.qt_compat import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.layout_profile import LayoutProfile
from app.ui.login_dialog import LoginDialog
from app.ui.tabs.admin_action_logs_tab import AdminActionLogsTab
from app.ui.tabs.admin_team_manage_tab import AdminTeamManageTab
from app.ui.tabs.analysis_tab import AnalysisTab
from app.ui.tabs.conflict_tab import ConflictTab
from app.ui.tabs.entry_tab import EntryTab
from app.ui.tabs.export_tab import ExportTab
from app.ui.tabs.field_report_config_tab import FieldReportConfigTab
from app.ui.tabs.import_tab import ImportTab
from app.ui.tabs.local_data_manage_tab import LocalDataManageTab
from app.ui.tabs.logs_tab import LogsTab
from app.ui.tabs.legacy_migration_tab import LegacyMigrationTab
from app.ui.tabs.missing_check_tab import MissingCheckTab
from app.ui.tabs.preview_tab import PreviewTab
from app.ui.tabs.query_tab import QueryTab
from app.ui.tabs.settings_tab import SettingsTab
from app.ui.tabs.summary_tab import SummaryTab
from app.ui.tabs.team_setup_tab import TeamSetupTab
from app.ui.tabs.template_tab import TemplateTab
from app.ui.ui_adaptive import UIAdaptiveCoordinator


class MainWindow(QMainWindow):
    def __init__(self, services: dict, db_path: str, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        self.db_path = db_path
        self.admin_unlocked = False
        self.admin_username = ""
        self.view_scale_service = self.services["view_scale_service"]
        self.ui_scale_manager = self.services["ui_scale_manager"]
        self.view_actions: dict[str, QAction] = {}
        self.ui_adaptive = UIAdaptiveCoordinator(self)
        self._layout_profile: LayoutProfile | None = None

        self.setWindowTitle("团队经理日报管理系统 V2.3.1 -win7")
        self.resize(1420, 900)
        self.setProperty("_view_scale_factor", float(self.services["settings_service"].get_view_scale_factor() or 1.0))

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.ElideNone)
        self.tabs.tabBar().setObjectName("mainNavTabBar")
        self.tabs.tabBar().setUsesScrollButtons(True)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setElideMode(Qt.ElideNone)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.tabBar().setDocumentMode(True)
        self.central = QWidget()
        self.central_layout = QVBoxLayout(self.central)
        self.central_layout.setContentsMargins(10, 10, 10, 10)
        self.central_layout.setSpacing(8)

        self.brand_bar = self._build_brand_bar()
        self.central_layout.addWidget(self.brand_bar)
        self.central_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(self.central)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self._apply_window_branding()
        self._build_tabs()
        self._build_menu()
        self._refresh_admin_status()

        # 核心注入：应用现代UI主题
        self._apply_modern_theme()
        self.apply_view_scale(self.view_scale_service.get_mode(), persist_mode=False)
        self._apply_layout_profile(force=True)

    @staticmethod
    def _logo_path() -> Path:
        return Path(__file__).resolve().parents[2] / "assets" / "银税logo.png"

    def _build_brand_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("brandBar")

        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(8)

        self.brand_logo = QLabel()
        self.brand_logo.setObjectName("brandLogo")
        self.brand_logo.setFixedSize(28, 28)
        self.brand_logo.setAlignment(Qt.AlignCenter)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)

        self.brand_title = QLabel("银税团队经理日报系统")
        self.brand_title.setObjectName("brandTitle")
        self.brand_subtitle = QLabel("离线填报 · 本地保存 · 导入汇总")
        self.brand_subtitle.setObjectName("brandSubtitle")

        text_col.addWidget(self.brand_title)
        text_col.addWidget(self.brand_subtitle)

        row.addWidget(self.brand_logo)
        row.addLayout(text_col)
        row.addStretch()
        return bar

    def _apply_window_branding(self) -> None:
        logo_path = self._logo_path()
        if not logo_path.exists():
            return

        icon = QIcon(str(logo_path))
        self.setWindowIcon(icon)
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(icon)

        pixmap = QPixmap(str(logo_path))
        if pixmap.isNull():
            return
        size = max(20, int(self.brand_logo.width() or 30))
        self._refresh_brand_logo(size)

    def _refresh_brand_logo(self, side: int) -> None:
        logo_path = self._logo_path()
        if not logo_path.exists():
            self.brand_logo.clear()
            return
        pixmap = QPixmap(str(logo_path))
        if pixmap.isNull():
            self.brand_logo.clear()
            return
        side_px = max(20, int(side))
        self.brand_logo.setFixedSize(side_px, side_px)
        scaled = pixmap.scaled(side_px - 4, side_px - 4, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.brand_logo.setPixmap(scaled)

    def _apply_modern_theme(self) -> None:
        """注入白/暗红配色的现代企业级QSS样式"""
        # 1. 设置全局现代无衬线字体
        font = QFont("Microsoft YaHei", 10)
        font.setStyleHint(QFont.StyleHint.SansSerif)
        QApplication.setFont(font)

        # 2. 核心QSS样式表
        qss = """
        /* === 全局底层 === */
        QWidget {
            color: #2C3E50;
            background-color: #F4F6F9; /* 浅灰底色衬托白色卡片 */
        }

        /* === 主窗口与状态栏 === */
        QMainWindow {
            background-color: #F4F6F9;
        }
        QStatusBar {
            background-color: #FFFFFF;
            color: #6C7A89;
            border-top: 1px solid #E0E4E8;
        }
        QMenuBar {
            background-color: #FFFFFF;
            border-bottom: 1px solid #E0E4E8;
        }
        QMenuBar::item:selected {
            background-color: #FDF0F2;
            color: #9A1622;
        }

        /* === 顶部导航选项卡 === */
        QTabWidget::pane {
            border: 1px solid #E0E4E8;
            background: #FFFFFF; /* 卡片白底 */
            border-radius: 6px;
            margin: 6px;
        }
        #brandBar {
            background: #FFFFFF;
            border: 1px solid #E0E4E8;
            border-radius: 6px;
        }
        QLabel#brandTitle {
            color: #9A1622;
            font-size: 15px;
            font-weight: bold;
        }
        QLabel#brandSubtitle {
            color: #6C7A89;
            font-size: 10px;
        }
        QTabBar::tab {
            background: transparent;
            color: #6C7A89;
            padding: 8px 18px;
            font-size: 13px;
            font-weight: bold;
            border: none;
            border-bottom: 3px solid transparent;
            margin-top: 2px;
        }
        QTabBar::tab:hover {
            color: #9A1622;
            background-color: #FDF0F2;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
        }
        QTabBar::tab:selected {
            color: #9A1622; /* 主题暗红 */
            background-color: #FFF7F8;
            border-bottom: 3px solid #9A1622;
        }
        QTabWidget#chartTabs::pane {
            margin: 2px;
            border: 1px solid #E3E8EF;
            border-radius: 4px;
        }
        QTabWidget#chartTabs QTabBar::tab {
            padding: 6px 14px;
            font-size: 12px;
            min-width: 54px;
        }

        /* === 按钮体系：默认次按钮，按 buttonRole 切换主/危险按钮 === */
        QPushButton {
            background-color: #FFFFFF;
            color: #344054;
            border: 1px solid #CBD5E1;
            padding: 6px 14px;
            border-radius: 4px;
            font-weight: 600;
        }
        QPushButton:hover {
            background-color: #FFF7F8;
            color: #9A1622;
            border: 1px solid #D48790;
        }
        QPushButton:pressed {
            background-color: #FDECEF;
        }
        QPushButton[buttonRole="primary"] {
            background-color: #9A1622;
            color: #FFFFFF;
            border: 1px solid #9A1622;
        }
        QPushButton[buttonRole="primary"]:hover {
            background-color: #B31A28;
            color: #FFFFFF;
            border: 1px solid #B31A28;
        }
        QPushButton[buttonRole="primary"]:pressed {
            background-color: #7A111A;
            border: 1px solid #7A111A;
        }
        QPushButton[buttonRole="danger"] {
            background-color: #FFF1F2;
            color: #B42318;
            border: 1px solid #F1B7B4;
        }
        QPushButton[buttonRole="danger"]:hover {
            background-color: #FFE4E6;
            color: #9F1B13;
            border: 1px solid #DC6B67;
        }
        QPushButton[buttonRole="danger"]:pressed {
            background-color: #FEE2E2;
        }
        QPushButton[buttonRole="ghost"] {
            background-color: transparent;
            color: #9A1622;
            border: 1px solid transparent;
            padding: 4px 10px;
        }
        QPushButton[buttonRole="ghost"]:hover {
            background-color: #FFF7F8;
            border: 1px solid #F1B7B4;
        }
        QPushButton:disabled {
            background-color: #EEF2F7;
            color: #98A2B3;
            border: 1px solid #D9DEE7;
        }

        /* === 输入框与下拉菜单 === */
        QLineEdit, QComboBox, QSpinBox, QDateEdit, QTextEdit {
            padding: 6px 12px;
            border: 1px solid #DCDFE6;
            border-radius: 4px;
            background-color: #FFFFFF;
            selection-background-color: #9A1622;
        }
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus, QTextEdit:focus {
            border: 1px solid #9A1622; /* 激活态边框变红 */
        }
        QComboBox::drop-down {
            border: none;
        }

        /* === 区块、KPI 与提示文本 === */
        QGroupBox {
            background-color: #FFFFFF;
            border: 1px solid #E3E8EF;
            border-radius: 6px;
            margin-top: 10px;
            font-weight: 700;
            color: #25364A;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0px 4px;
            color: #25364A;
            background-color: #FFFFFF;
        }
        QWidget#toolbarPanel {
            background-color: #FFFFFF;
            border: 1px solid #E3E8EF;
            border-radius: 6px;
        }
        QWidget#kpiCard, QWidget#analysisKpiCard {
            background-color: #F8FAFC;
            border: 1px solid #E3E8EF;
            border-radius: 6px;
        }
        QLabel#kpiTitle, QLabel#summaryTitle {
            color: #667085;
            font-size: 11px;
            background: transparent;
        }
        QLabel#kpiValue, QLabel#summaryValue {
            color: #1F2937;
            font-size: 16px;
            font-weight: 700;
            background: transparent;
        }
        QLabel#hintText {
            color: #667085;
            background: transparent;
        }
        QLabel#statusText {
            color: #667085;
            font-weight: 600;
            background: transparent;
        }

        /* === 数据表格 === */
        QTableView, QTableWidget {
            background-color: #FFFFFF;
            alternate-background-color: #F8FAFC;
            border: 1px solid #E3E8EF;
            border-radius: 4px;
            gridline-color: #F0F2F5;
            selection-background-color: #FDF0F2; /* 选中行浅红底 */
            selection-color: #9A1622;
            outline: none;
        }
        QHeaderView::section {
            background-color: #F1F5F9;
            color: #334155;
            font-weight: bold;
            padding: 6px;
            border: none;
            border-bottom: 1px solid #CBD5E1;
            border-right: 1px solid #F0F2F5;
        }

        /* === 滚动条美化 (去除系统原生粗糙感) === */
        QScrollBar:vertical {
            border: none;
            background: #F0F2F5;
            width: 8px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #C0C4CC;
            min-height: 30px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical:hover {
            background: #909399;
        }
        """
        self.setStyleSheet(qss)

    def _build_tabs(self) -> None:
        self.team_setup_tab = TeamSetupTab(
            self.services["team_service"],
            weekly_target_service=self.services.get("weekly_target_service"),
            admin_team_service=self.services["admin_team_service"],
            operator_getter=self.get_admin_operator,
        )
        self.entry_tab = EntryTab(self.services["record_service"], self.services["team_service"])
        self.preview_tab = PreviewTab(
            self.services["record_service"],
            self.services["team_service"],
            self.services["settings_service"],
            self.services["report_image_service"],
            target_alert_service=self.services.get("target_alert_service"),
            star_customer_alert_service=self.services.get("star_customer_alert_service"),
        )
        self.query_tab = QueryTab(
            self.services["record_service"],
            self.services["team_service"],
            self.services["analytics_service"],
            target_alert_service=self.services.get("target_alert_service"),
            star_customer_alert_service=self.services.get("star_customer_alert_service"),
            settings_service=self.services.get("settings_service"),
            report_image_service=self.services.get("report_image_service"),
        )
        self.analysis_tab = AnalysisTab(
            self.services["record_service"],
            self.services["team_service"],
            self.services["analytics_service"],
        )
        self.export_tab = ExportTab(
            self.services["export_service"],
            self.services["settings_service"],
            self.services["team_service"],
        )

        self.import_tab = ImportTab(self.services["import_service"])
        self.legacy_migration_tab = LegacyMigrationTab(
            self.services["legacy_migration_service"],
            operator_getter=self.get_admin_operator,
        )
        self.conflict_tab = ConflictTab(self.services["import_service"])
        self.missing_check_tab = MissingCheckTab(self.services["import_service"], self.services["settings_service"])
        self.summary_tab = SummaryTab(
            self.services["summary_service"],
            self.services["excel_service"],
            self.services["settings_service"],
        )
        self.template_tab = TemplateTab(self.services["template_service"])
        self.settings_tab = SettingsTab(
            self.services["settings_service"],
            self.services["auth_service"],
            self.services["template_service"],
            self.services["view_scale_service"],
            db_path=self.db_path,
        )
        self.logs_tab = LogsTab(self.services["import_service"])
        self.admin_team_manage_tab = AdminTeamManageTab(
            admin_team_service=self.services["admin_team_service"],
            team_service=self.services["team_service"],
            operator_getter=self.get_admin_operator,
        )
        self.local_data_manage_tab = LocalDataManageTab(
            admin_data_service=self.services["admin_data_service"],
            operator_getter=self.get_admin_operator,
        )
        self.admin_action_logs_tab = AdminActionLogsTab(self.services["admin_action_log_service"])
        self.field_report_config_tab = FieldReportConfigTab(
            self.services["field_admin_config_service"],
            operator_getter=self.get_admin_operator,
        )

        self.manager_tabs = [
            ("基础设置", self.team_setup_tab),
            ("数据录入", self.entry_tab),
            ("今日展示", self.preview_tab),
            ("查询汇总", self.query_tab),
            ("数据分析", self.analysis_tab),
            ("JSON导出", self.export_tab),
        ]
        self.admin_tabs = [
            ("团队配置管理", self.admin_team_manage_tab),
            ("字段与报表配置", self.field_report_config_tab),
            ("本地数据管理", self.local_data_manage_tab),
            ("JSON导入", self.import_tab),
            ("数据迁移（旧版JSON）", self.legacy_migration_tab),
            ("冲突记录", self.conflict_tab),
            ("导入缺失检查", self.missing_check_tab),
            ("公司汇总", self.summary_tab),
            ("模板配置", self.template_tab),
            ("系统设置", self.settings_tab),
            ("导入日志", self.logs_tab),
            ("管理员操作日志", self.admin_action_logs_tab),
        ]

        for title, widget in self.manager_tabs:
            self.tabs.addTab(widget, title)
        self._refresh_tab_tooltips()

        self.team_setup_tab.config_saved.connect(self.on_team_config_saved)
        self.team_setup_tab.team_archived.connect(self.on_admin_team_changed)
        self.team_setup_tab.team_archived.connect(self.admin_action_logs_tab.on_query)
        self.entry_tab.record_saved.connect(self.preview_tab.refresh)
        self.entry_tab.record_saved.connect(self.query_tab.on_query)
        self.entry_tab.record_saved.connect(self.analysis_tab.on_query)

        self.import_tab.import_finished.connect(self.logs_tab.on_query)
        self.import_tab.import_finished.connect(self.conflict_tab.on_query)
        self.import_tab.import_finished.connect(self.missing_check_tab.on_query)
        self.import_tab.import_finished.connect(self.team_setup_tab.reload_teams)
        self.import_tab.import_finished.connect(self.entry_tab.reload_teams)
        self.import_tab.import_finished.connect(self.preview_tab.reload_teams)
        self.import_tab.import_finished.connect(self.preview_tab.refresh)
        self.import_tab.import_finished.connect(self.query_tab.reload_teams)
        self.import_tab.import_finished.connect(self.query_tab.on_query)
        self.import_tab.import_finished.connect(self.analysis_tab.reload_teams)
        self.import_tab.import_finished.connect(self.analysis_tab.on_query)
        self.import_tab.import_finished.connect(self.export_tab.reload_teams)
        self.import_tab.import_finished.connect(self.admin_team_manage_tab.reload_teams)
        self.import_tab.import_finished.connect(self.local_data_manage_tab.reload_team_filters)
        self.import_tab.import_finished.connect(self.local_data_manage_tab.on_query)
        self.import_tab.view_import_data_requested.connect(self.on_view_import_data_requested)
        self.legacy_migration_tab.migration_finished.connect(self.logs_tab.on_query)
        self.legacy_migration_tab.migration_finished.connect(self.team_setup_tab.reload_teams)
        self.legacy_migration_tab.migration_finished.connect(self.entry_tab.reload_teams)
        self.legacy_migration_tab.migration_finished.connect(self.preview_tab.reload_teams)
        self.legacy_migration_tab.migration_finished.connect(self.preview_tab.refresh)
        self.legacy_migration_tab.migration_finished.connect(self.query_tab.reload_teams)
        self.legacy_migration_tab.migration_finished.connect(self.query_tab.on_query)
        self.legacy_migration_tab.migration_finished.connect(self.analysis_tab.reload_teams)
        self.legacy_migration_tab.migration_finished.connect(self.analysis_tab.on_query)
        self.legacy_migration_tab.migration_finished.connect(self.local_data_manage_tab.reload_team_filters)
        self.legacy_migration_tab.migration_finished.connect(self.local_data_manage_tab.on_query)

        self.admin_team_manage_tab.team_changed.connect(self.on_admin_team_changed)
        self.admin_team_manage_tab.team_changed.connect(self.admin_action_logs_tab.on_query)

        self.local_data_manage_tab.records_changed.connect(self.preview_tab.refresh)
        self.local_data_manage_tab.records_changed.connect(self.query_tab.on_query)
        self.local_data_manage_tab.records_changed.connect(self.analysis_tab.on_query)
        self.local_data_manage_tab.records_changed.connect(self.admin_action_logs_tab.on_query)

        self.field_report_config_tab.config_changed.connect(self.on_field_config_changed)
        self.field_report_config_tab.config_changed.connect(self.admin_action_logs_tab.on_query)
        self.template_tab.template_changed.connect(self.settings_tab.load_settings)
        self.settings_tab.view_scale_changed.connect(self.on_view_scale_changed_from_settings)

    def on_team_config_saved(self, team_id: int) -> None:
        self.services["team_service"].set_current_team_id(team_id)
        self.entry_tab.reload_teams()
        self.preview_tab.reload_teams()
        self.query_tab.reload_teams()
        self.analysis_tab.reload_teams()
        self.export_tab.reload_teams()
        self.admin_team_manage_tab.reload_teams()
        self.local_data_manage_tab.reload_team_filters()

    def on_admin_team_changed(self) -> None:
        self.team_setup_tab.reload_teams()
        self.entry_tab.reload_teams()
        self.preview_tab.reload_teams()
        self.query_tab.reload_teams()
        self.analysis_tab.reload_teams()
        self.export_tab.reload_teams()
        self.local_data_manage_tab.reload_team_filters()

    def on_field_config_changed(self) -> None:
        reload_entry = getattr(self.entry_tab, "reload_field_config", None)
        if callable(reload_entry):
            reload_entry()
        reload_preview = getattr(self.preview_tab, "reload_field_config", None)
        if callable(reload_preview):
            reload_preview()
        reload_query = getattr(self.query_tab, "reload_field_config", None)
        if callable(reload_query):
            reload_query()
        reload_analysis = getattr(self.analysis_tab, "reload_field_config", None)
        if callable(reload_analysis):
            reload_analysis()

    def on_view_import_data_requested(self, context: dict) -> None:
        tab_index = self.tabs.indexOf(self.query_tab)
        if tab_index >= 0:
            self.tabs.setCurrentIndex(tab_index)
        apply_context = getattr(self.query_tab, "apply_import_context", None)
        if callable(apply_context):
            apply_context(context)
        else:
            self.query_tab.reload_teams()
            self.query_tab.on_query()

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        admin_menu = menubar.addMenu("管理员")

        self.login_action = QAction("管理员登录", self)
        self.lock_action = QAction("锁定管理员功能", self)

        admin_menu.addAction(self.login_action)
        admin_menu.addAction(self.lock_action)

        self.login_action.triggered.connect(self.on_admin_login)
        self.lock_action.triggered.connect(self.lock_admin_tabs)

        self._build_view_menu(menubar)

    def _build_view_menu(self, menubar) -> None:
        view_menu = menubar.addMenu("视图")
        mode_items = [
            ("自动", "auto"),
            ("70%", "70%"),
            ("100%", "100%"),
            ("130%", "130%"),
        ]
        for text, mode in mode_items:
            action = QAction(text, self)
            action.setCheckable(True)
            action.triggered.connect(lambda *_, m=mode: self.on_view_mode_selected(m))
            view_menu.addAction(action)
            self.view_actions[mode] = action
        self._update_view_menu_checks(self.view_scale_service.get_mode())

    def on_admin_login(self) -> None:
        if self.admin_unlocked:
            QMessageBox.information(self, "提示", "管理员功能已解锁")
            return

        dialog = LoginDialog(self.services["auth_service"], self)
        if dialog_exec(dialog) == LoginDialog.Accepted:
            self.admin_username = dialog.username_edit.text().strip() or "admin"
            self.unlock_admin_tabs()

    def unlock_admin_tabs(self) -> None:
        if self.admin_unlocked:
            return
        for title, widget in self.admin_tabs:
            self.tabs.addTab(widget, title)
        self._refresh_tab_tooltips()
        self.admin_unlocked = True
        self._refresh_admin_status()

    def lock_admin_tabs(self) -> None:
        if not self.admin_unlocked:
            return

        for _, widget in self.admin_tabs:
            index = self.tabs.indexOf(widget)
            if index >= 0:
                self.tabs.removeTab(index)
        self.admin_unlocked = False
        self.admin_username = ""
        self._refresh_admin_status()

    def get_admin_operator(self) -> str:
        return self.admin_username or "admin"

    def _refresh_admin_status(self) -> None:
        factor = self.services["settings_service"].get_view_scale_factor()
        scale_text = f"{factor:.2f}x"
        if self.admin_unlocked:
            self.status.showMessage(f"当前状态：管理员已解锁 | 视图缩放 {scale_text}")
            self.login_action.setEnabled(False)
            self.lock_action.setEnabled(True)
        else:
            self.status.showMessage(f"当前状态：经理模式 | 视图缩放 {scale_text}")
            self.login_action.setEnabled(True)
            self.lock_action.setEnabled(False)

    def _persist_view_preferences(self) -> None:
        for widget in [getattr(self, "entry_tab", None)]:
            persist = getattr(widget, "persist_table_view_state", None)
            if callable(persist):
                try:
                    persist()
                except Exception:  # noqa: BLE001
                    pass

    def closeEvent(self, event) -> None:  # noqa: N802
        self._persist_view_preferences()
        self.lock_admin_tabs()
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_layout_profile(force=False)

    def _update_view_menu_checks(self, mode: str) -> None:
        for key, action in self.view_actions.items():
            action.blockSignals(True)
            action.setChecked(key == mode)
            action.blockSignals(False)

    def _refresh_tab_tooltips(self) -> None:
        for i in range(self.tabs.count()):
            self.tabs.setTabToolTip(i, self.tabs.tabText(i))

    def on_view_mode_selected(self, mode: str) -> None:
        self.apply_view_scale(mode, persist_mode=True)

    def on_view_scale_changed_from_settings(self, mode: str) -> None:
        self.apply_view_scale(mode, persist_mode=True)

    def apply_view_scale(self, mode: str, persist_mode: bool) -> None:
        factor = self.ui_scale_manager.apply(self, mode=mode, persist_mode=persist_mode)
        self.setProperty("_view_scale_factor", float(factor))
        self._apply_layout_profile(force=True)
        self._update_view_menu_checks(self.view_scale_service.normalize_mode(mode))
        self.status.showMessage(f"当前状态：{'管理员已解锁' if self.admin_unlocked else '经理模式'} | 视图缩放 {factor:.2f}x")

    def _apply_layout_profile(self, force: bool) -> None:
        self.ui_adaptive.apply_for_width(self.width(), force=force)

    @staticmethod
    def _scaled(value: int, factor: float, floor: int) -> int:
        return max(floor, int(round(float(value) * float(factor))))

    def apply_layout_profile(self, profile: LayoutProfile) -> None:
        self._layout_profile = profile
        metrics = profile.metrics
        factor = float(self.property("_view_scale_factor") or 1.0)

        page_margin = self._scaled(metrics.page_margin, factor, floor=4)
        page_spacing = self._scaled(metrics.page_spacing, factor, floor=4)
        self.central_layout.setContentsMargins(page_margin, page_margin, page_margin, page_margin)
        self.central_layout.setSpacing(page_spacing)

        bar_layout = self.brand_bar.layout()
        if bar_layout is not None:
            padding_h = self._scaled(metrics.brand_padding_h, factor, floor=4)
            padding_v = self._scaled(metrics.brand_padding_v, factor, floor=2)
            bar_layout.setContentsMargins(padding_h, padding_v, padding_h, padding_v)
            bar_layout.setSpacing(self._scaled(metrics.section_spacing, factor, floor=4))

        self._refresh_brand_logo(self._scaled(metrics.brand_logo_size, factor, floor=20))

        title_font = QFont(self.brand_title.font())
        title_font.setPointSize(self._scaled(metrics.brand_title_font, factor, floor=10))
        self.brand_title.setFont(title_font)

        subtitle_font = QFont(self.brand_subtitle.font())
        subtitle_font.setPointSize(self._scaled(metrics.brand_subtitle_font, factor, floor=8))
        self.brand_subtitle.setFont(subtitle_font)

        tab_font_px = self._scaled(metrics.nav_tab_font, factor, floor=10)
        tab_padding_h = self._scaled(metrics.nav_tab_padding_h, factor, floor=10)
        tab_padding_v = self._scaled(metrics.nav_tab_padding_v, factor, floor=5)
        tab_height = max(28, tab_font_px + tab_padding_v * 2 + 2)
        tab_min_width = max(86, tab_padding_h * 2 + tab_font_px * 2)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.ElideNone)
        self.tabs.tabBar().setUsesScrollButtons(True)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setElideMode(Qt.ElideNone)
        self.tabs.tabBar().setMinimumHeight(tab_height)
        self.tabs.tabBar().setMaximumHeight(tab_height + 4)
        self.tabs.tabBar().setStyleSheet(
            "\n".join(
                [
                    "QTabBar#mainNavTabBar::tab {",
                    "  background: transparent;",
                    "  color: #6C7A89;",
                    f"  padding: {tab_padding_v}px {tab_padding_h}px;",
                    f"  font-size: {tab_font_px}px;",
                    "  font-weight: 700;",
                    f"  min-height: {tab_height}px;",
                    f"  min-width: {tab_min_width}px;",
                    "  border: none;",
                    "  border-bottom: 3px solid transparent;",
                    "  margin-top: 2px;",
                    "}",
                    "QTabBar#mainNavTabBar::tab:hover {",
                    "  color: #9A1622;",
                    "  background-color: #FDF0F2;",
                    "  border-top-left-radius: 6px;",
                    "  border-top-right-radius: 6px;",
                    "}",
                    "QTabBar#mainNavTabBar::tab:selected {",
                    "  color: #9A1622;",
                    "  background-color: #FFF7F8;",
                    "  border-bottom: 3px solid #9A1622;",
                    "}",
                ]
            )
        )
        self._refresh_tab_tooltips()
