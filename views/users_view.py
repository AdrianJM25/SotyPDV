import logging
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from controllers.auth_controller import AuthController
from utils.exceptions import POSError
from views.ui_helpers import center_window

log = logging.getLogger(__name__)

BG, CARD, TEAL, TEAL_H = '#F2F5FA', '#FFFFFF', '#0F766E', '#115E59'
TEXT, MUTED, RED, GREEN, BORDER = '#142338', '#64748B', '#B42318', '#15803D', '#E1E7EF'
ALL_BRANCHES = 'Todas las sucursales'
COLS = (('Usuario', 2), ('Nombre', 3), ('Rol', 2), ('Sucursal', 2), ('Estado', 2), ('Último acceso', 2))
ACTIONS_W = 330


def _fmt_date(iso):
    if not iso:
        return 'Nunca'
    try:
        return datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone().strftime('%d/%m/%Y %H:%M')
    except ValueError:
        return iso


def _error_text(exc):
    if isinstance(exc, POSError):
        return str(exc)
    log.exception('Error en módulo de usuarios')
    return 'Ocurrió un error inesperado. Revisa pos.log.'


# ====================================================================== diálogos
class _Modal(ctk.CTkToplevel):
    def __init__(self, parent, title, width, height):
        super().__init__(parent)
        self.title(title)
        self.configure(fg_color=CARD)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        center_window(self, parent.winfo_toplevel(), width, height)
        self.after(150, self._grab)
        self.bind('<Escape>', lambda e: self.destroy())
        self.lbl_error = None

    def _grab(self):
        if self.winfo_exists():
            self.grab_set()
            self.focus_force()

    def _error_label(self, row):
        self.lbl_error = ctk.CTkLabel(self, text='', text_color=RED, wraplength=380,
                                      font=ctk.CTkFont(size=13), height=36)
        self.lbl_error.grid(row=row, column=0, columnspan=2, padx=24, pady=(4, 0))

    def _field(self, row, label, show=None, placeholder=''):
        ctk.CTkLabel(self, text=label, text_color=MUTED, anchor='w').grid(
            row=row, column=0, padx=(24, 8), pady=6, sticky='w')
        entry = ctk.CTkEntry(self, width=260, height=36, show=show, placeholder_text=placeholder,
                             fg_color='#F8FAFC', border_color='#CBD5E1', text_color=TEXT)
        entry.grid(row=row, column=1, padx=(0, 24), pady=6, sticky='e')
        return entry

    def _buttons(self, row, text, command):
        frame = ctk.CTkFrame(self, fg_color='transparent')
        frame.grid(row=row, column=0, columnspan=2, padx=24, pady=(8, 20), sticky='e')
        ctk.CTkButton(frame, text='Cancelar', width=110, fg_color='#EDF2F7', hover_color='#DBE5EF',
                      text_color=TEXT, command=self.destroy).pack(side='left', padx=6)
        self.btn_ok = ctk.CTkButton(frame, text=text, width=130, fg_color=TEAL, hover_color=TEAL_H,
                                    command=command)
        self.btn_ok.pack(side='left', padx=6)

    def _show_error(self, message):
        self.lbl_error.configure(text=message)


