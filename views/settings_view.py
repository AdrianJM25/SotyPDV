"""Módulo de Configuración.

La pestaña «General» se dibuja automáticamente desde el registro SETTING_DEFS del controlador:
para agregar una configuración nueva solo hay que declararla allí.
"""
import logging
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from utils.exceptions import POSError, ValidationError

if __package__:
    from .icons import icon as get_icon
else:
    from icons import icon as get_icon

log = logging.getLogger(__name__)

# Colores de tu paleta
BG, WHITE, INK, MUTED = '#F5F9FC', '#FFFFFF', '#023047', '#5B7385'
SKY, BLUE_DARK = '#8ECAE6', '#1A7F99'
ORANGE, ORANGE_DARK = '#FB8500', '#E07600'
SOFT, SOFT_HOVER = '#EAF5FB', '#D5EBF6'
RED, RED_SOFT = '#B42318', '#FEF2F2'
BORDER = '#D7E6EF'


# --- Funciones de diseño locales para esta vista ---
def label(parent, text, size=14, bold=False, color=INK, **kw):
    return ctk.CTkLabel(parent, text=text, text_color=color,
                        font=ctk.CTkFont(size=size, weight='bold' if bold else 'normal'), **kw)


def card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=WHITE, corner_radius=14, border_width=1, border_color=BORDER, **kw)


def button(parent, text, command, primary=False, icon=None, **kw):
    kw.setdefault('height', 40)
    kw.setdefault('font', ctk.CTkFont(size=13, weight='bold'))
    if icon:
        try:
            kw['image'] = get_icon(icon, WHITE if primary else INK, 18)
            kw['compound'] = 'left'
        except Exception:      # un icono que no existe no debe romper la pantalla
            pass
    return ctk.CTkButton(parent, text=text, command=command, corner_radius=10,
                         fg_color=ORANGE if primary else SOFT,
                         hover_color=ORANGE_DARK if primary else SOFT_HOVER,
                         text_color=WHITE if primary else INK,
                         text_color_disabled='#A9BCC8', **kw)


def _resolve_user_id(app_controller, user_data):
    """Id del usuario activo para la bitácora (opcional: si no se encuentra, se guarda sin usuario)."""
    for source in (user_data, getattr(app_controller, 'current_user', None)):
        if source is None:
            continue
        try:
            data = source if isinstance(source, dict) else dict(source)
        except Exception:
            continue
        if data.get('id') or data.get('user_id'):
            return data.get('id') or data.get('user_id')
    return None


