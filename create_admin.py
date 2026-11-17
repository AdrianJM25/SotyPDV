from models.base_model import BaseModel
from utils.security import hash_pin

ADMIN_USERNAME = "admin"
ADMIN_PIN = "123456"   # cámbialo después del primer login


def create_initial_admin():
    base = BaseModel()

    try:
        # 0. Si el admin ya existe, no hay nada que hacer
        base.cursor.execute(
            "SELECT 1 FROM users WHERE username = ? AND deleted_at IS NULL", (ADMIN_USERNAME,))
        if base.cursor.fetchone():
            print(f"ℹ️ El usuario '{ADMIN_USERNAME}' ya existe. No se hizo ningún cambio.")
            return

        # 1. Sucursal Matriz (se reutiliza si ya existe)
        base.cursor.execute("SELECT id FROM branches WHERE code = 'MAT' AND deleted_at IS NULL")
        row = base.cursor.fetchone()
        if row:
            branch_id = row["id"]
        else:
            branch_id = base.generate_uuid()
            base.cursor.execute("""
                INSERT INTO branches (id, code, name, city, is_active)
                VALUES (?, 'MAT', 'Sucursal Matriz (Jiutepec)', 'Jiutepec', 1)
            """, (branch_id,))

        # 2. Caja Principal (se reutiliza si ya existe)
        base.cursor.execute(
            "SELECT id FROM cash_registers WHERE branch_id = ? AND code = 'C01' AND deleted_at IS NULL",
            (branch_id,))
        if not base.cursor.fetchone():
            base.cursor.execute("""
                INSERT INTO cash_registers (id, branch_id, code, name, ticket_series, is_active)
                VALUES (?, ?, 'C01', 'Caja Principal', 'A', 1)
            """, (base.generate_uuid(), branch_id))

        # 3. Rol Administrador (lo crea el seed)
        base.cursor.execute(
            "SELECT id FROM roles WHERE name = 'Administrador' AND deleted_at IS NULL")
        role_result = base.cursor.fetchone()
        if not role_result:
            base.db.rollback()
            print("❌ Error: No se encontró el rol Administrador. ¿Ejecutaste pos_seed_sqlite.sql?")
            return
        role_id = role_result["id"]

        # 4. Usuario Administrador
        base.cursor.execute("""
            INSERT INTO users (id, branch_id, role_id, username, full_name, pin_hash, is_active, sync_status)
            VALUES (?, ?, ?, ?, 'Super Administrador', ?, 1, 0)
        """, (base.generate_uuid(), branch_id, role_id, ADMIN_USERNAME, hash_pin(ADMIN_PIN)))

        base.db.commit()
        print("✅ ¡Entorno creado exitosamente!")
        print("Sucursal: Matriz (Jiutepec)")
        print("Caja: Principal (C01)")
        print(f"Usuario: {ADMIN_USERNAME}  |  PIN: {ADMIN_PIN}")

    except Exception as e:
        base.db.rollback()
        print(f"❌ Error al crear administrador: {e}")


if __name__ == "__main__":
    create_initial_admin()