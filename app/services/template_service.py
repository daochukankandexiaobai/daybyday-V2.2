from __future__ import annotations

from app.config.field_compat import default_template_fields
from app.db.repositories import TemplateRepository
from app.utils.date_utils import now_iso


DEFAULT_FIELDS = default_template_fields(include_future=False)


class TemplateService:
    def __init__(self, template_repo: TemplateRepository, settings_service) -> None:
        self.template_repo = template_repo
        self.settings_service = settings_service

    def list_templates(self) -> list[dict]:
        return self.template_repo.list_templates()

    def get_active_template(self) -> dict | None:
        return self.template_repo.get_active_template()

    def get_active_template_version(self) -> str:
        active = self.get_active_template()
        if active:
            return active["template_version"]
        return self.settings_service.get("template_version", "")

    def get_fields(self, template_id: int) -> list[dict]:
        return self.template_repo.get_fields(template_id)

    def create_template(
        self,
        template_name: str,
        template_version: str,
        fields: list[dict] | None = None,
        make_active: bool = False,
    ) -> tuple[bool, str]:
        if self.template_repo.get_by_version(template_version):
            return False, "模板版本已存在"

        template_id = self.template_repo.create_template(
            template_name=template_name,
            template_version=template_version,
            is_active=1 if make_active else 0,
            created_at=now_iso(),
        )
        self.template_repo.replace_fields(template_id, fields or DEFAULT_FIELDS)

        if make_active:
            self.template_repo.set_active(template_id)
            self.settings_service.set_template_version(template_version)

        return True, "模板创建成功"

    def set_active_template(self, template_id: int) -> tuple[bool, str]:
        templates = self.template_repo.list_templates()
        target = next((x for x in templates if x["id"] == template_id), None)
        if target is None:
            return False, "模板不存在"

        self.template_repo.set_active(template_id)
        self.settings_service.set_template_version(target["template_version"])
        return True, "已切换当前模板"

    def update_template_fields(self, template_id: int, fields: list[dict]) -> tuple[bool, str]:
        for item in fields:
            if not item.get("field_key") or not item.get("field_label"):
                return False, "字段 key/label 不能为空"
            if item.get("field_type") not in {"text", "int", "date", "textarea"}:
                return False, "字段类型仅支持 text/int/date/textarea"

        self.template_repo.replace_fields(template_id, fields)
        return True, "字段已保存"
