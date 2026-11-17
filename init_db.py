import os
import sqlite3
from config.db_connection import DBConnection

def execute_sql_file(cursor, filepath):
    """Lee un archivo .sql y ejecuta su contenido en la base de datos."""
    print(f"Leyendo {filepath}...")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            sql_script = f.read()
        
        # executescript permite correr comandos múltiples (como triggers e inserts)
        cursor.executescript(sql_script)
        print(f"✓ Éxito al ejecutar: {os.path.basename(filepath)}")
    except FileNotFoundError:
        print(f"❌ Error: No se encontró el archivo {filepath}")
    except sqlite3.Error as e:
        print(f"❌ Error de SQLite en {os.path.basename(filepath)}: {e}")
        # Algunos triggers de error de validación lanzan excepción, la mostramos
        raise e

def initialize_database():
    print("Iniciando reconstrucción de la base de datos SotyPDV...")
    
    # 1. Por seguridad, vamos a borrar la base de datos vieja si existe, 
    # para asegurar que el nuevo esquema se aplique desde cero.
    if os.path.exists("pos_local.db"):
        os.remove("pos_local.db")
        print("✓ Base de datos anterior eliminada.")

    db = DBConnection().connect()
    cursor = db.cursor()

    # 2. Rutas a los archivos SQL
    schema_path = os.path.join("sql", "pos_schema_sqlite.sql")
    seed_path = os.path.join("sql", "pos_seed_sqlite.sql")

    # 3. Ejecutar el esquema (crea todas las tablas y triggers)
    print("\n--- PASO 1: CREANDO ESQUEMA (TABLAS Y TRIGGERS) ---")
    execute_sql_file(cursor, schema_path)

    # 4. Ejecutar la semilla (inserta roles, permisos, configuraciones básicas)
    print("\n--- PASO 2: INSERTANDO DATOS SEMILLA ---")
    execute_sql_file(cursor, seed_path)

    db.commit()
    print("\n¡Base de datos inicializada completamente!")
    
    print("\n--- PASO 3: REQUERIDO ---")
    print("Por favor, ejecuta ahora: py create_admin.py para crear tu usuario de acceso.")

if __name__ == "__main__":
    initialize_database()