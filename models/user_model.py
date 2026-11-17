import sqlite3

from models.base_model import BaseModel
from utils.exceptions import ValidationError
from utils.security import hash_pin

_UPDATABLE = {"branch_id", "role_id", "full_name", "email", "phone", "is_active"}


class UserModel(BaseModel):
    _SELECT = """
        SELECT u.id, u.branch_id, u.role_id, u.username, u.full_name, u.email, u.phone,
               u.is_active, u.pin_locked_until, u.last_login_at, u.created_at,
               r.name AS role_name, b.name AS branch_name
        FROM users u
        JOIN roles r ON r.id = u.role_id
        LEFT JOIN branches b ON b.id = u.branch_id
    """

    # ---------- Lectura (nunca devuelve pin_hash ni password_hash) ----------
    def get_by_id(self, user_id: str):
        self.cursor.execute(
            self._SELECT + " WHERE u.id = ? AND u.deleted_at IS NULL", (user_id,))
        return self.cursor.fetchone()

    def list_all(self, include_inactive: bool = True):
        sql = self._SELECT + " WHERE u.deleted_at IS NULL"
        if not include_inactive:
            sql += " AND u.is_active = 1"
        self.cursor.execute(sql + " ORDER BY u.full_name")
        return self.cursor.fetchall()

    def list_roles(self):
        self.cursor.execute(
            "SELECT id, name FROM roles WHERE deleted_at IS NULL ORDER BY name")
        return self.cursor.fetchall()

    def list_branches(self):
        self.cursor.execute(
            "SELECT id, name FROM branches WHERE deleted_at IS NULL AND is_active = 1 ORDER BY name")
        return self.cursor.fetchall()

    # ---------- Escritura ----------
    def create(self, *, username, full_name, role_id, pin, branch_id=None,
               email=None, phone=None) -> str:
        user_id = self.generate_uuid()
        try:
            self.cursor.execute(
                """INSERT INTO users
                   (id, branch_id, role_id, username, full_name, email, phone,
                    pin_hash, is_active, sync_status)
                   VALUES (?,?,?,?,?,?,?,?,1,0)""",
                (user_id, branch_id or None, role_id, username.strip().lower(),
                 full_name.strip(), (email or "").strip() or None,
                 (phone or "").strip() or None, hash_pin(pin)),
            )
            self.db.commit()
        except sqlite3.IntegrityError as e:
            self.db.rollback()
            msg = str(e).lower()
            if "username" in msg:
                raise ValidationError("Ese nombre de usuario ya existe.") from e
            if "email" in msg:
                raise ValidationError("Ese correo ya está registrado.") from e
            raise
        except Exception:
            self.db.rollback()
            raise
        return user_id

    def update(self, user_id: str, **fields) -> None:
        data = {k: v for k, v in fields.items() if k in _UPDATABLE}
        if not data:
            return
        for k in ("email", "phone", "branch_id"):      # texto vacío -> NULL
            if k in data and isinstance(data[k], str):
                data[k] = data[k].strip() or None
        sets = ", ".join(f"{k} = ?" for k in data)
        try:
            self.cursor.execute(
                f"UPDATE users SET {sets}, updated_at = ?, sync_status = 0 WHERE id = ?",
                (*data.values(), self.get_timestamp(), user_id),
            )
            self.db.commit()
        except sqlite3.IntegrityError as e:
            self.db.rollback()
            raise ValidationError("El correo ya está registrado.") from e
        except Exception:
            self.db.rollback()
            raise

    def unlock(self, user_id: str) -> None:
        """Quita el bloqueo puesto en pin_locked_until y reinicia el contador."""
        self._run("UPDATE users SET pin_locked_until = NULL, pin_failed_attempts = 0, "
                  "updated_at = ?, sync_status = 0 WHERE id = ?", (self.get_timestamp(), user_id))

    def soft_delete(self, user_id: str) -> None:
        now = self.get_timestamp()
        self._run("UPDATE users SET deleted_at = ?, is_active = 0, updated_at = ?, "
                  "sync_status = 0 WHERE id = ?", (now, now, user_id))

    def count_active_with_role(self, role_id: str, exclude_user_id: str | None = None) -> int:
        self.cursor.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role_id = ? AND is_active = 1 "
            "AND deleted_at IS NULL AND id != ?", (role_id, exclude_user_id or ""))
        return self.cursor.fetchone()["n"]

    # ---------- interno ----------
    def _run(self, sql: str, params: tuple) -> None:
        try:
            self.cursor.execute(sql, params)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise