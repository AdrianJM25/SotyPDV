"""Dinero seguro: en la BD siempre son ENTEROS en centavos. Nunca uses int(float(x) * 100):
int(float('0.29') * 100) == 28 (error de punto flotante)."""
from decimal import Decimal, InvalidOperation

from utils.exceptions import ValidationError

_CENT = Decimal("0.01")


def to_cents(value, *, allow_zero: bool = True, max_cents: int | None = None) -> int:
    """Convierte pesos (str / int / float / Decimal) a centavos. Acepta '$1,250.50'.
    Rechaza: vacío, no numérico, notación científica, negativos y más de 2 decimales."""
    if value is None or isinstance(value, bool):
        raise ValidationError("Captura un monto.")
    if isinstance(value, float):
        value = repr(round(value, 2))
    text = str(value).strip().replace("$", "").replace(",", "").replace(" ", "")
    if not text:
        raise ValidationError("Captura un monto.")
    if "e" in text.lower():
        raise ValidationError(f"'{value}' no es un monto válido.")
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise ValidationError(f"'{value}' no es un monto válido.") from None
    if not amount.is_finite():
        raise ValidationError(f"'{value}' no es un monto válido.")
    if amount != amount.quantize(_CENT):
        raise ValidationError("El monto admite como máximo 2 decimales.")
    cents = int(amount * 100)
    if cents < 0:
        raise ValidationError("El monto no puede ser negativo.")
    if cents == 0 and not allow_zero:
        raise ValidationError("El monto debe ser mayor que cero.")
    if max_cents is not None and cents > max_cents:
        raise ValidationError(f"El monto máximo permitido es ${max_cents / 100:,.2f}.")
    return cents


def cents_to_pesos(cents: int) -> Decimal:
    return (Decimal(int(cents)) / 100).quantize(_CENT)


def format_money(cents: int | None, symbol: str = "$") -> str:
    cents = int(cents or 0)
    return f"{'-' if cents < 0 else ''}{symbol}{abs(cents_to_pesos(cents)):,.2f}"
