import logging
from config.db_connection import DBConnection

log = logging.getLogger(__name__)

class SuppliersController:
    def __init__(self):
        self.conn = DBConnection().connect()
        self.cursor = self.conn.cursor()

    def get_suppliers(self, search_query=""):
        """Obtiene la lista de proveedores activos."""
        query = "SELECT * FROM suppliers WHERE deleted_at IS NULL"
        params = []
        
        if search_query:
            query += " AND (name LIKE ? OR code LIKE ? OR tax_id LIKE ? OR contact_name LIKE ?)"
            search = f"%{search_query}%"
            params.extend([search, search, search, search])
            
        query += " ORDER BY name ASC"
        return self.cursor.execute(query, params).fetchall()

    def save_supplier(self, data, supplier_id=None):
        """Inserta o actualiza un proveedor."""
        # Convertir strings vacíos a None para evitar choques en la base de datos
        for key in data:
            if data[key] == "":
                data[key] = None
                
        try:
            if supplier_id:
                query = """
                    UPDATE suppliers 
                    SET code=?, name=?, legal_name=?, tax_id=?, contact_name=?, 
                        phone=?, email=?, address=?, notes=?, 
                        updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status=0
                    WHERE id=?
                """
                self.cursor.execute(query, (
                    data.get('code'), data.get('name'), data.get('legal_name'), data.get('tax_id'),
                    data.get('contact_name'), data.get('phone'), data.get('email'), data.get('address'), 
                    data.get('notes'), supplier_id
                ))
            else:
                query = """
                    INSERT INTO suppliers (code, name, legal_name, tax_id, contact_name, phone, email, address, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                self.cursor.execute(query, (
                    data.get('code'), data.get('name'), data.get('legal_name'), data.get('tax_id'),
                    data.get('contact_name'), data.get('phone'), data.get('email'), data.get('address'), 
                    data.get('notes')
                ))
            self.conn.commit()
            return True
        except Exception as e:
            log.exception(f"Error guardando proveedor: {e}")
            self.conn.rollback()
            return False
        
    def delete_supplier(self, supplier_id):
        """Realiza un borrado lógico del proveedor."""
        try:
            self.cursor.execute("""
                UPDATE suppliers 
                SET deleted_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status=0 
                WHERE id=?
            """, (supplier_id,))
            self.conn.commit()
            return True
        except Exception as e:
            log.exception("Error eliminando proveedor")
            self.conn.rollback()
            return False