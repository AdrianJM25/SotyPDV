import logging
from decimal import Decimal, InvalidOperation

from models.base_model import BaseModel
from utils.exceptions import BusinessRuleError, ValidationError, POSError

log = logging.getLogger(__name__)

_SELECT = """
    SELECT p.id, p.sku, p.name, p.sale_price, p.cost_price, p.track_inventory, p.tax_rate_id,
           COALESCE(t.rate, 0)         AS tax_rate,
           u.code                      AS unit_code,
           u.allows_decimals           AS allows_decimals,
           COALESCE(s.quantity, 0)     AS stock
    FROM products p
    JOIN units u            ON u.id = p.unit_id
    LEFT JOIN tax_rates t   ON t.id = p.tax_rate_id
    LEFT JOIN inventory_stock s ON s.product_id = p.id AND s.branch_id = :branch AND s.deleted_at IS NULL
    WHERE p.is_active = 1 AND p.deleted_at IS NULL
"""

class ProductController(BaseModel):
    """Consulta y gestión de productos para el punto de venta."""

    MAX_CODE_LEN = 64
    MIN_SEARCH_LEN = 2

    # ==================================================================
    # BÚSQUEDAS DE VENTA
    # ==================================================================
    def get_product_by_code(self, raw_code, branch_id=None):
        code = self.normalize_code(raw_code)
        row = self.cursor.execute(
            _SELECT + " AND (p.sku = :code OR EXISTS (SELECT 1 FROM product_barcodes b "
                      "WHERE b.product_id = p.id AND b.barcode = :code AND b.deleted_at IS NULL)) LIMIT 1",
            {"branch": branch_id, "code": code}).fetchone()
        return self._format(row) if row else None

    def get_product_by_sku(self, sku, branch_id=None):
        return self.get_product_by_code(sku, branch_id)

    def search_products(self, text, branch_id=None, limit=200):
        text = (text or "").strip()
        limit = max(1, min(int(limit), 500)) 
        
        if not text:
            rows = self.cursor.execute(
                _SELECT + " ORDER BY p.name LIMIT :limit",
                {"branch": branch_id, "limit": limit}).fetchall()
        else:
            like = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            rows = self.cursor.execute(
                _SELECT + " AND (p.name LIKE :q ESCAPE '\\' OR p.sku LIKE :q ESCAPE '\\' OR EXISTS ("
                          "SELECT 1 FROM product_barcodes b WHERE b.product_id = p.id AND b.barcode LIKE :q "
                          "ESCAPE '\\' AND b.deleted_at IS NULL)) ORDER BY p.name LIMIT :limit",
                {"branch": branch_id, "q": like, "limit": limit}).fetchall()
                
        return [self._format(r) for r in rows]

    # ==================================================================
    # REGLAS Y VALIDACIONES
    # ==================================================================
    def check_stock(self, product: dict, quantity) -> None:
        try:
            qty = Decimal(str(quantity))
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError("La cantidad debe ser numérica.") from None
        if not qty.is_finite() or qty <= 0 or qty > 999999:
            raise ValidationError("La cantidad debe estar entre 0 y 999999, sin incluir cero.")
        if not product.get("allows_decimals", False) and qty != qty.to_integral_value():
            raise ValidationError("Este producto no admite cantidades fraccionadas.")
        if qty != qty.quantize(Decimal(".001")):
            raise ValidationError("Usa como máximo tres decimales.")
        if not product["track_inventory"] or self._allow_negative_stock():
            return
        if Decimal(str(product["stock"])) < qty:
            raise BusinessRuleError(
                f"Existencia insuficiente de '{product['name']}': hay {product['stock']:g}.")

    def _allow_negative_stock(self) -> bool:
        row = self.cursor.execute(
            "SELECT setting_value FROM settings WHERE setting_key = 'allow_negative_stock' "
            "AND deleted_at IS NULL").fetchone()
        return True if row is None else str(row["setting_value"]).strip().lower() in ("1", "true", "yes")

    @classmethod
    def normalize_code(cls, raw) -> str:
        if raw is None:
            raise ValidationError("Código vacío.")
        code = "".join(ch for ch in str(raw) if ch.isprintable()).strip()
        if not code:
            raise ValidationError("Código vacío.")
        if len(code) > cls.MAX_CODE_LEN:
            raise ValidationError(f"Código demasiado largo (máx. {cls.MAX_CODE_LEN} caracteres).")
        return code

    @staticmethod
    def _format(row) -> dict:
        p = dict(row)
        p["sale_price_cents"] = int(p["sale_price"])
        p["cost_price_cents"] = int(p["cost_price"])
        p["sale_price"] = p["sale_price_cents"] / 100.0
        p["tax_rate"] = float(p["tax_rate"])
        p["track_inventory"] = bool(p["track_inventory"])
        p["allows_decimals"] = bool(p["allows_decimals"])
        p["stock"] = float(p["stock"])
        return p

    # ==================================================================
    # MÉTODOS CRUD DEL MÓDULO DE INVENTARIO 
    # ==================================================================
    def get_catalog_data(self):
        if self.cursor.execute("SELECT COUNT(*) as c FROM units").fetchone()['c'] == 0:
            now = self.get_timestamp()
            self.cursor.execute("INSERT INTO units (id, code, name, allows_decimals, created_at, updated_at) VALUES (?, 'PZA', 'Pieza', 0, ?, ?)", 
                                (self.generate_uuid(), now, now))
            self.db.commit()

        units = self.cursor.execute("SELECT id, name FROM units WHERE is_active = 1 AND deleted_at IS NULL").fetchall()
        categories = self.cursor.execute("SELECT id, name FROM categories WHERE is_active = 1 AND deleted_at IS NULL").fetchall()
        return {
            "units": [{"id": u["id"], "name": u["name"]} for u in units],
            "categories": [{"id": c["id"], "name": c["name"]} for c in categories]
        }

    def get_active_categories(self):
        query = "SELECT id, name FROM categories WHERE deleted_at IS NULL AND is_active = 1 ORDER BY name ASC"
        return self.cursor.execute(query).fetchall()

    def get_all_products(self):
        rows = self.cursor.execute("""
            SELECT p.id, p.sku, p.name, p.sale_price, p.cost_price, p.track_inventory,
                   u.name as unit_name, COALESCE(c.name, 'Sin categoría') as category_name, 
                   COALESCE((SELECT SUM(quantity) FROM inventory_stock WHERE product_id = p.id AND deleted_at IS NULL), 0) as stock
            FROM products p
            JOIN units u ON u.id = p.unit_id
            LEFT JOIN categories c ON c.id = p.category_id
            WHERE p.is_active = 1 AND p.deleted_at IS NULL
            ORDER BY p.name
        """).fetchall()
        
        result = []
        for r in rows:
            d = dict(r)
            d["sale_price_fmt"] = f"${d['sale_price'] / 100:.2f}"
            d["cost_price_fmt"] = f"${d['cost_price'] / 100:.2f}"
            result.append(d)
        return result

    def get_product_by_id(self, product_id):
        row = self.cursor.execute("""
            SELECT id, sku, name, cost_price, sale_price, unit_id, category_id, track_inventory
            FROM products WHERE id = ? AND deleted_at IS NULL
        """, (product_id,)).fetchone()
        return dict(row) if row else None

    def save_product(self, data):
        if not data.get("sku") or not data.get("name") or not data.get("unit_id"):
            raise ValidationError("SKU, Nombre y Unidad son campos obligatorios.")
            
        cost_cents = int(float(data.get("cost_price", 0)) * 100)
        sale_cents = int(float(data.get("sale_price", 0)) * 100)
        now = self.get_timestamp()
        
        try:
            prod_id = self.generate_uuid()
            self.cursor.execute("""
                INSERT INTO products (id, sku, name, unit_id, category_id, cost_price, sale_price, track_inventory, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (prod_id, data["sku"].strip(), data["name"].strip(), data["unit_id"], 
                  data.get("category_id") or None, cost_cents, sale_cents, data.get("track_inventory", 1), now, now))
            self.db.commit()
            return prod_id
        except Exception as e:
            self.db.rollback()
            if "UNIQUE" in str(e).upper():
                raise BusinessRuleError(f"El SKU '{data['sku']}' ya está en uso por otro producto.")
            log.exception("Error guardando producto")
            raise POSError("Ocurrió un error interno al guardar el producto.")

    def update_product(self, product_id, data):
        if not data.get("sku") or not data.get("name") or not data.get("unit_id"):
            raise ValidationError("SKU, Nombre y Unidad son campos obligatorios.")
            
        cost_cents = int(float(data.get("cost_price", 0)) * 100)
        sale_cents = int(float(data.get("sale_price", 0)) * 100)
        now = self.get_timestamp()
        
        try:
            self.cursor.execute("""
                UPDATE products 
                SET sku = ?, name = ?, unit_id = ?, category_id = ?, cost_price = ?, sale_price = ?, 
                    track_inventory = ?, updated_at = ?, sync_status = 0
                WHERE id = ?
            """, (data["sku"].strip(), data["name"].strip(), data["unit_id"], data.get("category_id") or None, 
                  cost_cents, sale_cents, data.get("track_inventory", 1), now, product_id))
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            if "UNIQUE" in str(e).upper():
                raise BusinessRuleError(f"El SKU '{data['sku']}' ya está en uso por otro producto.")
            log.exception("Error actualizando producto")
            raise POSError("Ocurrió un error interno al actualizar el producto.")

    def delete_product(self, product_id):
        try:
            self.cursor.execute("""
                UPDATE products 
                SET deleted_at = ?, sync_status = 0 
                WHERE id = ?
            """, (self.get_timestamp(), product_id))
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            log.exception("Error eliminando producto")
            raise POSError("Ocurrió un error al eliminar el producto.")


def get_product_by_id(self, product_id):
        row = self.cursor.execute("""
            SELECT id, sku, name, cost_price, sale_price, unit_id, category_id, track_inventory
            FROM products WHERE id = ? AND deleted_at IS NULL
        """, (product_id,)).fetchone()
        return dict(row) if row else None



def update_product(self, product_id, data):
        if not data.get("sku") or not data.get("name") or not data.get("unit_id"):
            raise ValueError("SKU, Nombre y Unidad son obligatorios.")
            
        cost_cents = int(float(data.get("cost_price", 0)) * 100)
        sale_cents = int(float(data.get("sale_price", 0)) * 100)
        now = self.get_timestamp()
        
        try:
            self.cursor.execute("""
                UPDATE products 
                SET sku = ?, name = ?, unit_id = ?, category_id = ?, cost_price = ?, sale_price = ?, 
                    track_inventory = ?, updated_at = ?, sync_status = 0
                WHERE id = ?
            """, (data["sku"].strip(), data["name"].strip(), data["unit_id"], data.get("category_id") or None, 
                  cost_cents, sale_cents, data.get("track_inventory", 1), now, product_id))
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            raise e

def delete_product(self, product_id):
        self.cursor.execute("UPDATE products SET deleted_at = ?, sync_status = 0 WHERE id = ?", 
                            (self.get_timestamp(), product_id))
        self.db.commit()
        return True