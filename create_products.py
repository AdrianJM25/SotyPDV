from models.base_model import BaseModel

def create_test_products():
    base = BaseModel()
    try:
        # Obtener IDs de Unidad (Pieza) e Impuesto (IVA 16%) de la semilla
        base.cursor.execute("SELECT id FROM units WHERE code = 'PZA'")
        unit_id = base.cursor.fetchone()['id']
        
        base.cursor.execute("SELECT id FROM tax_rates WHERE code = 'IVA16'")
        tax_id = base.cursor.fetchone()['id']

        productos = [
            ('7501055300075', 'Coca Cola Regular 600ml', 1200, 1800), # Costo: $12.00, Venta: $18.00
            ('7501011167367', 'Papas Sabritas Original 40g', 1000, 1600) # Costo: $10.00, Venta: $16.00
        ]

        for sku, name, cost, price in productos:
            base.cursor.execute("""
                INSERT OR IGNORE INTO products 
                (id, unit_id, tax_rate_id, sku, name, cost_price, sale_price, track_inventory, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1)
            """, (base.generate_uuid(), unit_id, tax_id, sku, name, cost, price))

        base.db.commit()
        print("✅ Productos de prueba creados exitosamente.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    create_test_products()