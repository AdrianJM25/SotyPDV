"""Dashboard SotyPOS: barra superior con botón Inicio + área de trabajo."""
import customtkinter as ctk

from controllers.auth_controller import AuthController

if __package__:
    from .icons import icon as get_icon
    from .terminal_view import (BG, WHITE, NAVY, MUTED, BLUE_DARK, SOFT, SOFT_HOVER,
                                SKY, ORANGE, AMBER, RED, BORDER)
else:
    from icons import icon as get_icon
    from terminal_view import (BG, WHITE, NAVY, MUTED, BLUE_DARK, SOFT, SOFT_HOVER,
                               SKY, ORANGE, AMBER, RED, BORDER)

# (id, nombre visible, icono)
MODULES = [
    ('ventas', 'Punto de Venta', 'cart'),
    ('productos', 'Productos', 'box'),
    ('categorias', 'Categorías', 'tag'),
    ('clientes', 'Clientes', 'users'),
    ('proveedores', 'Proveedores', 'users'),
    ('reportes', 'Reportes', 'chart'),
    ('corte', 'Corte de Caja', 'cash'),
    ('usuarios', 'Usuarios', 'users'),
    ('descuentos', 'Descuentos', 'tag'),
    ('ajustes', 'Configuración', 'gear'),
]
MODULE_META = {mod_id: (text, icon) for mod_id, text, icon in MODULES}

# Módulos que requieren un permiso para verse y abrirse
MODULE_PERMISSIONS = {
    'usuarios': 'users.manage',
    'descuentos': 'settings.manage',
}


