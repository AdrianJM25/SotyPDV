import customtkinter as ctk
from tkinter import ttk, messagebox
import logging

log = logging.getLogger(__name__)

class CustomersView(ctk.CTkFrame):
    def __init__(self, master, app_controller):
        super().__init__(master, fg_color="transparent")
        self.app_controller = app_controller
        if not hasattr(app_controller, "customers_controller"):
            from controllers.customers_controller import CustomersController
            app_controller.customers_controller = CustomersController()
            
        self.controller = app_controller.customers_controller
        
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        self._build_header()
        self._build_table()
        self.load_data()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        
        ctk.CTkLabel(header, text="Directorio de Clientes", font=ctk.CTkFont(size=24, weight="bold"), text_color="#142338").pack(side="left")
        
        # Barra de búsqueda rápida
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.load_data())
        search_entry = ctk.CTkEntry(header, textvariable=self.search_var, placeholder_text="🔍 Buscar por nombre, teléfono o RFC...", width=280, height=38)
        search_entry.pack(side="left", padx=20)

        # Botones de Acción (Derecha)
        btn_add = ctk.CTkButton(header, text="+ Nuevo", font=ctk.CTkFont(weight="bold"), 
                                fg_color="#0F766E", hover_color="#115E59", height=38, width=90, command=lambda: self.open_customer_modal())
        btn_add.pack(side="right", padx=(5, 0))

        btn_delete = ctk.CTkButton(header, text="Eliminar", font=ctk.CTkFont(weight="bold"), 
                                   fg_color="#B42318", hover_color="#911e14", height=38, width=90, command=self.delete_selected_customer)
        btn_delete.pack(side="right", padx=(5, 0))

        btn_edit = ctk.CTkButton(header, text="Editar", font=ctk.CTkFont(weight="bold"), 
                                 fg_color="#D97706", hover_color="#B45309", height=38, width=90, command=self.edit_selected_customer)
        btn_edit.pack(side="right", padx=(5, 0))

        btn_detail = ctk.CTkButton(header, text="Ver Detalle", font=ctk.CTkFont(weight="bold"), 
                                   fg_color="#1E3A8A", hover_color="#1E40AF", height=38, width=100, command=self.open_customer_detail)
        btn_detail.pack(side="right", padx=(5, 0))

    def _build_table(self):
        table_frame = ctk.CTkFrame(self, fg_color="#FFFFFF", corner_radius=15, border_width=1, border_color="#E1E7EF")
        table_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        table_frame.pack_propagate(False)
        
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Customer.Treeview", background="#FFFFFF", foreground="#142338", rowheight=38, 
                        fieldbackground="#FFFFFF", borderwidth=0, font=("Arial", 11))
        style.map('Customer.Treeview', background=[('selected', '#EAF6F3')], foreground=[('selected', '#0F766E')])
        style.configure("Customer.Treeview.Heading", background="#F8FAFC", foreground="#64748B", font=("Arial", 11, "bold"), borderwidth=0)
        
        columns = ("name", "phone", "tax_id", "email", "birthday")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse", style="Customer.Treeview")
        
        self.tree.heading("name", text="Nombre / Razón Social")
        self.tree.heading("phone", text="Teléfono")
        self.tree.heading("tax_id", text="RFC / Datos Fiscales")
        self.tree.heading("email", text="Correo Electrónico")
        self.tree.heading("birthday", text="Cumpleaños")
        
        self.tree.column("name", width=260)
        self.tree.column("phone", width=130)
        self.tree.column("tax_id", width=140)
        self.tree.column("email", width=200)
        self.tree.column("birthday", width=100, anchor="center")
        
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        scrollbar.pack(side="right", fill="y", pady=10)

        # Doble clic abre el detalle completo
        self.tree.bind("<Double-1>", lambda e: self.open_customer_detail())

    def load_data(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        query = self.search_var.get()
        customers = self.controller.get_all_customers(query)
        
        for c in customers:
            self.tree.insert("", "end", iid=c["id"], values=(
                c["name"], c["phone"] or "N/A", c["tax_id"] or "N/A", c["email"] or "N/A", c["birthday"] or "N/A"
            ))

    def edit_selected_customer(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Selección requerida", "Por favor selecciona un cliente de la lista para editar.", parent=self)
            return
        customer_id = selected[0]
        customer_data = self.controller.get_customer_by_id(customer_id)
        if customer_data:
            self.open_customer_modal(customer_data)

    def delete_selected_customer(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Selección requerida", "Por favor selecciona un cliente de la lista para eliminar.", parent=self)
            return
        
        customer_id = selected[0]
        customer_data = self.controller.get_customer_by_id(customer_id)
        
        if messagebox.askyesno("Confirmar eliminación", f"¿Estás seguro de que deseas eliminar al cliente '{customer_data['name']}'?", parent=self):
            try:
                self.controller.delete_customer(customer_id)
                self.load_data()
                messagebox.showinfo("Éxito", "Cliente eliminado correctamente.", parent=self)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)

    def open_customer_detail(self):
        """Muestra una ventana modal con los datos completos del cliente y su historial de compras."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Selección requerida", "Por favor selecciona un cliente para ver su detalle.", parent=self)
            return
        
        customer_id = selected[0]
        c = self.controller.get_customer_by_id(customer_id)
        history = self.controller.get_customer_history(customer_id)
        
        if not c:
            return

        win = ctk.CTkToplevel(self)
        win.title(f"Detalle del Cliente - {c['name']}")
        win.geometry("600x650")
        win.resizable(False, False)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        
        win.update_idletasks()
        x = (win.winfo_screenwidth() - 600) // 2
        y = (win.winfo_screenheight() - 650) // 2
        win.geometry(f"+{x}+{y}")

        # Tarjeta de Datos Generales
        ctk.CTkLabel(win, text=c["name"], font=ctk.CTkFont(size=22, weight="bold"), text_color="#0F766E").pack(pady=(20, 5))
        
        info_frame = ctk.CTkFrame(win, fg_color="#F8FAFC", corner_radius=12, border_width=1, border_color="#E1E7EF")
        info_frame.pack(fill="x", padx=30, pady=10)
        
        details = [
            ("Teléfono:", c["phone"] or "No registrado"),
            ("Correo:", c["email"] or "No registrado"),
            ("RFC / Datos Fiscales:", c["tax_id"] or "No registrado"),
            ("Razón Social:", c["legal_name"] or "No registrado"),
            ("Cumpleaños:", c["birthday"] or "No registrado"),
            ("Dirección:", c["address"] or "No registrada")
        ]
        
        for i, (lbl, val) in enumerate(details):
            r, col = divmod(i, 2)
            f = ctk.CTkFrame(info_frame, fg_color="transparent")
            f.grid(row=r, column=col, sticky="w", padx=15, pady=6)
            ctk.CTkLabel(f, text=lbl, font=ctk.CTkFont(weight="bold"), text_color="#64748B").pack(anchor="w")
            ctk.CTkLabel(f, text=val, text_color="#142338").pack(anchor="w")

        info_frame.grid_columnconfigure((0, 1), weight=1)

        # Historial de Compras (Datos conectados)
        ctk.CTkLabel(win, text="Historial de Compras", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=30, pady=(15, 5))
        
        history_frame = ctk.CTkFrame(win, fg_color="#FFFFFF", corner_radius=10, border_width=1, border_color="#E1E7EF")
        history_frame.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        
        style = ttk.Style()
        columns = ("ticket", "total", "date")
        tree_hist = ttk.Treeview(history_frame, columns=columns, show="headings", selectmode="none")
        tree_hist.heading("ticket", text="Folio / Ticket")
        tree_hist.heading("total", text="Total")
        tree_hist.heading("date", text="Fecha de Venta")
        
        tree_hist.column("ticket", width=150)
        tree_hist.column("total", width=120, anchor="e")
        tree_hist.column("date", width=240, anchor="center")
        
        tree_hist.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        
        if history:
            for h in history:
                tree_hist.insert("", "end", values=(h["ticket_number"], h["total_fmt"], h["sold_at"]))
        else:
            tree_hist.insert("", "end", values=("Sin compras registradas", "", ""))

        ctk.CTkButton(win, text="Cerrar", font=ctk.CTkFont(size=14), height=38, fg_color="#64748B", hover_color="#475569", command=win.destroy).pack(pady=(0, 20))

    def open_customer_modal(self, customer=None):
        is_edit = customer is not None
        win = ctk.CTkToplevel(self)
        win.title("Editar Cliente" if is_edit else "Nuevo Cliente")
        win.geometry("520x620")
        win.resizable(False, False)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        
        win.update_idletasks()
        x = (win.winfo_screenwidth() - 520) // 2
        y = (win.winfo_screenheight() - 620) // 2
        win.geometry(f"+{x}+{y}")

        ctk.CTkLabel(win, text="Información del Cliente", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=20)
        
        form_frame = ctk.CTkFrame(win, fg_color="transparent")
        form_frame.pack(fill="both", expand=True, padx=40)
        
        vars = {
            "name": ctk.StringVar(value=customer["name"] if is_edit else ""),
            "phone": ctk.StringVar(value=customer["phone"] if is_edit else ""),
            "email": ctk.StringVar(value=customer["email"] if is_edit else ""),
            "birthday": ctk.StringVar(value=customer["birthday"] if is_edit else ""),
            "tax_id": ctk.StringVar(value=customer["tax_id"] if is_edit else ""),
            "address": ctk.StringVar(value=customer["address"] if is_edit else "")
        }
        
        def add_field(label, var, placeholder=""):
            ctk.CTkLabel(form_frame, text=label, font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(8, 2))
            return ctk.CTkEntry(form_frame, textvariable=var, placeholder_text=placeholder, height=35)

        add_field("Nombre Completo *", vars["name"]).pack(fill="x")
        add_field("Teléfono", vars["phone"], "Ej. 7771234567").pack(fill="x")
        add_field("Correo Electrónico", vars["email"], "correo@ejemplo.com").pack(fill="x")
        add_field("Cumpleaños", vars["birthday"], "AAAA-MM-DD").pack(fill="x")
        add_field("RFC / Datos Fiscales", vars["tax_id"], "XAXX010101000").pack(fill="x")
        add_field("Dirección Fiscal / Envío", vars["address"]).pack(fill="x")

        def on_save():
            try:
                data = {k: v.get() for k, v in vars.items()}
                self.controller.save_customer(data, customer_id=customer["id"] if is_edit else None)
                self.load_data()
                win.destroy()
            except Exception as e:
                messagebox.showwarning("Aviso", str(e), parent=win)

        ctk.CTkButton(win, text="Guardar Cliente", font=ctk.CTkFont(size=14, weight="bold"), height=45,
                      fg_color="#0F766E", hover_color="#115E59", command=on_save).pack(fill="x", padx=40, pady=20)