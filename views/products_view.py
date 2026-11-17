import customtkinter as ctk
from tkinter import ttk, messagebox
import logging

log = logging.getLogger(__name__)

class ProductsView(ctk.CTkFrame):
    def __init__(self, master, app_controller):
        super().__init__(master, fg_color="transparent")
        self.app_controller = app_controller
        self.product_controller = app_controller.product_controller
        
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        self._build_header()
        self._build_table()
        self.load_data()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        
        ctk.CTkLabel(header, text="Catálogo de Productos", font=ctk.CTkFont(size=24, weight="bold"), text_color="#142338").pack(side="left")
        
        btn_add = ctk.CTkButton(header, text="+ Nuevo Producto", font=ctk.CTkFont(weight="bold"), 
                                fg_color="#0F766E", hover_color="#115E59", command=self.open_new_product_modal)
        btn_add.pack(side="right")

    def _build_table(self):
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background="#FFFFFF", foreground="#142338", rowheight=35, 
                        fieldbackground="#FFFFFF", bordercolor="#E1E7EF", borderwidth=0, font=("Arial", 11))
        style.map('Treeview', background=[('selected', '#EAF6F3')], foreground=[('selected', '#0F766E')])
        style.configure("Treeview.Heading", background="#F8FAFC", foreground="#64748B", font=("Arial", 11, "bold"), borderwidth=0)
        
        table_frame = ctk.CTkFrame(self, fg_color="#FFFFFF", corner_radius=15, border_width=1, border_color="#E1E7EF")
        table_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        table_frame.pack_propagate(False)
        
        columns = ("id", "sku", "name", "category", "unit", "cost", "price", "stock")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        
        self.tree.heading("id", text="ID")
        self.tree.heading("sku", text="SKU / Código")
        self.tree.heading("name", text="Producto")
        self.tree.heading("category", text="Categoría")
        self.tree.heading("unit", text="Unidad")
        self.tree.heading("cost", text="Costo")
        self.tree.heading("price", text="Precio Venta")
        self.tree.heading("stock", text="Existencia")
        
        self.tree.column("id", width=0, stretch=False)
        self.tree.column("sku", width=120)
        self.tree.column("name", width=250)
        self.tree.column("category", width=120)
        self.tree.column("unit", width=80, anchor="center")
        self.tree.column("cost", width=90, anchor="e")
        self.tree.column("price", width=90, anchor="e")
        self.tree.column("stock", width=90, anchor="center")
        
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        scrollbar.pack(side="right", fill="y", pady=10)

        self.tree.bind("<Double-1>", lambda e: self.edit_selected())
        
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))
        
        ctk.CTkButton(action_frame, text="Ver / Editar", fg_color="#3B82F6", hover_color="#2563EB", 
                      command=self.edit_selected).pack(side="left", padx=(0, 10))
        ctk.CTkButton(action_frame, text="Eliminar", fg_color="#EF4444", hover_color="#DC2626", 
                      command=self.delete_selected).pack(side="left")

    def load_data(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        products = self.product_controller.get_all_products()
        for p in products:
            stock_text = f"{p['stock']:g}" if p.get('track_inventory') else "N/A"
            cat_name = p.get("category_name") or "Sin categoría"
            unit_name = p.get("unit_name") or "Pieza"
            
            self.tree.insert("", "end", values=(
                p["id"], p["sku"], p["name"], cat_name, unit_name, 
                p.get("cost_price_fmt", "$0.00"), p.get("sale_price_fmt", "$0.00"), stock_text
            ))

    def get_selected_product_id(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Atención", "Selecciona un producto de la lista.")
            return None
        return self.tree.item(selected[0], "values")[0]

    def edit_selected(self):
        product_id = self.get_selected_product_id()
        if product_id:
            product_data = self.product_controller.get_product_by_id(product_id)
            if product_data:
                self.open_edit_product_modal(product_data)
            else:
                messagebox.showerror("Error", "No se pudo cargar la información.")

    def delete_selected(self):
        product_id = self.get_selected_product_id()
        if product_id:
            if messagebox.askyesno("Confirmar Eliminación", "¿Estás seguro de que deseas eliminar este producto?"):
                try:
                    self.product_controller.delete_product(product_id)
                    self.load_data()
                except Exception as e:
                    messagebox.showerror("Error", f"No se pudo eliminar: {e}")

    # ==========================================
    # MODAL: NUEVO PRODUCTO
    # ==========================================
    def open_new_product_modal(self):
        win = ctk.CTkToplevel(self)
        win.title("Nuevo Producto")
        win.geometry("500x700")
        win.resizable(False, False)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        
        win.update_idletasks()
        win.geometry(f"+{(win.winfo_screenwidth()-500)//2}+{(win.winfo_screenheight()-700)//2}")

        ctk.CTkLabel(win, text="Nuevo Producto", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=20)
        
        form = ctk.CTkFrame(win, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=40)
        
        vars = {
            "sku": ctk.StringVar(), "name": ctk.StringVar(),
            "cost_price": ctk.StringVar(value="0.00"), "sale_price": ctk.StringVar(value="0.00"),
            "track_inventory": ctk.BooleanVar(value=True)
        }
        
        def add_field(label, var):
            ctk.CTkLabel(form, text=label, font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(10, 2))
            ctk.CTkEntry(form, textvariable=var, height=35).pack(fill="x")

        add_field("SKU / Código de Barras *", vars["sku"])
        add_field("Nombre del Producto *", vars["name"])
        
        prices = ctk.CTkFrame(form, fg_color="transparent")
        prices.pack(fill="x", pady=10)
        prices.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(prices, text="Costo ($)", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(prices, textvariable=vars["cost_price"], height=35).grid(row=1, column=0, sticky="ew", padx=(0, 5))
        ctk.CTkLabel(prices, text="Precio Venta ($) *", font=ctk.CTkFont(weight="bold")).grid(row=0, column=1, sticky="w")
        ctk.CTkEntry(prices, textvariable=vars["sale_price"], height=35).grid(row=1, column=1, sticky="ew", padx=(5, 0))

        catalog = self.product_controller.get_catalog_data()
        
        ctk.CTkLabel(form, text="Categoría", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(10, 2))
        category_map = {"Sin categoría": None}
        cat_names = ["Sin categoría"]
        if hasattr(self.product_controller, 'get_active_categories'):
            for cat in self.product_controller.get_active_categories():
                category_map[cat['name']] = cat['id']
                cat_names.append(cat['name'])
        cat_var = ctk.StringVar(value="Sin categoría")
        ctk.CTkOptionMenu(form, variable=cat_var, values=cat_names, fg_color="#F8FAFC", text_color="#142338").pack(fill="x")

        ctk.CTkLabel(form, text="Unidad de Medida *", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(10, 2))
        unit_names = [u['name'] for u in catalog.get('units', [])]
        unit_var = ctk.StringVar(value=unit_names[0] if unit_names else "")
        ctk.CTkOptionMenu(form, variable=unit_var, values=unit_names, fg_color="#F8FAFC", text_color="#142338").pack(fill="x")

        ctk.CTkLabel(form, text="Manejar Inventario", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(15, 2))
        ctk.CTkSwitch(form, text="Descontar existencias", variable=vars["track_inventory"], progress_color="#0F766E").pack(anchor="w")

        def on_save():
            try:
                data = {
                    "sku": vars["sku"].get().strip(),
                    "name": vars["name"].get().strip(),
                    "cost_price": vars["cost_price"].get(),
                    "sale_price": vars["sale_price"].get(),
                    "category_id": category_map.get(cat_var.get()),
                    "unit_id": next((u['id'] for u in catalog.get('units', []) if u['name'] == unit_var.get()), None),
                    "track_inventory": 1 if vars["track_inventory"].get() else 0
                }
                self.product_controller.save_product(data)
                self.load_data()
                win.destroy()
            except Exception as e:
                messagebox.showwarning("Error", str(e), parent=win)

        ctk.CTkButton(win, text="Crear Producto", font=ctk.CTkFont(size=14, weight="bold"), height=45,
                      fg_color="#0F766E", hover_color="#115E59", command=on_save).pack(fill="x", padx=40, pady=20)

    # ==========================================
    # MODAL: EDITAR PRODUCTO
    # ==========================================
    def open_edit_product_modal(self, product_data):
        win = ctk.CTkToplevel(self)
        win.title("Editar Producto")
        win.geometry("500x700")
        win.resizable(False, False)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        
        win.update_idletasks()
        win.geometry(f"+{(win.winfo_screenwidth()-500)//2}+{(win.winfo_screenheight()-700)//2}")

        ctk.CTkLabel(win, text="Editar Producto", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=20)
        
        form = ctk.CTkFrame(win, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=40)
        
        vars = {
            "sku": ctk.StringVar(value=product_data.get('sku', '')), 
            "name": ctk.StringVar(value=product_data.get('name', '')),
            "cost_price": ctk.StringVar(value=str(product_data.get('cost_price', 0) / 100)), 
            "sale_price": ctk.StringVar(value=str(product_data.get('sale_price', 0) / 100)),
            "track_inventory": ctk.BooleanVar(value=bool(product_data.get('track_inventory', True)))
        }
        
        def add_field(label, var):
            ctk.CTkLabel(form, text=label, font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(10, 2))
            ctk.CTkEntry(form, textvariable=var, height=35).pack(fill="x")

        add_field("SKU / Código de Barras *", vars["sku"])
        add_field("Nombre del Producto *", vars["name"])
        
        prices = ctk.CTkFrame(form, fg_color="transparent")
        prices.pack(fill="x", pady=10)
        prices.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(prices, text="Costo ($)", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(prices, textvariable=vars["cost_price"], height=35).grid(row=1, column=0, sticky="ew", padx=(0, 5))
        ctk.CTkLabel(prices, text="Precio Venta ($) *", font=ctk.CTkFont(weight="bold")).grid(row=0, column=1, sticky="w")
        ctk.CTkEntry(prices, textvariable=vars["sale_price"], height=35).grid(row=1, column=1, sticky="ew", padx=(5, 0))

        catalog = self.product_controller.get_catalog_data()
        
        ctk.CTkLabel(form, text="Categoría", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(10, 2))
        category_map = {"Sin categoría": None}
        cat_names = ["Sin categoría"]
        if hasattr(self.product_controller, 'get_active_categories'):
            for cat in self.product_controller.get_active_categories():
                category_map[cat['name']] = cat['id']
                cat_names.append(cat['name'])
                
        initial_cat = next((name for name, cid in category_map.items() if cid == product_data.get('category_id')), "Sin categoría")
        cat_var = ctk.StringVar(value=initial_cat)
        ctk.CTkOptionMenu(form, variable=cat_var, values=cat_names, fg_color="#F8FAFC", text_color="#142338").pack(fill="x")

        ctk.CTkLabel(form, text="Unidad de Medida *", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(10, 2))
        unit_names = [u['name'] for u in catalog.get('units', [])]
        initial_unit = next((u['name'] for u in catalog['units'] if u['id'] == product_data.get('unit_id')), unit_names[0] if unit_names else "")
        unit_var = ctk.StringVar(value=initial_unit)
        ctk.CTkOptionMenu(form, variable=unit_var, values=unit_names, fg_color="#F8FAFC", text_color="#142338").pack(fill="x")

        ctk.CTkLabel(form, text="Manejar Inventario", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(15, 2))
        ctk.CTkSwitch(form, text="Descontar existencias", variable=vars["track_inventory"], progress_color="#0F766E").pack(anchor="w")

        def on_save():
            try:
                data = {
                    "sku": vars["sku"].get().strip(),
                    "name": vars["name"].get().strip(),
                    "cost_price": vars["cost_price"].get(),
                    "sale_price": vars["sale_price"].get(),
                    "category_id": category_map.get(cat_var.get()),
                    "unit_id": next((u['id'] for u in catalog.get('units', []) if u['name'] == unit_var.get()), None),
                    "track_inventory": 1 if vars["track_inventory"].get() else 0
                }
                self.product_controller.update_product(product_data['id'], data)
                self.load_data()
                win.destroy()
            except Exception as e:
                messagebox.showwarning("Error", str(e), parent=win)

        ctk.CTkButton(win, text="Guardar Cambios", font=ctk.CTkFont(size=14, weight="bold"), height=45,
                      fg_color="#3B82F6", hover_color="#2563EB", command=on_save).pack(fill="x", padx=40, pady=20)