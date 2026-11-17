import copy
import logging
import tkinter.messagebox as messagebox

import customtkinter as ctk

from controllers.auth_controller import AuthController
from controllers.cash_controller import CashController
from controllers.product_controller import ProductController
from controllers.sales_controller import SalesController
from utils.exceptions import BusinessRuleError, POSError, ValidationError
from views.login_view import LoginView
from views.terminal_view import TerminalView
from views.ui_helpers import Jobs, Activity, center_window, keyboard_button
from controllers.user_controller import UserController
from controllers.discount_controller import DiscountController


logging.basicConfig(
    filename="pos.log", level=logging.INFO, encoding="utf-8",
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("soty.main")


class SotyPOSApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SotyPOS · Acceso")
        width = max(1100, min(1280, self.winfo_screenwidth() - 40))
        height = max(720, min(860, self.winfo_screenheight() - 80))
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(1100, 720)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.current_view = None
        self.current_user = None
        self.current_register = None
        self._busy = False
        self._session_closed = False
        self._z_print_warning = None
        self.report_callback_exception = self._on_tk_exception
        self.protocol("WM_DELETE_WINDOW", self.handle_window_close)

        self._startup_jobs = Jobs(self)
        self._startup = [
            ('auth_controller', AuthController, 'Preparando acceso…'),
            ('user_controller', UserController, 'Cargando usuarios…'),
            ('discount_controller', DiscountController, 'Cargando descuentos…'),
            ('cash_controller', CashController, 'Cargando cajas y turnos…'),
            ('product_controller', ProductController, 'Preparando catálogo…'),
            ('sales_controller', SalesController, 'Preparando ventas…'),
        ]
        self._show_startup()

    def _show_startup(self):
        self._busy = True
        splash = ctk.CTkFrame(self, fg_color='#F2F5FA', corner_radius=0)
        splash.grid_columnconfigure(0, weight=1)
        splash.grid_rowconfigure(0, weight=1)
        splash.grid_rowconfigure(2, weight=1)
        card = ctk.CTkFrame(splash, fg_color='#FFFFFF', corner_radius=20)
        card.grid(row=1, column=0, padx=30, pady=30)
        ctk.CTkLabel(card, text='SotyPOS', text_color='#0F766E',
                     font=ctk.CTkFont(size=36, weight='bold')).pack(padx=60, pady=(32, 8))
        ctk.CTkLabel(card, text='Preparando tu punto de venta', text_color='#64748B').pack(padx=40, pady=8)
        self._startup_activity = Activity(card)
        self._startup_activity.pack(fill='x', padx=30, pady=20)
        self._startup_error = ctk.CTkLabel(card, text='', wraplength=400, text_color='#B42318')
        self._startup_error.pack(padx=20)
        self._retry_startup = keyboard_button(ctk.CTkButton(card, text='Reintentar', command=lambda: self._start_stage(self._failed_stage)))
        self._replace_view(splash)
        self._startup_activity.start('Iniciando…')
        self._startup_jobs.later(80, lambda: self._start_stage(0))

    def _start_stage(self, index):
        self._busy = True
        self._retry_startup.pack_forget()
        self._startup_error.configure(text='')
        if index == len(self._startup):
            self._startup_activity.stop()
            self._busy = False
            self.show_login_view()
            return
        name, factory, caption = self._startup[index]
        self._startup_activity.start(caption)
        def initialize():
            try:
                setattr(self, name, factory())
            except Exception:
                log.exception('Error preparando %s', name)
                self._failed_stage = index
                self._busy = False
                self._startup_activity.stop()
                self._startup_error.configure(text='No se pudo preparar el sistema. Revisa la conexión y pos.log.')
                self._retry_startup.pack(pady=(8, 24))
                return
            self._startup_jobs.later(50, lambda: self._start_stage(index+1))
        self._startup_jobs.later(30, initialize)

    def _on_tk_exception(self, exc_type, exc, tb):
        if isinstance(exc, POSError):
            messagebox.showwarning("Aviso", str(exc), parent=self)
            return
        log.error("Error de interfaz", exc_info=(exc_type, exc, tb))
        messagebox.showerror(
            "Error", "Ocurrió un error inesperado. Revisa pos.log.", parent=self)

    def _replace_view(self, view):
        previous = self.current_view
        self.current_view = view
        if previous:
            previous.destroy()
        view.grid(row=0, column=0, sticky="nsew")

    def show_login_view(self):
        self.current_user = None
        self.current_register = None
        self._session_closed = False
        self._z_print_warning = None
        self.title("SotyPOS · Acceso")
        self._replace_view(LoginView(self, login_callback=self.handle_login))

    def _login_error(self, message):
        if isinstance(self.current_view, LoginView):
            self.current_view.show_error(message)

    def handle_login(self, username, pin):
        if self._busy:
            return None
        self._busy = True
        try:
            user = dict(self.auth_controller.login(username, pin))
            register_row = self.cash_controller.get_default_register()
            if register_row is None:
                raise BusinessRuleError("No hay una caja configurada para este equipo.")
            register = dict(register_row)
            
            # branch_id NULL = acceso a todas las sucursales
            if user.get("branch_id") not in (None, register["branch_id"]):
                raise BusinessRuleError("Tu usuario no pertenece a la sucursal de esta caja.")
                
            user["branch_id"] = register["branch_id"]     # sucursal de trabajo de este equipo
            user["register_id"] = register["id"]
            
            session = self.cash_controller.get_open_session(register["id"])
            if session is None:
                return self.prompt_open_session(user, register)
                
            user["session_id"] = session["id"]
            self.show_terminal_view(user, register)
            log.info("Turno %s recuperado por %s", session["id"], user["username"])
            return True
            
        except POSError as exc:
            self._login_error(str(exc))
        except Exception:
            log.exception("No se pudo iniciar sesión")
            self._login_error("No se pudo iniciar sesión. Revisa pos.log.")
        finally:
            self._busy = False
        # None permite conservar el mensaje específico en LoginView.
        return None

    def prompt_open_session(self, user, register):
        AuthController.require_permission(user, "cash.open")
        prompt = f"Bienvenido, {user['name']}\n\nIngresa el fondo inicial de caja ($):"
        while True:
            dialog = ctk.CTkInputDialog(text=prompt, title="Apertura de turno")
            dialog._initial_focus = getattr(dialog, '_entry', None)
            center_window(dialog, self, 480, 300)
            raw = dialog.get_input()
            if raw is None:
                self._login_error("Apertura cancelada. La caja sigue cerrada.")
                return None
            try:
                session_id = self.cash_controller.open_session(
                    register["branch_id"], register["id"], user["id"], raw)
            except ValidationError as exc:
                prompt = f"{exc}\n\nIngresa el fondo inicial de caja ($):"
                continue
            user["session_id"] = session_id
            self.show_terminal_view(user, register)
            return True

    def show_terminal_view(self, user_data, register):
        # 1. Mantenemos tus variables de estado originales intactas
        self.current_user = dict(user_data)
        self.current_register = dict(register)
        self._session_closed = False
        self._z_print_warning = None
        
        # 2. Limpiamos la pantalla de login
        if self.current_view:
            self.current_view.destroy()
            
        # 3. Llamamos al Dashboard y le pasamos 'self' (toda la app)
        from views.dashboard_view import DashboardView
        self.current_view = DashboardView(self, self.current_user, self)
        self.current_view.grid(row=0, column=0, sticky="nsew")

    def _require_user(self):
        if self.current_user is None:
            raise BusinessRuleError("Inicia sesión para continuar.")
        if self._session_closed:
            raise BusinessRuleError("El turno está cerrado. Inicia sesión y abre un nuevo turno.")
        return self.current_user

    def _require_open_turn(self):
        user = self._require_user()
        session = self.cash_controller.get_open_session(user["register_id"])
        if session is None or session["id"] != user["session_id"]:
            raise BusinessRuleError("Este turno ya no está abierto. Vuelve a iniciar sesión.")
        return user

    def handle_scan(self, code):
        user = self._require_user()
        product = self.product_controller.get_product_by_code(code, user["branch_id"])
        if product is None:
            self.bell()
            return False
        self.current_view.add_item_to_ui(product)
        return True

    def handle_search(self, query):
        user = self._require_user()
        return self.product_controller.search_products(query, user["branch_id"])

    def handle_stock_check(self, product, quantity):
        user = self._require_user()
        # Reconsultar existencias: el producto del ticket puede haberse quedado desactualizado.
        fresh = self.product_controller.get_product_by_code(product["sku"], user["branch_id"])
        if fresh is None or fresh["id"] != product["id"]:
            raise BusinessRuleError("El producto ya no está disponible. Actualiza el ticket.")
        self.product_controller.check_stock(fresh, quantity)

    def handle_checkout(self, payload):
        user = self._require_user()
        sale_payload = copy.deepcopy(payload)
        sale_payload["user_id"] = user["id"]
        # El controlador verifica el turno y reconoce reintentos ya registrados.
        # La vista conserva el ticket si se lanza una excepción.
        return self.sales_controller.create_sale(
            payload=sale_payload,
            branch_id=user["branch_id"],
            register_id=user["register_id"],
            session_id=user["session_id"],
            cashier_name=user["name"],
        )

    def handle_cash_management(self):
        """Compatibilidad con accesos externos: navegar, nunca abrir un modal."""
        if isinstance(self.current_view, TerminalView):
            self.current_view.select_tab("Caja y corte")

    def handle_cash_balance(self):
        user = self._require_open_turn()
        return self.cash_controller.get_balance(user["session_id"])

    def handle_cash_close(self, counted_cash, notes, expected_cash):
        """Retorna el resultado confirmado que espera CashCloseView."""
        user = self._require_open_turn()
        AuthController.require_permission(user, "cash.close")
        if self.current_view.ticket_rows:
            raise BusinessRuleError("Cobra o vacía el ticket pendiente antes de cerrar la caja.")
        if self._busy:
            raise BusinessRuleError("Hay otra operación en curso.")
        self._busy = True
        try:
            result = self.cash_controller.close_session(
                session_id=user["session_id"],
                user_id=user["id"],
                counted_cash=str(counted_cash),
                notes=notes,
                expected_cash=expected_cash,
            )
            # El cierre ya quedó guardado: una falla de impresión no debe revertir su estado.
            self._session_closed = True
            self._z_print_warning = None
            try:
                self._print_z_report(result)
            except Exception:
                log.exception("Corte guardado; no se pudo imprimir el reporte Z")
                self._z_print_warning = (
                    "El corte está guardado, pero no se pudo imprimir. "
                    "Revisa la impresora; no repitas el cierre."
                )
            return result
        finally:
            self._busy = False

    def _print_z_report(self, totals):
        # Importación diferida: una impresora no disponible no impide iniciar el sistema.
        from utils.printer import TicketPrinter

        row = self.sales_controller.cursor.execute(
            "SELECT setting_value FROM settings "
            "WHERE setting_key = 'business_name' AND deleted_at IS NULL"
        ).fetchone()
        business_name = row["setting_value"] if row else "SotyPOS"
        printed = TicketPrinter().print_z_report(
            business_name=business_name,
            register_name=self.current_register["name"],
            cashier_name=self.current_user["name"],
            totals=totals,
        )
        if printed is False:
            raise RuntimeError("La impresora reportó un fallo al imprimir el corte Z.")

    def handle_cash_closed(self, result):
        """TerminalView ya bloqueó ventas; conservar el resumen en la pestaña."""
        self._session_closed = True
        self.title(f"SotyPOS · {self.current_user['name']} · Turno cerrado")
        log.info("Turno %s cerrado. Diferencia: %s centavos",
                 self.current_user["session_id"], result["difference"])
        if self._z_print_warning:
            notice = self.current_view.cash_page.notice
            notice.configure(
                text=f"{notice.cget('text')}\n{self._z_print_warning}",
                text_color="#B42318",
                
            )

    def logout(self):
        # TerminalView confirma previamente si hay productos sin cobrar.
        if self._busy:
            return
        cash_page = getattr(self.current_view, "cash_page", None)
        if cash_page and not cash_page.closed and (
            any(var.get().strip() for var in cash_page.entries.values())
            or cash_page.txt_notes.get("1.0", "end-1c").strip()
        ):
            if not messagebox.askyesno(
                "Conteo pendiente", "¿Descartar el conteo sin guardar y cerrar sesión?",
                parent=self,
            ):
                return
        log.info("Logout: %s", self.current_user["username"] if self.current_user else "?")
        self.show_login_view()

    def handle_window_close(self):
        if self._busy or getattr(self.current_view, "_busy", False):
            return
        if getattr(self.current_view, "_dialog", None):
            return
        cash_page = getattr(self.current_view, "cash_page", None)
        if cash_page and cash_page._busy:
            return
        pending_ticket = bool(getattr(self.current_view, "ticket_rows", {}))
        pending_count = bool(cash_page and not cash_page.closed and (
            any(var.get().strip() for var in cash_page.entries.values())
            or cash_page.txt_notes.get("1.0", "end-1c").strip()
        ))
        if pending_ticket or pending_count:
            if not messagebox.askyesno(
                "Salir del sistema",
                "Hay un ticket o conteo sin guardar. ¿Descartarlo y salir?\n\n"
                "Cerrar la aplicación no realiza el corte de caja.", parent=self,
            ):
                return
        self.destroy()

    def destroy(self):
        if hasattr(self, '_startup_jobs'):
            self._startup_jobs.close()
        super().destroy()


if __name__ == "__main__":
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    app = SotyPOSApp()
    app.mainloop()