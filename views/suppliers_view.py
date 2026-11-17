import customtkinter as ctk
from datetime import datetime, timezone
from tkinter import messagebox

if __package__:
    from .icons import icon as get_icon
    from .ui_helpers import center_window
else:
    from icons import icon as get_icon
    from ui_helpers import center_window

# Paleta de colores
BG, WHITE, INK, MUTED = '#F5F9FC', '#FFFFFF', '#023047', '#5B7385'
SKY, BLUE_DARK = '#8ECAE6', '#1A7F99'
ORANGE, ORANGE_DARK = '#FB8500', '#E07600'
SOFT, SOFT_HOVER = '#EAF5FB', '#D5EBF6'
RED, RED_HOVER = '#E63946', '#D62828'

# --- Funciones de diseño locales ---
def label(parent, text, size=14, bold=False, color=INK, **kw):
    return ctk.CTkLabel(parent, text=text, text_color=color, font=ctk.CTkFont(size=size, weight='bold' if bold else 'normal'), **kw)

def card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=WHITE, corner_radius=14, border_width=1, border_color='#D7E6EF', **kw)

def button(parent, text, command, primary=False, danger=False, icon=None, **kw):
    kw.setdefault('height', 40)
    kw.setdefault('font', ctk.CTkFont(size=13, weight='bold'))
    
    if danger:
        fg, hover, text_color = RED, RED_HOVER, WHITE
    elif primary:
        fg, hover, text_color = ORANGE, ORANGE_DARK, WHITE
    else:
        fg, hover, text_color = SOFT, SOFT_HOVER, INK

    if icon:
        try:
            kw['image'] = get_icon(icon, text_color, 18)
            kw['compound'] = 'left'
        except KeyError:
            pass # Evita el crash si el icono no existe en el diccionario
        
    return ctk.CTkButton(parent, text=text, command=command, corner_radius=10, fg_color=fg, hover_color=hover, text_color=text_color, **kw)

# --- Ficha completa del proveedor (modal de solo lectura) ---
# (titulo de sección, [(columna, etiqueta, ocupa_2_columnas), ...])
DETAIL_SECTIONS = [
    ('Datos generales', [('code', 'Código interno', False), ('tax_id', 'RFC / Tax ID', False),
                         ('name', 'Nombre comercial', False), ('legal_name', 'Razón social', False)]),
    ('Contacto', [('contact_name', 'Contacto principal', False), ('phone', 'Teléfono', False),
                  ('email', 'Email', True)]),
    ('Domicilio', [('address', 'Dirección', True), ('city', 'Ciudad', False), ('state', 'Estado', False),
                   ('postal_code', 'Código postal', False)]),
    ('Condiciones', [('payment_terms_days', 'Crédito', False), ('notes', 'Notas / Condiciones', True)]),
    ('Registro', [('created_at', 'Creado', False), ('updated_at', 'Última modificación', False),
                  ('sync_status', 'Sincronización', False), ('id', 'ID interno', True)]),
]


def _fmt_datetime(value):
    """ISO-8601 (UTC) -> hora local legible."""
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone().strftime('%d/%m/%Y %H:%M')
    except (TypeError, ValueError):
        return str(value)


def _display_value(key, value):
    if key == 'sync_status':
        return 'Sincronizado' if value == 1 else 'Pendiente de subir'
    if key == 'payment_terms_days':
        return 'Contado' if not value else f"{value} días"
    if value is None or str(value).strip() == '':
        return '—'
    if key in ('created_at', 'updated_at'):
        return _fmt_datetime(value)
    return str(value)


