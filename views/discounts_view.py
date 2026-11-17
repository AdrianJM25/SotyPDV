import logging
from tkinter import messagebox

import customtkinter as ctk

from controllers.auth_controller import AuthController
from utils.discounts import is_valid_now
from utils.exceptions import POSError
from views.users_view import (_Modal, _error_text, BG, CARD, TEAL, TEAL_H, TEXT,
                              MUTED, RED, GREEN, BORDER)

log = logging.getLogger(__name__)

TYPES = {'Porcentaje (%)': 'percent', 'Monto fijo ($)': 'fixed'}
COLS = (('Nombre', 3), ('Descuento', 2), ('Vigencia', 3), ('Autorización', 2), ('Estado', 2))
ACTIONS_W = 330


def _value_text(d):
    return f"{d['value']:g} %" if d['discount_type'] == 'percent' else f"${d['value'] / 100:,.2f}"


def _validity_text(d):
    a, b = (d['valid_from'] or '')[:10], (d['valid_until'] or '')[:10]
    if not a and not b:
        return 'Sin límite'
    return f"{a or '…'}  →  {b or '…'}"


class DiscountForm(_Modal):
    def __init__(self, parent, controller, current_user, on_saved, discount=None):
        super().__init__(parent, 'Editar descuento' if discount else 'Nuevo descuento', 480, 560)
        self.controller, self.current_user, self.on_saved, self.discount = controller, current_user, on_saved, discount

        self.e_name = self._field(0, 'Nombre *', placeholder='Ej. Día del cliente')
        ctk.CTkLabel(self, text='Tipo *', text_color=MUTED).grid(row=1, column=0, padx=(24, 8), pady=6, sticky='w')
        self.opt_type = ctk.CTkOptionMenu(self, values=list(TYPES), width=260, height=36,
                                          fg_color=TEAL, button_color=TEAL_H)
        self.opt_type.grid(row=1, column=1, padx=(0, 24), pady=6, sticky='e')
        self.e_value = self._field(2, 'Valor * (% o pesos)')
        self.e_from = self._field(3, 'Vigente desde', placeholder='AAAA-MM-DD (opcional)')
        self.e_until = self._field(4, 'Vigente hasta', placeholder='AAAA-MM-DD (opcional)')

        self.var_auth = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(self, text='Requiere autorización de supervisor', variable=self.var_auth,
                      progress_color=TEAL).grid(row=5, column=0, columnspan=2, padx=24, pady=8, sticky='w')
        self.var_active = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(self, text='Activo', variable=self.var_active,
                      progress_color=TEAL).grid(row=6, column=0, columnspan=2, padx=24, pady=8, sticky='w')

        if discount:
            self.e_name.insert(0, discount['name'])
            fixed = discount['discount_type'] == 'fixed'
            self.opt_type.set('Monto fijo ($)' if fixed else 'Porcentaje (%)')
            self.e_value.insert(0, f"{discount['value'] / 100:.2f}" if fixed else f"{discount['value']:g}")
            self.e_from.insert(0, (discount['valid_from'] or '')[:10])
            self.e_until.insert(0, (discount['valid_until'] or '')[:10])
            self.var_auth.set(bool(discount['requires_authorization']))
            self.var_active.set(bool(discount['is_active']))

        self._error_label(7)
        self._buttons(8, 'Guardar', self._save)
        self.bind('<Return>', lambda e: self._save())
        self.after(200, self.e_name.focus_set)

    def _save(self):
        data = dict(name=self.e_name.get(), discount_type=TYPES[self.opt_type.get()],
                    value=self.e_value.get(), requires_authorization=self.var_auth.get(),
                    valid_from=self.e_from.get(), valid_until=self.e_until.get(),
                    is_active=self.var_active.get())
        try:
            if self.discount:
                self.controller.update_discount(self.current_user, self.discount['id'], **data)
            else:
                self.controller.create_discount(self.current_user, **data)
        except Exception as exc:
            self._show_error(_error_text(exc))
            return
        self.on_saved()
        self.destroy()


