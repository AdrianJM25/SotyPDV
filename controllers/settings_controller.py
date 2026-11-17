"""Controlador de Configuración del sistema (tabla `settings`, clave/valor).

Diseño:
  * REGISTRO de configuraciones (SETTING_DEFS): cada clave se declara UNA vez con etiqueta, grupo, tipo,
    valor por defecto y reglas de validación. La vista se genera desde ese registro, así que agregar una
    configuración nueva = agregar una línea aquí.
  * Lectura tipada con valor por defecto: `SettingsController().get('store_name')` nunca devuelve basura
    ni falla si la fila aún no existe. Cualquier otro módulo puede usarlo en una línea.
  * Escritura ATÓMICA: `save_many()` valida todo primero y guarda todo en una sola transacción
    (o no guarda nada). Solo escribe lo que cambió y deja rastro en audit_logs.
  * Los errores se LANZAN (ValidationError / POSError), no se esconden detrás de `return False`.
  * No se toca updated_at / sync_status en los UPDATE: lo hace el trigger trg_settings_touch.

Booleanos se guardan como '1' / '0' (compatible con ProductController._allow_negative_stock).
"""
import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from models.base_model import BaseModel
from utils.exceptions import POSError, ValidationError

log = logging.getLogger(__name__)

TRUE_VALUES = ("1", "true", "yes", "on", "si", "sí")


@dataclass(frozen=True)
class SettingDef:
    key: str
    label: str
    group: str
    type: str = "string"            # string | integer | decimal | boolean | json
    default: object = None
    description: str = ""
    required: bool = False
    max_len: int = 200
    choices: tuple = ()             # valores permitidos (p. ej. (58, 80))
    min: float = None
    max: float = None
    uppercase: bool = False


# (id, título, descripción) en el orden en que se muestran
GROUPS = [
    ("business", "Datos del negocio", "Aparecen en el encabezado de los tickets y reportes."),
    ("ticket", "Ticket de venta", "Formato de impresión."),
    ("sales", "Ventas e inventario", "Reglas que aplica el punto de venta."),
]

SETTING_DEFS = [
    SettingDef("store_name", "Nombre del negocio", "business", default="Mi Negocio POS", required=True, max_len=80),
    SettingDef("store_tax_id", "RFC del negocio", "business", default="", max_len=20, uppercase=True),
    SettingDef("store_address", "Dirección", "business", default="", max_len=200),
    SettingDef("store_phone", "Teléfono", "business", default="", max_len=30),

    SettingDef("ticket_footer_msg", "Mensaje al pie del ticket", "ticket", default="¡Gracias por su compra!", max_len=120),
    SettingDef("ticket_paper_width", "Ancho del papel (mm)", "ticket", "integer", default=80, choices=(58, 80),
               description="58 mm o 80 mm según tu impresora térmica."),
    SettingDef("ticket_copies", "Copias del ticket", "ticket", "integer", default=1, min=1, max=5),
    SettingDef("ticket_show_business_data", "Imprimir dirección, teléfono y RFC en el ticket", "ticket", "boolean",
               default=True),

    SettingDef("currency_symbol", "Símbolo de moneda", "sales", default="$", required=True, max_len=5),
    SettingDef("tax_included_in_prices", "Los precios del catálogo ya incluyen impuestos", "sales", "boolean",
               default=True),
    SettingDef("allow_negative_stock", "Permitir vender sin existencias suficientes", "sales", "boolean",
               default=True, description="Si se desactiva, el punto de venta bloquea ventas que dejen el inventario "
                                         "en negativo."),
]
DEF_BY_KEY = {d.key: d for d in SETTING_DEFS}


# ----------------------------------------------------------------------
# Conversión valor <-> texto de la base
# ----------------------------------------------------------------------
def parse_value(value_type, raw, default=None):
    """Texto guardado en la BD -> valor Python. Si está vacío o corrupto devuelve `default`."""
    if raw is None:
        return default
    try:
        if value_type == "boolean":
            return str(raw).strip().lower() in TRUE_VALUES
        if value_type == "integer":
            return int(Decimal(str(raw).strip()))
        if value_type == "decimal":
            return Decimal(str(raw).strip())
        if value_type == "json":
            return json.loads(raw)
    except (InvalidOperation, ValueError, TypeError):
        log.warning("Valor corrupto en settings (%s): %r", value_type, raw)
        return default
    return str(raw)


def serialize_value(value_type, value) -> str:
    if value_type == "boolean":
        return "1" if value else "0"
    if value_type == "json":
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