class SupplierDetailModal(ctk.CTkToplevel):
    """Muestra todos los atributos de un proveedor. `supp` es la fila de la tabla suppliers."""

    def __init__(self, parent, supp, on_edit=None):
        super().__init__(parent)
        self.supp, self.on_edit = supp, on_edit
        self.title('Detalle del proveedor')
        self.configure(fg_color=BG)
        self.resizable(False, False)
        self.bind('<Escape>', lambda e: self.destroy())

        keys = supp.keys()
        get = lambda k: supp[k] if k in keys else None
        active = get('is_active') in (None, 1)

        # Encabezado: nombre + estado
        head = card(self)
        head.pack(fill='x', padx=20, pady=(20, 10))
        top = ctk.CTkFrame(head, fg_color='transparent')
        top.pack(fill='x', padx=20, pady=(16, 4))
        label(top, get('name') or '—', 20, True, wraplength=420, justify='left').pack(side='left')
        ctk.CTkLabel(top, text='Activo' if active else 'Inactivo', corner_radius=10, height=24,
                     fg_color=SOFT if active else '#F1F1F1', text_color=BLUE_DARK if active else MUTED,
                     font=ctk.CTkFont(size=12, weight='bold')).pack(side='right', ipadx=10)
        if get('legal_name'):
            label(head, get('legal_name'), 13, False, MUTED, wraplength=520, justify='left').pack(
                anchor='w', padx=20, pady=(0, 14))
        else:
            ctk.CTkFrame(head, fg_color='transparent', height=10).pack()

        # Botones (se empacan antes del cuerpo para que nunca queden cortados)
        foot = ctk.CTkFrame(self, fg_color='transparent')
        foot.pack(side='bottom', fill='x', padx=20, pady=(6, 20))
        button(foot, 'Cerrar', self.destroy, width=100).pack(side='right')
        if on_edit:
            button(foot, 'Editar', self._edit, primary=True, width=100).pack(side='right', padx=(0, 10))

        # Cuerpo con scroll por si la pantalla es pequeña
        body = ctk.CTkScrollableFrame(self, fg_color='transparent')
        body.pack(fill='both', expand=True, padx=10)
        for title, fields in DETAIL_SECTIONS:
            section = card(body)
            section.pack(fill='x', padx=10, pady=6)
            section.grid_columnconfigure((0, 1), weight=1, uniform='cols')
            label(section, title.upper(), 11, True, ORANGE).grid(
                row=0, column=0, columnspan=2, sticky='w', padx=16, pady=(12, 2))
            row, col = 1, 0
            for key, caption, wide in fields:
                if wide and col == 1:
                    row, col = row + 1, 0
                cell = ctk.CTkFrame(section, fg_color='transparent')
                cell.grid(row=row, column=col, columnspan=2 if wide else 1, sticky='ew', padx=16, pady=(4, 6))
                label(cell, caption, 11, True, MUTED).pack(anchor='w')
                label(cell, _display_value(key, get(key)), 13, False, wraplength=520 if wide else 250,
                      justify='left').pack(anchor='w')
                if wide or col == 1:
                    row, col = row + 1, 0
                else:
                    col = 1
            ctk.CTkFrame(section, fg_color='transparent', height=4).grid(row=row + 1, column=0)

        center_window(self, parent, 640, 680)

    def _edit(self):
        self.destroy()
        if self.on_edit:
            self.on_edit(self.supp)


