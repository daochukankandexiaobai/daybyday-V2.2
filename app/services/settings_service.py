from __future__ import annotations

from app.db.repositories import SettingsRepository


class SettingsService:
    def __init__(self, settings_repo: SettingsRepository) -> None:
        self.settings_repo = settings_repo

    def get(self, key: str, default: str = "") -> str:
        return self.settings_repo.get(key, default)

    def set(self, key: str, value: str) -> None:
        self.settings_repo.set(key, value)

    def get_all(self) -> dict[str, str]:
        return self.settings_repo.all_settings()

    def save_basic_settings(self, company_name: str, default_export_dir: str, app_version: str) -> None:
        self.set("company_name", company_name)
        self.set("default_export_dir", default_export_dir)
        self.set("app_version", app_version)

    def get_view_scale_mode(self) -> str:
        mode = self.get("view_scale_mode", "auto").strip().lower()
        if mode not in {"auto", "70%", "100%", "130%"}:
            return "auto"
        return mode

    def set_view_scale_mode(self, mode: str) -> None:
        normalized = (mode or "").strip().lower()
        if normalized not in {"auto", "70%", "100%", "130%"}:
            normalized = "auto"
        self.set("view_scale_mode", normalized)

    def get_view_scale_factor(self) -> float:
        raw = self.get("view_scale_factor", "1.0").strip()
        try:
            value = float(raw)
        except ValueError:
            value = 1.0
        return max(0.5, min(1.8, value))

    def set_view_scale_factor(self, factor: float) -> None:
        self.set("view_scale_factor", f"{max(0.5, min(1.8, float(factor))):.2f}")

    def get_template_version(self) -> str:
        return self.get("template_version", "")

    def set_template_version(self, template_version: str) -> None:
        self.set("template_version", template_version)
        self.set("current_template_version", template_version)

    def is_strict_template_mode(self) -> bool:
        return self.get("strict_template_mode", "1") == "1"

    def set_strict_template_mode(self, strict: bool) -> None:
        self.set("strict_template_mode", "1" if strict else "0")

    def get_schema_version(self) -> str:
        return self.get("schema_version", "")

    def get_business_rules_version(self) -> str:
        return self.get("business_rules_version", "")
