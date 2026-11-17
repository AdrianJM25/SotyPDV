import uuid
from datetime import datetime, timezone
from config.db_connection import DBConnection

class BaseModel:
    def __init__(self):
        # Todos los modelos heredan la conexión a la base de datos
        self.db = DBConnection().connect()
        self.cursor = self.db.cursor()

    @staticmethod
    def generate_uuid():
        """Genera un UUID v4 seguro para sincronizar con PostgreSQL en Laravel."""
        return str(uuid.uuid4())

    @staticmethod
    def get_timestamp():
        """Genera la fecha y hora actual en formato estándar (UTC)."""
        return datetime.now(timezone.utc).isoformat()