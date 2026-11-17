"""Controlador de Sucursales (tabla `branches`).

Reglas de negocio (las sucursales son referenciadas por cajas, usuarios, turnos, ventas, compras,
devoluciones e inventario, así que NO se pueden borrar a la ligera):
  * Código obligatorio, único entre sucursales vigentes, en MAYÚSCULAS (letras, números, guion y guion bajo).
  * Nombre obligatorio.
  * Desactivar: bloqueado si es la ÚLTIMA sucursal activa o si tiene un turno de caja abierto.
  * Eliminar (baja lógica con deleted_at): solo si NUNCA se usó (sin cajas, usuarios, turnos, ventas,
    compras, devoluciones ni movimientos de inventario) y si no es la última sucursal.
  * validate() devuelve errores POR CAMPO para pintarlos en el formulario; save_branch() valida y escribe
    en una transacción, con registro en audit_logs.
  * En los UPDATE no se toca updated_at / sync_status: lo hace el trigger trg_branches_touch.
"""
import json
import logging
import re

from models.base_model import BaseModel
from utils.exceptions import BusinessRuleError, POSError, ValidationError

log = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CODE_RE = re.compile(r"^[A-Z0-9_-]{1,20}$")

FIELDS = {          # clave -> (etiqueta, longitud máxima)
    "code": ("Código", 20), "name": ("Nombre", 100), "address": ("Dirección", 200), "city": ("Ciudad", 80),
    "state": ("Estado", 80), "postal_code": ("Código postal", 10), "phone": ("Teléfono", 30), "email": ("Correo", 120),
}

# Tablas con historial: si una sucursal aparece aquí, ya no se puede eliminar.
_USAGE = (
    ("cash_registers", "cajas", "deleted_at IS NULL"),
    ("users", "usuarios", "deleted_at IS NULL"),
    ("cash_sessions", "turnos de caja", "1=1"),
    ("sales", "ventas", "1=1"),
    ("sale_returns", "devoluciones", "1=1"),
    ("purchases", "compras", "1=1"),
    ("inventory_movements", "movimientos de inventario", "1=1"),
)


