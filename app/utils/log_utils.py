from __future__ import annotations

import logging
from pathlib import Path

from app.utils.paths import app_data_dir


APP_LOGGER_NAME = "team_report_app"


def _logs_dir() -> Path:
    log_dir = app_data_dir("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def configure_app_logging() -> Path:
    """配置项目级日志输出到 logs/app.log。"""

    log_path = _logs_dir() / "app.log"
    logger = logging.getLogger(APP_LOGGER_NAME)
    logger.setLevel(logging.INFO)

    # 避免重复添加 handler（例如脚本多次调用）。
    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler):
            return log_path

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.propagate = False
    logger.info("应用日志初始化完成")
    return log_path


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{APP_LOGGER_NAME}.{name}")
