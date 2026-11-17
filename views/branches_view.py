"""Pestaña «Sucursales» de Configuración: lista, alta/edición, desactivar y eliminar."""
import logging
from tkinter import ttk, messagebox

import customtkinter as ctk

from utils.exceptions import BusinessRuleError, POSError, ValidationError

if __package__:
    from .ui_helpers import center_window, keyboard_button, Jobs
else:
    from ui_helpers import center_window, keyboard_button, Jobs

log = logging.getLogger(__name__)

# Colores de tu paleta
BG, WHITE, INK, MUTED = '#F5F9FC', '#FFFFFF', '#023047', '#5B7385'
SKY, BLUE_DARK = '#8ECAE6', '#1A7F99'
ORANGE, ORANGE_DARK = '#FB8500', '#E07600'
SOFT, SOFT_HOVER = '#EAF5FB', '#D5EBF6'
RED, RED_HOVER, RED_SOFT = '#E63946', '#D62828', '#FEF2F2'
ERR = '#B42318'
BORDER = '#D7E6EF'


def label(parent, text, size=14, bold=False, color=INK, **kw):
    return ctk.CTkLabel(parent, text=text, text_color=color,
                        font=ctk.CTkFont(size=size, weight='bold' if bold else 'normal'), **kw)


def card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=WHITE, corner_radius=14, border_width=1, border_color=BORDER, **kw)


def button(parent, text, command, primary=False, danger=False, **kw):
    kw.setdefault('height', 38)
    kw.setdefault('font', ctk.CTkFont(size=13, weight='bold'))
    if danger:
        fg, hover, color = RED_SOFT, '#FBD5D5', ERR
    elif primary:
        fg, hover, color = ORANGE, ORANGE_DARK, WHITE
    else:
        fg, hover, color = SOFT, SOFT_HOVER, INK
    return ctk.CTkButton(parent, text=text, command=command, corner_radius=10, fg_color=fg, hover_color=hover,
                         text_color=color, text_color_disabled='#A9BCC8', **kw)


def guarded(parent, action):
    """Ejecuta action(); los errores de negocio salen como aviso. Devuelve (ok, resultado)."""
    try:
        return True, action()
    except (ValidationError, BusinessRuleError) as exc:
        messagebox.showwarning('Sucursales', str(exc), parent=parent)
    except POSError as exc:
        messagebox.showerror('Sucursales', str(exc), parent=parent)
    except Exception:
        log.exception('Error inesperado en Sucursales')
        messagebox.showerror('Sucursales', 'Ocurrió un error inesperado. Revisa pos.log.', parent=parent)
    return False, None


