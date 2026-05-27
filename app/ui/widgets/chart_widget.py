from __future__ import annotations

from typing import Any

from app.ui.layout_profile import LayoutProfile
from app.utils.qt_compat import QLabel, QVBoxLayout, QWidget
from app.utils.qt_compat import QT_BINDING

try:
    import matplotlib

    if QT_BINDING == "PySide2":
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    else:
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

    from matplotlib.figure import Figure

    matplotlib.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False
    MATPLOTLIB_AVAILABLE = True
    MATPLOTLIB_ERROR = ""
except Exception as exc:  # noqa: BLE001
    FigureCanvas = None  # type: ignore[assignment]
    Figure = None  # type: ignore[assignment]
    MATPLOTLIB_AVAILABLE = False
    MATPLOTLIB_ERROR = str(exc)


class ChartWidget(QWidget):
    """matplotlib 图表容器（PySide2）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._font_scale = 1.0
        self._last_plot: tuple[str, dict[str, Any]] | None = None
        self._available = bool(MATPLOTLIB_AVAILABLE)
        self._unavailable_reason = str(MATPLOTLIB_ERROR or "").strip()
        self._chart_min_height = 260
        self.setMinimumHeight(self._chart_min_height)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._message_label = QLabel("")
        self._message_label.setWordWrap(True)
        self._message_label.setVisible(False)
        layout.addWidget(self._message_label)

        self.figure = None
        self.canvas = None
        self.axes = None

        if MATPLOTLIB_AVAILABLE:
            self.figure = Figure(figsize=(7.2, 4.2), dpi=100)
            self.canvas = FigureCanvas(self.figure)
            self.axes = self.figure.add_subplot(111)
            layout.addWidget(self.canvas, 1)
            self.clear_chart("暂无数据")
        else:
            detail = f"（{self._unavailable_reason}）" if self._unavailable_reason else ""
            self._show_message(f"未安装或未正确加载 matplotlib，图表不可用{detail}")

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def unavailable_reason(self) -> str:
        return self._unavailable_reason

    def _show_message(self, text: str) -> None:
        self._message_label.setText(text)
        self._message_label.setVisible(True)
        if self.canvas is not None:
            self.canvas.setVisible(False)

    def _show_canvas(self) -> None:
        if self.canvas is None:
            return
        self._message_label.setVisible(False)
        self.canvas.setVisible(True)

    @staticmethod
    def _fmt_number(value: float, as_percent: bool) -> str:
        if as_percent:
            return f"{value * 100:.2f}%"
        if abs(value) >= 1000:
            return f"{value:,.2f}"
        if float(value).is_integer():
            return str(int(value))
        return f"{value:.2f}"

    def _base_font(self, default_size: float) -> float:
        return max(8.0, default_size * float(self._font_scale))

    def _resolve_line_ticks(self, labels: list[str]) -> tuple[list[int], list[str], int]:
        if not labels:
            return [], [], 0
        total = len(labels)
        if total <= 10:
            idx = list(range(total))
            return idx, [labels[i] for i in idx], 0

        target_count = 8
        step = max(1, total // target_count)
        idx = list(range(0, total, step))
        if idx[-1] != total - 1:
            idx.append(total - 1)
        tick_labels = [labels[i] for i in idx]
        rotation = 30 if len(idx) > 6 else 0
        return idx, tick_labels, rotation

    @staticmethod
    def _calc_left_margin(labels: list[str]) -> float:
        if not labels:
            return 0.16
        max_len = max(len(str(item)) for item in labels)
        # 让较长的客户经理名称有足够左边距，不至于被截断
        return min(0.42, max(0.16, 0.11 + max_len * 0.014))

    def clear_chart(self, message: str = "暂无数据") -> None:
        if self.axes is None or self.canvas is None:
            self._show_message(message)
            return
        self._show_canvas()
        self.axes.clear()
        self.axes.set_xticks([])
        self.axes.set_yticks([])
        self.axes.text(
            0.5,
            0.5,
            message,
            ha="center",
            va="center",
            fontsize=self._base_font(11),
            color="#6C757D",
            transform=self.axes.transAxes,
        )
        self.figure.tight_layout()
        self.canvas.draw_idle()
        self._last_plot = ("clear", {"message": message})

    def plot_line(self, dates: list[str], series: list[dict[str, Any]], title: str, y_label: str = "") -> None:
        if self.axes is None or self.canvas is None:
            self._show_message("未安装或未正确加载 matplotlib，图表不可用。")
            return
        if not dates or not series:
            self.clear_chart("当前条件下暂无趋势数据")
            return

        self._show_canvas()
        self.axes.clear()

        x_values = list(range(len(dates)))
        has_data = False
        for line in series:
            label = str(line.get("label", ""))
            values = [float(item or 0) for item in line.get("values", [])]
            if not values:
                continue
            has_data = True
            self.axes.plot(x_values, values, marker="o", linewidth=1.8, markersize=3.5, label=label)

        if not has_data:
            self.clear_chart("当前条件下暂无趋势数据")
            return

        tick_idx, tick_labels, rotation = self._resolve_line_ticks(dates)
        self.axes.set_title(title, fontsize=self._base_font(11), pad=10)
        if y_label:
            self.axes.set_ylabel(y_label, fontsize=self._base_font(9))
        self.axes.set_xticks(tick_idx)
        self.axes.set_xticklabels(tick_labels, rotation=rotation, ha="right" if rotation else "center", fontsize=self._base_font(8))
        self.axes.tick_params(axis="y", labelsize=self._base_font(8))
        self.axes.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.35)
        if len(series) > 1:
            self.axes.legend(loc="best", fontsize=self._base_font(8))

        self.figure.tight_layout()
        self.canvas.draw_idle()
        self._last_plot = (
            "line",
            {
                "dates": list(dates),
                "series": [dict(item) for item in series],
                "title": title,
                "y_label": y_label,
            },
        )

    def plot_horizontal_bar(
        self,
        labels: list[str],
        values: list[float],
        title: str,
        x_label: str = "",
        as_percent: bool = False,
    ) -> None:
        if self.axes is None or self.canvas is None:
            self._show_message("未安装或未正确加载 matplotlib，图表不可用。")
            return
        if not labels or not values:
            self.clear_chart("当前条件下暂无排行数据")
            return

        self._show_canvas()
        self.axes.clear()

        render_labels = list(reversed(labels))
        render_values = list(reversed([float(item or 0) for item in values]))
        y_positions = list(range(len(render_labels)))
        bars = self.axes.barh(y_positions, render_values, color="#2E6EBA")
        self.axes.set_yticks(y_positions)
        self.axes.set_yticklabels(render_labels, fontsize=self._base_font(8))
        self.axes.tick_params(axis="x", labelsize=self._base_font(8))
        self.axes.set_title(title, fontsize=self._base_font(11), pad=10)
        if x_label:
            self.axes.set_xlabel(x_label, fontsize=self._base_font(9))
        self.axes.grid(axis="x", linestyle="--", linewidth=0.6, alpha=0.35)

        max_value = max(render_values) if render_values else 0.0
        offset = max(max_value * 0.02, 0.02 if as_percent else 0.2)
        for bar, value in zip(bars, render_values):
            self.axes.text(
                bar.get_width() + offset,
                bar.get_y() + bar.get_height() / 2.0,
                self._fmt_number(value, as_percent=as_percent),
                va="center",
                fontsize=self._base_font(8),
                color="#1F2D3D",
            )

        left_margin = self._calc_left_margin(render_labels)
        self.figure.subplots_adjust(left=left_margin, right=0.97, top=0.9, bottom=0.14)
        self.canvas.draw_idle()
        self._last_plot = (
            "barh",
            {
                "labels": list(labels),
                "values": list(values),
                "title": title,
                "x_label": x_label,
                "as_percent": as_percent,
            },
        )

    def plot_funnel(self, labels: list[str], values: list[float], title: str) -> None:
        if self.axes is None or self.canvas is None:
            self._show_message("未安装或未正确加载 matplotlib，图表不可用。")
            return
        if not labels or not values:
            self.clear_chart("当前条件下暂无转化数据")
            return

        self._show_canvas()
        self.axes.clear()

        x_positions = list(range(len(labels)))
        values_float = [float(item or 0) for item in values]
        colors = ["#3C7DC4", "#4B8FD4", "#5FA1E0", "#78B3EA", "#8CC0F0"]
        bars = self.axes.bar(x_positions, values_float, color=colors[: len(values_float)])
        self.axes.set_xticks(x_positions)
        self.axes.set_xticklabels(labels, fontsize=self._base_font(8))
        self.axes.tick_params(axis="y", labelsize=self._base_font(8))
        self.axes.set_title(title, fontsize=self._base_font(11), pad=10)
        self.axes.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.35)

        max_value = max(values_float) if values_float else 0.0
        offset = max(max_value * 0.03, 0.2)
        for bar, value in zip(bars, values_float):
            self.axes.text(
                bar.get_x() + bar.get_width() / 2.0,
                bar.get_height() + offset,
                self._fmt_number(value, as_percent=False),
                ha="center",
                va="bottom",
                fontsize=self._base_font(8),
                color="#1F2D3D",
            )

        self.figure.tight_layout()
        self.canvas.draw_idle()
        self._last_plot = ("funnel", {"labels": list(labels), "values": list(values), "title": title})

    def apply_layout_profile(self, profile: LayoutProfile) -> None:
        factor = float(self.window().property("_view_scale_factor") or 1.0) if self.window() is not None else 1.0
        self._chart_min_height = max(220, int(round(profile.metrics.chart_min_height * factor)))
        self.setMinimumHeight(self._chart_min_height)
        if self._last_plot is not None:
            self.apply_view_scale(self._font_scale)

    def apply_view_scale(self, factor: float) -> None:
        self._font_scale = max(0.7, float(factor))
        if self._last_plot is None:
            return

        plot_type, payload = self._last_plot
        if plot_type == "clear":
            self.clear_chart(str(payload.get("message", "暂无数据")))
            return
        if plot_type == "line":
            self.plot_line(
                dates=list(payload.get("dates", [])),
                series=list(payload.get("series", [])),
                title=str(payload.get("title", "")),
                y_label=str(payload.get("y_label", "")),
            )
            return
        if plot_type == "barh":
            self.plot_horizontal_bar(
                labels=list(payload.get("labels", [])),
                values=[float(item or 0) for item in payload.get("values", [])],
                title=str(payload.get("title", "")),
                x_label=str(payload.get("x_label", "")),
                as_percent=bool(payload.get("as_percent", False)),
            )
            return
        if plot_type == "funnel":
            self.plot_funnel(
                labels=list(payload.get("labels", [])),
                values=[float(item or 0) for item in payload.get("values", [])],
                title=str(payload.get("title", "")),
            )
