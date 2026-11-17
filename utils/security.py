"""Hash de PIN con scrypt + sal aleatoria por usuario (solo biblioteca estándar).

Compatibilidad: los PIN guardados con sha256 simple (64 caracteres hex, sin sal) se siguen aceptando y
se actualizan solos a scrypt en el siguiente login exitoso (ver AuthController).
"""
import base64
import hashlib
import hmac
import os
import re

_N, _R, _P, _DKLEN = 2**14, 8, 1, 32
_LEGACY_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def hash_pin(pin: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(pin.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return "$".join(["scrypt", str(_N), str(_R), str(_P),
                     base64.b64encode(salt).decode(), base64.b64encode(dk).decode()])


def is_legacy_hash(stored: str | None) -> bool:
    return bool(stored) and bool(_LEGACY_SHA256.match(stored))


def verify_pin(pin: str, stored: str | None) -> bool:
    if not stored:
        return False
    if is_legacy_hash(stored):
        return hmac.compare_digest(hashlib.sha256(pin.encode()).hexdigest(), stored)
    try:
        algo, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(hash_b64)
        dk = hashlib.scrypt(pin.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False