class SettingsView(ctk.CTkFrame):
    TABS = ["General", "Sucursales", "Cajas y Terminales", "Roles y Permisos"]

    def __init__(self, master, app_controller, user_data=None):
        super().__init__(master, fg_color=BG)
        self.app_controller, self.user_data = app_controller, user_data
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.panel = None
        self.current_tab = "General"

        self._build_header()
        self.content = ctk.CTkFrame(self, fg_color='transparent')
        self.content.grid(row=1, column=0, sticky='nsew', padx=24, pady=(20, 24))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        # El controlador se crea aquí; si falla, se MUESTRA el motivo (no se oculta).
        try:
            from controllers.settings_controller import SettingsController
            self.ctrl = getattr(app_controller, 'settings_controller', None) or SettingsController()
            self.ctrl.ensure_defaults()
        except Exception as exc:
            log.exception('No se pudo iniciar el módulo de configuración')
            self.ctrl = None
            self._show_fatal(exc)
            return
        self._show_tab("General")

    # ------------------------------------------------------------------ estructura
    def _build_header(self):
        head = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=0, height=70)
        head.grid(row=0, column=0, sticky='ew')
        head.grid_propagate(False)
        label(head, 'Configuración del Sistema', 22, True).pack(side='left', padx=24)
        self.active_tab = ctk.StringVar(value="General")
        self.tabs = ctk.CTkSegmentedButton(
            head, values=self.TABS, variable=self.active_tab, command=self._on_tab,
            selected_color=SKY, selected_hover_color=SKY, unselected_color=BG, unselected_hover_color=SOFT_HOVER,
            text_color=INK, font=ctk.CTkFont(size=13, weight='bold'))
        self.tabs.pack(side='right', padx=24, pady=18)

    def _clear(self):
        for widget in self.content.winfo_children():
            widget.destroy()
        self.panel = None

    def _show_fatal(self, exc):
        self._clear()
        box = card(self.content)
        box.grid(row=0, column=0, sticky='nsew')
        label(box, 'No se pudo cargar la configuración', 18, True, RED).pack(pady=(60, 8))
        label(box, str(exc) or exc.__class__.__name__, 13, False, MUTED, wraplength=640, justify='center').pack()
        label(box, 'Revisa pos.log para ver el detalle técnico.', 12, False, MUTED).pack(pady=8)

    def _on_tab(self, name):
        """Cambia de pestaña; si hay cambios sin guardar pide confirmación y, si se cancela, regresa a la anterior."""
        if name == self.current_tab:
            return
        if self.panel is not None and self.panel.is_dirty() and not messagebox.askyesno(
                'Cambios sin guardar', 'Hay cambios sin guardar en la configuración.\n¿Descartarlos y cambiar de pestaña?',
                parent=self.winfo_toplevel()):
            self.active_tab.set(self.current_tab)
            return
        self._show_tab(name)

    def _show_tab(self, name):
        self._clear()
        self.current_tab = name
        self.active_tab.set(name)
        if name == "General":
            self.panel = GeneralSettingsPanel(self.content, self.ctrl, _resolve_user_id(self.app_controller, self.user_data))
            self.panel.grid(row=0, column=0, sticky='nsew')
        elif name == "Sucursales":
            from controllers.branches_controller import BranchesController
            from views.branches_view import BranchesPanel
            ctrl = getattr(self.app_controller, 'branches_controller', None)
            try:
                ctrl = ctrl or BranchesController()
            except Exception as exc:
                log.exception('No se pudo iniciar Sucursales')
                self._show_fatal(exc)
                return
            self.panel = BranchesPanel(self.content, ctrl, _resolve_user_id(self.app_controller, self.user_data))
            self.panel.grid(row=0, column=0, sticky='nsew')
        else:
            box = card(self.content)
            box.grid(row=0, column=0, sticky='nsew')
            label(box, f'«{name}» está en construcción.', 16, False, MUTED).place(relx=.5, rely=.5, anchor='center')

    def has_unsaved_changes(self):
        return self.panel is not None and self.panel.is_dirty()