class SuppliersView(ctk.CTkFrame):
    def __init__(self, master, app_controller):
        super().__init__(master, fg_color=BG)
        self.app_controller = app_controller
        
        # Inicializar el controlador
        try:
            from controllers.suppliers_controller import SuppliersController
            self.ctrl = SuppliersController()
        except ImportError:
            self.ctrl = None

        self.current_supplier_id = None
        
        # Configuración del grid principal (2 columnas)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_list_panel()
        self._build_form_panel()
        self.load_suppliers()

    def _build_header(self):
        head = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=0, height=70)
        head.grid(row=0, column=0, columnspan=2, sticky='ew')
        head.grid_propagate(False)
        label(head, 'Proveedores', 22, True).pack(side='left', padx=24)

    def _build_list_panel(self):
        panel = card(self)
        panel.grid(row=1, column=0, sticky='nsew', padx=(24, 12), pady=24)
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        # Barra de búsqueda
        search_frame = ctk.CTkFrame(panel, fg_color='transparent')
        search_frame.grid(row=0, column=0, sticky='ew', padx=20, pady=(20, 10))
        search_frame.grid_columnconfigure(0, weight=1)
        
        self.var_search = ctk.StringVar()
        entry = ctk.CTkEntry(search_frame, textvariable=self.var_search, placeholder_text="Buscar por nombre, código o RFC...", height=38, fg_color=BG, border_color=SKY, text_color=INK)
        entry.grid(row=0, column=0, sticky='ew', padx=(0,10))
        entry.bind('<KeyRelease>', lambda e: self.load_suppliers())
        
        button(search_frame, 'Nuevo Proveedor', self.clear_form, primary=True).grid(row=0, column=1)

        # Lista (Scrollable)
        self.list_frame = ctk.CTkScrollableFrame(panel, fg_color='transparent')
        self.list_frame.grid(row=2, column=0, sticky='nsew', padx=10, pady=10)

    def _build_form_panel(self):
        self.form_panel = card(self)
        self.form_panel.grid(row=1, column=1, sticky='nsew', padx=(12, 24), pady=24)
        
        label(self.form_panel, 'Detalles del Proveedor', 18, True).pack(anchor='w', padx=24, pady=(24, 10))
        
        self.vars = {
            'name': ctk.StringVar(), 'legal_name': ctk.StringVar(),
            'code': ctk.StringVar(), 'tax_id': ctk.StringVar(),
            'contact_name': ctk.StringVar(), 'phone': ctk.StringVar(),
            'email': ctk.StringVar(), 'address': ctk.StringVar(),
            'notes': ctk.StringVar()
        }

        form = ctk.CTkFrame(self.form_panel, fg_color='transparent')
        form.pack(fill='both', expand=True, padx=24, pady=10)
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)

        # --- Fila 1 ---
        label(form, 'Nombre Comercial *', 12, True, MUTED).grid(row=0, column=0, sticky='w', pady=(0,2))
        ctk.CTkEntry(form, textvariable=self.vars['name'], height=36, fg_color=BG, border_color=SKY, text_color=INK).grid(row=1, column=0, sticky='ew', padx=(0,10), pady=(0,15))
        
        label(form, 'Razón Social', 12, True, MUTED).grid(row=0, column=1, sticky='w', pady=(0,2))
        ctk.CTkEntry(form, textvariable=self.vars['legal_name'], height=36, fg_color=BG, border_color=SKY, text_color=INK).grid(row=1, column=1, sticky='ew', pady=(0,15))

        # --- Fila 2 ---
        label(form, 'Código interno', 12, True, MUTED).grid(row=2, column=0, sticky='w', pady=(0,2))
        ctk.CTkEntry(form, textvariable=self.vars['code'], height=36, fg_color=BG, border_color=SKY, text_color=INK).grid(row=3, column=0, sticky='ew', padx=(0,10), pady=(0,15))
        
        label(form, 'RFC / Tax ID', 12, True, MUTED).grid(row=2, column=1, sticky='w', pady=(0,2))
        ctk.CTkEntry(form, textvariable=self.vars['tax_id'], height=36, fg_color=BG, border_color=SKY, text_color=INK).grid(row=3, column=1, sticky='ew', pady=(0,15))

        # --- Fila 3 ---
        label(form, 'Contacto principal', 12, True, MUTED).grid(row=4, column=0, sticky='w', pady=(0,2))
        ctk.CTkEntry(form, textvariable=self.vars['contact_name'], height=36, fg_color=BG, border_color=SKY, text_color=INK).grid(row=5, column=0, sticky='ew', padx=(0,10), pady=(0,15))
        
        label(form, 'Teléfono', 12, True, MUTED).grid(row=4, column=1, sticky='w', pady=(0,2))
        ctk.CTkEntry(form, textvariable=self.vars['phone'], height=36, fg_color=BG, border_color=SKY, text_color=INK).grid(row=5, column=1, sticky='ew', pady=(0,15))

        # --- Fila 4 ---
        label(form, 'Email', 12, True, MUTED).grid(row=6, column=0, sticky='w', pady=(0,2))
        ctk.CTkEntry(form, textvariable=self.vars['email'], height=36, fg_color=BG, border_color=SKY, text_color=INK).grid(row=7, column=0, sticky='ew', padx=(0,10), pady=(0,15))
        
        label(form, 'Dirección', 12, True, MUTED).grid(row=6, column=1, sticky='w', pady=(0,2))
        ctk.CTkEntry(form, textvariable=self.vars['address'], height=36, fg_color=BG, border_color=SKY, text_color=INK).grid(row=7, column=1, sticky='ew', pady=(0,15))

        # --- Fila 5 ---
        label(form, 'Notas / Condiciones', 12, True, MUTED).grid(row=8, column=0, columnspan=2, sticky='w', pady=(0,2))
        ctk.CTkEntry(form, textvariable=self.vars['notes'], height=36, fg_color=BG, border_color=SKY, text_color=INK).grid(row=9, column=0, columnspan=2, sticky='ew', pady=(0,25))

        # --- Botones de acción ---
        action_frame = ctk.CTkFrame(self.form_panel, fg_color='transparent')
        action_frame.pack(fill='x', padx=24, pady=24)
        
        button(action_frame, 'Guardar', self.save_supplier, primary=True).pack(side='right', padx=(10,0))
        
        # El botón de eliminar se crea pero no se muestra (pack) hasta que seleccionamos un proveedor
        self.btn_delete = button(action_frame, 'Eliminar', self.delete_supplier, danger=True)

    def load_suppliers(self):
        if not self.ctrl: return
        for widget in self.list_frame.winfo_children():
            widget.destroy()
            
        suppliers = self.ctrl.get_suppliers(self.var_search.get())
        for supp in suppliers:
            row = ctk.CTkFrame(self.list_frame, fg_color=WHITE, corner_radius=8)
            row.pack(fill='x', pady=2, padx=5)
            
            info = f"{supp['name']}"
            if supp['contact_name']: 
                info += f" | {supp['contact_name']}"
            
            name_lbl = label(row, info, 13, True)
            name_lbl.pack(side='left', padx=15, pady=12)
            button(row, 'Editar', lambda s=supp: self.load_form(s), height=30).pack(side='right', padx=15)
            button(row, 'Ver', lambda s=supp: self.show_supplier(s), height=30, width=70).pack(side='right')
            # Clic en la fila o en el nombre = ver ficha completa
            for widget in (row, name_lbl):
                widget.bind('<Button-1>', lambda e, s=supp: self.show_supplier(s))
                widget.configure(cursor='hand2')

    def show_supplier(self, supp):
        """Abre la ficha completa (solo lectura). Desde ahí se puede pasar a editar."""
        SupplierDetailModal(self.winfo_toplevel(), supp, on_edit=self.load_form)

    def load_form(self, supp):
        self.current_supplier_id = supp['id']
        for key in self.vars:
            self.vars[key].set(supp[key] if supp[key] else "")
        self.btn_delete.pack(side='left')

    def clear_form(self):
        self.current_supplier_id = None
        for key in self.vars:
            self.vars[key].set("")
        self.btn_delete.pack_forget()

    def save_supplier(self):
        # 1. Validación de seguridad (por si el controlador falló al importar)
        if not self.ctrl: 
            messagebox.showerror("Error Crítico", "No se encontró controllers/suppliers_controller.py o tiene un error de sintaxis.")
            return
            
        # 2. Recolectar datos
        data = {k: v.get().strip() for k, v in self.vars.items()}
        
        # 3. Validar campos obligatorios
        if not data['name']:
            messagebox.showwarning("Faltan datos", "El nombre comercial es obligatorio.")
            return
            
        # 4. Intentar guardar
        if self.ctrl.save_supplier(data, self.current_supplier_id):
            messagebox.showinfo("Éxito", "Proveedor guardado correctamente.")
            self.load_suppliers()
            self.clear_form()
        else:
            messagebox.showerror("Error", "No se pudo guardar el proveedor.\n\nAsegúrate de que el Código interno o RFC no estén duplicados en otro proveedor.")

    def delete_supplier(self):
        if not self.ctrl or not self.current_supplier_id: return
        
        if messagebox.askyesno("Confirmar", "¿Seguro que deseas eliminar este proveedor?"):
            if self.ctrl.delete_supplier(self.current_supplier_id):
                self.load_suppliers()
                self.clear_form()
            else:
                messagebox.showerror("Error", "No se pudo eliminar el proveedor.")