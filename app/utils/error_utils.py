from __future__ import annotations

import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from types import TracebackType

from app.utils.qt_compat import QApplication, QMessageBox


def _logs_dir() -> Path:
    base_dir = Path(__file__).resolve().parents[2]
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _write_exception_log(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType | None,
    context: str,
) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_part = datetime.now().strftime("%Y%m%d")
    log_path = _logs_dir() / f"error_{date_part}.log"

    detail = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    content = (
        f"[{timestamp}] context={context}\n"
        f"{detail}\n"
        f"{'-' * 88}\n"
    )
    with log_path.open("a", encoding="utf-8") as f:
        f.write(content)
    return log_path


def _show_friendly_error(exc_value: BaseException, log_path: Path) -> None:
    app = QApplication.instance()
    if app is None:
        return

    QMessageBox.critical(
        None,
        "程序异常",
        (
            "程序发生未处理异常，已记录到错误日志。\n"
            f"日志文件：{log_path}\n"
            f"异常信息：{exc_value}"
        ),
    )


def _handle_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType | None,
    context: str,
) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    try:
        log_path = _write_exception_log(exc_type, exc_value, exc_traceback, context)
    except Exception:  # noqa: BLE001
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    if context == "main_thread":
        try:
            _show_friendly_error(exc_value, log_path)
        except Exception:  # noqa: BLE001
            pass

    sys.__excepthook__(exc_type, exc_value, exc_traceback)


def install_global_exception_handler() -> None:
    """安装全局异常处理：错误日志 + 友好弹窗。"""

    def _sys_hook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        _handle_exception(exc_type, exc_value, exc_traceback, context="main_thread")

    def _thread_hook(args: threading.ExceptHookArgs) -> None:
        thread_name = getattr(args.thread, "name", "thread")
        _handle_exception(args.exc_type, args.exc_value, args.exc_traceback, context=f"thread:{thread_name}")

    sys.excepthook = _sys_hook
    if hasattr(threading, "excepthook"):
        threading.excepthook = _thread_hook