class GeneralSettingsPanel(ctk.CTkFrame):
    """Formulario generado desde SETTING_DEFS, con errores por campo y detección de cambios."""

    def __init__(self, master, ctrl, user_id=None):
        super().__init__(master, fg_color='transparent')
        self.ctrl, self.user_id = ctrl, user_id
        self.defs = {}               # clave -> SettingDef
        self.vars = {}               # clave -> StringVar / BooleanVar
        self.error_labels = {}       # clave -> CTkLabel
        self.inputs = {}             # clave -> widget (para dar foco)
        self.baseline = {}
        self._loading = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_body()
        self._build_footer()
        self.load()

    # ------------------------------------------------------------------ construcción
    def _build_body(self):
        body = ctk.CTkScrollableFrame(self, fg_color='transparent')
        body.grid(row=0, column=0, sticky='nsew')
        body.grid_columnconfigure(0, weight=1)
        for row, (gid, title, desc, defs) in enumerate(self.ctrl.definitions()):
            section = card(body)
            section.grid(row=row, column=0, sticky='ew', pady=(0, 14), padx=(0, 6))
            label(section, title, 18, True).pack(anchor='w', padx=28, pady=(22, 0))
            label(section, desc, 12, False, MUTED).pack(anchor='w', padx=28, pady=(0, 6))
            for d in defs:
                self._build_field(section, d)
            ctk.CTkFrame(section, fg_color='transparent', height=10).pack()

    def _build_field(self, parent, d):
        self.defs[d.key] = d
        box = ctk.CTkFrame(parent, fg_color='transparent')
        box.pack(fill='x', padx=28, pady=(8, 0))

        if d.type == 'boolean':
            var = ctk.BooleanVar()
            widget = ctk.CTkSwitch(box, text=d.label, variable=var, progress_color=BLUE_DARK, text_color=INK,
                                   font=ctk.CTkFont(size=13, weight='bold'))
            widget.pack(anchor='w')
            var.trace_add('write', lambda *a: self._on_change())
        else:
            label(box, d.label, 12, True, MUTED).pack(anchor='w', pady=(0, 3))
            var = ctk.StringVar()
            if d.choices:
                widget = ctk.CTkOptionMenu(box, variable=var, values=[str(c) for c in d.choices], width=160, height=36,
                                           fg_color=WHITE, button_color=SKY, button_hover_color=BLUE_DARK,
                                           text_color=INK, dropdown_text_color=INK, command=lambda _v: self._on_change())
            else:
                width = 420 if d.type == 'string' and d.max_len > 20 else 160
                widget = ctk.CTkEntry(box, textvariable=var, width=width, height=36, fg_color=WHITE,
                                      border_color=SKY, text_color=INK)
                var.trace_add('write', lambda *a: self._on_change())
            widget.pack(anchor='w')
        if d.description:
            label(box, d.description, 11, False, MUTED, wraplength=620, justify='left').pack(anchor='w', pady=(2, 0))
        err = label(box, '', 11, False, RED, wraplength=620, justify='left')   # se muestra solo si hay error
        self.vars[d.key], self.inputs[d.key], self.error_labels[d.key] = var, widget, err

    def _build_footer(self):
        bar = card(self)
        bar.grid(row=1, column=0, sticky='ew', pady=(12, 0))
        self.status = label(bar, '', 12, False, MUTED)
        self.status.pack(side='left', padx=24, pady=14)
        self.btn_save = button(bar, 'Guardar cambios', self.save, primary=True, icon='check', width=170)
        self.btn_save.pack(side='right', padx=(8, 20), pady=12)
        self.btn_discard = button(bar, 'Descartar', self.load, width=110)
        self.btn_discard.pack(side='right', pady=12)

    # ------------------------------------------------------------------ datos
    def _current(self):
        """Valores crudos del formulario (strings, y bool para los interruptores)."""
        return {k: v.get() for k, v in self.vars.items()}

    def load(self):
        """Carga los valores guardados (o los de por defecto) y deja el formulario sin cambios."""
        try:
            values = self.ctrl.get_all()
        except Exception as exc:
            log.exception('Error leyendo configuración')
            messagebox.showerror('Configuración', f'No se pudo leer la configuración.\n\n{exc}', parent=self.winfo_toplevel())
            return
        self._loading = True
        try:
            for key, var in self.vars.items():
                value = values.get(key)
                var.set(bool(value) if isinstance(var, ctk.BooleanVar) else ('' if value is None else str(value)))
                self._set_error(key, '')
        finally:
            self._loading = False
        self.baseline = self._current()
        self._set_status('', MUTED)
        self._sync_buttons()

    def is_dirty(self):
        return self._current() != self.baseline

    def _on_change(self):
        if self._loading:
            return
        self._sync_buttons()
        if self.is_dirty():
            self._set_status('● Cambios sin guardar', ORANGE_DARK)
        else:
            self._set_status('', MUTED)

    def _sync_buttons(self):
        state = 'normal' if self.is_dirty() else 'disabled'
        self.btn_save.configure(state=state)
        self.btn_discard.configure(state=state)

    def _set_status(self, text, color):
        self.status.configure(text=text, text_color=color)

    def _set_error(self, key, message):
        err = self.error_labels[key]
        err.configure(text=message)
        if message:
            err.pack(anchor='w')
        else:
            err.pack_forget()
        widget = self.inputs[key]
        if isinstance(widget, ctk.CTkEntry):
            widget.configure(border_color=RED if message else SKY, fg_color=RED_SOFT if message else WHITE)

    # ------------------------------------------------------------------ guardar
    def save(self):
        if not self.is_dirty():
            return
        values = self._current()
        _clean, errors = self.ctrl.validate(values)          # errores por campo, sin tocar la BD
        for key in self.vars:
            self._set_error(key, errors.get(key, ''))
        if errors:
            first = next(k for k in self.vars if k in errors)
            try:
                self.inputs[first].focus_set()
            except Exception:
                pass
            self._set_status(f'Corrige {len(errors)} campo(s) marcados en rojo.', RED)
            return
        try:
            changed = self.ctrl.save_many(values, user_id=self.user_id)
        except (ValidationError, POSError) as exc:
            messagebox.showerror('Configuración', str(exc), parent=self.winfo_toplevel())
            return
        except Exception:
            log.exception('Error inesperado guardando configuración')
            messagebox.showerror('Configuración', 'Ocurrió un error inesperado. No se guardó ningún cambio.',
                                 parent=self.winfo_toplevel())
            return
        self.load()           # re-lee: muestra los valores ya normalizados (espacios, mayúsculas...)
        self._set_status(f'✓ Guardado a las {datetime.now():%H:%M}' if changed else 'Sin cambios.', BLUE_DARK)