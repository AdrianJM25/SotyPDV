import customtkinter as ctk
from tkinter import messagebox

if __package__:
    from .icons import icon as get_icon
else:
    from icons import icon as get_icon

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
            pass
        
    return ctk.CTkButton(parent, text=text, command=command, corner_radius=10, fg_color=fg, hover_color=hover, text_color=text_color, **kw)


class CategoriesView(ctk.CTkFrame):
    def __init__(self, master, app_controller):
        super().__init__(master, fg_color=BG)
        self.app_controller = app_controller
        
        try:
            from controllers.categories_controller import CategoriesController
            self.ctrl = CategoriesController()
        except ImportError:
            self.ctrl = None

        self.current_category_id = None
        self.parent_map = {} # Mapea nombres a IDs para el OptionMenu
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_list_panel()
        self._build_form_panel()
        self.load_categories()

    def _build_header(self):
        head = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=0, height=70)
        head.grid(row=0, column=0, columnspan=2, sticky='ew')
        head.grid_propagate(False)
        label(head, 'Categorías', 22, True).pack(side='left', padx=24)

    def _build_list_panel(self):
        panel = card(self)
        panel.grid(row=1, column=0, sticky='nsew', padx=(24, 12), pady=24)
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        search_frame = ctk.CTkFrame(panel, fg_color='transparent')
        search_frame.grid(row=0, column=0, sticky='ew', padx=20, pady=(20, 10))
        search_frame.grid_columnconfigure(0, weight=1)
        
        self.var_search = ctk.StringVar()
        entry = ctk.CTkEntry(search_frame, textvariable=self.var_search, placeholder_text="Buscar categoría...", height=38, fg_color=BG, border_color=SKY, text_color=INK)
        entry.grid(row=0, column=0, sticky='ew', padx=(0,10))
        entry.bind('<KeyRelease>', lambda e: self.load_categories())
        
        button(search_frame, 'Nueva Categoría', self.clear_form, primary=True).grid(row=0, column=1)

        self.list_frame = ctk.CTkScrollableFrame(panel, fg_color='transparent')
        self.list_frame.grid(row=2, column=0, sticky='nsew', padx=10, pady=10)

    def _build_form_panel(self):
        self.form_panel = card(self)
        self.form_panel.grid(row=1, column=1, sticky='nsew', padx=(12, 24), pady=24)
        
        label(self.form_panel, 'Detalles de Categoría', 18, True).pack(anchor='w', padx=24, pady=(24, 10))
        
        self.vars = {
            'name': ctk.StringVar(), 
            'description': ctk.StringVar(),
            'color': ctk.StringVar(), 
            'sort_order': ctk.StringVar(value="0"),
            'parent_name': ctk.StringVar(value="Ninguna")
        }

        form = ctk.CTkFrame(self.form_panel, fg_color='transparent')
        form.pack(fill='both', expand=True, padx=24, pady=10)
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)

        # Fila 1
        label(form, 'Nombre de la Categoría *', 12, True, MUTED).grid(row=0, column=0, sticky='w', pady=(0,2))
        ctk.CTkEntry(form, textvariable=self.vars['name'], height=36, fg_color=BG, border_color=SKY, text_color=INK).grid(row=1, column=0, sticky='ew', padx=(0,10), pady=(0,15))
        
        label(form, 'Categoría Padre (Subcategoría de)', 12, True, MUTED).grid(row=0, column=1, sticky='w', pady=(0,2))
        self.opt_parent = ctk.CTkOptionMenu(form, variable=self.vars['parent_name'], values=["Ninguna"], height=36, fg_color=BG, button_color=SKY, button_hover_color=BLUE_DARK, text_color=INK)
        self.opt_parent.grid(row=1, column=1, sticky='ew', pady=(0,15))

        # Fila 2
        label(form, 'Descripción', 12, True, MUTED).grid(row=2, column=0, columnspan=2, sticky='w', pady=(0,2))
        ctk.CTkEntry(form, textvariable=self.vars['description'], height=36, fg_color=BG, border_color=SKY, text_color=INK).grid(row=3, column=0, columnspan=2, sticky='ew', pady=(0,15))

        # Fila 3
        label(form, 'Color (Hex, ej: #FF8800)', 12, True, MUTED).grid(row=4, column=0, sticky='w', pady=(0,2))
        ctk.CTkEntry(form, textvariable=self.vars['color'], height=36, fg_color=BG, border_color=SKY, text_color=INK).grid(row=5, column=0, sticky='ew', padx=(0,10), pady=(0,15))
        
        label(form, 'Orden de visualización (Número)', 12, True, MUTED).grid(row=4, column=1, sticky='w', pady=(0,2))
        ctk.CTkEntry(form, textvariable=self.vars['sort_order'], height=36, fg_color=BG, border_color=SKY, text_color=INK).grid(row=5, column=1, sticky='ew', pady=(0,15))

        action_frame = ctk.CTkFrame(self.form_panel, fg_color='transparent')
        action_frame.pack(fill='x', padx=24, pady=24)
        
        button(action_frame, 'Guardar', self.save_category, primary=True).pack(side='right', padx=(10,0))
        self.btn_delete = button(action_frame, 'Eliminar', self.delete_category, danger=True)
        self.btn_delete.pack_forget()

    def load_parent_options(self):
        if not self.ctrl: return
        parents = self.ctrl.get_parent_options(exclude_id=self.current_category_id)
        self.parent_map = {"Ninguna": None}
        options = ["Ninguna"]
        for p in parents:
            self.parent_map[p['name']] = p['id']
            options.append(p['name'])
        self.opt_parent.configure(values=options)

    def load_categories(self):
        if not self.ctrl: return
        self.load_parent_options()
        
        for widget in self.list_frame.winfo_children():
            widget.destroy()
            
        categories = self.ctrl.get_categories(self.var_search.get())
        for cat in categories:
            row = ctk.CTkFrame(self.list_frame, fg_color=WHITE, corner_radius=8)
            row.pack(fill='x', pady=2, padx=5)
            
            info = cat['name']
            if cat['parent_name']:
                info = f"{cat['parent_name']} > {info}"
                
            label(row, info, 13, True).pack(side='left', padx=15, pady=12)
            button(row, 'Editar', lambda c=cat: self.load_form(c), height=30).pack(side='right', padx=15)

    def load_form(self, cat):
        self.current_category_id = cat['id']
        self.load_parent_options() # Recargar para excluir la actual y evitar ciclos
        
        self.vars['name'].set(cat['name'] or "")
        self.vars['description'].set(cat['description'] or "")
        self.vars['color'].set(cat['color'] or "")
        self.vars['sort_order'].set(str(cat['sort_order']))
        self.vars['parent_name'].set(cat['parent_name'] if cat['parent_name'] else "Ninguna")
        
        self.btn_delete.pack(side='left')

    def clear_form(self):
        self.current_category_id = None
        self.load_parent_options()
        
        self.vars['name'].set("")
        self.vars['description'].set("")
        self.vars['color'].set("")
        self.vars['sort_order'].set("0")
        self.vars['parent_name'].set("Ninguna")
        
        self.btn_delete.pack_forget()

    def save_category(self):
        if not self.ctrl: 
            messagebox.showerror("Error Crítico", "Controlador no disponible.")
            return
            
        data = {
            'name': self.vars['name'].get().strip(),
            'description': self.vars['description'].get().strip(),
            'color': self.vars['color'].get().strip(),
            'sort_order': self.vars['sort_order'].get().strip() or "0",
            'parent_id': self.parent_map.get(self.vars['parent_name'].get())
        }
        
        if not data['name']:
            messagebox.showwarning("Faltan datos", "El nombre de la categoría es obligatorio.")
            return
            
        if self.ctrl.save_category(data, self.current_category_id):
            messagebox.showinfo("Éxito", "Categoría guardada correctamente.")
            self.load_categories()
            self.clear_form()
        else:
            messagebox.showerror("Error", "No se pudo guardar la categoría.")

    def delete_category(self):
        if not self.ctrl or not self.current_category_id: return
        
        if messagebox.askyesno("Confirmar", "¿Seguro que deseas eliminar esta categoría?"):
            try:
                if self.ctrl.delete_category(self.current_category_id):
                    self.load_categories()
                    self.clear_form()
            except ValueError as ve:
                messagebox.showwarning("Aviso", str(ve))
            except Exception:
                messagebox.showerror("Error", "No se pudo eliminar la categoría.")