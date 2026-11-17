"""Errores 'esperados' del POS. Su mensaje (str(error)) es apto para mostrarlo tal cual al usuario.
Cualquier otra excepción es un bug: se registra en el log y se muestra un mensaje genérico."""


class POSError(Exception):
    """Base de todos los errores controlados."""


class ValidationError(POSError):
    """El dato capturado no es válido (monto, PIN, código...)."""


class NotFoundError(POSError):
    pass


class BusinessRuleError(POSError):
    """La operación viola una regla del negocio (ya hay un turno abierto, saldo insuficiente...)."""


class AuthError(POSError):
    pass


class LockedError(AuthError):
    """Demasiados intentos fallidos o usuario bloqueado."""


class PermissionDenied(POSError):
    pass