class SettingsController(BaseModel):

    # ------------------------------------------------------------------ lectura
    def definitions(self):
        """Registro completo, agrupado, para que la vista dibuje el formulario."""
        return [(gid, title, desc, [d for d in SETTING_DEFS if d.group == gid]) for gid, title, desc in GROUPS]

    def get_all(self) -> dict:
        """{clave: valor tipado}. Las claves del registro siempre vienen (con su valor por defecto si no existen)."""
        rows = self.cursor.execute(
            "SELECT setting_key, setting_value, value_type FROM settings WHERE deleted_at IS NULL").fetchall()
        stored = {r["setting_key"]: r for r in rows}
        result = {}
        for d in SETTING_DEFS:
            row = stored.get(d.key)
            raw = row["setting_value"] if row else None
            result[d.key] = d.default if raw is None else parse_value(d.type, raw, d.default)
        for key, row in stored.items():            # claves que no están en el registro (otros módulos)
            if key not in result:
                result[key] = parse_value(row["value_type"], row["setting_value"])
        return result

    def get(self, key, default=None):
        """Un valor tipado. Usa el valor por defecto del registro si la fila no existe."""
        d = DEF_BY_KEY.get(key)
        row = self.cursor.execute(
            "SELECT setting_value, value_type FROM settings WHERE setting_key = ? AND deleted_at IS NULL",
            (key,)).fetchone()
        if d:
            fallback = d.default if default is None else default
            return fallback if not row or row["setting_value"] is None else parse_value(d.type, row["setting_value"], fallback)
        return default if not row else parse_value(row["value_type"], row["setting_value"], default)

    # ------------------------------------------------------------------ validación
    def validate(self, values: dict):
        """Devuelve (valores_limpios, errores_por_clave). No toca la base de datos."""
        clean, errors = {}, {}
        for key, raw in values.items():
            d = DEF_BY_KEY.get(key)
            if d is None:
                errors[key] = "Configuración desconocida."
                continue
            try:
                clean[key] = self._normalize(d, raw)
            except ValidationError as exc:
                errors[key] = str(exc)
        return clean, errors

    @staticmethod
    def _normalize(d: SettingDef, raw):
        if d.type == "boolean":
            return bool(raw) if isinstance(raw, bool) else str(raw).strip().lower() in TRUE_VALUES

        text = " ".join(str(raw if raw is not None else "").split())
        if not text:
            if d.required:
                raise ValidationError("Este campo es obligatorio.")
            if d.type == "string":
                return ""
            raise ValidationError("Este campo es obligatorio.")

        if d.type == "string":
            if len(text) > d.max_len:
                raise ValidationError(f"Máximo {d.max_len} caracteres.")
            return text.upper() if d.uppercase else text
        if d.type in ("integer", "decimal"):
            try:
                number = Decimal(text)
                if not number.is_finite():
                    raise InvalidOperation
            except InvalidOperation:
                raise ValidationError("Debe ser un número.") from None
            if d.type == "integer":
                if number != number.to_integral_value():
                    raise ValidationError("Debe ser un número entero.")
                number = int(number)
            if d.choices and number not in d.choices:
                raise ValidationError("Elige una de las opciones: " + ", ".join(map(str, d.choices)) + ".")
            if d.min is not None and number < d.min:
                raise ValidationError(f"Debe ser mayor o igual a {d.min:g}.")
            if d.max is not None and number > d.max:
                raise ValidationError(f"Debe ser menor o igual a {d.max:g}.")
            return number
        raise ValidationError("Tipo de configuración no soportado desde este formulario.")

    # ------------------------------------------------------------------ escritura
    def save_many(self, values: dict, user_id=None, branch_id=None) -> list:
        """Valida TODO y guarda en una sola transacción. Devuelve las claves que realmente cambiaron."""
        clean, errors = self.validate(values)
        if errors:
            raise ValidationError("\n".join(f"• {DEF_BY_KEY[k].label if k in DEF_BY_KEY else k}: {m}"
                                            for k, m in errors.items()))
        try:
            rows = self.cursor.execute(
                "SELECT id, setting_key, setting_value, value_type FROM settings WHERE deleted_at IS NULL").fetchall()
            existing = {r["setting_key"]: r for r in rows}
            now = self.get_timestamp()
            old_values, new_values = {}, {}

            for key, value in clean.items():
                d = DEF_BY_KEY[key]
                db_value = serialize_value(d.type, value)
                row = existing.get(key)
                if row is None:
                    self.cursor.execute(
                        """INSERT INTO settings (id, setting_key, setting_value, value_type, description, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (self.generate_uuid(), key, db_value, d.type, d.label, now, now))
                    old_values[key], new_values[key] = None, db_value
                elif row["setting_value"] != db_value or row["value_type"] != d.type:
                    self.cursor.execute(
                        "UPDATE settings SET setting_value = ?, value_type = ? WHERE id = ?",
                        (db_value, d.type, row["id"]))
                    old_values[key], new_values[key] = row["setting_value"], db_value

            if new_values:
                self._audit("settings.update", user_id, branch_id, old_values, new_values)
            self.db.commit()
            return list(new_values)
        except Exception:
            self.db.rollback()
            log.exception("Error guardando configuración")
            raise POSError("Ocurrió un error interno al guardar la configuración. No se guardó ningún cambio.") from None

    def ensure_defaults(self) -> int:
        """Crea las filas que falten con su valor por defecto (idempotente). Devuelve cuántas creó."""
        try:
            existing = {r["setting_key"] for r in self.cursor.execute(
                "SELECT setting_key FROM settings WHERE deleted_at IS NULL").fetchall()}
            now, created = self.get_timestamp(), 0
            for d in SETTING_DEFS:
                if d.key in existing:
                    continue
                self.cursor.execute(
                    """INSERT INTO settings (id, setting_key, setting_value, value_type, description, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (self.generate_uuid(), d.key, serialize_value(d.type, d.default), d.type, d.label, now, now))
                created += 1
            self.db.commit()
            return created
        except Exception:
            self.db.rollback()
            log.exception("Error creando configuraciones por defecto")
            raise POSError("No se pudieron crear las configuraciones iniciales.") from None

    def _audit(self, action, user_id, branch_id, old, new):
        now = self.get_timestamp()
        self.cursor.execute(
            """INSERT INTO audit_logs (id, user_id, branch_id, action, entity_type, old_values, new_values,
                                       description, occurred_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'settings', ?, ?, ?, ?, ?, ?)""",
            (self.generate_uuid(), user_id, branch_id, action, json.dumps(old, ensure_ascii=False),
             json.dumps(new, ensure_ascii=False), "Configuración modificada: " + ", ".join(new), now, now, now))