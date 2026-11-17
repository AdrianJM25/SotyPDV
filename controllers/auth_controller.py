import logging
import math
import time
from datetime import datetime, timezone

from models.base_model import BaseModel
from utils.exceptions import AuthError, LockedError, PermissionDenied, ValidationError
from utils.security import hash_pin, is_legacy_hash, verify_pin

log = logging.getLogger(__name__)


class AuthController(BaseModel):
    """Inicio de sesión con USERNAME + PIN. Varios usuarios pueden compartir el mismo PIN:
    la identidad la da el username y el PIN solo se verifica contra el hash de ese usuario.

    * El PIN se valida (solo dígitos, 4-8) antes de tocar la BD.
    * sha256 sin sal -> scrypt con sal; los usuarios antiguos se migran solos al iniciar sesión.
    * Anti fuerza bruta POR USERNAME (existente o no): 5 fallos seguidos bloquean 30 s, 1 min, 5 min, 15 min.
    * Se respeta `pin_locked_until` (bloqueo puesto por un administrador) y roles eliminados.
    * Devuelve los permisos del rol para que la UI oculte/deshabilite lo que no corresponde.
    """

    PIN_MIN_LEN = 4
    PIN_MAX_LEN = 8
    MAX_ATTEMPTS = 5
    LOCK_SECONDS = (30, 60, 300, 900)
    GENERIC_ERROR = "Usuario o PIN incorrectos."

    _dummy_hash: str | None = None   # para igualar tiempos cuando el usuario no existe

    def __init__(self):
        super().__init__()
        # username(minúsculas) -> {"failures": int, "level": int, "locked_until": monotonic}
        self._throttle: dict[str, dict] = {}

    # ------------------------------------------------------------------ API pública
    def login(self, username: str, entered_pin: str) -> dict:
        """Devuelve {id, name, username, branch_id, role_id, role_name, permissions[]}.
        Lanza ValidationError / AuthError / LockedError."""
        user = self._authenticate(username, entered_pin)
        pin = entered_pin.strip()
        self._after_successful_login(user, pin)
        log.info("Login exitoso: %s (%s)", user["username"], user["role_name"])
        return self._session_user(user)

    def authorize_supervisor(self, username: str, pin: str, permission: str) -> dict:
        """Autorización puntual (cancelar venta, descuento...): un supervisor teclea SU usuario y PIN
        sin cerrar la sesión del cajero. Devuelve los datos del supervisor que autorizó."""
        user = self._authenticate(username, pin)
        if permission not in self._permissions(user["role_id"]):
            raise PermissionDenied("Ese usuario no tiene permiso para autorizar esta acción.")
        log.info("Autorización '%s' concedida por %s", permission, user["username"])
        return self._session_user(user)

    @staticmethod
    def has_permission(user_data: dict | None, permission: str) -> bool:
        return bool(user_data) and permission in user_data.get("permissions", [])

    @classmethod
    def require_permission(cls, user_data: dict | None, permission: str) -> None:
        if not cls.has_permission(user_data, permission):
            raise PermissionDenied("No tienes permiso para realizar esta acción.")

    def set_user_pin(self, user_id: str, new_pin: str) -> None:
        pin = self._normalize_pin(new_pin)
        if not self.cursor.execute("SELECT 1 FROM users WHERE id = ? AND deleted_at IS NULL",
                                   (user_id,)).fetchone():
            raise AuthError("Usuario no encontrado.")
        now = self.get_timestamp()
        try:
            self.cursor.execute(
                "UPDATE users SET pin_hash = ?, pin_failed_attempts = 0, pin_locked_until = NULL, "
                "updated_at = ?, sync_status = 0 WHERE id = ?", (hash_pin(pin), now, user_id))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    # ------------------------------------------------------------------ núcleo de autenticación
    def _authenticate(self, username: str, pin: str):
        username = self._normalize_username(username)
        pin = self._normalize_pin(pin)
        self._check_throttle(username)

        user = self._find_user(username)
        if user is None:
            verify_pin(pin, self._get_dummy_hash())          # mismo costo que un usuario real
            self._register_failure(username, None)           # siempre lanza
        if not verify_pin(pin, user["pin_hash"]):
            self._register_failure(username, user["id"])     # siempre lanza

        self._check_user_not_locked(user)
        self._reset_throttle(username)
        return user

    # ------------------------------------------------------------------ validación
    @staticmethod
    def _normalize_username(username) -> str:
        if not isinstance(username, str) or not username.strip():
            raise ValidationError("Ingresa tu usuario.")
        return username.strip().lower()

    def _normalize_pin(self, pin) -> str:
        if not isinstance(pin, str):
            raise ValidationError("Ingresa tu PIN.")
        pin = pin.strip()
        if not pin:
            raise ValidationError("Ingresa tu PIN.")
        if not pin.isascii() or not pin.isdigit():
            raise ValidationError("El PIN solo contiene números.")
        if not self.PIN_MIN_LEN <= len(pin) <= self.PIN_MAX_LEN:
            raise ValidationError(f"El PIN debe tener entre {self.PIN_MIN_LEN} y {self.PIN_MAX_LEN} dígitos.")
        return pin

    # ------------------------------------------------------------------ throttle por username
    def _state(self, username: str) -> dict:
        return self._throttle.setdefault(username, {"failures": 0, "level": 0, "locked_until": 0.0})

    def _check_throttle(self, username: str) -> None:
        remaining = self._state(username)["locked_until"] - time.monotonic()
        if remaining > 0:
            raise LockedError(f"Demasiados intentos fallidos. Espera {math.ceil(remaining)} segundos.")

    def _register_failure(self, username: str, user_id: str | None) -> None:
        st = self._state(username)
        st["failures"] += 1
        log.warning("Login fallido para '%s' (%d/%d)", username, st["failures"], self.MAX_ATTEMPTS)
        if user_id:
            self._bump_failed_attempts(user_id)
        if st["failures"] >= self.MAX_ATTEMPTS:
            seconds = self.LOCK_SECONDS[min(st["level"], len(self.LOCK_SECONDS) - 1)]
            st["level"] += 1
            st["failures"] = 0
            st["locked_until"] = time.monotonic() + seconds
            raise LockedError(f"Demasiados intentos fallidos. Login bloqueado {seconds} segundos.")
        raise AuthError(f"{self.GENERIC_ERROR} Intentos restantes: {self.MAX_ATTEMPTS - st['failures']}.")

    def _reset_throttle(self, username: str) -> None:
        self._throttle.pop(username, None)

    def _bump_failed_attempts(self, user_id: str) -> None:
        """Solo informativo (no toca sync_status: el contador no necesita viajar a la nube)."""
        try:
            self.cursor.execute(
                "UPDATE users SET pin_failed_attempts = pin_failed_attempts + 1 WHERE id = ?", (user_id,))
            self.db.commit()
        except Exception:
            self.db.rollback()
            log.exception("No se pudo registrar el intento fallido")

    @staticmethod
    def _is_future(iso_value: str | None) -> bool:
        if not iso_value:
            return False
        try:
            return datetime.fromisoformat(iso_value.replace("Z", "+00:00")).astimezone(timezone.utc) \
                   > datetime.now(timezone.utc)
        except ValueError:
            return False

    def _check_user_not_locked(self, user) -> None:
        if self._is_future(user["pin_locked_until"]):
            raise LockedError("Este usuario está bloqueado temporalmente. Contacta a un administrador.")

    @classmethod
    def _get_dummy_hash(cls) -> str:
        if cls._dummy_hash is None:
            cls._dummy_hash = hash_pin("000000")
        return cls._dummy_hash

    # ------------------------------------------------------------------ acceso a datos
    def _find_user(self, username: str):
        self.cursor.execute("""
            SELECT u.id, u.username, u.full_name, u.branch_id, u.role_id, u.pin_hash, u.pin_locked_until,
                   r.name AS role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE u.username = ? COLLATE NOCASE
              AND u.pin_hash IS NOT NULL AND u.is_active = 1
              AND u.deleted_at IS NULL AND r.deleted_at IS NULL
        """, (username,))
        return self.cursor.fetchone()

    def _permissions(self, role_id: str) -> set:
        self.cursor.execute("""
            SELECT p.code FROM role_permissions rp
            JOIN permissions p ON p.id = rp.permission_id
            WHERE rp.role_id = ? AND rp.deleted_at IS NULL AND p.deleted_at IS NULL
        """, (role_id,))
        return {row["code"] for row in self.cursor.fetchall()}

    def _session_user(self, user) -> dict:
        return {
            "id": user["id"], "name": user["full_name"], "username": user["username"],
            "branch_id": user["branch_id"], "role_id": user["role_id"], "role_name": user["role_name"],
            "permissions": sorted(self._permissions(user["role_id"])),
        }

    def _after_successful_login(self, user, pin: str) -> None:
        """Registra el acceso y migra hashes antiguos. Un fallo aquí NUNCA debe impedir entrar."""
        try:
            now = self.get_timestamp()
            new_hash = hash_pin(pin) if is_legacy_hash(user["pin_hash"]) else user["pin_hash"]
            self.cursor.execute(
                "UPDATE users SET last_login_at = ?, pin_failed_attempts = 0, pin_locked_until = NULL, "
                "pin_hash = ?, updated_at = ?, sync_status = 0 WHERE id = ?",
                (now, new_hash, now, user["id"]))
            self.db.commit()
            if new_hash != user["pin_hash"]:
                log.info("PIN de %s migrado de sha256 a scrypt", user["username"])
        except Exception:
            self.db.rollback()
            log.exception("No se pudo registrar el acceso de %s", user["username"])