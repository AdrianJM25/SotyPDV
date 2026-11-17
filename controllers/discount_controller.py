from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from controllers.auth_controller import AuthController
from models.discount_model import DiscountModel
from utils.discounts import calc_amount, is_valid_now
from utils.exceptions import PermissionDenied, ValidationError

PERM_MANAGE = "settings.manage"
PERM_AUTHORIZE = "sales.discount"


class DiscountController:
    def __init__(self):
        self.model = DiscountModel()

    @staticmethod
    def _require(current_user):
        AuthController.require_permission(current_user, PERM_MANAGE)

    def _get_or_fail(self, discount_id):
        d = self.model.get_by_id(discount_id)
        if not d:
            raise ValidationError("Descuento no encontrado.")
        return d

    # ---------- validación ----------
    @staticmethod
    def _date(text, end=False):
        text = (text or "").strip()
        if not text:
            return None
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            raise ValidationError("Fecha inválida. Usa el formato AAAA-MM-DD.")
        return text + ("T23:59:59.999Z" if end else "T00:00:00.000Z")

    def _clean(self, name, discount_type, value, requires_authorization,
               valid_from, valid_until, is_active=True) -> dict:
        name = (name or "").strip()
        if not name:
            raise ValidationError("El nombre es obligatorio.")
        if discount_type not in ("percent", "fixed"):
            raise ValidationError("Tipo de descuento inválido.")
        try:
            v = Decimal(str(value).replace(",", "").replace("$", "").strip())
        except InvalidOperation:
            raise ValidationError("El valor debe ser un número.")
        if discount_type == "percent":
            if not (0 < v <= 100):
                raise ValidationError("El porcentaje debe estar entre 0 y 100.")
            stored = float(v)
        else:
            cents = int((v * 100).quantize(Decimal(1), ROUND_HALF_UP))
            if cents <= 0:
                raise ValidationError("El monto debe ser mayor a cero.")
            stored = float(cents)
        vf, vu = self._date(valid_from), self._date(valid_until, end=True)
        if vf and vu and vf > vu:
            raise ValidationError("La fecha inicial no puede ser posterior a la final.")
        return {"name": name, "discount_type": discount_type, "value": stored,
                "requires_authorization": 1 if requires_authorization else 0,
                "valid_from": vf, "valid_until": vu, "is_active": 1 if is_active else 0}

    # ---------- administración (settings.manage) ----------
    def list_discounts(self, current_user):
        self._require(current_user)
        return self.model.list_all()

    def create_discount(self, current_user, **data) -> str:
        self._require(current_user)
        return self.model.create(**self._clean(**data))

    def update_discount(self, current_user, discount_id, **data) -> None:
        self._require(current_user)
        self._get_or_fail(discount_id)
        self.model.update(discount_id, **self._clean(**data))

    def set_active(self, current_user, discount_id, active: bool) -> None:
        self._require(current_user)
        self._get_or_fail(discount_id)
        self.model.set_active(discount_id, active)

    def delete_discount(self, current_user, discount_id) -> None:
        self._require(current_user)
        self._get_or_fail(discount_id)
        self.model.soft_delete(discount_id)

    def search_products(self, current_user, text=""):
        self._require(current_user)
        return self.model.search_products(text)

    def get_product_ids(self, current_user, discount_id) -> set:
        self._require(current_user)
        return self.model.product_ids(discount_id)

    def set_products(self, current_user, discount_id, product_ids) -> None:
        self._require(current_user)
        self._get_or_fail(discount_id)
        self.model.set_products(discount_id, set(product_ids))

    # ---------- uso en ventas (cualquier usuario con sesión) ----------
    def list_available(self, current_user):
        """Descuentos activos y vigentes, para elegirlos en el cobro."""
        if not current_user:
            raise PermissionDenied("Inicia sesión para continuar.")
        return [d for d in self.model.list_all() if is_valid_now(d)]

    def best_for_product(self, product_id, line_base_cents):
        """Mejor descuento vigente ligado al producto (el de mayor monto) o None."""
        best = None
        for d in self.model.for_product(product_id):
            if not is_valid_now(d):
                continue
            amount = calc_amount(d["discount_type"], d["value"], line_base_cents)
            if amount > 0 and (best is None or amount > best["amount"]):
                best = {"discount_id": d["id"], "amount": amount, "name": d["name"],
                        "requires_authorization": bool(d["requires_authorization"])}
        return best
    def resolve_for_sale(self, current_user, discount_id, base_cents, authorizer=None) -> dict:
        """Valida un descuento global y calcula su monto sobre `base_cents`.
        `authorizer`: dict devuelto por AuthController.authorize_supervisor, si hizo falta."""
        d = self._get_or_fail(discount_id)
        if not is_valid_now(d):
            raise ValidationError("Este descuento no está vigente.")
        approved_by = None
        if d["requires_authorization"] and not AuthController.has_permission(current_user, PERM_AUTHORIZE):
            if not authorizer or not AuthController.has_permission(authorizer, PERM_AUTHORIZE):
                raise PermissionDenied("Este descuento requiere autorización de un supervisor.")
            approved_by = authorizer["id"]
        amount = calc_amount(d["discount_type"], d["value"], base_cents)
        if amount <= 0:
            raise ValidationError("El descuento no aplica a este importe.")
        return {"discount_id": d["id"], "name": d["name"], "amount": amount,
                "authorized_by": approved_by or current_user["id"]}