from controllers.auth_controller import AuthController
from models.user_model import UserModel
from utils.exceptions import ValidationError

PERM_GESTIONAR = "users.manage"


class UserController:
    def __init__(self):
        self.model = UserModel()
        self.auth = AuthController()

    # ---------- helpers ----------
    @staticmethod
    def _require(current_user: dict) -> None:
        AuthController.require_permission(current_user, PERM_GESTIONAR)

    def _get_or_fail(self, user_id: str):
        user = self.model.get_by_id(user_id)
        if not user:
            raise ValidationError("Usuario no encontrado.")
        return user

    def _can_manage(self, role_id: str) -> bool:
        return PERM_GESTIONAR in self.auth._permissions(role_id)

    def _ensure_not_last_admin(self, target) -> None:
        """No permite quitar (desactivar, eliminar o cambiar de rol) al último
        usuario activo cuyo rol puede gestionar usuarios."""
        if not (target["is_active"] and self._can_manage(target["role_id"])):
            return
        others = [u for u in self.model.list_all(include_inactive=False)
                  if u["id"] != target["id"]]
        if not any(self._can_manage(u["role_id"]) for u in others):
            raise ValidationError("No puedes dejar el sistema sin un administrador activo.")

    # ---------- consultas ----------
    def list_users(self, current_user: dict):
        self._require(current_user)
        return self.model.list_all()

    def list_roles(self, current_user: dict):
        self._require(current_user)
        return self.model.list_roles()

    def list_branches(self, current_user: dict):
        self._require(current_user)
        return self.model.list_branches()

    # ---------- altas y cambios ----------
    def create_user(self, current_user: dict, *, username, full_name, role_id, pin,
                    branch_id=None, email=None, phone=None) -> str:
        self._require(current_user)
        if not (username or "").strip() or not (full_name or "").strip():
            raise ValidationError("Usuario y nombre completo son obligatorios.")
        if not role_id:
            raise ValidationError("Selecciona un rol.")
        pin = self.auth._normalize_pin(pin)          # valida 4-8 dígitos
        return self.model.create(username=username, full_name=full_name, role_id=role_id,
                                 pin=pin, branch_id=branch_id, email=email, phone=phone)

    def update_user(self, current_user: dict, user_id: str, **fields) -> None:
        self._require(current_user)
        target = self._get_or_fail(user_id)
        is_self = user_id == current_user["id"]

        deactivating = fields.get("is_active") in (0, False)
        role_changing = "role_id" in fields and fields["role_id"] != target["role_id"]

        if is_self and deactivating:
            raise ValidationError("No puedes desactivar tu propio usuario.")
        if is_self and role_changing:
            raise ValidationError("No puedes cambiar tu propio rol.")
        if deactivating or role_changing:
            self._ensure_not_last_admin(target)
        self.model.update(user_id, **fields)

    def reset_pin(self, current_user: dict, user_id: str, new_pin: str) -> None:
        self._require(current_user)
        self._get_or_fail(user_id)
        self.auth.set_user_pin(user_id, new_pin)     # valida, hashea y limpia el bloqueo

    def unlock_user(self, current_user: dict, user_id: str) -> None:
        self._require(current_user)
        self._get_or_fail(user_id)
        self.model.unlock(user_id)

    def delete_user(self, current_user: dict, user_id: str) -> None:
        self._require(current_user)
        target = self._get_or_fail(user_id)
        if user_id == current_user["id"]:
            raise ValidationError("No puedes eliminar tu propio usuario.")
        self._ensure_not_last_admin(target)
        self.model.soft_delete(user_id)