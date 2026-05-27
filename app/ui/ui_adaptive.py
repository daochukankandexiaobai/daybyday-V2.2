from __future__ import annotations

from app.ui.layout_profile import LayoutProfile, resolve_layout_profile
from app.utils.qt_compat import QWidget


class UIAdaptiveCoordinator:
    """Centralized adaptive layout dispatcher based on window width."""

    def __init__(self, root_widget: QWidget) -> None:
        self.root_widget = root_widget
        self.current_profile: LayoutProfile | None = None

    def apply_for_width(self, width: int, force: bool = False) -> LayoutProfile:
        profile = resolve_layout_profile(width)
        if not force and self.current_profile is not None and self.current_profile.mode == profile.mode:
            return self.current_profile

        self.current_profile = profile
        widgets: list[QWidget] = [self.root_widget]
        widgets.extend(self.root_widget.findChildren(QWidget))
        for widget in widgets:
            hook = getattr(widget, "apply_layout_profile", None)
            if callable(hook):
                try:
                    hook(profile)
                except Exception:  # noqa: BLE001
                    pass
        return profile

