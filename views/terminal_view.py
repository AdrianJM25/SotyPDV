"""Terminal SotyPOS; compatible con los cuatro argumentos originales.

Venta y Caja y corte comparten una ventana. Ver INTEGRACION.md.
La persistencia, los permisos y el inventario siempre se validan en el servidor/controlador.
"""
import copy

from utils.discounts import prorate
from utils.exceptions import PermissionDenied
import re
import logging
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from tkinter import messagebox, ttk
if __package__:
    from .ui_helpers import Jobs, Activity, keyboard_checkbox, center_window, keyboard_button, select_entry
    from .icons import icon as get_icon
else:
    from ui_helpers import Jobs, Activity, keyboard_checkbox, center_window, keyboard_button, select_entry
    from icons import icon as get_icon
import customtkinter as ctk

log = logging.getLogger(__name__)

# ── Paleta ──────────────────────────────────────────────────────────────────
# Base: #8ecae6 · #219ebc · #023047 · #ffb703 · #fb8500
SKY, BLUE, NAVY, AMBER, ORANGE = '#8ECAE6', '#219EBC', '#023047', '#FFB703', '#FB8500'
BLUE_DARK = '#1A7F99'        # azul del texto/acentos sobre blanco (contraste AA)
ORANGE_DARK = '#E07600'
SOFT, SOFT_HOVER = '#EAF5FB', '#D5EBF6'   # tintes del cielo para botones y paneles
DISABLED_BG, DISABLED_FG = '#D9E4EB', '#8FA3B2'

# Nombres originales (otros módulos pueden importarlos)
BG, WHITE, INK, MUTED = '#F5F9FC', '#FFFFFF', NAVY, '#5B7385'
TEAL, BORDER, RED = BLUE_DARK, '#D7E6EF', '#B42318'

STYLES = {
    'primary': dict(fg_color=ORANGE, hover_color=ORANGE_DARK, text_color=NAVY),
    'accent': dict(fg_color=BLUE_DARK, hover_color='#14657B', text_color=WHITE),
    'soft': dict(fg_color=SOFT, hover_color=SOFT_HOVER, text_color=NAVY),
    'danger': dict(fg_color=WHITE, hover_color='#FDECEA', text_color=RED,
                   border_width=1, border_color='#F1C6C1'),
}
ICON_COLOR = {'primary': NAVY, 'accent': WHITE, 'soft': NAVY, 'danger': RED}
TAB_ICONS = {'Venta': 'cart', 'Caja y corte': 'calc', 'Historial': 'receipt'}
def decimal_value(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Ingresa un número válido.') from None
    if not number.is_finite():
        raise ValueError('Ingresa un número finito.')
    return number


def money(cents):
    return f'${Decimal(cents) / 100:,.2f}'


def price_cents(product):
    
    value = (decimal_value(product['sale_price_cents']) if 'sale_price_cents' in product
             else decimal_value(product['sale_price']) * 100)
    if value < 0 or value > 100000000 or value != value.to_integral_value():
        raise ValueError('El precio debe estar entre 0 y 1,000,000 y tener como máximo dos decimales.')
    return int(value)


def line_cents(product, quantity):
    return int((Decimal(price_cents(product)) * decimal_value(quantity)).quantize(
        Decimal('1'), rounding=ROUND_HALF_UP))


def quantity_value(product, value):
    q = decimal_value(value)
    if q <= 0 or q > 999999:
        raise ValueError('La cantidad debe ser mayor que cero y no superar 999,999.')
    if not product.get('allows_decimals', False) and q != q.to_integral_value():
        raise ValueError('Este producto solo se vende en unidades enteras.')
    if q != q.quantize(Decimal('.001')):
        raise ValueError('Usa como máximo tres decimales en la cantidad.')
    return q


def label(parent, text, size=14, bold=False, color=INK, **kw):
    return ctk.CTkLabel(parent, text=text, text_color=color,
        font=ctk.CTkFont(size=size, weight='bold' if bold else 'normal'), **kw)


def button(parent, text, command, primary=False, kind=None, icon=None, **kw):
    """kind: 'primary' (naranja, acción principal) · 'accent' (azul) · 'soft' · 'danger'."""
    kind = kind or ('primary' if primary else 'soft')
    kw.setdefault('height', 40)
    kw.setdefault('font', ctk.CTkFont(size=13, weight='bold'))
    size = kw.pop('icon_size', 18)
    if icon:
        kw['image'] = get_icon(icon, ICON_COLOR[kind], size)
        kw['compound'] = 'left'
    btn = ctk.CTkButton(parent, text=text, command=command, corner_radius=10,
                        text_color_disabled=DISABLED_FG, **STYLES[kind], **kw)
    btn = keyboard_button(btn)
    btn._kind = kind
    return btn


def set_enabled(btn, enabled):
    """Activa/desactiva y apaga el color sólido para que un botón inactivo no parezca activo."""
    kind = getattr(btn, '_kind', 'soft')
    solid = kind in ('primary', 'accent')
    if enabled:
        btn.configure(state='normal', fg_color=STYLES[kind]['fg_color'])
    else:
        btn.configure(state='disabled', fg_color=DISABLED_BG if solid else STYLES[kind]['fg_color'])


def card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=WHITE, corner_radius=14, border_width=1,
                        border_color=BORDER, **kw)


