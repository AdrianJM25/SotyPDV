import logging
import customtkinter as ctk
if __package__:
    from .ui_helpers import Jobs, Activity, keyboard_button
else:
    from ui_helpers import Jobs, Activity, keyboard_button

log = logging.getLogger(__name__)

HINT = 'Usuario y PIN de 4 a 8 dígitos · Enter para ingresar'


class LoginView(ctk.CTkFrame):
    def __init__(self, master, login_callback):
        super().__init__(master, fg_color='#F2F5FA')
        self.jobs = Jobs(self)
        self.key_buttons = []
        self.login_callback = login_callback
        self.user_var = ctk.StringVar(value='')
        self.pin_var = ctk.StringVar(value='')
        self._busy = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_ui()
        self._focus_job = self.jobs.later(100, self.entry_user.focus_set)
        self.user_var.trace_add('write', lambda *a: self._on_input_change())
        self.pin_var.trace_add('write', lambda *a: self._on_input_change())
        self._sync_login()

    def _build_ui(self):
        card = ctk.CTkFrame(self, fg_color='#FFFFFF', corner_radius=24,
                            border_width=2, border_color='#E1E7EF')
        card.grid(row=0, column=0, padx=20, pady=16)
        card.grid_columnconfigure((0, 1, 2), weight=1)

        # ESPACIO PARA LOGOTIPO (puedes reemplazar el texto con un ctk.CTkImage)
        self.lbl_logo = ctk.CTkLabel(card, text='POS', font=ctk.CTkFont(size=40))
        self.lbl_logo.grid(row=0, column=0, columnspan=3, pady=(14, 0))

        ctk.CTkLabel(card, text='SotyPOS', text_color='#0F766E',
                     font=ctk.CTkFont(size=30, weight='bold')).grid(
                         row=1, column=0, columnspan=3, pady=(2, 0))

        ctk.CTkLabel(card, text='Ingresa tu usuario y PIN', text_color='#64748B',
                     font=ctk.CTkFont(size=14)).grid(row=2, column=0, columnspan=3, pady=(0, 12))

        # Campo de usuario
        validate_user = (self.register(lambda v: len(v) <= 32 and ' ' not in v), '%P')
        self.entry_user = ctk.CTkEntry(
            card, textvariable=self.user_var, placeholder_text='Usuario',
            justify='center', height=48, width=320, fg_color='#F8FAFC',
            border_color='#CBD5E1', border_width=2, text_color='#142338',
            font=ctk.CTkFont(size=20), validate='key', validatecommand=validate_user)
        self.entry_user.grid(row=3, column=0, columnspan=3, padx=30, pady=(0, 8), sticky='ew')
        self.entry_user.bind('<Return>', lambda e: self._focus_pin())

        # Campo de PIN
        validate_pin = (self.register(lambda v: not v or (v.isascii() and v.isdigit() and len(v) <= 8)), '%P')
        self.entry_pin = ctk.CTkEntry(
            card, textvariable=self.pin_var, show='●', placeholder_text='PIN',
            justify='center', height=56, width=320, fg_color='#F8FAFC',
            border_color='#CBD5E1', border_width=2, text_color='#142338',
            font=ctk.CTkFont(size=30, weight='bold'), validate='key', validatecommand=validate_pin)
        self.entry_pin.grid(row=4, column=0, columnspan=3, padx=30, sticky='ew')
        self.entry_pin.bind('<Return>', lambda e: self._submit())
        self.entry_pin.bind('<Escape>', lambda e: self.pin_var.set(''))

        # Etiqueta de error reservada (no mueve la interfaz al aparecer)
        self.lbl_error = ctk.CTkLabel(card, text='', text_color='#B42318',
                                      font=ctk.CTkFont(size=13), height=40, wraplength=320)
        self.lbl_error.grid(row=5, column=0, columnspan=3, pady=(4, 4))

        # Teclado numérico (escribe solo en el PIN)
        for i, key in enumerate(('1', '2', '3', '4', '5', '6', '7', '8', '9', 'Limpiar', '0', '⌫')):
            special = key in ('Limpiar', '⌫')
            btn = keyboard_button(ctk.CTkButton(
                card, text=key, width=96, height=46, corner_radius=12,
                fg_color='#FDE8E8' if special else '#EDF2F7',
                hover_color='#FBD5D5' if special else '#DBE5EF',
                text_color='#B42318' if special else '#142338',
                font=ctk.CTkFont(size=22 if len(key) == 1 else 14, weight='bold'),
                command=lambda k=key: self._btn_click(k)))
            self.key_buttons.append(btn)
            btn.grid(row=6 + i // 3, column=i % 3, padx=8, pady=4)

        self.btn_login = ctk.CTkButton(
            card, text='Ingresar', height=48, corner_radius=12,
            fg_color='#0F766E', hover_color='#115E59',
            font=ctk.CTkFont(size=18, weight='bold'), command=self._submit)
        keyboard_button(self.btn_login)
        self.btn_login.grid(row=10, column=0, columnspan=3, padx=30, pady=(12, 6), sticky='ew')

        self.activity = Activity(card)
        self.activity.grid(row=11, column=0, columnspan=3, padx=30, pady=(0, 12), sticky='ew')
        self.activity.stop(HINT)

    # ------------------------------------------------------------------ helpers
    def _username(self) -> str:
        return self.user_var.get().strip()

    def _pin_valid(self) -> bool:
        pin = self.pin_var.get()
        return pin.isascii() and pin.isdigit() and 4 <= len(pin) <= 8

    def _focus_pin(self):
        self.entry_pin.focus_set()

    def _on_input_change(self):
        self._sync_login()

    def _sync_login(self):
        ok = bool(self._username()) and self._pin_valid() and not self._busy
        self.btn_login.configure(state='normal' if ok else 'disabled')

    # ------------------------------------------------------------------ errores
    def show_error(self, message):
        """Muestra el error, marca los campos en rojo y limpia el PIN (el usuario se conserva)."""
        self.lbl_error.configure(text=str(message))
        if message:
            self.entry_pin.configure(border_color='#B42318', fg_color='#FEF2F2')
            self.pin_var.set('')

    def _clear_error_visuals(self):
        if self.winfo_exists():
            self.lbl_error.configure(text='')
            for e in (self.entry_user, self.entry_pin):
                e.configure(border_color='#CBD5E1', fg_color='#F8FAFC')

    # ------------------------------------------------------------------ teclado en pantalla
    def _btn_click(self, valor):
        if self._busy:
            return
        self._clear_error_visuals()
        if valor == 'Limpiar':
            self.pin_var.set('')
        elif valor == '⌫':
            self.pin_var.set(self.pin_var.get()[:-1])
        elif valor.isascii() and valor.isdigit() and len(self.pin_var.get()) < 8:
            self.pin_var.set(self.pin_var.get() + valor)
        self.entry_pin.focus_set()

    # ------------------------------------------------------------------ envío
    def _submit(self):
        if self._busy:
            return
        username, pin = self._username(), self.pin_var.get()
        if not username:
            self.show_error('Escribe tu usuario.')
            self.entry_user.focus_set()
            return
        if not self._pin_valid():
            self.show_error('Escribe un PIN de 4 a 8 dígitos.')
            self.entry_pin.focus_set()
            return
        self._busy = True
        self._clear_error_visuals()
        self._sync_login()
        self.entry_user.configure(state='disabled')
        self.entry_pin.configure(state='disabled')
        for btn in self.key_buttons:
            btn.configure(state='disabled')
        self.btn_login.configure(text='Validando…')
        self.activity.start('Validando acceso…')
        self.jobs.later(70, lambda: self._authenticate(username, pin))

    def _authenticate(self, username, pin):
        try:
            result = self.login_callback(username, pin)
            if result is False and self.winfo_exists():
                self.show_error('Usuario o PIN incorrectos.')
        except Exception as exc:
            if self.winfo_exists():
                if type(exc).__module__.startswith('utils.exceptions'):
                    self.show_error(str(exc))
                else:
                    log.exception('Error de acceso')
                    self.show_error('No se pudo iniciar sesión. Intenta nuevamente.')
        finally:
            self._busy = False
            if self.winfo_exists():
                self.activity.stop(HINT)
                self.entry_user.configure(state='normal')
                self.entry_pin.configure(state='normal')
                for btn in self.key_buttons:
                    btn.configure(state='normal')
                self.pin_var.set('')
                self.btn_login.configure(text='Ingresar')
                self._sync_login()
                # Si el usuario sigue escrito, el foco vuelve al PIN; si no, al usuario
                (self.entry_pin if self._username() else self.entry_user).focus_set()

    def destroy(self):
        self.jobs.close()
        super().destroy()