class UserForm(_Modal):
    """Alta (user=None) o edición de un usuario."""

    def __init__(self, parent, controller, current_user, roles, branches, on_saved, user=None):
        editing = user is not None
        super().__init__(parent, 'Editar usuario' if editing else 'Nuevo usuario', 480, 620 if not editing else 560)
        self.controller, self.current_user, self.on_saved, self.user = controller, current_user, on_saved, user
        self.roles = {r['name']: r['id'] for r in roles}
        self.branches = {b['name']: b['id'] for b in branches}

        self.e_username = self._field(0, 'Usuario *', placeholder='sin espacios')
        self.e_name = self._field(1, 'Nombre completo *')

        ctk.CTkLabel(self, text='Rol *', text_color=MUTED).grid(row=2, column=0, padx=(24, 8), pady=6, sticky='w')
        self.opt_role = ctk.CTkOptionMenu(self, values=list(self.roles) or [''], width=260, height=36,
                                          fg_color=TEAL, button_color=TEAL_H)
        self.opt_role.grid(row=2, column=1, padx=(0, 24), pady=6, sticky='e')

        ctk.CTkLabel(self, text='Sucursal', text_color=MUTED).grid(row=3, column=0, padx=(24, 8), pady=6, sticky='w')
        self.opt_branch = ctk.CTkOptionMenu(self, values=[ALL_BRANCHES, *self.branches], width=260, height=36,
                                            fg_color=TEAL, button_color=TEAL_H)
        self.opt_branch.grid(row=3, column=1, padx=(0, 24), pady=6, sticky='e')

        self.e_email = self._field(4, 'Correo')
        self.e_phone = self._field(5, 'Teléfono')

        self.e_pin = self.e_pin2 = None
        if not editing:
            self.e_pin = self._field(6, 'PIN * (4-8 dígitos)', show='●')
            self.e_pin2 = self._field(7, 'Confirmar PIN *', show='●')
            row = 8
        else:
            self.var_active = ctk.BooleanVar(value=bool(user['is_active']))
            ctk.CTkSwitch(self, text='Usuario activo', variable=self.var_active,
                          progress_color=TEAL).grid(row=6, column=0, columnspan=2, padx=24, pady=8, sticky='w')
            row = 7
            self.e_username.insert(0, user['username'])
            self.e_username.configure(state='disabled')
            self.e_name.insert(0, user['full_name'])
            self.opt_role.set(user['role_name'])
            self.opt_branch.set(user['branch_name'] or ALL_BRANCHES)
            self.e_email.insert(0, user['email'] or '')
            self.e_phone.insert(0, user['phone'] or '')

        self._error_label(row)
        self._buttons(row + 1, 'Guardar', self._save)
        self.bind('<Return>', lambda e: self._save())
        self.after(200, (self.e_name if editing else self.e_username).focus_set)

    def _save(self):
        name, role_name = self.e_name.get().strip(), self.opt_role.get()
        branch_name = self.opt_branch.get()
        branch_id = None if branch_name == ALL_BRANCHES else self.branches.get(branch_name)
        role_id = self.roles.get(role_name)
        email, phone = self.e_email.get().strip(), self.e_phone.get().strip()
        try:
            if self.user is None:
                username = self.e_username.get().strip()
                if ' ' in username:
                    raise POSError('El usuario no puede contener espacios.')
                if self.e_pin.get() != self.e_pin2.get():
                    raise POSError('Los PIN no coinciden.')
                self.controller.create_user(
                    self.current_user, username=username, full_name=name, role_id=role_id,
                    pin=self.e_pin.get(), branch_id=branch_id, email=email, phone=phone)
            else:
                if not name:
                    raise POSError('El nombre completo es obligatorio.')
                self.controller.update_user(
                    self.current_user, self.user['id'], full_name=name, role_id=role_id,
                    branch_id=branch_id, email=email, phone=phone,
                    is_active=1 if self.var_active.get() else 0)
        except Exception as exc:
            self._show_error(_error_text(exc))
            return
        self.on_saved()
        self.destroy()


class PinDialog(_Modal):
    def __init__(self, parent, controller, current_user, user, on_saved):
        super().__init__(parent, 'Restablecer PIN', 460, 330)
        self.controller, self.current_user, self.user, self.on_saved = controller, current_user, user, on_saved
        ctk.CTkLabel(self, text=f"Nuevo PIN para {user['full_name']} ({user['username']})",
                     text_color=TEXT, font=ctk.CTkFont(size=14, weight='bold'),
                     wraplength=400).grid(row=0, column=0, columnspan=2, padx=24, pady=(20, 8))
        self.e_pin = self._field(1, 'Nuevo PIN', show='●', placeholder='4-8 dígitos')
        self.e_pin2 = self._field(2, 'Confirmar PIN', show='●')
        self._error_label(3)
        self._buttons(4, 'Cambiar PIN', self._save)
        self.bind('<Return>', lambda e: self._save())
        self.after(200, self.e_pin.focus_set)

    def _save(self):
        try:
            if self.e_pin.get() != self.e_pin2.get():
                raise POSError('Los PIN no coinciden.')
            self.controller.reset_pin(self.current_user, self.user['id'], self.e_pin.get())
        except Exception as exc:
            self._show_error(_error_text(exc))
            return
        self.on_saved()
        self.destroy()


