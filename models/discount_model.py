from models.base_model import BaseModel

_UUID = ("lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || "
         "substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || "
         "substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6)))")

_FIELDS = ("name", "discount_type", "value", "requires_authorization",
           "valid_from", "valid_until", "is_active")


class DiscountModel(BaseModel):
    def __init__(self):
        super().__init__()
        self._ensure_schema()

    def _ensure_schema(self):
        self.cursor.executescript(f"""
            CREATE TABLE IF NOT EXISTS product_discounts (
                id TEXT NOT NULL PRIMARY KEY DEFAULT ({_UUID}) CHECK (length(id) = 36),
                product_id  TEXT NOT NULL REFERENCES products (id),
                discount_id TEXT NOT NULL REFERENCES discounts (id),
                sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
                created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                deleted_at  TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS ux_product_discounts
                ON product_discounts (product_id, discount_id) WHERE deleted_at IS NULL;
            CREATE INDEX IF NOT EXISTS idx_product_discounts_discount
                ON product_discounts (discount_id);
        """)
        self.db.commit()

    # ---------- lectura ----------
    def list_all(self):
        self.cursor.execute("SELECT * FROM discounts WHERE deleted_at IS NULL ORDER BY name")
        return self.cursor.fetchall()

    def get_by_id(self, discount_id):
        self.cursor.execute("SELECT * FROM discounts WHERE id = ? AND deleted_at IS NULL", (discount_id,))
        return self.cursor.fetchone()

    def product_ids(self, discount_id) -> set:
        self.cursor.execute("SELECT product_id FROM product_discounts "
                            "WHERE discount_id = ? AND deleted_at IS NULL", (discount_id,))
        return {r["product_id"] for r in self.cursor.fetchall()}

    def for_product(self, product_id):
        """Descuentos ligados a un producto (la vigencia se valida en el controlador)."""
        self.cursor.execute("""
            SELECT d.* FROM discounts d
            JOIN product_discounts pd ON pd.discount_id = d.id AND pd.deleted_at IS NULL
            WHERE pd.product_id = ? AND d.deleted_at IS NULL
        """, (product_id,))
        return self.cursor.fetchall()

    def search_products(self, text="", limit=200):
        like = f"%{text.strip()}%"
        self.cursor.execute("""
            SELECT id, sku, name FROM products
            WHERE deleted_at IS NULL AND (name LIKE ? OR sku LIKE ?)
            ORDER BY name LIMIT ?
        """, (like, like, limit))
        return self.cursor.fetchall()

    # ---------- escritura ----------
    def create(self, **d) -> str:
        discount_id = self.generate_uuid()
        self._run("INSERT INTO discounts (id, name, discount_type, value, requires_authorization, "
                  "valid_from, valid_until, is_active, sync_status) VALUES (?,?,?,?,?,?,?,?,0)",
                  (discount_id, *[d[f] for f in _FIELDS]))
        return discount_id

    def update(self, discount_id, **d) -> None:
        sets = ", ".join(f"{f} = ?" for f in _FIELDS)
        self._run(f"UPDATE discounts SET {sets}, updated_at = ?, sync_status = 0 WHERE id = ?",
                  (*[d[f] for f in _FIELDS], self.get_timestamp(), discount_id))

    def set_active(self, discount_id, active: bool) -> None:
        self._run("UPDATE discounts SET is_active = ?, updated_at = ?, sync_status = 0 WHERE id = ?",
                  (1 if active else 0, self.get_timestamp(), discount_id))

    def soft_delete(self, discount_id) -> None:
        now = self.get_timestamp()
        try:
            self.cursor.execute("UPDATE discounts SET deleted_at = ?, is_active = 0, updated_at = ?, "
                                "sync_status = 0 WHERE id = ?", (now, now, discount_id))
            self.cursor.execute("UPDATE product_discounts SET deleted_at = ?, updated_at = ?, "
                                "sync_status = 0 WHERE discount_id = ? AND deleted_at IS NULL",
                                (now, now, discount_id))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def set_products(self, discount_id, product_ids: set) -> None:
        current, now = self.product_ids(discount_id), self.get_timestamp()
        try:
            for pid in current - product_ids:
                self.cursor.execute("UPDATE product_discounts SET deleted_at = ?, updated_at = ?, "
                                    "sync_status = 0 WHERE discount_id = ? AND product_id = ? "
                                    "AND deleted_at IS NULL", (now, now, discount_id, pid))
            for pid in product_ids - current:
                self.cursor.execute("INSERT INTO product_discounts (id, product_id, discount_id) "
                                    "VALUES (?,?,?)", (self.generate_uuid(), pid, discount_id))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _run(self, sql, params):
        try:
            self.cursor.execute(sql, params)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise