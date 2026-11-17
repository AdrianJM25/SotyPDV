import sqlite3
from sqlite3 import Error

class DBConnection:
    _instance = None

    def __new__(cls):
        # Patrón Singleton: Asegura que solo exista una instancia de la conexión en toda la app
        if cls._instance is None:
            cls._instance = super(DBConnection, cls).__new__(cls)
            cls._instance.connection = None
        return cls._instance

    def connect(self):
        if self.connection is None:
            try:
                # check_same_thread=False permite que procesos en segundo plano (como la sincronización a Laravel) usen la conexión
                self.connection = sqlite3.connect("pos_local.db", check_same_thread=False)
                
                # Activar llaves foráneas (SQLite las trae apagadas por defecto)
                self.connection.execute("PRAGMA foreign_keys = 1")
                
                # Permite acceder a las columnas por su nombre (ej. fila['nombre']) en lugar de índices (fila[0])
                self.connection.row_factory = sqlite3.Row 
            except Error as e:
                print(f"Error crítico conectando a SQLite: {e}")
        
        return self.connection

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None