class BranchesController(BaseModel):

    # ------------------------------------------------------------------ consultas
    def list_branches(self, search="", include_inactive=True):
        sql = """SELECT b.id, b.code, b.name, b.address, b.city, b.state, b.postal_code, b.phone, b.email,
                        b.is_active, b.created_at, b.updated_at, b.sync_status,
                        (SELECT COUNT(*) FROM cash_registers r WHERE r.branch_id = b.id AND r.deleted_at IS NULL) AS registers,
                        (SELECT COUNT(*) FROM users u WHERE u.branch_id = b.id AND u.deleted_at IS NULL) AS users
                 FROM branches b WHERE b.deleted_at IS NULL"""
        params = {}
        if not include_inactive:
            sql += " AND b.is_active = 1"
        text = (search or "").strip()
        if text:
            sql += (" AND (b.code LIKE :q ESCAPE '\\' OR b.name LIKE :q ESCAPE '\\' OR b.city LIKE :q ESCAPE '\\'"
                    " OR b.state LIKE :q ESCAPE '\\')")
            params["q"] = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sql += " ORDER BY b.is_active DESC, b.name COLLATE NOCASE"
        return [dict(r, is_active=bool(r["is_active"])) for r in self.cursor.execute(sql, params).fetchall()]

    def get_branch(self, branch_id):
        row = self.cursor.execute(
            "SELECT * FROM branches WHERE id = ? AND deleted_at IS NULL", (branch_id,)).fetchone()
        if not row:
            raise BusinessRuleError("La sucursal ya no existe.")
        return dict(row, is_active=bool(row["is_active"]))

    def usage(self, branch_id) -> dict:
        """{'cajas': 2, 'ventas': 130, ...} solo con los conteos > 0."""
        result = {}
        for table, label, where in _USAGE:
            n = self.cursor.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE branch_id = ? AND {where}", (branch_id,)).fetchone()["n"]
            if n:
                result[label] = n
        return result

    # ------------------------------------------------------------------ validación
    def validate(self, data, branch_id=None):
        """(valores_limpios, errores_por_campo). Revisa también que el código no esté repetido."""
        clean, errors = {}, {}
        for key, (label, limit) in FIELDS.items():
            value = " ".join(str(data.get(key) or "").split())
            if len(value) > limit:
                errors[key] = f"Máximo {limit} caracteres."
            clean[key] = value or None

        if not clean["code"]:
            errors.setdefault("code", "El código es obligatorio.")
        else:
            clean["code"] = clean["code"].upper()
            if "code" not in errors and not _CODE_RE.match(clean["code"]):
                errors["code"] = "Usa solo letras, números, guion (-) o guion bajo (_), sin espacios."
            elif "code" not in errors:
                dup = self.cursor.execute(
                    "SELECT 1 FROM branches WHERE code = ? AND deleted_at IS NULL AND id != ?",
                    (clean["code"], branch_id or "")).fetchone()
                if dup:
                    errors["code"] = "Ya existe una sucursal con este código."
        if not clean["name"]:
            errors.setdefault("name", "El nombre es obligatorio.")
        if clean["email"] and "email" not in errors and not _EMAIL_RE.match(clean["email"]):
            errors["email"] = "El correo electrónico no es válido."
        return clean, errors

    # ------------------------------------------------------------------ escritura
    def save_branch(self, data, branch_id=None, user_id=None):
        """Crea (branch_id=None) o actualiza una sucursal. Devuelve su id."""
        clean, errors = self.validate(data, branch_id)
        if errors:
            raise ValidationError("\n".join(f"• {FIELDS[k][0]}: {m}" for k, m in errors.items()))
        now = self.get_timestamp()
        cols = list(FIELDS)
        try:
            if branch_id:
                old = self.cursor.execute(
                    "SELECT * FROM branches WHERE id = ? AND deleted_at IS NULL", (branch_id,)).fetchone()
                if not old:
                    raise BusinessRuleError("La sucursal ya no existe.")
                self.cursor.execute("UPDATE branches SET " + ", ".join(f"{c} = ?" for c in cols) + " WHERE id = ?",
                                    [clean[c] for c in cols] + [branch_id])
                changed = [c for c in cols if old[c] != clean[c]]
                self._audit("branch.update", branch_id, user_id, {c: old[c] for c in changed},
                            {c: clean[c] for c in changed}, f"Sucursal editada: {clean['name']}")
            else:
                branch_id = self.generate_uuid()
                self.cursor.execute(
                    "INSERT INTO branches (id, " + ", ".join(cols) + ", created_at, updated_at) VALUES (?, "
                    + ", ".join("?" for _ in cols) + ", ?, ?)",
                    [branch_id] + [clean[c] for c in cols] + [now, now])
                self._audit("branch.create", branch_id, user_id, None, {c: clean[c] for c in cols},
                            f"Sucursal creada: {clean['name']}")
            self.db.commit()
            return branch_id
        except BusinessRuleError:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            log.exception("Error guardando sucursal")
            raise POSError("Ocurrió un error interno al guardar la sucursal.") from None

    def set_active(self, branch_id, active, user_id=None):
        try:
            branch = self.get_branch(branch_id)
            if branch["is_active"] == bool(active):
                return
            if not active:
                others = self.cursor.execute(
                    "SELECT COUNT(*) AS n FROM branches WHERE is_active = 1 AND deleted_at IS NULL AND id != ?",
                    (branch_id,)).fetchone()["n"]
                if others == 0:
                    raise BusinessRuleError("No puedes desactivar la última sucursal activa: el sistema necesita al menos una.")
                open_sessions = self.cursor.execute(
                    "SELECT COUNT(*) AS n FROM cash_sessions WHERE branch_id = ? AND status = 'open' AND deleted_at IS NULL",
                    (branch_id,)).fetchone()["n"]
                if open_sessions:
                    raise BusinessRuleError(
                        f"La sucursal tiene {open_sessions} turno(s) de caja abierto(s). Ciérralos antes de desactivarla.")
            self.cursor.execute("UPDATE branches SET is_active = ? WHERE id = ?", (1 if active else 0, branch_id))
            self._audit("branch.activate" if active else "branch.deactivate", branch_id, user_id,
                        {"is_active": int(branch["is_active"])}, {"is_active": 1 if active else 0},
                        f"Sucursal {'reactivada' if active else 'desactivada'}: {branch['name']}")
            self.db.commit()
        except BusinessRuleError:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            log.exception("Error cambiando estado de sucursal")
            raise POSError("Ocurrió un error interno al actualizar la sucursal.") from None

    def delete_branch(self, branch_id, user_id=None):
        """Baja lógica. Solo sucursales que nunca se usaron."""
        try:
            branch = self.get_branch(branch_id)
            used = self.usage(branch_id)
            if used:
                detail = ", ".join(f"{n} {label}" for label, n in used.items())
                raise BusinessRuleError(
                    f"No se puede eliminar: la sucursal tiene {detail}. "
                    "Puedes desactivarla para que ya no se use, conservando su historial.")
            total = self.cursor.execute("SELECT COUNT(*) AS n FROM branches WHERE deleted_at IS NULL").fetchone()["n"]
            if total <= 1:
                raise BusinessRuleError("No puedes eliminar la única sucursal del sistema.")
            self.cursor.execute("UPDATE branches SET deleted_at = ? WHERE id = ?", (self.get_timestamp(), branch_id))
            self._audit("branch.delete", branch_id, user_id, {"code": branch["code"], "name": branch["name"]}, None,
                        f"Sucursal eliminada: {branch['name']}")
            self.db.commit()
        except BusinessRuleError:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            log.exception("Error eliminando sucursal")
            raise POSError("Ocurrió un error interno al eliminar la sucursal.") from None

    def _audit(self, action, entity_id, user_id, old, new, description):
        now = self.get_timestamp()
        self.cursor.execute(
            """INSERT INTO audit_logs (id, user_id, branch_id, action, entity_type, entity_id, old_values, new_values,
                                       description, occurred_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'branches', ?, ?, ?, ?, ?, ?, ?)""",
            (self.generate_uuid(), user_id, entity_id if action != "branch.delete" else None, action, entity_id,
             json.dumps(old, ensure_ascii=False) if old is not None else None,
             json.dumps(new, ensure_ascii=False) if new is not None else None, description, now, now, now))