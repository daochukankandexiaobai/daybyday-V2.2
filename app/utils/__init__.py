from app.utils.date_utils import now_iso, resolve_date_range, today_str
from app.utils.hash_utils import hash_record_payload
from app.utils.log_utils import configure_app_logging, get_logger


def install_global_exception_handler(*args, **kwargs):
    from app.utils.error_utils import install_global_exception_handler as _install

    return _install(*args, **kwargs)


__all__ = [
    "today_str",
    "now_iso",
    "resolve_date_range",
    "hash_record_payload",
    "install_global_exception_handler",
    "configure_app_logging",
    "get_logger",
]
