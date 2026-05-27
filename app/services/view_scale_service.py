from __future__ import annotations


class ViewScaleService:
    """全局视图缩放配置服务。"""

    MODE_AUTO = "auto"
    MODE_70 = "70%"
    MODE_100 = "100%"
    MODE_130 = "130%"
    VALID_MODES = (MODE_AUTO, MODE_70, MODE_100, MODE_130)
    MODE_TO_FACTOR = {
        MODE_70: 0.70,
        MODE_100: 1.00,
        MODE_130: 1.30,
    }

    def __init__(self, settings_service) -> None:
        self.settings_service = settings_service

    @classmethod
    def normalize_mode(cls, mode: str | None) -> str:
        text = (mode or "").strip().lower()
        return text if text in cls.VALID_MODES else cls.MODE_AUTO

    def get_mode(self) -> str:
        return self.normalize_mode(self.settings_service.get_view_scale_mode())

    def resolve_factor(self, mode: str | None = None, screen_width: int | None = None) -> float:
        normalized = self.normalize_mode(mode) if mode is not None else self.get_mode()
        if normalized != self.MODE_AUTO:
            return float(self.MODE_TO_FACTOR.get(normalized, 1.0))
        return self.auto_factor(screen_width)

    @staticmethod
    def auto_factor(screen_width: int | None) -> float:
        if screen_width is None:
            return 1.0
        if screen_width <= 1366:
            return 0.70
        if screen_width >= 1920:
            return 1.30
        return 1.00

    def save_mode(self, mode: str, effective_factor: float) -> None:
        normalized = self.normalize_mode(mode)
        self.settings_service.set_view_scale_mode(normalized)
        self.settings_service.set_view_scale_factor(effective_factor)