class DashboardView(ctk.CTkFrame):
    def __init__(self, master, user_data, app_controller):
        super().__init__(master, fg_color=BG, corner_radius=0)
        self.user_data = user_data
        self.app_controller = app_controller  # Referencia a main.py
        self.current_content = None

        # Layout principal (2 filas: barra superior y contenido)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 1. Barra superior
        self._build_topbar()

        # 2. Contenedor de contenido
        self.content_frame = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content_frame.grid(row=1, column=0, sticky='nsew')

        # 3. Cuadrícula de inicio por defecto
        self.show_home()

    # ------------------------------------------------------------------ permisos
    def _can_open(self, module_id):
        perm = MODULE_PERMISSIONS.get(module_id)
        return perm is None or AuthController.has_permission(self.user_data, perm)

    # ------------------------------------------------------------------ barra superior
    def _build_topbar(self):
        """Barra de navegación superior."""
        topbar = ctk.CTkFrame(self, fg_color=NAVY, height=60, corner_radius=0)
        topbar.grid(row=0, column=0, sticky='ew')
        topbar.grid_propagate(False)

        ctk.CTkLabel(topbar, text="SotyPDV", font=ctk.CTkFont(size=18, weight='bold'),
                     text_color=WHITE).pack(side='left', padx=20)

        # Botón Inicio
        try:
            img_home = get_icon('store', WHITE, 20)
        except KeyError:
            img_home = None

        btn_home = ctk.CTkButton(topbar, text=" Inicio", image=img_home, command=self.show_home,
                                 fg_color='transparent', hover_color=BLUE_DARK, text_color=WHITE,
                                 font=ctk.CTkFont(size=14, weight='bold'))
        btn_home.pack(side='left', padx=10)

        # Botón de salir (derecha)
        try:
            img_logout = get_icon('logout', WHITE, 18)
        except KeyError:
            img_logout = None

        btn_logout = ctk.CTkButton(topbar, text="Cerrar Sesión", image=img_logout,
                                   command=self.app_controller.logout,
                                   width=130, height=36, fg_color=RED, hover_color='#D62828',
                                   text_color=WHITE, font=ctk.CTkFont(size=13, weight='bold'))
        btn_logout.pack(side='right', padx=20, pady=12)

        # Usuario y rol (derecha). login() devuelve el nombre en la clave 'name'
        user_name = self.user_data.get('name') or self.user_data.get('full_name') or 'Usuario'
        role = self.user_data.get('role_name')
        label = f"👤 {user_name}" + (f" · {role}" if role else "")
        ctk.CTkLabel(topbar, text=label, text_color=SKY,
                     font=ctk.CTkFont(size=13, weight='bold')).pack(side='right', padx=15)

    # ------------------------------------------------------------------ inicio
    def show_home(self):
        """Dibuja la cuadrícula de iconos principales."""
        self._clear_content()

        grid_container = ctk.CTkFrame(self.content_frame, fg_color='transparent')
        grid_container.place(relx=0.5, rely=0.45, anchor='center')

        ctk.CTkLabel(grid_container, text="Módulos del Sistema",
                     font=ctk.CTkFont(size=26, weight='bold'),
                     text_color=NAVY).grid(row=0, column=0, columnspan=4, pady=(0, 40))

        # Botones grandes en cuadrícula (máx. 4 columnas), solo los permitidos
        col, row = 0, 1
        for mod_id, title, icon_name in MODULES:
            if not self._can_open(mod_id):
                continue
            btn = self._create_module_button(grid_container, title, icon_name,
                                             lambda m=mod_id: self.show_module(m))
            btn.grid(row=row, column=col, padx=15, pady=15)

            col += 1
            if col > 3:
                col = 0
                row += 1

    def _create_module_button(self, parent, text, icon_name, command):
        """Crea un botón grande con icono arriba y texto abajo."""
        try:
            img = get_icon(icon_name, BLUE_DARK, 42)
        except KeyError:
            img = None

        return ctk.CTkButton(parent, text=text, image=img, command=command,
                             compound='top', width=150, height=130,
                             fg_color=WHITE, hover_color=SOFT_HOVER, text_color=NAVY,
                             border_color=BORDER, border_width=2, corner_radius=15,
                             font=ctk.CTkFont(size=15, weight='bold'))

    def _clear_content(self):
        """Limpia el contenedor principal para cambiar de vista."""
        if self.current_content:
            self.current_content.destroy()
            self.current_content = None
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    # ------------------------------------------------------------------ módulos
    def show_module(self, module_id):
        """Carga la vista específica del módulo seleccionado."""
        if not self._can_open(module_id):
            return

        # 'corte' abre el punto de venta directamente en la pestaña "Caja y corte"
        open_cash_tab = module_id == 'corte'
        if open_cash_tab:
            module_id = 'ventas'

        self._clear_content()

        if module_id == 'ventas':
            from views.terminal_view import TerminalView
            self.current_content = TerminalView(
                self.content_frame,
                self.user_data,
                logout_callback=self.app_controller.logout,
                add_product_callback=self.app_controller.handle_scan,
                search_callback=self.app_controller.handle_search,
                stock_callback=self.app_controller.handle_stock_check,
                checkout_callback=self.app_controller.handle_checkout,
                cash_balance_callback=self.app_controller.handle_cash_balance,
                cash_close_callback=self.app_controller.handle_cash_close,
                on_cash_closed=self.app_controller.handle_cash_closed,
                session_label=f"{self.app_controller.current_register['name']} · Turno abierto",
                discount_controller=self.app_controller.discount_controller,
                auth_controller=self.app_controller.auth_controller
            )
            self.current_content.pack(fill='both', expand=True)
            if open_cash_tab:
                self.current_content.select_tab("Caja y corte")

        elif module_id == 'productos':
            from views.products_view import ProductsView
            self.current_content = ProductsView(self.content_frame, self.app_controller)
            self.current_content.pack(fill='both', expand=True)

        elif module_id == 'clientes':
            from views.customers_view import CustomersView
            self.current_content = CustomersView(self.content_frame, self.app_controller)
            self.current_content.pack(fill='both', expand=True)

        elif module_id == 'categorias':
            if __package__:
                from .categories_view import CategoriesView
            else:
                from categories_view import CategoriesView
            self.current_content = CategoriesView(self.content_frame, self.app_controller)
            self.current_content.pack(fill='both', expand=True)
            
        elif module_id == 'descuentos':
            from views.discounts_view import DiscountsView
            self.current_content = DiscountsView(self.content_frame, self.app_controller)
            self.current_content.pack(fill='both', expand=True)

        elif module_id == 'proveedores':
            if __package__:
                from .suppliers_view import SuppliersView
            else:
                from suppliers_view import SuppliersView
            self.current_content = SuppliersView(self.content_frame, self.app_controller)
            self.current_content.pack(fill='both', expand=True)

        elif module_id == 'usuarios':
            from views.users_view import UsersView
            self.current_content = UsersView(self.content_frame, self.app_controller)
            self.current_content.pack(fill='both', expand=True)

        elif module_id == 'ajustes':
            if __package__:
                from .settings_view import SettingsView
            else:
                from settings_view import SettingsView
            self.current_content = SettingsView(self.content_frame, self.app_controller)
            self.current_content.pack(fill='both', expand=True)

        else:
            self._build_placeholder(module_id)

    def _build_placeholder(self, module_id):
        """Pantalla temporal para módulos aún en construcción (Reportes)."""
        text, icon_name = MODULE_META.get(module_id, (module_id.capitalize(), 'gear'))
        self.current_content = ctk.CTkFrame(self.content_frame, fg_color='transparent')
        self.current_content.pack(fill='both', expand=True)

        panel = ctk.CTkFrame(self.current_content, fg_color=WHITE, corner_radius=16,
                             border_width=1, border_color=BORDER)
        panel.place(relx=0.5, rely=0.5, anchor='center')

        try:
            img = get_icon(icon_name, SKY, 72)
        except KeyError:
            img = None

        ctk.CTkLabel(panel, text='', image=img).pack(padx=70, pady=(36, 10))
        ctk.CTkLabel(panel, text=text, font=ctk.CTkFont(size=24, weight='bold'),
                     text_color=NAVY).pack()
        ctk.CTkLabel(panel, text='Este módulo está en construcción.',
                     font=ctk.CTkFont(size=14), text_color=MUTED).pack(pady=(4, 36))