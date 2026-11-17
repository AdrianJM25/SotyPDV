import logging
import os
import sqlite3

from models.base_model import BaseModel
from utils.exceptions import (AuthError, BusinessRuleError, NotFoundError, PermissionDenied,
                              ValidationError)
from utils.money import to_cents

log = logging.getLogger(__name__)

MOVEMENT_TYPES = ("cash_in", "cash_out")
MOVEMENT_CATEGORIES = ("deposit", "change_fund", "withdrawal", "expense", "supplier_payment", "other")


class CashController(BaseModel):
    """Turnos de caja.

    Cambios respecto a la versión anterior:
      * Dinero: Decimal -> centavos exactos (int(float(x)*100) perdía centavos: 0.29 -> 28).
      * open_session valida monto (>= 0, máx. $1,000,000, máx. 2 decimales), usuario activo con permiso
        'cash.open', caja activa y de esa sucursal, y que no haya ya un turno abierto.
      * Todo en una transacción con rollback; el índice único de la BD es la última barrera contra
        dos aperturas simultáneas.
      * get_default_register respeta deleted_at y ya NO elige "cualquier caja": usa la de este equipo
        (variable de entorno SOTY_REGISTER_ID o parámetro `register_id`) o la única que exista.
      * Nuevos: movimientos de efectivo (entradas/salidas), saldo esperado y cierre de turno con corte.
      * Cada operación deja registro en audit_logs.
    """

    MAX_AMOUNT_CENTS = 1_000_000_00          # $1,000,000.00

    def __init__(self, register_id: str | None = None):
        super().__init__()
        self.register_id = register_id or os.environ.get("SOTY_REGISTER_ID")

    # ------------------------------------------------------------------ consultas
    def get_default_register(self):
        """Caja de ESTE equipo. Devuelve None si no hay ninguna configurada."""
        if self.register_id:
            row = self.cursor.execute(
                "SELECT id, branch_id, name FROM cash_registers "
                "WHERE id = ? AND is_active = 1 AND deleted_at IS NULL", (self.register_id,)).fetchone()
            if not row:
                raise NotFoundError("La caja configurada para este equipo no existe o está inactiva.")
            return row
        rows = self.cursor.execute(
            "SELECT id, branch_id, name FROM cash_registers WHERE is_active = 1 AND deleted_at IS NULL "
            "ORDER BY created_at LIMIT 2").fetchall()
        if len(rows) > 1:
            raise BusinessRuleError(
                "Hay varias cajas activas y no se sabe cuál es esta. Define SOTY_REGISTER_ID con el id de la caja.")
        return rows[0] if rows else None

    def get_open_session(self, register_id):
        """Turno abierto de la caja (o None)."""
        self._require_text(register_id, "caja")
        return self.cursor.execute(
            "SELECT id, opening_amount, opened_by_user_id, opened_at FROM cash_sessions "
            "WHERE cash_register_id = ? AND status = 'open' AND deleted_at IS NULL "
            "ORDER BY opened_at DESC LIMIT 1", (register_id,)).fetchone()

    def get_balance(self, session_id: str) -> dict:
        """Montos en CENTAVOS: opening_amount, cash_sales, cash_in, cash_out, cash_refunds, expected_cash."""
        row = self.cursor.execute(
            "SELECT * FROM v_cash_session_balance WHERE cash_session_id = ?", (session_id,)).fetchone()
        if not row:
            raise NotFoundError("Turno no encontrado.")
        return dict(row)

    # ------------------------------------------------------------------ apertura
    def open_session(self, branch_id, register_id, user_id, opening_amount):
        """`opening_amount` en PESOS (str/int/float/Decimal). Devuelve el id del turno.
        Lanza ValidationError / NotFoundError / BusinessRuleError / AuthError / PermissionDenied."""
        self._require_text(branch_id, "sucursal")
        self._require_text(register_id, "caja")
        self._require_text(user_id, "usuario")
        cents = to_cents(opening_amount, max_cents=self.MAX_AMOUNT_CENTS)

        register = self.cursor.execute(
            "SELECT id, branch_id, is_active FROM cash_registers WHERE id = ? AND deleted_at IS NULL",
            (register_id,)).fetchone()
        if not register:
            raise NotFoundError("La caja no existe.")
        if not register["is_active"]:
            raise BusinessRuleError("La caja está desactivada.")
        if register["branch_id"] != branch_id:
            raise BusinessRuleError("La caja no pertenece a la sucursal indicada.")
        self._require_user_permission(user_id, "cash.open")
        if self.get_open_session(register_id):
            raise BusinessRuleError("Esta caja ya tiene un turno abierto.")

        session_id, now = self.generate_uuid(), self.get_timestamp()
        try:
            self.cursor.execute("""
                INSERT INTO cash_sessions
                (id, branch_id, cash_register_id, opened_by_user_id, status, opening_amount,
                 opened_at, created_at, updated_at, sync_status)
                VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?, 0)
            """, (session_id, branch_id, register_id, user_id, cents, now, now, now))
            self._audit("cash.open", "cash_sessions", session_id, user_id, branch_id, register_id,
                        {"opening_amount": cents})
            self.db.commit()
        except sqlite3.IntegrityError as exc:
            self.db.rollback()
            if "UNIQUE" in str(exc).upper():      # otro proceso abrió el turno entre la consulta y el insert
                raise BusinessRuleError("Esta caja ya tiene un turno abierto.") from exc
            log.exception("Integridad al abrir turno")
            raise
        except Exception:
            self.db.rollback()
            log.exception("Error abriendo turno")
            raise
        log.info("Turno %s abierto con %d centavos", session_id, cents)
        return session_id

    # ------------------------------------------------------------------ movimientos manuales
    def add_movement(self, session_id, user_id, movement_type, amount, description, category="other"):
        """Entrada o salida manual de efectivo. `amount` en pesos (> 0). Devuelve el id del movimiento."""
        if movement_type not in MOVEMENT_TYPES:
            raise ValidationError("Tipo de movimiento inválido.")
        if category not in MOVEMENT_CATEGORIES:
            raise ValidationError("Categoría de movimiento inválida.")
        description = (description or "").strip()
        if not description:
            raise ValidationError("Escribe una descripción del movimiento.")
        if len(description) > 200:
            raise ValidationError("La descripción es demasiado larga (máx. 200 caracteres).")
        cents = to_cents(amount, allow_zero=False, max_cents=self.MAX_AMOUNT_CENTS)
        self._require_user_permission(user_id, "cash.movements")
        if self.db.in_transaction:
            raise BusinessRuleError("Hay una operación pendiente en esta conexión.")
        movement_id, now = self.generate_uuid(), self.get_timestamp()
        try:
            self.cursor.execute("BEGIN IMMEDIATE")
            session = self._require_open_session(session_id)
            if movement_type == "cash_out" and cents > self.get_balance(session_id)["expected_cash"]:
                raise BusinessRuleError("No hay suficiente efectivo en caja para esta salida.")
            self.cursor.execute("""
                INSERT INTO cash_movements (id, cash_session_id, user_id, movement_type, category, amount,
                                            description, occurred_at, created_at, updated_at, sync_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (movement_id, session_id, user_id, movement_type, category, cents, description, now, now, now))
            self._audit(f"cash.{movement_type}", "cash_movements", movement_id, user_id,
                        session["branch_id"], session["cash_register_id"], {"amount": cents, "category": category})
            self.db.commit()
        except Exception:
            self.db.rollback()
            log.exception("Error registrando movimiento de caja")
            raise
        return movement_id

    # ------------------------------------------------------------------ cierre
    def close_session(self, session_id, user_id, counted_cash, notes=None, *, expected_cash=None) -> dict:
        """Cierra el turno comparando el efectivo contado contra el esperado.
        Devuelve {expected_cash, counted_cash, difference} en CENTAVOS (difference < 0 = faltante)."""
        counted = to_cents(counted_cash, max_cents=self.MAX_AMOUNT_CENTS)
        notes = (notes or "").strip() or None
        if notes and len(notes) > 1000:
            raise ValidationError("Las observaciones no deben superar 1,000 caracteres.")
        self._require_user_permission(user_id, "cash.close")
        if self.db.in_transaction:
            raise BusinessRuleError("Hay una operación pendiente en esta conexión.")
        now = self.get_timestamp()
        try:
            self.cursor.execute("BEGIN IMMEDIATE")
            session = self._require_open_session(session_id)
            balance = self.get_balance(session_id)
            expected = int(balance["expected_cash"])
            if expected_cash is not None and (type(expected_cash) is not int or expected_cash != expected):
                raise BusinessRuleError("El saldo cambió. Actualiza el resumen y revisa el corte nuevamente.")
            difference = counted - expected

            sales = {r["payment_method_id"]: r["total"] for r in self.cursor.execute(
                "SELECT sp.payment_method_id, SUM(sp.amount) AS total FROM sale_payments sp "
                "JOIN sales s ON s.id = sp.sale_id WHERE s.cash_session_id = ? AND s.status = 'completed' "
                "AND s.deleted_at IS NULL AND sp.deleted_at IS NULL GROUP BY sp.payment_method_id",
                (session_id,)).fetchall()}
            refunds = {r["refund_payment_method_id"]: r["total"] for r in self.cursor.execute(
                "SELECT refund_payment_method_id, SUM(total) AS total FROM sale_returns "
                "WHERE cash_session_id = ? AND deleted_at IS NULL GROUP BY refund_payment_method_id",
                (session_id,)).fetchall()}
            methods = self.cursor.execute(
                "SELECT id, method_type FROM payment_methods WHERE deleted_at IS NULL").fetchall()
            if sum(pm["method_type"] == "cash" for pm in methods) != 1:
                raise BusinessRuleError("Configura exactamente un método de efectivo antes de cerrar la caja.")
            for pm in methods:
                is_cash = pm["method_type"] == "cash"
                s_amt, r_amt = sales.get(pm["id"], 0), refunds.get(pm["id"], 0)
                if not is_cash and not s_amt and not r_amt:
                    continue
                exp = expected if is_cash else s_amt - r_amt
                got = counted if is_cash else None          # tarjeta/transferencia: se concilia aparte
                self.cursor.execute("""
                    INSERT INTO cash_session_totals (id, cash_session_id, payment_method_id, sales_amount,
                        refunds_amount, expected_amount, counted_amount, difference_amount,
                        created_at, updated_at, sync_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """, (self.generate_uuid(), session_id, pm["id"], s_amt, r_amt, exp, got,
                      (got - exp) if got is not None else None, now, now))

            self.cursor.execute("""
                UPDATE cash_sessions SET status = 'closed', closed_at = ?, closed_by_user_id = ?,
                    expected_cash_amount = ?, counted_cash_amount = ?, cash_difference = ?,
                    closing_notes = ?, updated_at = ?, sync_status = 0
                WHERE id = ? AND status = 'open'
            """, (now, user_id, expected, counted, difference, notes, now, session_id))
            if self.cursor.rowcount != 1:
                raise BusinessRuleError("El turno ya fue cerrado.")
            self._audit("cash.close", "cash_sessions", session_id, user_id, session["branch_id"],
                        session["cash_register_id"],
                        {"expected": expected, "counted": counted, "difference": difference})
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {"expected_cash": expected, "counted_cash": counted, "difference": difference}

    # ------------------------------------------------------------------ internos
    @staticmethod
    def _require_text(value, label: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"Falta el dato requerido: {label}.")

    def _require_open_session(self, session_id):
        self._require_text(session_id, "turno")
        row = self.cursor.execute(
            "SELECT id, branch_id, cash_register_id, status FROM cash_sessions "
            "WHERE id = ? AND deleted_at IS NULL", (session_id,)).fetchone()
        if not row:
            raise NotFoundError("Turno no encontrado.")
        if row["status"] != "open":
            raise BusinessRuleError("El turno ya está cerrado.")
        return row

    def _require_user_permission(self, user_id: str, permission: str) -> None:
        user = self.cursor.execute(
            "SELECT role_id FROM users WHERE id = ? AND is_active = 1 AND deleted_at IS NULL",
            (user_id,)).fetchone()
        if not user:
            raise AuthError("El usuario no existe o está inactivo.")
        has = self.cursor.execute(
            "SELECT 1 FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
            "WHERE rp.role_id = ? AND p.code = ? AND rp.deleted_at IS NULL AND p.deleted_at IS NULL",
            (user["role_id"], permission)).fetchone()
        if not has:
            raise PermissionDenied("No tienes permiso para realizar esta acción.")

    def _audit(self, action, entity_type, entity_id, user_id, branch_id, register_id, new_values: dict):
        import json
        now = self.get_timestamp()
        self.cursor.execute("""
            INSERT INTO audit_logs (id, user_id, branch_id, cash_register_id, action, entity_type, entity_id,
                                    new_values, occurred_at, created_at, updated_at, sync_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (self.generate_uuid(), user_id, branch_id, register_id, action, entity_type, entity_id,
              json.dumps(new_values), now, now, now))
