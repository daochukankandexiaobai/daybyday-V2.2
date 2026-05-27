from __future__ import annotations

from app.db.repositories import AdminUserRepository
from app.utils.date_utils import now_iso
from app.utils.hash_utils import generate_salt, hash_password, verify_password


class AuthService:
    def __init__(self, admin_repo: AdminUserRepository) -> None:
        self.admin_repo = admin_repo

    def login(self, username: str, password: str) -> bool:
        user = self.admin_repo.get_by_username(username.strip())
        if user is None:
            return False
        return verify_password(password, user["salt"], user["password_hash"])

    def change_password(self, username: str, old_password: str, new_password: str) -> tuple[bool, str]:
        user = self.admin_repo.get_by_username(username.strip())
        if user is None:
            return False, "用户不存在"
        if not verify_password(old_password, user["salt"], user["password_hash"]):
            return False, "旧密码错误"
        if len(new_password) < 6:
            return False, "新密码长度至少6位"

        salt = generate_salt()
        pwd_hash = hash_password(new_password, salt)
        self.admin_repo.update_password(username, pwd_hash, salt, now_iso())
        return True, "密码修改成功"
