import logging
from config.db_connection import DBConnection

log = logging.getLogger(__name__)

class CategoriesController:
    def __init__(self):
        self.conn = DBConnection().connect()
        self.cursor = self.conn.cursor()

    def get_categories(self, search_query=""):
        """Obtiene la lista de categorías activas."""
        query = """
            SELECT c.*, p.name as parent_name 
            FROM categories c
            LEFT JOIN categories p ON c.parent_id = p.id
            WHERE c.deleted_at IS NULL
        """
        params = []
        
        if search_query:
            query += " AND (c.name LIKE ? OR c.description LIKE ?)"
            search = f"%{search_query}%"
            params.extend([search, search])
            
        query += " ORDER BY c.sort_order ASC, c.name ASC"
        return self.cursor.execute(query, params).fetchall()

    def get_parent_options(self, exclude_id=None):
        """Obtiene categorías para usarlas como 'Categoría Padre' (evitando ciclos)."""
        query = "SELECT id, name FROM categories WHERE deleted_at IS NULL"
        params = []
        if exclude_id:
            query += " AND id != ?"
            params.append(exclude_id)
        query += " ORDER BY name ASC"
        return self.cursor.execute(query, params).fetchall()

    def save_category(self, data, category_id=None):
        """Inserta o actualiza una categoría."""
        for key in data:
            if data[key] == "" or data[key] == "Ninguna":
                data[key] = None
                
        try:
            if category_id:
                query = """
                    UPDATE categories 
                    SET parent_id=?, name=?, description=?, color=?, sort_order=?, 
                        updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status=0
                    WHERE id=?
                """
                self.cursor.execute(query, (
                    data.get('parent_id'), data.get('name'), data.get('description'), 
                    data.get('color'), data.get('sort_order', 0), category_id
                ))
            else:
                query = """
                    INSERT INTO categories (parent_id, name, description, color, sort_order)
                    VALUES (?, ?, ?, ?, ?)
                """
                self.cursor.execute(query, (
                    data.get('parent_id'), data.get('name'), data.get('description'), 
                    data.get('color'), data.get('sort_order', 0)
                ))
            self.conn.commit()
            return True
        except Exception as e:
            log.exception(f"Error guardando categoría: {e}")
            self.conn.rollback()
            return False

    def delete_category(self, category_id):
        """Realiza un borrado lógico de la categoría."""
        try:
            # Opción segura: verificar si tiene subcategorías antes de borrar
            has_children = self.cursor.execute("SELECT id FROM categories WHERE parent_id=? AND deleted_at IS NULL", (category_id,)).fetchone()
            if has_children:
                raise ValueError("No se puede eliminar una categoría que tiene subcategorías.")

            self.cursor.execute("""
                UPDATE categories 
                SET deleted_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status=0 
                WHERE id=?
            """, (category_id,))
            self.conn.commit()
            return True
        except Exception as e:
            log.exception(f"Error eliminando categoría: {e}")
            self.conn.rollback()
            raise e