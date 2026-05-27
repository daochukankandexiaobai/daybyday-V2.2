from __future__ import annotations

"""Win7 专用 Qt 兼容层（固定 PySide2）。

目标运行环境：Python 3.8 + PySide2 + Windows 7 x64。
本文件不再包含 PySide6 分支或动态 Qt 版本选择逻辑，以提升 PyInstaller 静态分析稳定性。
"""

from typing import Any

from PySide2.QtCore import QByteArray, QDate, QDateTime, QEvent, QModelIndex, QObject, QRect, Qt, QTimer, Signal, Slot  # type: ignore
from PySide2.QtGui import QColor, QFont, QFontMetrics, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap  # type: ignore
from PySide2.QtWidgets import (  # type: ignore
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QStatusBar,
    QStyledItemDelegate,
    QSplitter,
    QTabWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

QT_BINDING = "PySide2"


def app_exec(app: QApplication) -> int:
    """统一应用启动入口（PySide2）。"""
    return int(app.exec_())


def dialog_exec(dialog: QDialog) -> int:
    """统一对话框启动入口（PySide2）。"""
    return int(dialog.exec_())


def qt_enum_value(value: Any) -> int:
    """统一 Qt 枚举值读取。"""
    try:
        return int(value)
    except Exception:  # noqa: BLE001
        raw = getattr(value, "value", value)
        return int(raw)


__all__ = [
    "QT_BINDING",
    "Qt",
    "Signal",
    "Slot",
    "QDate",
    "QDateTime",
    "QByteArray",
    "QEvent",
    "QModelIndex",
    "QObject",
    "QRect",
    "QTimer",
    "QColor",
    "QFont",
    "QFontMetrics",
    "QIcon",
    "QImage",
    "QKeySequence",
    "QPainter",
    "QPen",
    "QPixmap",
    "QAction",
    "QApplication",
    "QCheckBox",
    "QComboBox",
    "QDateEdit",
    "QDialog",
    "QFileDialog",
    "QFrame",
    "QFormLayout",
    "QGridLayout",
    "QGroupBox",
    "QHeaderView",
    "QHBoxLayout",
    "QInputDialog",
    "QLabel",
    "QLineEdit",
    "QListWidget",
    "QListWidgetItem",
    "QMainWindow",
    "QMessageBox",
    "QPushButton",
    "QScrollArea",
    "QShortcut",
    "QSizePolicy",
    "QStatusBar",
    "QStyledItemDelegate",
    "QSplitter",
    "QTabWidget",
    "QTableView",
    "QTableWidget",
    "QTableWidgetItem",
    "QToolButton",
    "QVBoxLayout",
    "QWidget",
    "app_exec",
    "dialog_exec",
    "qt_enum_value",
]