# ====================================================================== vista principal
class UsersView(ctk.CTkFrame):
    def __init__(self, master, app_controller):
        super().__init__(master, fg_color=BG)
        self.controller = app_controller.user_controller
        self.current_user = app_controller.current_user
        self.users = []
        self.roles, self.branches = [], []
        self.search_var = ctk.StringVar()
        self.inactive_var = ctk.BooleanVar(value=True)

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

    # ------------------------------------------------------------ construcción
    def _build_header(self):
        bar = ctk.CTkFrame(self, fg_color='transparent')
        bar.grid(row=0, column=0, padx=24, pady=(20, 10), sticky='ew')
        bar.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(bar, text='Gestión de usuarios', text_color=TEAL,
                     font=ctk.CTkFont(size=26, weight='bold')).grid(row=0, column=0, sticky='w')
        ctk.CTkEntry(bar, textvariable=self.search_var, placeholder_text='Buscar usuario, nombre o rol…',
                     width=280, height=38, fg_color=CARD).grid(row=0, column=2, padx=10)
        ctk.CTkSwitch(bar, text='Mostrar inactivos', variable=self.inactive_var, progress_color=TEAL,
                      command=self._render).grid(row=0, column=3, padx=10)
        ctk.CTkButton(bar, text='+ Nuevo usuario', height=38, fg_color=TEAL, hover_color=TEAL_H,
                      font=ctk.CTkFont(weight='bold'), command=self._new).grid(row=0, column=4, padx=(10, 0))

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

    # ------------------------------------------------------------ datos
    def reload(self):
        try:
            self.users = [dict(u) for u in self.controller.list_users(self.current_user)]
            self.roles = self.controller.list_roles(self.current_user)
            self.branches = self.controller.list_branches(self.current_user)
        except Exception as exc:
            messagebox.showwarning('Usuarios', _error_text(exc), parent=self)
            self.users = []
        self._render()

    def _visible_users(self):
        q = self.search_var.get().strip().lower()
        result = []
        for u in self.users:
            if not self.inactive_var.get() and not u['is_active']:
                continue
            haystack = f"{u['username']} {u['full_name']} {u['role_name']}".lower()
            if q and q not in haystack:
                continue
            result.append(u)
        return result

    def _render(self):
        for child in self.scroll.winfo_children():
            child.destroy()
        visible = self._visible_users()
        if not visible:
            ctk.CTkLabel(self.scroll, text='No hay usuarios que mostrar.', text_color=MUTED).grid(pady=30)
        for i, u in enumerate(visible):
            self._build_row(i, u)
        self.lbl_status.configure(text=f'{len(visible)} de {len(self.users)} usuarios')

    def _build_row(self, index, u):
        locked = AuthController._is_future(u['pin_locked_until'])
        is_me = u['id'] == self.current_user['id']
        row = ctk.CTkFrame(self.scroll, fg_color='#F8FAFC' if index % 2 == 0 else CARD, corner_radius=8)
        row.grid(row=index, column=0, sticky='ew', pady=1, padx=2)
        self._configure_cols(row)

        if locked:
            status, color = 'Bloqueado', RED
        elif u['is_active']:
            status, color = 'Activo', GREEN
        else:
            status, color = 'Inactivo', MUTED

        values = (u['username'] + ('  (tú)' if is_me else ''), u['full_name'], u['role_name'],
                  u['branch_name'] or ALL_BRANCHES, status, _fmt_date(u['last_login_at']))
        for c, val in enumerate(values):
            ctk.CTkLabel(row, text=val, anchor='w', justify='left', wraplength=170,
                         text_color=color if c == 4 else TEXT,
                         font=ctk.CTkFont(size=13, weight='bold' if c in (0, 4) else 'normal')
                         ).grid(row=0, column=c, sticky='w', padx=6, pady=10)

        actions = ctk.CTkFrame(row, fg_color='transparent')
        actions.grid(row=0, column=len(COLS), sticky='e', padx=6)
        self._action(actions, 'Editar', TEAL, TEAL_H, 'white', lambda: self._edit(u))
        self._action(actions, 'PIN', '#EDF2F7', '#DBE5EF', TEXT, lambda: self._pin(u))
        if locked:
            self._action(actions, 'Desbloquear', '#FEF3C7', '#FDE68A', '#92400E', lambda: self._unlock(u))
        if not is_me:
            self._action(actions, 'Eliminar', '#FDE8E8', '#FBD5D5', RED, lambda: self._delete(u))

    @staticmethod
    def _action(parent, text, fg, hover, txt, command):
        ctk.CTkButton(parent, text=text, width=70 if text != 'Desbloquear' else 96, height=30,
                      corner_radius=8, fg_color=fg, hover_color=hover, text_color=txt,
                      font=ctk.CTkFont(size=12, weight='bold'), command=command).pack(side='left', padx=3)

    # ------------------------------------------------------------ acciones
    def _new(self):
        UserForm(self, self.controller, self.current_user, self.roles, self.branches, self.reload)

    def _edit(self, u):
        UserForm(self, self.controller, self.current_user, self.roles, self.branches, self.reload, user=u)

    def _pin(self, u):
        PinDialog(self, self.controller, self.current_user, u, self.reload)

    def _run(self, fn, *args):
        try:
            fn(self.current_user, *args)
        except Exception as exc:
            messagebox.showwarning('Usuarios', _error_text(exc), parent=self)
        self.reload()

    def _unlock(self, u):
        self._run(self.controller.unlock_user, u['id'])

    def _delete(self, u):
        if messagebox.askyesno(
                'Eliminar usuario',
                f"¿Eliminar a {u['full_name']} ({u['username']})?\n\n"
                "Ya no podrá iniciar sesión. Sus ventas y cortes anteriores se conservan.",
                parent=self):
            self._run(self.controller.delete_user, u['id'])