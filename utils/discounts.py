from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP


def _parse(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def is_valid_now(d, now=None) -> bool:
    """d: fila/dict de discounts. Activo, no eliminado y dentro de su vigencia."""
    if not d["is_active"] or d["deleted_at"]:
        return False
    now = now or datetime.now(timezone.utc)
    start, end = _parse(d["valid_from"]), _parse(d["valid_until"])
    return (start is None or start <= now) and (end is None or now <= end)


def calc_amount(discount_type: str, value: float, base_cents: int) -> int:
    """Monto del descuento en centavos, nunca mayor a la base."""
    if base_cents <= 0:
        return 0
    if discount_type == "percent":
        amount = int((Decimal(str(value)) * base_cents / 100).quantize(Decimal(1), ROUND_HALF_UP))
    else:
        amount = int(round(value))
    return max(0, min(amount, base_cents))


def prorate(amount: int, bases: list[int]) -> list[int]:
    """Reparte `amount` entre líneas en proporción a su base (método del mayor resto).
    La suma del resultado es exactamente `amount`."""
    total = sum(bases)
    if total <= 0 or amount <= 0:
        return [0] * len(bases)
    amount = min(amount, total)
    shares, rems = [], []
    for b in bases:
        q, r = divmod(amount * b, total)
        shares.append(q)
        rems.append(r)
    leftover = amount - sum(shares)
    for i in sorted(range(len(bases)), key=lambda i: rems[i], reverse=True)[:leftover]:
        shares[i] += 1
    return shares