class BranchesPanel(ctk.CTkFrame):
    STYLE = 'Soty.Treeview'

    def __init__(self, master, ctrl, user_id=None):
        super().__init__(master, fg_color='transparent')
        self.ctrl, self.user_id = ctrl, user_id
        self.jobs, self._search_job, self._rows = Jobs(self), None, {}
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_toolbar()
        self._build_table()
        self.refresh()

    def is_dirty(self):          # esta pestaña guarda en ventanas modales: nunca hay cambios pendientes
        return False

    # ------------------------------------------------------------------ construcción
    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color='transparent')
        bar.grid(row=0, column=0, sticky='ew', pady=(0, 12))
        self.search = ctk.CTkEntry(bar, width=320, height=38, fg_color=WHITE, border_color=SKY, text_color=INK,
                                   placeholder_text='Buscar por código, nombre o ciudad…')
        self.search.pack(side='left')
        self.search.bind('<KeyRelease>', lambda e: self._schedule_refresh())
        button(bar, '+ Nueva sucursal', self.new_branch, primary=True, width=150).pack(side='right')
        self.btn_delete = button(bar, 'Eliminar', self.delete_selected, danger=True, width=90, state='disabled')
        self.btn_delete.pack(side='right', padx=(0, 8))
        self.btn_toggle = button(bar, 'Desactivar', self.toggle_selected, width=110, state='disabled')
        self.btn_toggle.pack(side='right', padx=(0, 8))
        self.btn_edit = button(bar, 'Ver / Editar', self.edit_selected, width=110, state='disabled')
        self.btn_edit.pack(side='right', padx=(0, 8))

    def _build_table(self):
        style = ttk.Style()
        style.theme_use('default')
        style.configure(self.STYLE, background=WHITE, foreground=INK, rowheight=38, fieldbackground=WHITE,
                        borderwidth=0, font=('Arial', 11))
        style.map(self.STYLE, background=[('selected', SOFT)], foreground=[('selected', BLUE_DARK)])
        style.configure(self.STYLE + '.Heading', background=BG, foreground=MUTED, font=('Arial', 11, 'bold'),
                        borderwidth=0)

        frame = card(self)
        frame.grid(row=1, column=0, sticky='nsew')
        frame.pack_propagate(False)
        columns = (('code', 'Código', 90, 'w'), ('name', 'Sucursal', 230, 'w'), ('city', 'Ciudad', 140, 'w'),
                   ('phone', 'Teléfono', 120, 'w'), ('registers', 'Cajas', 60, 'center'),
                   ('users', 'Usuarios', 70, 'center'), ('status', 'Estado', 80, 'center'))
        self.tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show='headings', selectmode='browse',
                                 style=self.STYLE)
        for key, title, width, anchor in columns:
            self.tree.heading(key, text=title, anchor=anchor)
            self.tree.column(key, width=width, minwidth=50, anchor=anchor)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True, padx=(10, 0), pady=10)
        scroll.pack(side='right', fill='y', pady=10, padx=(0, 6))
        self.tree.tag_configure('inactive', foreground='#94A3B8')
        self.tree.bind('<<TreeviewSelect>>', lambda e: self._sync_buttons())
        self.tree.bind('<Double-1>', lambda e: self.edit_selected())
        self.tree.bind('<Return>', lambda e: self.edit_selected())

        self.count_lbl = label(self, '', 12, False, MUTED)
        self.count_lbl.grid(row=2, column=0, sticky='w', padx=6, pady=(8, 0))

    # ------------------------------------------------------------------ datos
    def _schedule_refresh(self):
        if self._search_job is not None:
            self.jobs.cancel(self._search_job)
        self._search_job = self.jobs.later(250, self.refresh)

    def refresh(self):
        ok, rows = guarded(self.winfo_toplevel(), lambda: self.ctrl.list_branches(self.search.get()))
        if not ok:
            return
        keep = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        self._rows = {r['id']: r for r in rows}
        for r in rows:
            self.tree.insert('', 'end', iid=r['id'], tags=() if r['is_active'] else ('inactive',), values=(
                r['code'], r['name'], r['city'] or '', r['phone'] or '', r['registers'], r['users'],
                'Activa' if r['is_active'] else 'Inactiva'))
        if keep and keep[0] in self._rows:
            self.tree.selection_set(keep[0])
        active = sum(1 for r in rows if r['is_active'])
        self.count_lbl.configure(text=f'{len(rows)} sucursal(es) · {active} activa(s)')
        self._sync_buttons()

    def _selected(self):
        sel = self.tree.selection()
        return self._rows.get(sel[0]) if sel else None

    def _sync_buttons(self):
        row = self._selected()
        state = 'normal' if row else 'disabled'
        self.btn_edit.configure(state=state)
        self.btn_delete.configure(state=state)
        self.btn_toggle.configure(state=state, text='Desactivar' if (row is None or row['is_active']) else 'Reactivar')

    # ------------------------------------------------------------------ acciones
    def new_branch(self):
        BranchForm(self, None)

    def edit_selected(self):
        row = self._selected()
        if not row:
            return
        ok, data = guarded(self.winfo_toplevel(), lambda: self.ctrl.get_branch(row['id']))
        if ok:
            BranchForm(self, data)
        else:
            self.refresh()

    def toggle_selected(self):
        row = self._selected()
        if not row:
            return
        top, activate = self.winfo_toplevel(), not row['is_active']
        if not activate and not messagebox.askyesno(
                'Desactivar sucursal',
                f"¿Desactivar la sucursal «{row['name']}»?\n\nSe conserva todo su historial; "
                f"tiene {row['registers']} caja(s) y {row['users']} usuario(s) asignados.", parent=top):
            return
        ok, _ = guarded(top, lambda: self.ctrl.set_active(row['id'], activate, self.user_id))
        self.refresh()

    def delete_selected(self):
        row = self._selected()
        if not row:
            return
        top = self.winfo_toplevel()
        if not messagebox.askyesno('Eliminar sucursal', f"¿Eliminar la sucursal «{row['name']}»?\n\n"
                                   "Solo se puede eliminar si nunca se ha usado.", parent=top):
            return
        guarded(top, lambda: self.ctrl.delete_branch(row['id'], self.user_id))
        self.refresh()

    def destroy(self):
        self.jobs.close()
        super().destroy()


