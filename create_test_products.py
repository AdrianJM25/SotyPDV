import sqlite3

from models.base_model import BaseModel

# (sku / código de barras, nombre, costo en centavos, precio en centavos)
PRODUCTS = [
    ("7501055300075", "Coca Cola Regular 600ml", 1200, 1800),
    ("7501011167367", "Papas Sabritas Original 40g", 1000, 1600),
]
INITIAL_STOCK = 50


def create_test_products():
    base = BaseModel()
    created = existing = 0
    try:
        db_file = base.cursor.execute("PRAGMA database_list").fetchone()["file"]
        print(f"📂 Base de datos usada: {db_file}")      # compáralo con la que abre tu app

        unit = base.cursor.execute("SELECT id FROM units WHERE code = 'PZA' AND deleted_at IS NULL").fetchone()
        tax = base.cursor.execute("SELECT id FROM tax_rates WHERE code = 'IVA16' AND deleted_at IS NULL").fetchone()
        if not unit or not tax:
            raise RuntimeError("Faltan la unidad 'PZA' o el impuesto 'IVA16'. Ejecuta primero la semilla "
                               "inicial (pos_seed_sqlite.sql).")
        branch = base.cursor.execute(
            "SELECT id FROM branches WHERE deleted_at IS NULL ORDER BY created_at LIMIT 1").fetchone()
        if not branch:
            print("⚠️  No hay sucursal: los productos se crean SIN existencias.")

        for sku, name, cost, price in PRODUCTS:
            if base.cursor.execute("SELECT 1 FROM products WHERE sku = ? AND deleted_at IS NULL", (sku,)).fetchone():
                existing += 1
                print(f"↩️  Ya existía: {sku} {name}")
                continue
            product_id, now = base.generate_uuid(), base.get_timestamp()
            try:
                # INSERT normal (NO "OR IGNORE"): si algo falla, quieres ver el error, no que se oculte.
                base.cursor.execute("""
                    INSERT INTO products (id, unit_id, tax_rate_id, sku, name, cost_price, sale_price,
                                          track_inventory, is_active, created_at, updated_at, sync_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?, 0)
                """, (product_id, unit["id"], tax["id"], sku, name, cost, price, now, now))
                if branch:      # entrada de kardex: el trigger actualiza inventory_stock
                    base.cursor.execute("""
                        INSERT INTO inventory_movements (id, branch_id, product_id, movement_type, quantity_change,
                                                         unit_cost, reason, occurred_at, created_at, updated_at, sync_status)
                        VALUES (?, ?, ?, 'initial', ?, ?, 'Inventario inicial de prueba', ?, ?, ?, 0)
                    """, (base.generate_uuid(), branch["id"], product_id, INITIAL_STOCK, cost, now, now, now))
                created += 1
                print(f"➕ Creado: {sku} {name}")
            except sqlite3.IntegrityError as exc:
                print(f"❌ No se pudo insertar '{sku}': {exc}")

        base.db.commit()
        active = base.cursor.execute(
            "SELECT COUNT(*) AS n FROM products WHERE is_active = 1 AND deleted_at IS NULL").fetchone()["n"]
        print(f"✅ Creados: {created} | ya existían: {existing} | productos activos en la BD: {active}")
    except Exception as exc:
        base.db.rollback()
        print(f"❌ Error: {exc}")


if __name__ == "__main__":
    create_test_products()