class TerminalView(ctk.CTkFrame):
    def __init__(self, master, user_data, logout_callback, add_product_callback, *,
                 search_callback=None, checkout_callback=None, stock_callback=None,
                 cash_callback=None, session_label=None,
                 cash_balance_callback=None, cash_close_callback=None, on_cash_closed=None,
                 discount_controller=None, auth_controller=None):
        
        super().__init__(master, fg_color=BG)
        self.jobs = Jobs(self)
        self.user_data = user_data
        self.logout_callback = logout_callback
        self.add_product_callback = add_product_callback
        self.search_callback = search_callback
        self.checkout_callback = checkout_callback
        self.stock_callback = stock_callback
        self.cash_callback = cash_callback
        self.cash_balance_callback = cash_balance_callback
        self.cash_close_callback = cash_close_callback
        if 'permissions' in user_data and 'cash.close' not in user_data['permissions']:
            self.cash_close_callback = None
        self.on_cash_closed = on_cash_closed
        self._session_closed = False
        self.active_tab = 'Venta'
        self.ticket_rows = {}
        self._busy = False
        self._dialog = None
        self._bindings = []
        self._request_id = str(uuid.uuid4())
        self.total_cents = 0
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.discount_controller = discount_controller
        self.auth_controller = auth_controller
        self._authorizer = None      # supervisor que autorizó descuentos de este ticket
        self._can_discount = 'sales.discount' in user_data.get('permissions', [])
        
        self._build_header(session_label)
        self._build_navigation()
        self._build_ticket_panel()
        self._build_control_panel()
        self._build_cash_page()
        self._build_history_page()  # <--- NUEVO: Construye la vista de historial
        self._update_totals()
        
        top = self.winfo_toplevel()
        actions = {
            '<F1>': self._help, 
            '<Control-Key-1>': lambda: self.select_tab('Venta'),
            '<Control-Key-2>': lambda: self.select_tab('Caja y corte'),
            '<Control-Key-3>': lambda: self.select_tab('Historial'),  # <--- NUEVO
            '<Control-Tab>': self._next_tab,
            '<F2>': lambda: self._shortcut(self._focus_scan),
            '<Control-l>': lambda: self._shortcut(self._focus_scan),
            '<F3>': lambda: self._shortcut(self._search),
            '<Control-f>': lambda: self._shortcut(self._search),
            '<F4>': lambda: self._shortcut(self._edit_last),
            '<F12>': lambda: self._shortcut(self._pay),
            '<Control-Return>': self._primary_action,
        }
        for key, action in actions.items():
            token = top.bind(key, lambda e, fn=action: self._global_action(fn), add='+')
            self._bindings.append((key, token))
        self._focus_job = self.jobs.later(120, self._focus_scan)

    # ... (código anterior del diccionario actions) ...
        
        for key, action in actions.items():
            token = top.bind(key, lambda e, fn=action: self._global_action(fn), add='+')
            self._bindings.append((key, token))
        self._focus_job = self.jobs.later(120, self._focus_scan)
        
        # --- FORZAR EL DIBUJO DE LA PESTAÑA PRINCIPAL ---
        self.select_tab('Venta')

    def _global_action(self, action):
        if self.winfo_ismapped() and not self._busy and not self._dialog and not getattr(self.cash_page, '_busy', False):
            action()
            return 'break'

    def _next_tab(self):
        tabs = ['Venta', 'Caja y corte', 'Historial']
        idx = tabs.index(self.active_tab)
        self.select_tab(tabs[(idx + 1) % len(tabs)])

    def _primary_action(self):
        if self.active_tab == 'Venta':
            self._pay()
        elif self.active_tab == 'Caja y corte' and self.cash_page.review_button.cget('state') == 'normal':
            self.cash_page.review()

    def _edit_last(self):
        if self.ticket_rows:
            self._edit_quantity(next(reversed(self.ticket_rows)))
        else:
            self.show_message('Agrega un producto antes de editar su cantidad.', True)

    def _help(self):
        if self._busy or getattr(self.cash_page, '_busy', False) or self._dialog:
            return
        previous = getattr(self, '_help_window', None)
        if previous is not None and previous.winfo_exists():
            previous.deiconify()
            previous.lift()
            previous.focus_set()
            return
        win = ctk.CTkToplevel(self)
        win.withdraw()
        win.title('Atajos de teclado')
        win.configure(fg_color=BG)
        win.resizable(False, False)
        self._help_window = win

        def close_help(event=None):
            win._position_jobs.close()
            win.destroy()
            self._help_window = None
            if not self._dialog:
                self._focus_scan()
            return 'break'
        
        win.protocol('WM_DELETE_WINDOW', close_help)
        win.bind('<Escape>', close_help)
        for key, action in {
            '<Control-Key-1>': lambda: self.select_tab('Venta'),
            '<Control-Key-2>': lambda: self.select_tab('Caja y corte'),
            '<Control-Key-3>': lambda: self.select_tab('Historial'),
            '<Control-Tab>': self._next_tab,
        }.items():
            win.bind(key, lambda e, fn=action: self._global_action(fn))
        center_window(win, self.winfo_toplevel(), 600, 520, modal=False)
        label(win, ' Muévete más rápido', 24, True, image=get_icon('info', BLUE_DARK, 26),
              compound='left').pack(anchor='w', padx=24, pady=(22, 10))
        panel = card(win)
        panel.pack(fill='x', padx=24)
        shortcuts = [('Ctrl + 1 / 2 / 3', 'Venta / Caja / Historial'), ('Ctrl + Tab', 'Cambiar de pestaña'),
            ('F2 / Ctrl + L', 'Ir al código de producto'), ('F3 / Ctrl + F', 'Buscar por nombre o código'),
            ('F4', 'Editar cantidad del último producto'), ('F12 / Ctrl + Enter', 'Abrir cobro desde Venta'),
            ('↑ / ↓ y Enter', 'Elegir y agregar en el buscador'), ('Tab / Shift + Tab', 'Avanzar / retroceder entre controles'),
            ('Escape', 'Volver al ticket sin borrar productos')]
        for key, caption in shortcuts:
            row = ctk.CTkFrame(panel, fg_color='transparent')
            row.pack(fill='x', padx=18, pady=4)
            label(row, key, 13, True, BLUE_DARK, width=180, anchor='w').pack(side='left')
            label(row, caption, 13).pack(side='left')
        close_button = button(win, 'Entendido · Esc', close_help, True, icon='check')
        close_button.pack(pady=18)
        win._initial_focus = close_button._canvas

    def _shortcut(self, fn):
        if self.winfo_ismapped() and self.active_tab == 'Venta' and not self._session_closed and not self._busy and self._dialog is None:
            fn()
            return 'break'

    def _build_header(self, session):
        bar = ctk.CTkFrame(self, fg_color=NAVY, corner_radius=0)
        bar.grid(row=0, column=0, columnspan=2, sticky='ew')
        bar.grid_columnconfigure(1, weight=1)
        brand = ctk.CTkFrame(bar, fg_color='transparent')
        brand.grid(row=0, column=0, padx=(24, 0), pady=12)
        logo = ctk.CTkFrame(brand, width=42, height=42, corner_radius=12, fg_color=ORANGE)
        logo.grid(row=0, column=0, padx=(0, 12))
        ctk.CTkLabel(logo, text='', image=get_icon('cart', NAVY, 24)).place(relx=.5, rely=.5, anchor='center')
        label(brand, 'SotyPOS', 24, True, WHITE).grid(row=0, column=1)
        label(bar, 'PUNTO DE VENTA', 12, True, SKY).grid(row=0, column=1, sticky='w', padx=8)
        self.session_badge = label(bar, session or 'Terminal de venta', 13, color=SKY,
                                   image=get_icon('user', SKY, 16), compound='left')
        self.session_badge.grid(row=0, column=2, padx=20)
        ctk.CTkFrame(bar, height=3, fg_color=AMBER, corner_radius=0).grid(
            row=1, column=0, columnspan=3, sticky='ew')

    def _build_navigation(self):
        nav = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=0)
        nav.grid(row=1, column=0, sticky='ew')
        nav.grid_columnconfigure(3, weight=1)  # Se ajustó el peso para 3 pestañas + botón ayuda
        
        self.nav_buttons = {}
        for col, caption in enumerate(('Venta', 'Caja y corte', 'Historial')):
            btn = button(nav, f"{caption} · Ctrl+{col+1}",
                         lambda name=caption: self.select_tab(name),
                         kind='accent' if col == 0 else 'soft', icon=TAB_ICONS[caption], icon_size=20,
                         width=190, font=ctk.CTkFont(size=14, weight='bold'))
            btn.grid(row=0, column=col, padx=(18 if col == 0 else 4, 4), pady=10)
            self.nav_buttons[caption] = btn
            
        button(nav, 'Ayuda · F1', self._help, icon='info', width=125).grid(row=0, column=3, sticky='e', padx=24)
        
        self.sale_page = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.sale_page.grid(row=2, column=0, sticky='nsew')
        self.sale_page.grid_columnconfigure(0, weight=1)
        self.sale_page.grid_columnconfigure(1, minsize=300)
        self.sale_page.grid_rowconfigure(1, weight=1)

    def _build_cash_page(self):
        if __package__:
            from .cash_close_view import CashCloseView
        else:
            from cash_close_view import CashCloseView
        self.cash_page = CashCloseView(self, self.user_data, self.cash_close_callback,
            balance_callback=self.cash_balance_callback,
            pending_sale_callback=lambda: bool(self.ticket_rows),
            on_closed_callback=self._cash_closed,
            on_back_callback=lambda: self.select_tab('Venta'))
        self.cash_page.grid(row=2, column=0, sticky='nsew')
        self.cash_page.grid_remove()

    def _build_history_page(self):
        try:
            if __package__:
                from .sales_history_view import SalesHistoryView
            else:
                from sales_history_view import SalesHistoryView
                
            class AppMock:
                pass
            mock = AppMock()
            try:
                from controllers.sales_controller import SalesController
                mock.sales_controller = SalesController()
                # Evita el crash si olvidaste agregar get_sales_list al controlador
                if not hasattr(mock.sales_controller, 'get_sales_list'):
                    mock.sales_controller = None
            except Exception:
                mock.sales_controller = None

            self.history_page = SalesHistoryView(self, mock)
            self.history_page.grid(row=2, column=0, sticky='nsew')
            self.history_page.grid_remove()
            
        except Exception as e:
            # Pantalla de respaldo para que la terminal no se rompa por completo
            self.history_page = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
            self.history_page.grid(row=2, column=0, sticky='nsew')
            label(self.history_page, f"⚠️ Error cargando vista Historial:\n{e}", 14, color=RED).pack(expand=True)
            self.history_page.grid_remove()

    def select_tab(self, name):
        if name not in self.nav_buttons or self._busy or self._dialog or getattr(self, 'cash_page', None) and self.cash_page._busy:
            return
        self.active_tab = name
        for caption, btn in self.nav_buttons.items():
            selected = caption == name
            style = STYLES['accent' if selected else 'soft']
            btn.configure(fg_color=style['fg_color'], hover_color=style['hover_color'],
                          text_color=style['text_color'],
                          image=get_icon(TAB_ICONS[caption], WHITE if selected else NAVY, 20))
            btn._kind = 'accent' if selected else 'soft'
            
        self.sale_page.grid_remove()
        if hasattr(self, 'cash_page'):
            self.cash_page.grid_remove()
        if hasattr(self, 'history_page'):
            self.history_page.grid_remove()

        if name == 'Venta':
            self.sale_page.grid()
            self._focus_scan()
        elif name == 'Caja y corte':
            self.cash_page.grid()
            self.cash_page.focus_set()
            self.cash_page.refresh()
        elif name == 'Historial':
            self.history_page.grid()
            self.history_page.load_sales()

    def _cash_closed(self, result):
        self._session_closed = True
        self.session_badge.configure(text='Turno cerrado', text_color=AMBER)
        self.entry_barcode.configure(state='disabled')
        set_enabled(self.btn_search, False)
        set_enabled(self.btn_add, False)
        self.integration.configure(text='Turno cerrado. Inicia sesión y abre un nuevo turno para vender.')
        self._update_totals()
        if self.on_cash_closed:
            self.on_cash_closed(result)



    def _build_ticket_panel(self):
        panel = card(self.sale_page)
        panel.grid(row=1, column=0, padx=(18, 10), pady=18, sticky='nsew')
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(3, weight=1)
        title = ctk.CTkFrame(panel, fg_color='transparent')
        title.grid(row=0, column=0, sticky='ew', padx=20, pady=(16, 8))
        title.grid_columnconfigure(0, weight=1)
        label(title, ' Venta actual', 23, True, image=get_icon('receipt', BLUE_DARK, 24),
              compound='left').grid(row=0, column=0, sticky='w')
        self.lbl_count = label(title, 'Sin productos', 12, True, BLUE_DARK, fg_color=SOFT,
                               corner_radius=12, width=120, height=26)
        self.lbl_count.grid(row=0, column=1)
        search = ctk.CTkFrame(panel, fg_color='transparent')
        search.grid(row=1, column=0, sticky='ew', padx=20, pady=(6, 4))
        search.grid_columnconfigure(1, weight=1)
        label(search, '', image=get_icon('barcode', BLUE_DARK, 26)).grid(row=0, column=0, padx=(0, 10))
        self.code_var = ctk.StringVar(value='')
        self.entry_barcode = ctk.CTkEntry(search, height=46, textvariable=self.code_var, fg_color=WHITE,
            border_color=SKY, border_width=2, text_color=INK,
            placeholder_text='Escanea o escribe el código · Enter para agregar')
        self.entry_barcode.grid(row=0, column=1, sticky='ew', padx=(0, 8))
        self.entry_barcode.bind('<Return>', self._on_scan)
        self.btn_add = button(search, 'Agregar', lambda: self._on_scan(None), kind='accent',
                              icon='plus', icon_size=16, width=105, height=46)
        self.btn_add.grid(row=0, column=2)
        self.code_var.trace_add('write', lambda *a: self._sync_add())
        self._sync_add()
        self.btn_search = button(search, 'Buscar · F3', self._search, icon='search', width=120, height=46)
        self.btn_search.grid(row=0, column=3, padx=(8, 0))
        if self.search_callback is None:
            set_enabled(self.btn_search, False)
        label(panel, 'F2 Código   •   F3 Buscar   •   F4 Cantidad   •   F12 Cobrar   •   F1 Ayuda',
              12, color=MUTED).grid(row=2, column=0, sticky='w', padx=20, pady=(4, 12))
        self.ticket_frame = ctk.CTkScrollableFrame(panel, fg_color='#F8FBFD', corner_radius=10)
        self.ticket_frame.grid(row=3, column=0, sticky='nsew', padx=16, pady=(0, 10))
        for col, (text, width) in enumerate((('PRODUCTO', 200), ('CANTIDAD', 125),
                                            ('PRECIO', 88), ('IMPORTE', 92), ('', 40))):
            self.ticket_frame.grid_columnconfigure(col, weight=1 if col == 0 else 0, minsize=width)
            label(self.ticket_frame, text, 11, True, MUTED).grid(row=0, column=col, padx=6, pady=12, sticky='w')
        self.empty = label(self.ticket_frame,
            'Tu ticket está vacío\n\nEscanea un producto o búscalo por nombre para comenzar.',
            16, color=MUTED, wraplength=440, height=220,
            image=get_icon('cart', SKY, 64), compound='top')
        self.empty.grid(row=1, column=0, columnspan=5, sticky='ew')
        self.status = label(panel, 'Listo para agregar productos.', 12, color=MUTED, anchor='w', wraplength=600)
        self.status.grid(row=4, column=0, sticky='ew', padx=20, pady=(0, 12))

    def _build_control_panel(self):
        side = card(self.sale_page, width=300)
        side.grid(row=1, column=1, sticky='nsew', padx=(0, 18), pady=18)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(6, weight=1)
        name = self.user_data.get('name') or self.user_data.get('full_name') or 'Cajero'
        label(side, 'ATENDIDO POR', 11, True, MUTED).grid(row=0, column=0, padx=22, pady=(20, 0), sticky='w')
        label(side, ' ' + str(name), 19, True, wraplength=260, image=get_icon('user', BLUE_DARK, 20),
              compound='left', justify='left').grid(row=1, column=0, padx=22, sticky='w')
        label(side, self.user_data.get('role_name', 'Operador'), 12, color=MUTED).grid(
            row=2, column=0, padx=22, pady=(0, 18), sticky='w')
        summary = ctk.CTkFrame(side, fg_color=NAVY, corner_radius=12)
        summary.grid(row=3, column=0, padx=18, sticky='ew')
        label(summary, 'TOTAL A COBRAR', 12, True, SKY).pack(anchor='w', padx=18, pady=(18, 0))
        self.lbl_total = label(summary, '$0.00', 34, True, AMBER)
        self.lbl_total.pack(anchor='w', padx=18, pady=(4, 4))
        self.lbl_subtotal = label(summary, '0 artículos', 13, color=SKY)
        self.lbl_subtotal.pack(anchor='w', padx=18, pady=(0, 16))
        self.btn_pay = button(side, 'Cobrar venta  ·  F12', self._pay, True, icon='cash', icon_size=22,
                              height=52, font=ctk.CTkFont(size=17, weight='bold'))
        self.btn_pay.grid(row=4, column=0, padx=18, pady=(18, 6), sticky='ew')
        self.integration = label(side, 'Confirma el pago antes de entregar el cambio.' if self.checkout_callback
                                 else 'Cobro pendiente de conectar al registro de ventas.',
                                 12, color=MUTED, wraplength=250)
        self.integration.grid(row=5, column=0, padx=20, sticky='ew')
        actions = ctk.CTkFrame(side, fg_color='transparent')
        actions.grid(row=7, column=0, padx=18, pady=18, sticky='ew')
        actions.grid_columnconfigure(0, weight=1)
        self.btn_cancel = button(actions, 'Vaciar ticket', self._cancel, kind='danger', icon='trash')
        self.btn_cancel.grid(row=0, column=0, sticky='ew', pady=4)
        button(actions, 'Ir a Caja y corte', self._cash, icon='calc').grid(row=1, column=0, sticky='ew', pady=4)
        button(actions, 'Cerrar sesión', self._logout, icon='logout').grid(row=2, column=0, sticky='ew', pady=4)

    def show_message(self, text, error=False):
        self.status.configure(text=str(text), text_color=RED if error else BLUE_DARK)

    def _error(self, exc):
        if isinstance(exc, ValueError) or type(exc).__module__.startswith('utils.exceptions'):
            return str(exc)
        log.exception('Error en terminal')
        return 'No se pudo completar la operación. Revisa la conexión e inténtalo nuevamente.'

    def _sync_add(self):
        set_enabled(self.btn_add, bool(self.code_var.get().strip() and not self._busy
                                       and not self._session_closed))

    def _focus_scan(self):
        if self.active_tab == 'Venta' and not self._session_closed:
            select_entry(self.entry_barcode)

    def _on_scan(self, event=None):
        if self._busy or self._dialog or self._session_closed or self.active_tab != 'Venta':
            return
        code = self.entry_barcode.get().strip()
        if not code:
            self.show_message('Escribe o escanea un código.', True)
            return
        self._busy = True
        self._sync_add()
        try:
            # El callback original agrega mediante add_item_to_ui; no se duplica su resultado.
            result = self.add_product_callback(code)
            if result is False:
                self.show_message('Producto no encontrado. Revisa el código o usa Buscar.', True)
            else:
                self.entry_barcode.delete(0, 'end')
        except Exception as exc:
            self.show_message(self._error(exc), True)
        finally:
            self._busy = False
            self._sync_add()
            self._focus_scan()

    def add_item_to_ui(self, producto, cantidad=1):
        if self._session_closed:
            raise ValueError('El turno está cerrado. Inicia un nuevo turno para vender.')
        if self._dialog and getattr(self, '_pay_open', False):
            raise ValueError('Cierra el cobro antes de modificar el ticket.')
        product = dict(producto)
        sku = str(product['sku'])
        price_cents(product)
        current = self.ticket_rows.get(sku)
        if current:
            product = current['producto']
        quantity = quantity_value(product, cantidad)
        new_qty = quantity_value(product, quantity + (current['cantidad'] if current else 0))
        self._validate_stock(product, new_qty)
        previous = line_cents(product, current['cantidad']) if current else 0
        if self.total_cents - previous + line_cents(product, new_qty) > 100000000:
            raise ValueError('La venta no puede superar $1,000,000.00.')
        if not current and len(self.ticket_rows) >= 1000:
            raise ValueError('El ticket admite hasta 1,000 productos distintos.')
        if current:
            current['cantidad'] = new_qty
        else:
            self.ticket_rows[sku] = {'producto': product, 'cantidad': new_qty, 'widgets': {}}
        self._render_rows()
        self.show_message(f"Agregado: {product['name']}")

    def _validate_stock(self, product, quantity):
        if self.stock_callback:
            self.stock_callback(copy.deepcopy(product), quantity)

    def _render_rows(self):
        for item in self.ticket_rows.values():
            for widget in item['widgets'].values():
                widget.destroy()
            item['widgets'] = {}
        self._compute_lines()
        self.empty.grid_remove() if self.ticket_rows else self.empty.grid()
        for index, (sku, item) in enumerate(self.ticket_rows.items(), 1):
            p, q = item['producto'], item['cantidad']
            info = f"{p['name']}\n{sku} · {p.get('unit_code', 'unidad')}"
            if p.get('track_inventory') and 'stock' in p:
                info += f" · Exist.: {p['stock']:g}"
            if item.get('disc'):
                info += f"\nDescuento {item['disc']['name']}: -{money(item['disc']['amount'])}"
            elif item.get('pending'):
                info += f"\n🔒 {item['pending']['name']}: requiere autorización"
            desc = label(self.ticket_frame, info, 14, anchor='w', justify='left', wraplength=260)
            desc.grid(row=index, column=0, padx=6, pady=12, sticky='ew')
            qty = ctk.CTkFrame(self.ticket_frame, fg_color='transparent')
            qty.grid(row=index, column=1, padx=4)
            button(qty, '', lambda s=sku: self._adjust(s, -1), icon='minus', icon_size=14,
                   width=30, height=32).pack(side='left')
            button(qty, f'{q:g}', lambda s=sku: self._edit_quantity(s), width=55, height=32).pack(side='left', padx=2)
            button(qty, '', lambda s=sku: self._adjust(s, 1), icon='plus', icon_size=14,
                   width=30, height=32).pack(side='left')
            price = label(self.ticket_frame, money(price_cents(p)), 13)
            price.grid(row=index, column=2, padx=6)
            subtotal = label(self.ticket_frame, money(item['net']), 14, True)
            subtotal.grid(row=index, column=3, padx=6)
            remove = button(self.ticket_frame, '', lambda s=sku: self.remove_item(s), kind='danger',
                            icon='close', icon_size=14, width=34, height=32)
            remove.grid(row=index, column=4, padx=4)
            item['widgets'] = {'lbl_desc': desc, 'quantity': qty, 'lbl_precio': price,
                               'lbl_subtotal': subtotal, 'btn_quitar': remove}
        self._update_totals()

    def _update_totals(self):
        rows = list(self.ticket_rows.values())
        self.total_cents = sum(i['net'] for i in rows)
        saved = sum(i['disc']['amount'] for i in rows if i.get('disc'))
        caption = f'{len(rows)} conceptos · ' + (f'Ahorro {money(saved)}' if saved else 'Precios de catálogo')
        if any(i.get('pending') for i in rows):
            caption += ' · 🔒 Descuento por autorizar'
        self.lbl_total.configure(text=money(self.total_cents))
        self.lbl_count.configure(text=f'{len(rows)} productos')
        self.lbl_subtotal.configure(text=caption)
        set_enabled(self.btn_pay, bool(rows and self.checkout_callback and not self._session_closed))
        set_enabled(self.btn_cancel, bool(rows))
    def remove_item(self, sku):
        if self._busy or self._session_closed or getattr(self, '_pay_open', False):
            return
        item = self.ticket_rows.pop(str(sku), None)
        if item:
            for widget in item['widgets'].values():
                widget.destroy()
            self._render_rows()
            self.show_message('Producto eliminado del ticket.')

    def _set_quantity(self, sku, value):
        if self._session_closed or getattr(self, '_pay_open', False):
            raise ValueError('No se puede modificar el ticket en este momento.')
        item = self.ticket_rows[sku]
        q = quantity_value(item['producto'], value)
        self._validate_stock(item['producto'], q)
        if self.total_cents - line_cents(item['producto'], item['cantidad']) + line_cents(item['producto'], q) > 100000000:
            raise ValueError('La venta no puede superar $1,000,000.00.')
        item['cantidad'] = q
        self._render_rows()
        self.show_message('Cantidad actualizada.')

    def _adjust(self, sku, delta):
        if self._busy or self._session_closed or self._dialog:
            return
        try:
            q = self.ticket_rows[sku]['cantidad'] + delta
            if q <= 0:
                if messagebox.askyesno('Quitar producto', '¿Quitar este producto del ticket?', parent=self):
                    self.remove_item(sku)
            else:
                self._set_quantity(sku, q)
        except Exception as exc:
            self.show_message(self._error(exc), True)

    def _modal(self, title, size='520x420'):
        if self._busy or self.cash_page._busy:
            return None
        if self._dialog:
            self._dialog.lift()
            return None
        help_window = getattr(self, '_help_window', None)
        if help_window is not None and help_window.winfo_exists():
            help_window._position_jobs.close()
            help_window.destroy()
            self._help_window = None
        win = ctk.CTkToplevel(self)
        win.withdraw()
        win.title(title)
        win.configure(fg_color=BG)
        win.resizable(False, False)
        win.protocol('WM_DELETE_WINDOW', self._close_dialog)
        win.bind('<Escape>', lambda e: self._close_dialog())
        win.jobs = Jobs(win)
        self._dialog = win
        width, height = map(int, size.split('x'))
        center_window(win, self.winfo_toplevel(), width, height)
        return win

    def _close_dialog(self):
        if self._busy:
            return
        if self._dialog:
            win = self._dialog
            job = getattr(win, '_search_job', None)   # cancela una búsqueda pendiente del buscador
            if job:
                win.after_cancel(job)
            win.jobs.close()
            win._position_jobs.close()
            win.grab_release()
            win.destroy()
            self._dialog = None
        self._pay_open = False
        self._focus_scan()

    def _edit_quantity(self, sku):
        if self._session_closed or sku not in self.ticket_rows:
            return
        win = self._modal('Editar cantidad', '460x340')
        if win is None:
            return
        item = self.ticket_rows[sku]
        label(win, item['producto']['name'], 20, True, wraplength=410).pack(padx=22, pady=(22, 8))
        label(win, 'Hasta tres decimales' if item['producto'].get('allows_decimals') else 'Solo unidades enteras', color=MUTED).pack()
        value = ctk.StringVar(value=str(item['cantidad']))
        entry = ctk.CTkEntry(win, textvariable=value, height=44, text_color=INK, fg_color=WHITE,
                             border_color=SKY, border_width=2)
        entry.pack(pady=14)
        entry.select_range(0, 'end')
        error = label(win, '', color=RED, wraplength=410, height=42)
        error.pack()

        def validate(*args):
            try:
                quantity_value(item['producto'], value.get())
                error.configure(text='')
                set_enabled(save_button, True)
            except ValueError as exc:
                error.configure(text=str(exc))
                set_enabled(save_button, False)

        def save():
            if save_button.cget('state') != 'normal':
                return
            try:
                self._set_quantity(sku, value.get())
            except Exception as exc:
                error.configure(text=self._error(exc))
                return
            self._close_dialog()
        save_button = button(win, 'Guardar cantidad · Enter', save, True, icon='check')
        save_button.pack(pady=8)
        button(win, 'Volver · Esc', self._close_dialog).pack(pady=4)
        value.trace_add('write', validate)
        entry.bind('<Return>', lambda e: save())
        win._initial_focus = entry
        validate()

    def _search(self):
        if not self.search_callback:
            self.show_message('La búsqueda por nombre aún no está conectada.', True)
            return

        win = self._modal('Buscar productos', '850x600')
        if win is None:
            return

        win._search_job = None
        search_var = ctk.StringVar(value=self.entry_barcode.get())
        current_results = {}

        # --- Encabezado ---
        label(win, ' Buscar y agregar productos', 24, True, image=get_icon('search', BLUE_DARK, 24),
              compound='left').pack(anchor='w', padx=24, pady=(22, 4))
        label(win, 'Escribe un nombre o código · ↑ ↓ para elegir · Enter para agregar · Esc para volver',
              color=MUTED).pack(anchor='w', padx=24)

        entry = ctk.CTkEntry(win, height=44, fg_color=WHITE, text_color=INK, textvariable=search_var,
                             border_color=SKY, border_width=2)
        entry.pack(fill='x', padx=24, pady=14)

        result_label = label(win, 'Cargando catálogo...', color=BLUE_DARK)
        result_label.pack(anchor='w', padx=24)

        # --- Tabla ---
        table_frame = card(win)
        table_frame.pack(fill='both', expand=True, padx=24, pady=(5, 15))

        style = ttk.Style()
        style.theme_use('default')
        style.configure('Search.Treeview', background=WHITE, foreground=INK, rowheight=36,
                        fieldbackground=WHITE, borderwidth=0, font=('Arial', 11))
        style.map('Search.Treeview', background=[('selected', SKY)], foreground=[('selected', NAVY)])
        style.configure('Search.Treeview.Heading', background=NAVY, foreground=WHITE,
                        font=('Arial', 11, 'bold'), borderwidth=0, relief='flat', padding=(8, 8))
        style.map('Search.Treeview.Heading', background=[('active', NAVY)])

        tree = ttk.Treeview(table_frame, columns=('sku', 'name', 'price', 'stock'), show='headings',
                            selectmode='browse', style='Search.Treeview')
        tree.tag_configure('odd', background='#F5F9FC')
        for col, text in (('sku', 'Código'), ('name', 'Producto'), ('price', 'Precio'), ('stock', 'Existencia')):
            tree.heading(col, text=text)
        tree.column('sku', width=140)
        tree.column('name', width=380)
        tree.column('price', width=100, anchor='e')
        tree.column('stock', width=100, anchor='center')

        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side='left', fill='both', expand=True, padx=2, pady=2)
        scrollbar.pack(side='right', fill='y', pady=2)

        # --- Pie ---
        bottom_frame = ctk.CTkFrame(win, fg_color='transparent')
        bottom_frame.pack(fill='x', padx=24, pady=(0, 20))
        qty_frame = ctk.CTkFrame(bottom_frame, fg_color='transparent')
        qty_frame.pack(side='left')
        label(qty_frame, 'Cantidad', 14, True).pack(side='left', padx=(0, 10))
        qty_var = ctk.StringVar(value='1')
        qty_entry = ctk.CTkEntry(qty_frame, textvariable=qty_var, width=80, justify='center', height=38,
                                 fg_color=WHITE, text_color=INK, border_color=SKY, border_width=2)
        qty_entry.pack(side='left')

        btn_add = button(bottom_frame, 'Agregar al ticket · Enter', lambda: add_selected(), True, icon='plus')
        btn_add.pack(side='right', padx=(10, 0))
        button(bottom_frame, 'Volver · Esc', self._close_dialog).pack(side='right')

        # --- Lógica ---
        def add_selected():
            selected = tree.selection()
            if not selected:
                result_label.configure(text='Selecciona un producto de la lista.', text_color=RED)
                return
            product = current_results.get(selected[0])
            if not product:
                return
            try:
                qty = qty_var.get().strip() or '1'
                self.add_item_to_ui(product, cantidad=qty)
            except Exception as exc:
                result_label.configure(text=self._error(exc), text_color=RED)
                return
            self.entry_barcode.delete(0, 'end')
            self._close_dialog()

        def run(text_to_search=''):
            # Texto vacío = catálogo completo; con texto = filtra por nombre o código.
            tree.delete(*tree.get_children())
            current_results.clear()
            try:
                products = list(self.search_callback(text_to_search))
                if not products:
                    result_label.configure(text='No hay productos para mostrar.' if not text_to_search
                                           else 'Sin resultados. Prueba otro nombre o código.', text_color=RED)
                elif text_to_search:
                    result_label.configure(text=f'{len(products)} resultados encontrados.', text_color=MUTED)
                else:
                    result_label.configure(text=f'Mostrando el catálogo completo ({len(products)} productos).',
                                           text_color=MUTED)
                for i, product in enumerate(products):
                    p = dict(product)
                    stock_str = f"{p.get('stock', 0):g}" if p.get('track_inventory') else 'N/A'
                    item_id = tree.insert('', 'end', values=(p['sku'], p['name'], money(price_cents(p)), stock_str),
                                          tags=('odd',) if i % 2 else ())
                    current_results[item_id] = p
                    if i == 0:   # el primero queda listo para agregar con Enter
                        tree.selection_set(item_id)
                        tree.focus(item_id)
            except Exception as exc:
                result_label.configure(text=self._error(exc), text_color=RED)

        def on_type(*args):
            if win._search_job:
                win.after_cancel(win._search_job)
            text = search_var.get().strip()
            win._search_job = win.after(300, lambda: run(text))

        search_var.trace_add('write', on_type)

        def move_focus(direction):
            items = tree.get_children()
            if not items:
                return 'break'
            selected = tree.selection()
            if not selected:
                new_sel = items[0] if direction == 1 else items[-1]
            else:
                new_sel = items[(items.index(selected[0]) + direction) % len(items)]
            tree.selection_set(new_sel)
            tree.focus(new_sel)
            tree.see(new_sel)
            return 'break'

        entry.bind('<Down>', lambda e: move_focus(1))
        entry.bind('<Up>', lambda e: move_focus(-1))
        entry.bind('<Return>', lambda e: add_selected())
        qty_entry.bind('<Return>', lambda e: add_selected())
        tree.bind('<Double-1>', lambda e: add_selected())
        tree.bind('<Return>', lambda e: add_selected())

        entry.focus_set()
        run(search_var.get().strip())   # al abrir muestra todo el catálogo (o lo ya escrito)

    def _clear(self):
        for item in self.ticket_rows.values():
            for widget in item['widgets'].values():
                widget.destroy()
        self.ticket_rows.clear()
        self._request_id = str(uuid.uuid4())
        self._authorizer = None
        self._render_rows()

    def _cancel(self):
        if self._dialog or self._busy or not self.ticket_rows:
            return
        if messagebox.askyesno('Vaciar ticket', '¿Eliminar todos los productos de esta venta sin cobrar?', parent=self):
            self._clear()
            self.show_message('Ticket vaciado. Puedes comenzar una nueva venta.')
            self._focus_scan()

    def _logout(self):
        if self._busy or self._dialog:
            return
        if self.ticket_rows and not messagebox.askyesno('Venta pendiente',
                'Hay productos sin cobrar. ¿Descartar el ticket y cerrar sesión?', parent=self):
            return
        try:
            self.logout_callback()
        except Exception as exc:
            self.show_message(self._error(exc), True)

    def _cash(self):
        self.select_tab('Caja y corte')

    def _payload(self, method, received, total, global_info=None):
        rows = list(self.ticket_rows.items())
        g_amount = global_info['amount'] if global_info else 0
        shares = prorate(g_amount, [i['net'] for _, i in rows])
        items, discount_total = [], 0
        for (sku, i), share in zip(rows, shares):
            d = i['disc']['amount'] if i.get('disc') else 0
            discount_total += d + share
            items.append({'product_id': i['producto'].get('id'), 'sku': sku,
                          'quantity': str(i['cantidad']),
                          'unit_price_cents': price_cents(i['producto']),
                          'discount_id': i['disc']['discount_id'] if i.get('disc') else None,
                          'discount_cents': d + share,
                          'line_total_cents': i['net'] - share})
        return {'request_id': self._request_id, 'user_id': self.user_data.get('id'),
                'items': items, 'total_cents': total, 'payment_method': method,
                'received_cents': received, 'change_cents': received - total,
                'discount_id': global_info['discount_id'] if global_info else None,
                'discount_total_cents': discount_total,
                'authorized_by': self._authorizer['id'] if self._authorizer else None}
    def _compute_lines(self):
        """Calcula bruto, descuento de producto y neto de cada línea."""
        for item in self.ticket_rows.values():
            p, q = item['producto'], item['cantidad']
            gross = line_cents(p, q)
            disc = pending = None
            if self.discount_controller and p.get('id'):
                try:
                    best = self.discount_controller.best_for_product(p['id'], gross)
                except Exception:
                    log.exception('No se pudo consultar el descuento del producto')
                    best = None
                if best:
                    if best['requires_authorization'] and not (self._can_discount or self._authorizer):
                        pending = best
                    else:
                        disc = best
            item.update(gross=gross, disc=disc, pending=pending,
                        net=gross - (disc['amount'] if disc else 0))

    def _pay(self):
        if not self.ticket_rows or not self.checkout_callback or self._busy or self._session_closed or self.active_tab != 'Venta':
            return
        # Descuentos de producto que esperan autorización de un supervisor
        if any(i.get('pending') for i in self.ticket_rows.values()):
            if messagebox.askyesno('Descuentos por autorizar',
                    'Hay descuentos que requieren autorización de un supervisor.\n\n'
                    '¿Autorizarlos ahora? Si eliges «No», se cobrará sin esos descuentos.', parent=self):
                sup = self._ask_supervisor(self)
                if sup:
                    self._authorizer = sup
                    self._render_rows()
        win = self._modal('Cobrar venta', '560x790')
        if win is None:
            return
        self._pay_open = True
        self._selected_customer_id = None
        disc = {'info': None}      # descuento global elegido en este cobro

        def pay_total():
            return self.total_cents - (disc['info']['amount'] if disc['info'] else 0)

        label(win, ' Cobrar venta', 24, True, image=get_icon('cash', BLUE_DARK, 26),
              compound='left').pack(anchor='w', padx=28, pady=(16, 4))

        # --- Cliente ---
        cust_card = ctk.CTkFrame(win, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        cust_card.pack(fill='x', padx=28, pady=(0, 10))
        cust_inner = ctk.CTkFrame(cust_card, fg_color='transparent')
        cust_inner.pack(fill='x', padx=16, pady=12)
        cust_inner.grid_columnconfigure(1, weight=1)
        logo_user = ctk.CTkFrame(cust_inner, width=36, height=36, corner_radius=10, fg_color=SOFT)
        logo_user.grid(row=0, column=0, rowspan=2, padx=(0, 12))
        logo_user.grid_propagate(False)
        ctk.CTkLabel(logo_user, text='', image=get_icon('user', BLUE_DARK, 18)).place(relx=.5, rely=.5, anchor='center')
        label(cust_inner, 'CLIENTE ASIGNADO', 10, True, MUTED).grid(row=0, column=1, sticky='w')
        cust_lbl_name = label(cust_inner, 'Público en general', 14, True, NAVY)
        cust_lbl_name.grid(row=1, column=1, sticky='w')

        def open_customer_selector():
            sel_win = ctk.CTkToplevel(win)
            sel_win.title("Seleccionar o registrar cliente")
            sel_win.geometry("500x620")
            sel_win.resizable(False, False)
            sel_win.transient(win)
            sel_win.grab_set()
            center_window(sel_win, win, 500, 620)
            sel_win.configure(fg_color=BG)
            main_container = ctk.CTkScrollableFrame(sel_win, fg_color="transparent")
            main_container.pack(fill="both", expand=True, padx=10, pady=10)
            label(main_container, 'Asignar Cliente', 20, True, image=get_icon('user', BLUE_DARK, 22),
                  compound='left').pack(anchor='w', padx=14, pady=(10, 8))
            try:
                from controllers.customers_controller import CustomersController
                cc = CustomersController()
            except Exception:
                log.exception("No se pudo cargar el controlador de clientes")
                cc = None
            search_c_var = ctk.StringVar()
            entry_c = ctk.CTkEntry(main_container, textvariable=search_c_var, placeholder_text="🔍 Buscar por nombre o teléfono...", height=40,
                                   fg_color=WHITE, text_color=INK, border_color=SKY, border_width=2)
            entry_c.pack(fill='x', padx=14, pady=6)
            list_frame = ctk.CTkFrame(main_container, fg_color=WHITE, corner_radius=10, border_width=1, border_color=BORDER)
            list_frame.pack(fill='x', padx=14, pady=6)
            rows_container = ctk.CTkScrollableFrame(list_frame, fg_color="transparent", height=140)
            rows_container.pack(fill='x', padx=4, pady=4)
            selected_temp = {'id': None, 'name': 'Público en general'}

            def populate_list(query=""):
                for w in rows_container.winfo_children():
                    w.destroy()

                def pick(cid, cname):
                    selected_temp['id'] = cid
                    selected_temp['name'] = cname
                    apply_selection()

                def create_row(cid, cname, cphone):
                    row = ctk.CTkFrame(rows_container, fg_color=SOFT if selected_temp['id'] == cid else 'transparent', corner_radius=6)
                    row.pack(fill='x', pady=2, padx=4)
                    ctk.CTkButton(row, text=f"  {cname}  ·  {cphone or 'Sin teléfono'}", fg_color='transparent', text_color=NAVY,
                                  hover_color=SOFT_HOVER, anchor='w', font=ctk.CTkFont(size=13, weight='bold'),
                                  command=lambda: pick(cid, cname)).pack(side='left', fill='x', expand=True, padx=4, pady=4)

                create_row(None, "Público en general", "")
                if cc:
                    for m in cc.get_all_customers(query):
                        create_row(m['id'], m['name'], m.get('phone'))

            search_c_var.trace_add('write', lambda *_: populate_list(search_c_var.get()))
            populate_list()

            def apply_selection():
                self._selected_customer_id = selected_temp['id']
                cust_lbl_name.configure(text=selected_temp['name'])
                sel_win.destroy()

            quick_frame = ctk.CTkFrame(main_container, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
            quick_frame.pack(fill='x', padx=14, pady=(10, 15))
            label(quick_frame, '¿Nuevo cliente? Registro rápido', 14, True, BLUE_DARK).pack(anchor='w', padx=16, pady=(12, 8))
            q_name, q_phone, q_email = ctk.StringVar(), ctk.StringVar(), ctk.StringVar()
            label(quick_frame, 'Nombre completo *', 11, bold=True, color=MUTED).pack(anchor='w', padx=16, pady=(4, 0))
            ctk.CTkEntry(quick_frame, textvariable=q_name, placeholder_text="Ej. Juan Pérez", height=35, fg_color=BG, border_color=BORDER).pack(fill='x', padx=16, pady=(2, 8))
            label(quick_frame, 'Teléfono o Correo * (Mínimo uno)', 11, bold=True, color=MUTED).pack(anchor='w', padx=16, pady=(4, 0))
            contact_frame = ctk.CTkFrame(quick_frame, fg_color="transparent")
            contact_frame.pack(fill='x', padx=16, pady=(2, 6))
            contact_frame.grid_columnconfigure((0, 1), weight=1)
            ctk.CTkEntry(contact_frame, textvariable=q_phone, placeholder_text="Teléfono", height=35, fg_color=BG, border_color=BORDER).grid(row=0, column=0, sticky='ew', padx=(0, 4))
            ctk.CTkEntry(contact_frame, textvariable=q_email, placeholder_text="Correo electrónico", height=35, fg_color=BG, border_color=BORDER).grid(row=0, column=1, sticky='ew', padx=(4, 0))

            def register_quick():
                name_val, phone_val, email_val = q_name.get().strip(), q_phone.get().strip(), q_email.get().strip()
                if not name_val:
                    messagebox.showwarning("Aviso", "El nombre del cliente es obligatorio.", parent=sel_win)
                    return
                if not phone_val and not email_val:
                    messagebox.showwarning("Aviso", "Debes ingresar al menos un número de teléfono o un correo electrónico.", parent=sel_win)
                    return
                if cc:
                    try:
                        customer_data = {"name": name_val, "phone": phone_val}
                        if email_val:
                            customer_data["email"] = email_val
                        new_id = cc.save_customer(customer_data)
                        selected_temp['id'] = new_id
                        selected_temp['name'] = name_val
                        apply_selection()
                    except Exception as e:
                        messagebox.showerror("Error", str(e), parent=sel_win)
                else:
                    messagebox.showwarning("Aviso", "Módulo de clientes no inicializado.", parent=sel_win)

            button(quick_frame, 'Registrar y seleccionar', register_quick, True, height=36, icon='check').pack(anchor='e', padx=16, pady=(6, 12))

        button(cust_card, 'Cambiar / Registrar cliente', open_customer_selector, kind='soft', icon='user', height=36).pack(fill='x', padx=16, pady=(0, 12))

        # --- Descuento global ---
        def open_discounts():
            if self._busy:
                return
            dc = self.discount_controller
            try:
                available = list(dc.list_available(self.user_data))
            except Exception as exc:
                error.configure(text=self._error(exc))
                return
            sel = ctk.CTkToplevel(win)
            sel.title('Aplicar descuento')
            sel.resizable(False, False)
            sel.transient(win)
            sel.configure(fg_color=BG)
            center_window(sel, win, 440, 480)
            sel.after(150, lambda: sel.winfo_exists() and sel.grab_set())
            label(sel, ' Descuentos disponibles', 20, True).pack(anchor='w', padx=20, pady=(18, 6))
            msg = label(sel, '', 12, color=RED, wraplength=390, height=34)
            msg.pack(padx=20)
            frame = ctk.CTkScrollableFrame(sel, fg_color=WHITE, corner_radius=10)
            frame.pack(fill='both', expand=True, padx=20, pady=6)

            def choose(d):
                base = self.total_cents      # ya incluye los descuentos de producto
                try:
                    try:
                        info = dc.resolve_for_sale(self.user_data, d['id'], base, self._authorizer)
                    except PermissionDenied:
                        sup = self._ask_supervisor(sel)
                        if sup is None:
                            return
                        info = dc.resolve_for_sale(self.user_data, d['id'], base, sup)
                        self._authorizer = sup
                except Exception as exc:
                    msg.configure(text=self._error(exc))
                    return
                disc['info'] = info
                sel.destroy()
                refresh_totals()

            if not available:
                label(frame, 'No hay descuentos vigentes.', 13, color=MUTED).pack(pady=24)
            for d in available:
                text = f"{f'{d['value']:g} %' if d['discount_type'] == 'percent' else money(int(d['value']))}"
                lock = '  🔒' if d['requires_authorization'] and not (self._can_discount or self._authorizer) else ''
                ctk.CTkButton(frame, text=f"{d['name']}  ·  {text}{lock}", anchor='w', height=42,
                              fg_color=SOFT, hover_color=SOFT_HOVER, text_color=NAVY,
                              font=ctk.CTkFont(size=14, weight='bold'),
                              command=lambda d=d: choose(d)).pack(fill='x', pady=3)
            button(sel, 'Cancelar · Esc', sel.destroy, height=36).pack(pady=(4, 16))
            sel.bind('<Escape>', lambda e: sel.destroy())

        def remove_discount():
            disc['info'] = None
            refresh_totals()

        if self.discount_controller:
            disc_row = ctk.CTkFrame(win, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
            disc_row.pack(fill='x', padx=28, pady=(0, 10))
            disc_row.grid_columnconfigure(0, weight=1)
            disc_lbl = label(disc_row, 'Sin descuento global', 13, True, NAVY, anchor='w', justify='left', wraplength=250)
            disc_lbl.grid(row=0, column=0, sticky='w', padx=14, pady=10)
            btn_disc = button(disc_row, 'Descuento', open_discounts, kind='soft', height=34, width=110)
            btn_disc.grid(row=0, column=1, padx=(0, 6), pady=8)
            btn_disc_off = button(disc_row, 'Quitar', remove_discount, kind='danger', height=34, width=70)
            btn_disc_off.grid(row=0, column=2, padx=(0, 10), pady=8)
            btn_disc_off.grid_remove()
        else:
            disc_lbl = btn_disc = btn_disc_off = None

        head = ctk.CTkFrame(win, fg_color=NAVY, corner_radius=14)
        head.pack(fill='x', padx=28, pady=(0, 10))
        label(head, 'TOTAL A COBRAR', 12, True, SKY).pack(anchor='w', padx=20, pady=(10, 0))
        lbl_modal_total = label(head, money(pay_total()), 32, True, AMBER)
        lbl_modal_total.pack(anchor='w', padx=20, pady=(0, 10))

        label(win, 'Forma de pago · Alt+1 / Alt+2 / Alt+3', 12, color=MUTED).pack(anchor='w', padx=28)
        method = ctk.StringVar(value='Efectivo')
        selector = ctk.CTkSegmentedButton(win, values=['Efectivo', 'Tarjeta', 'Transferencia'],
            variable=method, selected_color=SKY, selected_hover_color=SKY,
            unselected_color=SOFT, unselected_hover_color=SOFT_HOVER, text_color=NAVY,
            height=36, font=ctk.CTkFont(size=13, weight='bold'))
        selector.pack(fill='x', padx=28, pady=6)

        content = ctk.CTkFrame(win, fg_color='transparent', height=160)
        content.pack(fill='x', padx=28, pady=(5, 0))
        content.grid_columnconfigure(0, weight=1)

        cash_frame = ctk.CTkFrame(content, fg_color='transparent')
        cash_frame.grid(row=0, column=0, sticky='ew')
        label(cash_frame, 'Efectivo recibido', color=MUTED).pack(anchor='w', pady=(0, 2))
        received = ctk.StringVar(value='')
        entry = ctk.CTkEntry(cash_frame, textvariable=received, height=42, fg_color=WHITE,
            text_color=INK, placeholder_text='0.00', font=ctk.CTkFont(size=20),
            border_color=SKY, border_width=2)
        entry.pack(fill='x')

        quick = ctk.CTkFrame(cash_frame, fg_color='transparent')
        quick.pack(fill='x', pady=6)
        quick_buttons = []
        for caption, amount in [('Exacto', None), ('$100', 10000), ('$200', 20000), ('$500', 50000)]:
            btn = button(quick, caption,
                         lambda a=amount: received.set(f'{Decimal(pay_total() if a is None else a)/100:.2f}'),
                         width=102)
            btn.pack(side='left', padx=2)
            quick_buttons.append((btn, amount))

        def refresh_quick():
            for b, amt in quick_buttons:
                b.configure(state='disabled' if amt is not None and amt < pay_total() else 'normal')

        refresh_quick()

        external = ctk.CTkFrame(content, fg_color=SOFT, corner_radius=12)
        external.grid(row=0, column=0, sticky='ew')
        external_note = label(external, '', 13, color=BLUE_DARK, wraplength=420, justify='left')
        external_note.pack(anchor='w', padx=16, pady=(12, 8))
        verified = ctk.BooleanVar(value=False)
        check = ctk.CTkCheckBox(external, text='', variable=verified, text_color=INK,
                                fg_color=BLUE_DARK, hover_color='#14657B')
        keyboard_checkbox(check)
        check.pack(anchor='w', padx=16, pady=(2, 12))
        external.grid_remove()

        change = label(win, '', 18, True, BLUE_DARK)
        change.pack(anchor='w', padx=28, pady=8)
        error = label(win, '', 13, color=RED, wraplength=480, height=35)
        error.pack(fill='x', padx=28)
        activity = Activity(win)
        activity.pack(fill='x', padx=28)

        def amount_value():
            if method.get() != 'Efectivo':
                return pay_total()
            raw = received.get().strip()
            if not re.fullmatch(r'[0-9]+(?:[.,][0-9]{1,2})?', raw):
                raise ValueError('Escribe un importe sin separadores de miles, por ejemplo 150.50.')
            val = decimal_value(raw.replace(',', '.'))
            if val < 0 or val > 1000000 or val != val.quantize(Decimal('.01')):
                raise ValueError('Usa de 0 a 1,000,000 con máximo dos decimales, sin separadores de miles.')
            return int(val * 100)

        def update(*args):
            cash = method.get() == 'Efectivo'
            total_now = pay_total()
            valid = False
            try:
                amt = amount_value()
                diff = amt - total_now
                change.configure(text=('Cambio: ' + money(diff) if diff >= 0 else 'Faltan: ' + money(-diff))
                       if cash else 'Pago exacto · Sin cambio',
                       text_color=BLUE_DARK if diff >= 0 else RED)
                valid = total_now > 0 and diff >= 0 and (cash or verified.get()) and total_now <= 100000000
                if valid:
                    error.configure(text='')
                elif total_now <= 0:
                    error.configure(text='El descuento deja la venta en $0.00; no se puede cobrar.')
                else:
                    error.configure(text='El efectivo no cubre el total.' if cash
                                    else 'Confirma que el pago ya fue recibido.')
            except ValueError as exc:
                change.configure(text='Ingresa el efectivo recibido.', text_color=MUTED)
                error.configure(text='' if not received.get().strip() else str(exc))
            set_enabled(confirm, bool(valid and not self._busy))

        def refresh_totals():
            lbl_modal_total.configure(text=money(pay_total()))
            if disc_lbl is not None:
                if disc['info']:
                    disc_lbl.configure(text=f"{disc['info']['name']} · -{money(disc['info']['amount'])}")
                    btn_disc_off.grid()
                else:
                    disc_lbl.configure(text='Sin descuento global')
                    btn_disc_off.grid_remove()
            refresh_quick()
            update()

        def switch(value):
            if self._busy:
                return
            method.set(value)
            verified.set(False)
            if value == 'Efectivo':
                external.grid_remove()
                cash_frame.grid()
                select_entry(entry)
            else:
                cash_frame.grid_remove()
                external.grid()
                external_note.configure(text='Cobra en la terminal bancaria antes de registrar la venta.' if value == 'Tarjeta'
                                        else 'Verifica el depósito en la cuenta antes de registrar la venta.')
                check.configure(text='El pago con tarjeta fue aprobado' if value == 'Tarjeta' else 'La transferencia ya fue recibida')
                check._canvas.focus_set()
            update()

        def busy_controls(busy):
            selector.configure(state='disabled' if busy else 'normal')
            entry.configure(state='disabled' if busy else 'normal')
            check.configure(state='disabled' if busy else 'normal')
            back.configure(state='disabled' if busy else 'normal')
            for b, _ in quick_buttons:
                b.configure(state='disabled' if busy else 'normal')
            for b in (btn_disc, btn_disc_off):
                if b is not None:
                    b.configure(state='disabled' if busy else 'normal')
            if not busy:
                refresh_quick()

        def finish(payload):
            try:
                result = self.checkout_callback(copy.deepcopy(payload))
                if not isinstance(result, dict) or result.get('success') is not True or not result.get('sale_id'):
                    raise ValueError('No llegó confirmación del registro. Se conserva el ticket; verifica la venta antes de reintentar.')
            except Exception as exc:
                self._busy = False
                activity.stop()
                busy_controls(False)
                confirm.configure(text='Confirmar y registrar · Ctrl+Enter')
                update()
                error.configure(text=self._error(exc))
                return
            self._busy = False
            activity.stop()
            self._close_dialog()
            self._clear()
            message = f"Venta {result['sale_id']} registrada · Total {money(payload['total_cents'])} · Cambio {money(payload['change_cents'])}"
            if payload.get('discount_total_cents'):
                message += f" · Descuento {money(payload['discount_total_cents'])}"
            if result.get('print_warning'):
                message += ' · ' + result['print_warning']
            self.show_message(message)
            self.integration.configure(text=f"Última venta: {result['sale_id']}\nEntregar cambio: {money(payload['change_cents'])}")

        def submit(event=None):
            if self._busy:
                return 'break'
            update()
            if confirm.cget('state') != 'normal':
                return 'break'
            payload = self._payload({'Efectivo': 'cash', 'Tarjeta': 'card', 'Transferencia': 'transfer'}[method.get()],
                                    amount_value(), pay_total(), disc['info'])
            payload['customer_id'] = self._selected_customer_id
            self._busy = True
            busy_controls(True)
            set_enabled(confirm, False)
            confirm.configure(text='Registrando venta…')
            activity.start('Guardando venta. Espera la confirmación…')
            win.jobs.later(70, lambda: finish(payload))
            return 'break'

        confirm = button(win, 'Confirmar y registrar · Ctrl+Enter', submit, True, icon='check', height=42)
        confirm.pack(fill='x', padx=28, pady=(4, 4))
        back = button(win, 'Volver al ticket · Esc', self._close_dialog, height=36)
        back.pack(fill='x', padx=28, pady=2)

        received.trace_add('write', update)
        verified.trace_add('write', update)
        selector.configure(command=switch)
        for key, value in (('<Alt-Key-1>', 'Efectivo'), ('<Alt-Key-2>', 'Tarjeta'), ('<Alt-Key-3>', 'Transferencia')):
            win.bind(key, lambda e, v=value: switch(v))
        entry.bind('<Return>', submit)
        win.bind('<Control-Return>', submit)
        win._initial_focus = entry
        win.payment_ui = dict(method=method, switch=switch, received=received, verified=verified,
                             check=check, cash_frame=cash_frame, external=external, confirm=confirm, submit=submit)
        update()

    def destroy(self):
        self.jobs.close()
        for key, token in self._bindings:
            self.winfo_toplevel().unbind(key, token)
        if self._dialog:
            self._dialog.jobs.close()
            self._dialog._position_jobs.close()
            self._dialog.destroy()
        super().destroy()