class BranchForm(ctk.CTkToplevel):
    """Alta / edición en ventana modal, con errores por campo."""

    # (clave, etiqueta, fila, columna, columnas que ocupa)
    LAYOUT = [('code', 'Código *', 0, 0, 1), ('name', 'Nombre de la sucursal *', 0, 1, 1),
              ('phone', 'Teléfono', 1, 0, 1), ('email', 'Correo electrónico', 1, 1, 1),
              ('address', 'Dirección', 2, 0, 2),
              ('city', 'Ciudad', 3, 0, 1), ('state', 'Estado', 3, 1, 1),
              ('postal_code', 'Código postal', 4, 0, 1)]

    def __init__(self, panel, data):
        top = panel.winfo_toplevel()
        super().__init__(top)
        self.panel, self.data, self._busy = panel, data, False
        self.title('Editar sucursal' if data else 'Nueva sucursal')
        self.configure(fg_color=BG)
        self.resizable(False, False)
        self.bind('<Escape>', lambda e: self.destroy())

        label(self, 'Datos de la sucursal', 20, True).pack(pady=(18, 0))
        if data:
            usage = panel.ctrl.usage(data['id'])
            hint = ' · '.join(f'{n} {k}' for k, n in usage.items()) or 'Sin actividad registrada'
            status = 'Activa' if data['is_active'] else 'Inactiva'
            label(self, f'{status} · {hint}', 12, False, MUTED).pack(pady=(0, 2))

        buttons = ctk.CTkFrame(self, fg_color='transparent')
        buttons.pack(side='bottom', fill='x', padx=32, pady=(8, 18))
        self.btn_save = keyboard_button(button(buttons, 'Guardar', self._save, primary=True, width=120, height=42))
        self.btn_save.pack(side='right')
        keyboard_button(button(buttons, 'Cancelar', self.destroy, width=100, height=42)).pack(side='right', padx=8)

        form = ctk.CTkFrame(self, fg_color='transparent')
        form.pack(fill='both', expand=True, padx=32)
        form.grid_columnconfigure((0, 1), weight=1, uniform='c')
        self.vars, self.entries, self.errors = {}, {}, {}
        for key, caption, row, col, span in self.LAYOUT:
            var = ctk.StringVar(value=str(data[key]) if data and data.get(key) is not None else '')
            cell = ctk.CTkFrame(form, fg_color='transparent')
            cell.grid(row=row, column=col, columnspan=span, sticky='ew', pady=(8, 0),
                      padx=(0, 8) if (span == 1 and col == 0) else (8, 0) if col == 1 else 0)
            label(cell, caption, 12, True, MUTED).pack(anchor='w')
            entry = ctk.CTkEntry(cell, textvariable=var, height=36, fg_color=WHITE, border_color=SKY, text_color=INK)
            entry.pack(fill='x')
            err = label(cell, '', 11, False, ERR, wraplength=260, justify='left')
            entry.bind('<Return>', lambda e: self._save())
            self.vars[key], self.entries[key], self.errors[key] = var, entry, err
        self.entries['code'].bind('<KeyRelease>', lambda e: self._upper_code(), add='+')

        self._initial_focus = self.entries['code'] if not data else self.entries['name']
        center_window(self, top, 640, 560)

    def _upper_code(self):
        value = self.vars['code'].get()
        if value != value.upper():
            self.vars['code'].set(value.upper())

    def _show_errors(self, errors):
        for key, widget in self.entries.items():
            msg = errors.get(key, '')
            self.errors[key].configure(text=msg)
            if msg:
                self.errors[key].pack(anchor='w')
            else:
                self.errors[key].pack_forget()
            widget.configure(border_color=ERR if msg else SKY, fg_color=RED_SOFT if msg else WHITE)

    def _save(self):
        if self._busy:
            return
        values = {k: v.get() for k, v in self.vars.items()}
        branch_id = self.data['id'] if self.data else None
        _clean, errors = self.panel.ctrl.validate(values, branch_id)
        self._show_errors(errors)
        if errors:
            self.entries[next(k for k in self.vars if k in errors)].focus_set()
            return
        self._busy = True
        self.btn_save.configure(state='disabled')
        try:
            ok, _ = guarded(self, lambda: self.panel.ctrl.save_branch(values, branch_id, self.panel.user_id))
            if ok:
                self.panel.refresh()
                self.destroy()
        finally:
            if self.winfo_exists():
                self._busy = False
                self.btn_save.configure(state='normal')