class ProductsDialog(_Modal):
    """Selecciona a qué productos aplica un descuento."""

    def __init__(self, parent, controller, current_user, discount, on_saved):
        super().__init__(parent, f"Productos · {discount['name']}", 520, 620)
        self.controller, self.current_user, self.discount, self.on_saved = controller, current_user, discount, on_saved
        self.selected = set(controller.get_product_ids(current_user, discount['id']))
        self.search_var = ctk.StringVar()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkEntry(self, textvariable=self.search_var, placeholder_text='Buscar por nombre o código…',
                     height=38).grid(row=0, column=0, padx=24, pady=(20, 8), sticky='ew')
        self.scroll = ctk.CTkScrollableFrame(self, fg_color='#F8FAFC', corner_radius=10)
        self.scroll.grid(row=1, column=0, padx=24, pady=4, sticky='nsew')
        self.lbl_count = ctk.CTkLabel(self, text='', text_color=MUTED)
        self.lbl_count.grid(row=2, column=0, padx=24, sticky='w')
        self.lbl_error = ctk.CTkLabel(self, text='', text_color=RED, wraplength=440, height=30)
        self.lbl_error.grid(row=3, column=0, padx=24)
        frame = ctk.CTkFrame(self, fg_color='transparent')
        frame.grid(row=4, column=0, padx=24, pady=(4, 18), sticky='e')
        ctk.CTkButton(frame, text='Cancelar', width=110, fg_color='#EDF2F7', hover_color='#DBE5EF',
                      text_color=TEXT, command=self.destroy).pack(side='left', padx=6)
        ctk.CTkButton(frame, text='Guardar', width=130, fg_color=TEAL, hover_color=TEAL_H,
                      command=self._save).pack(side='left', padx=6)

        self._job = None
        self.search_var.trace_add('write', lambda *a: self._debounce())
        self._render()

    def _debounce(self):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(250, self._render)

    def _toggle(self, pid, var):
        (self.selected.add if var.get() else self.selected.discard)(pid)
        self._update_count()

    def _update_count(self):
        self.lbl_count.configure(text=f'{len(self.selected)} producto(s) seleccionado(s)')

    def _render(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        try:
            products = self.controller.search_products(self.current_user, self.search_var.get())
        except Exception as exc:
            self.lbl_error.configure(text=_error_text(exc))
            return
        for p in products:
            var = ctk.BooleanVar(value=p['id'] in self.selected)
            ctk.CTkCheckBox(self.scroll, text=f"{p['name']}  ·  {p['sku']}", variable=var,
                            fg_color=TEAL, hover_color=TEAL_H, text_color=TEXT,
                            command=lambda pid=p['id'], v=var: self._toggle(pid, v)
                            ).pack(anchor='w', pady=3, padx=6)
        if len(products) >= 200:
            ctk.CTkLabel(self.scroll, text='Mostrando los primeros 200. Afina la búsqueda.',
                         text_color=MUTED).pack(pady=6)
        self._update_count()

    def _save(self):
        try:
            self.controller.set_products(self.current_user, self.discount['id'], self.selected)
        except Exception as exc:
            self.lbl_error.configure(text=_error_text(exc))
            return
        self.on_saved()
        self.destroy()


class DiscountsView(ctk.CTkFrame):
    def __init__(self, master, app_controller):
        super().__init__(master, fg_color=BG)
        self.controller = app_controller.discount_controller
        self.current_user = app_controller.current_user
        self.discounts = []
        self.search_var = ctk.StringVar()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_header()
        self._build_table_header()
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=CARD, corner_radius=12,
                                             border_width=1, border_color=BORDER)
        self.scroll.grid(row=2, column=0, padx=24, pady=(0, 8), sticky='nsew')
        self.scroll.grid_columnconfigure(0, weight=1)
        self.lbl_status = ctk.CTkLabel(self, text='', text_color=MUTED, anchor='w')
        self.lbl_status.grid(row=3, column=0, padx=28, pady=(0, 12), sticky='w')
        self.search_var.trace_add('write', lambda *a: self._render())
        self.reload()

    def _build_header(self):
        bar = ctk.CTkFrame(self, fg_color='transparent')
        bar.grid(row=0, column=0, padx=24, pady=(20, 10), sticky='ew')
        bar.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(bar, text='Descuentos', text_color=TEAL,
                     font=ctk.CTkFont(size=26, weight='bold')).grid(row=0, column=0, sticky='w')
        ctk.CTkEntry(bar, textvariable=self.search_var, placeholder_text='Buscar descuento…',
                     width=280, height=38, fg_color=CARD).grid(row=0, column=2, padx=10)
        ctk.CTkButton(bar, text='+ Nuevo descuento', height=38, fg_color=TEAL, hover_color=TEAL_H,
                      font=ctk.CTkFont(weight='bold'), command=self._new).grid(row=0, column=3, padx=(10, 0))

    def _configure_cols(self, frame):
        for i, (_, w) in enumerate(COLS):
            frame.grid_columnconfigure(i, weight=w, uniform='col')
        frame.grid_columnconfigure(len(COLS), weight=0, minsize=ACTIONS_W)

    def _build_table_header(self):
        head = ctk.CTkFrame(self, fg_color='transparent')
        head.grid(row=1, column=0, padx=36, pady=(0, 4), sticky='ew')
        self._configure_cols(head)
        for i, (title, _) in enumerate(COLS):
            ctk.CTkLabel(head, text=title, text_color=MUTED, anchor='w',
                         font=ctk.CTkFont(size=12, weight='bold')).grid(row=0, column=i, sticky='w', padx=6)
        ctk.CTkLabel(head, text='Acciones', text_color=MUTED, anchor='e',
                     font=ctk.CTkFont(size=12, weight='bold')).grid(row=0, column=len(COLS), sticky='e', padx=6)

    def reload(self):
        try:
            self.discounts = [dict(d) for d in self.controller.list_discounts(self.current_user)]
        except Exception as exc:
            messagebox.showwarning('Descuentos', _error_text(exc), parent=self)
            self.discounts = []
        self._render()

    def _render(self):
        for child in self.scroll.winfo_children():
            child.destroy()
        q = self.search_var.get().strip().lower()
        visible = [d for d in self.discounts if q in d['name'].lower()]
        if not visible:
            ctk.CTkLabel(self.scroll, text='No hay descuentos que mostrar.', text_color=MUTED).grid(pady=30)
        for i, d in enumerate(visible):
            self._build_row(i, d)
        self.lbl_status.configure(text=f'{len(visible)} de {len(self.discounts)} descuentos')

    def _build_row(self, index, d):
        row = ctk.CTkFrame(self.scroll, fg_color='#F8FAFC' if index % 2 == 0 else CARD, corner_radius=8)
        row.grid(row=index, column=0, sticky='ew', pady=1, padx=2)
        self._configure_cols(row)

        if not d['is_active']:
            status, color = 'Inactivo', MUTED
        elif is_valid_now(d):
            status, color = 'Vigente', GREEN
        else:
            status, color = 'Fuera de vigencia', '#B45309'

        values = (d['name'], _value_text(d), _validity_text(d),
                  'Sí' if d['requires_authorization'] else 'No', status)
        for c, val in enumerate(values):
            ctk.CTkLabel(row, text=val, anchor='w', justify='left', wraplength=200,
                         text_color=color if c == 4 else TEXT,
                         font=ctk.CTkFont(size=13, weight='bold' if c in (0, 4) else 'normal')
                         ).grid(row=0, column=c, sticky='w', padx=6, pady=10)

        actions = ctk.CTkFrame(row, fg_color='transparent')
        actions.grid(row=0, column=len(COLS), sticky='e', padx=6)
        self._action(actions, 'Editar', TEAL, TEAL_H, 'white', lambda: self._edit(d))
        self._action(actions, 'Productos', '#EDF2F7', '#DBE5EF', TEXT, lambda: self._products(d), 86)
        self._action(actions, 'Desactivar' if d['is_active'] else 'Activar', '#FEF3C7', '#FDE68A',
                     '#92400E', lambda: self._toggle(d), 86)
        self._action(actions, 'Eliminar', '#FDE8E8', '#FBD5D5', RED, lambda: self._delete(d))

    @staticmethod
    def _action(parent, text, fg, hover, txt, command, width=66):
        ctk.CTkButton(parent, text=text, width=width, height=30, corner_radius=8, fg_color=fg,
                      hover_color=hover, text_color=txt, font=ctk.CTkFont(size=12, weight='bold'),
                      command=command).pack(side='left', padx=2)

    def _new(self):
        DiscountForm(self, self.controller, self.current_user, self.reload)

    def _edit(self, d):
        DiscountForm(self, self.controller, self.current_user, self.reload, discount=d)

    def _products(self, d):
        ProductsDialog(self, self.controller, self.current_user, d, self.reload)

    def _run(self, fn, *args):
        try:
            fn(self.current_user, *args)
        except Exception as exc:
            messagebox.showwarning('Descuentos', _error_text(exc), parent=self)
        self.reload()

    def _toggle(self, d):
        self._run(self.controller.set_active, d['id'], not d['is_active'])

    def _delete(self, d):
        if messagebox.askyesno('Eliminar descuento',
                               f"¿Eliminar «{d['name']}»?\n\nSe quita también de sus productos. "
                               "Las ventas que ya lo usaron conservan su registro.", parent=self):
            self._run(self.controller.delete_discount, d['id'])