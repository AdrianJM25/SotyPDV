import customtkinter as ctk
from tkinter import ttk
import logging
from decimal import Decimal

if __package__:
    from .ui_helpers import center_window
    from .icons import icon as get_icon
else:
    from ui_helpers import center_window
    from icons import icon as get_icon

log = logging.getLogger(__name__)

# Paleta SotyPDV
BG, WHITE, INK, MUTED = '#F5F9FC', '#FFFFFF', '#023047', '#5B7385'
SKY, BLUE_DARK, NAVY, BORDER = '#8ECAE6', '#1A7F99', '#023047', '#D7E6EF'

def money(cents):
    return f'${Decimal(cents) / 100:,.2f}'

def label(parent, text, size=14, bold=False, color=INK, **kw):
    return ctk.CTkLabel(parent, text=text, text_color=color,
                        font=ctk.CTkFont(size=size, weight='bold' if bold else 'normal'), **kw)

def card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER, **kw)

class SalesHistoryView(ctk.CTkFrame):
    def __init__(self, master, app_controller):
        super().__init__(master, fg_color=BG)
        self.app_controller = app_controller
        self.sales_controller = getattr(self.app_controller, 'sales_controller', None)
        
        self.grid_columnconfigure(0, weight=6)  # Panel izquierdo (Lista)
        self.grid_columnconfigure(1, weight=4)  # Panel derecho (Detalles)
        self.grid_rowconfigure(0, weight=1)
        
        self._build_list_panel()
        self._build_details_panel()
        self.load_sales()

    def _build_list_panel(self):
        left_panel = ctk.CTkFrame(self, fg_color='transparent')
        left_panel.grid(row=0, column=0, sticky='nsew', padx=(20, 10), pady=20)
        left_panel.grid_rowconfigure(1, weight=1)
        
        # Encabezado y Búsqueda
        top_frame = ctk.CTkFrame(left_panel, fg_color='transparent')
        top_frame.grid(row=0, column=0, sticky='ew', pady=(0, 15))
        
        label(top_frame, ' Historial de Ventas', 22, True, image=get_icon('receipt', BLUE_DARK, 24), compound='left').pack(side='left')
        
        self.search_var = ctk.StringVar()
        search_entry = ctk.CTkEntry(top_frame, textvariable=self.search_var, placeholder_text="Buscar por folio (ej. TKT-00001)...", 
                                    width=250, height=36, fg_color=WHITE, border_color=SKY, border_width=2)
        search_entry.pack(side='right')
        self.search_var.trace_add('write', lambda *_: self.load_sales(self.search_var.get()))
        
        # Tabla de Ventas
        table_container = card(left_panel)
        table_container.grid(row=1, column=0, sticky='nsew')
        
        style = ttk.Style()
        style.theme_use('default')
        style.configure('History.Treeview', background=WHITE, foreground=INK, rowheight=36, fieldbackground=WHITE, borderwidth=0)
        style.map('History.Treeview', background=[('selected', SKY)], foreground=[('selected', NAVY)])
        style.configure('History.Treeview.Heading', background=NAVY, foreground=WHITE, font=('Arial', 11, 'bold'), borderwidth=0)
        
        self.tree = ttk.Treeview(table_container, columns=('id', 'ticket', 'date', 'cashier', 'total'), show='headings', style='History.Treeview')
        self.tree.heading('ticket', text='Folio')
        self.tree.heading('date', text='Fecha / Hora')
        self.tree.heading('cashier', text='Cajero')
        self.tree.heading('total', text='Total')
        
        self.tree.column('id', width=0, stretch=False) # Oculto
        self.tree.column('ticket', width=120, anchor='center')
        self.tree.column('date', width=160, anchor='center')
        self.tree.column('cashier', width=180, anchor='w')
        self.tree.column('total', width=100, anchor='e')
        
        scrollbar = ttk.Scrollbar(table_container, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side='left', fill='both', expand=True, padx=2, pady=2)
        scrollbar.pack(side='right', fill='y', pady=2)
        
        self.tree.bind('<<TreeviewSelect>>', self._on_select_sale)

    def _build_details_panel(self):
        self.right_panel = card(self)
        self.right_panel.grid(row=0, column=1, sticky='nsew', padx=(10, 20), pady=20)
        self.right_panel.grid_rowconfigure(2, weight=1)
        self.right_panel.grid_propagate(False)
        
        self.lbl_empty = label(self.right_panel, 'Selecciona una venta\npara ver sus detalles.', 14, color=MUTED, justify='center')
        self.lbl_empty.place(relx=0.5, rely=0.5, anchor='center')
        
        self.details_content = ctk.CTkFrame(self.right_panel, fg_color='transparent')
        
        # Encabezado Detalle
        header = ctk.CTkFrame(self.details_content, fg_color=NAVY, corner_radius=10)
        header.pack(fill='x', padx=16, pady=16)
        
        self.lbl_ticket_title = label(header, 'TKT-00000', 20, True, WHITE)
        self.lbl_ticket_title.pack(anchor='w', padx=16, pady=(12, 0))
        self.lbl_ticket_date = label(header, 'Fecha', 12, color=SKY)
        self.lbl_ticket_date.pack(anchor='w', padx=16, pady=(0, 12))
        
        # Lista de Productos
        label(self.details_content, 'PRODUCTOS VENDIDOS', 11, True, MUTED).pack(anchor='w', padx=20, pady=(10, 5))
        self.items_frame = ctk.CTkScrollableFrame(self.details_content, fg_color='#F8FBFD', corner_radius=8, border_width=1, border_color=BORDER)
        self.items_frame.pack(fill='both', expand=True, padx=16, pady=5)
        
        # Resumen de Pago
        summary = ctk.CTkFrame(self.details_content, fg_color=BG, corner_radius=8)
        summary.pack(fill='x', padx=16, pady=16)
        
        self.lbl_pay_method = label(summary, 'Método: Efectivo', 12, color=MUTED)
        self.lbl_pay_method.pack(anchor='w', padx=16, pady=(12, 2))
        self.lbl_pay_tendered = label(summary, 'Recibido: $0.00 | Cambio: $0.00', 12, color=MUTED)
        self.lbl_pay_tendered.pack(anchor='w', padx=16, pady=(0, 4))
        self.lbl_pay_total = label(summary, 'Total: $0.00', 22, True, BLUE_DARK)
        self.lbl_pay_total.pack(anchor='e', padx=16, pady=(4, 12))

    def load_sales(self, search_query=""):
        self.tree.delete(*self.tree.get_children())
        if not self.sales_controller:
            return
        
        sales = self.sales_controller.get_sales_list(limit=200, search_query=search_query)
        for i, s in enumerate(sales):
            tag = 'odd' if i % 2 == 0 else 'even'
            self.tree.tag_configure(tag, background=BG if tag == 'odd' else WHITE)
            self.tree.insert('', 'end', values=(s['id'], s['ticket_number'], s['sold_at'], s['cashier_name'] or 'Cajero', money(s['total'])), tags=(tag,))

    def _on_select_sale(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        
        sale_id = self.tree.item(selected[0])['values'][0]
        ticket = self.tree.item(selected[0])['values'][1]
        date = self.tree.item(selected[0])['values'][2]
        total = self.tree.item(selected[0])['values'][4]
        
        self._show_details(sale_id, ticket, date, total)

    def _show_details(self, sale_id, ticket, date, total_str):
        if not self.sales_controller:
            return
            
        self.lbl_empty.place_forget()
        self.details_content.pack(fill='both', expand=True)
        
        self.lbl_ticket_title.configure(text=ticket)
        self.lbl_ticket_date.configure(text=date)
        self.lbl_pay_total.configure(text=f"Total: {total_str}")
        
        # Limpiar productos anteriores
        for w in self.items_frame.winfo_children():
            w.destroy()
            
        details = self.sales_controller.get_sale_details(sale_id)
        
        # Cargar Items
        for item in details['items']:
            row = ctk.CTkFrame(self.items_frame, fg_color='transparent')
            row.pack(fill='x', pady=4)
            row.grid_columnconfigure(0, weight=1)
            
            qty_fmt = float(item['quantity'])
            qty_str = f"{qty_fmt:g}"
            
            info = label(row, f"{item['product_name']}\n{item['product_sku']}  ·  Cant: {qty_str} x {money(item['unit_price'])}", 12, justify='left')
            info.grid(row=0, column=0, sticky='w', padx=5)
            
            total_item = label(row, money(item['line_total']), 13, True, NAVY)
            total_item.grid(row=0, column=1, sticky='e', padx=5)
            
            ctk.CTkFrame(self.items_frame, height=1, fg_color=BORDER).pack(fill='x', padx=10, pady=2)
            
        # Cargar Info Pago
        payment = details['payment']
        if payment:
            methods = {'cash': 'Efectivo', 'card': 'Tarjeta', 'transfer': 'Transferencia'}
            self.lbl_pay_method.configure(text=f"Forma de pago: {methods.get(payment['method_type'], payment['method_type'])}")
            self.lbl_pay_tendered.configure(text=f"Recibido: {money(payment['amount_tendered'])}  ·  Cambio: {money(payment['change_amount'])}")

            