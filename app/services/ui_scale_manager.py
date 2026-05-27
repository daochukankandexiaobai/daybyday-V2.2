from __future__ import annotations

from app.utils.qt_compat import QApplication, QFont, QTableWidget, QWidget


class UIScaleManager:
    """统一处理全局视图缩放。"""

    def __init__(self, view_scale_service) -> None:
        self.view_scale_service = view_scale_service

    def apply(self, root_widget: QWidget, mode: str | None = None, persist_mode: bool = False) -> float:
        app = QApplication.instance()
        screen_width = None
        if app is not None:
            screen = app.primaryScreen()
            if screen is not None:
                try:
                    screen_width = int(screen.availableGeometry().width())
                except Exception:  # noqa: BLE001
                    screen_width = None

        actual_mode = self.view_scale_service.normalize_mode(mode) if mode is not None else self.view_scale_service.get_mode()
        factor = float(self.view_scale_service.resolve_factor(actual_mode, screen_width=screen_width))

        if mode is not None and persist_mode:
            self.view_scale_service.save_mode(actual_mode, factor)
        else:
            self.view_scale_service.settings_service.set_view_scale_factor(factor)

        if app is not None:
            self._apply_app_font(app, factor)

        self._scale_layout_tree(root_widget)
        self._scale_widget_tree(root_widget, factor)
        return factor

    @staticmethod
    def _apply_app_font(app: QApplication, factor: float) -> None:
        base_family = app.property("_scale_base_font_family")
        base_size = app.property("_scale_base_font_size")
        if base_family is None or base_size is None:
            current = app.font()
            base_family = current.family()
            size = float(current.pointSizeF() if current.pointSizeF() > 0 else current.pointSize() or 10)
            if size <= 0:
                size = 10.0
            app.setProperty("_scale_base_font_family", base_family)
            app.setProperty("_scale_base_font_size", size)
            base_size = size

        target_size = max(7.0, min(20.0, float(base_size) * factor))
        font = QFont(str(base_family), int(round(target_size)))
        app.setFont(font)

    def _scale_layout_tree(self, root_widget: QWidget) -> None:
        layout = root_widget.layout()
        if layout is None:
            return
        self._scale_layout_recursive(layout, float(self.view_scale_service.settings_service.get_view_scale_factor()))

    def _scale_layout_recursive(self, layout, factor: float) -> None:
        if layout is None:
            return

        base_spacing = layout.property("_scale_base_spacing")
        if base_spacing is None:
            spacing = layout.spacing()
            if spacing < 0:
                spacing = 0
            layout.setProperty("_scale_base_spacing", int(spacing))
            base_spacing = spacing
        layout.setSpacing(max(0, int(round(float(base_spacing) * factor))))

        base_margins = layout.property("_scale_base_margins")
        if base_margins is None:
            margins = layout.contentsMargins()
            base_margins = [margins.left(), margins.top(), margins.right(), margins.bottom()]
            layout.setProperty("_scale_base_margins", base_margins)
        if isinstance(base_margins, (list, tuple)) and len(base_margins) == 4:
            scaled = [max(0, int(round(float(v) * factor))) for v in base_margins]
            layout.setContentsMargins(scaled[0], scaled[1], scaled[2], scaled[3])

        for i in range(layout.count()):
            item = layout.itemAt(i)
            child_layout = item.layout()
            if child_layout is not None:
                self._scale_layout_recursive(child_layout, factor)

    def _scale_widget_tree(self, root_widget: QWidget, factor: float) -> None:
        widgets = [root_widget]
        widgets.extend(root_widget.findChildren(QWidget))
        for widget in widgets:
            self._scale_widget(widget, factor)
            apply_hook = getattr(widget, "apply_view_scale", None)
            if callable(apply_hook):
                try:
                    apply_hook(factor)
                except Exception:  # noqa: BLE001
                    pass

    def _scale_widget(self, widget: QWidget, factor: float) -> None:
        class_name = widget.metaObject().className() if widget.metaObject() is not None else widget.__class__.__name__

        if class_name in {"QPushButton"}:
            self._set_scaled_min_height(widget, factor, default_height=32, minimum_height=22)
        elif class_name in {"QLineEdit", "QComboBox", "QDateEdit"}:
            self._set_scaled_min_height(widget, factor, default_height=30, minimum_height=20)
        elif class_name in {"QGroupBox"}:
            self._set_scaled_min_height(widget, factor, default_height=40, minimum_height=28)

        if isinstance(widget, QTableWidget):
            self._scale_table_widget(widget, factor)

    @staticmethod
    def _set_scaled_min_height(widget: QWidget, factor: float, default_height: int, minimum_height: int) -> None:
        base_height = widget.property("_scale_base_min_height")
        if base_height is None:
            current = int(widget.minimumHeight() or 0)
            base_height = current if current > 0 else default_height
            widget.setProperty("_scale_base_min_height", int(base_height))

        scaled = max(minimum_height, int(round(float(base_height) * factor)))
        widget.setMinimumHeight(scaled)

    @staticmethod
    def _scale_table_widget(table: QTableWidget, factor: float) -> None:
        vh = table.verticalHeader()
        hh = table.horizontalHeader()

        base_row_h = table.property("_scale_base_row_h")
        if base_row_h is None:
            row_h = int(vh.defaultSectionSize() or 0)
            if row_h <= 0:
                row_h = 28
            table.setProperty("_scale_base_row_h", row_h)
            base_row_h = row_h

        base_head_h = table.property("_scale_base_head_h")
        if base_head_h is None:
            head_h = int(hh.height() or 0)
            if head_h <= 0:
                head_h = 34
            table.setProperty("_scale_base_head_h", head_h)
            base_head_h = head_h

        vh.setDefaultSectionSize(max(18, int(round(float(base_row_h) * factor))))
        hh.setMinimumHeight(max(22, int(round(float(base_head_h) * factor))))

