import logging
from models.base_model import BaseModel
from utils.exceptions import ValidationError, POSError

log = logging.getLogger(__name__)

class CustomersController(BaseModel):
    def __init__(self):
        super().__init__()

    def get_all_customers(self, search_text=""):
        """Devuelve la lista de clientes filtrada por nombre, teléfono o RFC."""
        search_text = (search_text or "").strip()
        
        if search_text:
            like = f"%{search_text}%"
            rows = self.cursor.execute("""
                SELECT id, name, phone, email, birth_date, tax_id, legal_name, address
                FROM customers
                WHERE deleted_at IS NULL AND (name LIKE ? OR phone LIKE ? OR tax_id LIKE ?)
                ORDER BY name
            """, (like, like, like)).fetchall()
        else:
            rows = self.cursor.execute("""
                SELECT id, name, phone, email, birth_date, tax_id, legal_name, address
                FROM customers
                WHERE deleted_at IS NULL
                ORDER BY name
            """).fetchall()
        
        result = []
        for r in rows:
            d = dict(r)
            d["birthday"] = d.pop("birth_date", "")
            result.append(d)
        return result

    def get_customer_by_id(self, customer_id):
        """Obtiene un cliente específico por su ID."""
        row = self.cursor.execute("""
            SELECT id, name, phone, email, birth_date, tax_id, legal_name, address
            FROM customers
            WHERE id = ? AND deleted_at IS NULL
        """, (customer_id,)).fetchone()
        
        if not row:
            return None
        d = dict(row)
        d["birthday"] = d.pop("birth_date", "")
        return d

    def save_customer(self, data, customer_id=None):
        """Registra un nuevo cliente o actualiza uno existente."""
        if not data.get("name"):
            raise ValidationError("El nombre del cliente es obligatorio.")
            
        now = self.get_timestamp()
        try:
            if customer_id:
                self.cursor.execute("""
                    UPDATE customers 
                    SET name = ?, phone = ?, email = ?, birth_date = ?, tax_id = ?, legal_name = ?, address = ?, updated_at = ?, sync_status = 0
                    WHERE id = ?
                """, (
                    data.get("name").strip(),
                    data.get("phone", "").strip(),
                    data.get("email", "").strip(),
                    data.get("birthday", "").strip(),
                    data.get("tax_id", "").strip(),
                    data.get("legal_name", "").strip(),
                    data.get("address", "").strip(),
                    now,
                    customer_id
                ))
                self.db.commit()
                return customer_id
            else:
                new_id = self.generate_uuid()
                self.cursor.execute("""
                    INSERT INTO customers (id, name, phone, email, birth_date, tax_id, legal_name, address, created_at, updated_at, sync_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """, (
                    new_id,
                    data.get("name").strip(),
                    data.get("phone", "").strip(),
                    data.get("email", "").strip(),
                    data.get("birthday", "").strip(),
                    data.get("tax_id", "").strip(),
                    data.get("legal_name", "").strip(),
                    data.get("address", "").strip(),
                    now, now
                ))
                self.db.commit()
                return new_id
        except Exception as e:
            self.db.rollback()
            log.exception("Error guardando cliente")
            raise POSError("Error al guardar el cliente en la base de datos.")

    def delete_customer(self, customer_id):
        """Realiza un borrado lógico (soft delete) del cliente."""
        now = self.get_timestamp()
        try:
            self.cursor.execute("""
                UPDATE customers 
                SET deleted_at = ?, sync_status = 0 
                WHERE id = ?
            """, (now, customer_id))
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            log.exception("Error eliminando cliente")
            raise POSError("No se pudo eliminar el cliente.")

    def get_customer_history(self, customer_id):
        """Obtiene el historial de compras conectado del cliente."""
        try:
            rows = self.cursor.execute("""
                SELECT id, ticket_number, total, sold_at 
                FROM sales 
                WHERE customer_id = ? AND deleted_at IS NULL
                ORDER BY sold_at DESC
            """, (customer_id,)).fetchall()
            
            result = []
            for r in rows:
                d = dict(r)
                d["total_fmt"] = f"${d['total'] / 100:.2f}"
                result.append(d)
            return result
        except Exception:
            # Si la tabla sales no cuenta con customer_id en alguna implementación previa, retorna vacío de forma segura
            return []