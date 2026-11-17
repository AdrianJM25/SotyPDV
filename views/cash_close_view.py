"""Arqueo integrado en una pestaña. No crea ventanas ni bloquea la navegación."""
from decimal import Decimal
import logging
import customtkinter as ctk
if __package__:
    from .ui_helpers import Jobs, Activity, keyboard_checkbox, keyboard_button
else:
    from ui_helpers import Jobs, Activity, keyboard_checkbox, keyboard_button

log = logging.getLogger(__name__)
BG, WHITE, INK, MUTED = '#F2F5FA', '#FFFFFF', '#142338', '#64748B'
TEAL, RED = '#0F766E', '#B42318'
DENOMINATIONS = {
    'Billetes': (100000, 50000, 20000, 10000, 5000, 2000),
    'Monedas': (2000, 1000, 500, 200, 100, 50, 20, 10),
}


def money(cents):
    return f'${Decimal(cents) / 100:,.2f}'


def count_cash(values):
    """Claves (categoría, centavos): billete y moneda de $20 son independientes."""
    total = 0
    for (category, cents), raw in values.items():
        if category not in DENOMINATIONS or cents not in DENOMINATIONS[category]:
            raise ValueError('Denominación no válida.')
        raw = str(raw).strip()
        if raw and (not raw.isascii() or not raw.isdigit() or len(raw) > 5):
            raise ValueError('Las piezas deben ser enteros de 0 a 99,999.')
        total += cents * int(raw or '0')
    if total > 100000000:
        raise ValueError('El conteo no puede superar $1,000,000.00.')
    return total


def text(parent, value, size=14, bold=False, color=INK, **kwargs):
    return ctk.CTkLabel(parent, text=value, text_color=color,
        font=ctk.CTkFont(size=size, weight='bold' if bold else 'normal'), **kwargs)


class CashCloseView(ctk.CTkFrame):
    def __init__(self, master, current_user, on_confirm_callback, *, balance_callback=None,
                 pending_sale_callback=None, on_closed_callback=None, on_back_callback=None):
        super().__init__(master, fg_color=BG, corner_radius=0)
        self.jobs = Jobs(self)
        self.current_user = current_user
        self.on_confirm_callback = on_confirm_callback
        self.balance_callback = balance_callback
        self.pending_sale_callback = pending_sale_callback or (lambda: False)
        self.on_closed_callback = on_closed_callback
        self.on_back_callback = on_back_callback
        self.entries, self.row_totals, self.inputs = {}, {}, []
        self.total_cents = 0
        self.current_total = Decimal('0')
        self.total_var = ctk.StringVar(value='$0.00')
        self.balance = None
        self._busy = self.closed = self._ready = False
        self._reviewing = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_ui()
        self._ready = True
        self._calculate_total()

    def _button(self, parent, caption, command, primary=False, **kwargs):
        return keyboard_button(ctk.CTkButton(parent, text=caption, command=command, height=42,
            fg_color=TEAL if primary else '#EAF0F6', hover_color='#115E59' if primary else '#DCE5EF',
            text_color=WHITE if primary else INK, **kwargs))

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color='transparent')
        header.grid(row=0, column=0, padx=22, pady=(14, 10), sticky='ew')
        header.grid_columnconfigure(0, weight=1)
        text(header, 'Caja y corte', 26, True).grid(row=0, column=0, sticky='w')
        text(header, '1. Revisa el saldo     2. Cuenta el efectivo     3. Confirma el cierre',
             13, color=MUTED).grid(row=1, column=0, sticky='w')
        self.refresh_button = self._button(header, 'Actualizar saldo', self.refresh, width=140)
        self.refresh_button.grid(row=0, column=1, rowspan=2, padx=8)
        body = ctk.CTkScrollableFrame(self, fg_color='transparent', corner_radius=0)
        self._body = body
        body.grid(row=1, column=0, sticky='nsew', padx=12, pady=(0, 8))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        summary = ctk.CTkFrame(body, fg_color=WHITE, corner_radius=14)
        summary.grid(row=0, column=0, columnspan=2, sticky='ew', padx=6, pady=6)
        summary.grid_columnconfigure((0, 1, 2), weight=1)
        self.summary_labels = {}
        for col, (key, caption) in enumerate((('expected_cash','EFECTIVO ESPERADO'),
                                              ('counted','EFECTIVO CONTADO'), ('difference','DIFERENCIA'))):
            text(summary, caption, 12, True, MUTED).grid(row=0, column=col, sticky='w', padx=22, pady=(16, 2))
            val = text(summary, '—' if key != 'counted' else '$0.00', 29, True, TEAL)
            val.grid(row=1, column=col, sticky='w', padx=22, pady=(0, 16))
            self.summary_labels[key] = val
        counts = ctk.CTkFrame(body, fg_color=WHITE, corner_radius=14)
        counts.grid(row=1, column=0, sticky='nsew', padx=6, pady=8)
        counts.grid_columnconfigure((0,1), weight=1)
        text(counts, 'Conteo por denominación', 20, True).grid(row=0, column=0, columnspan=2, sticky='w', padx=18, pady=(16, 2))
        text(counts, 'Captura piezas. Los campos vacíos cuentan como cero.', 12, color=MUTED).grid(
            row=1, column=0, columnspan=2, sticky='w', padx=18, pady=(0, 8))
        validate = (self.register(lambda v: not v or (v.isascii() and v.isdigit() and len(v) <= 5)), '%P')
        for col, (category, cents_list) in enumerate(DENOMINATIONS.items()):
            frame = ctk.CTkFrame(counts, fg_color='#F8FAFC', corner_radius=10)
            frame.grid(row=2, column=col, sticky='nsew', padx=10, pady=(0, 14))
            frame.grid_columnconfigure(2, weight=1)
            text(frame, category, 16, True, TEAL).grid(row=0, column=0, columnspan=3, padx=10, pady=10, sticky='w')
            for row, cents in enumerate(cents_list, 1):
                key = category, cents
                var = ctk.StringVar(value='')
                self.entries[key] = var
                text(frame, money(cents), 13, True, width=65).grid(row=row, column=0, padx=(6, 0), pady=5)
                entry = ctk.CTkEntry(frame, textvariable=var, width=66, height=36,
                    justify='center', text_color=INK, fg_color=WHITE, border_color='#DCE4EE',
                    validate='key', validatecommand=validate)
                entry.grid(row=row, column=1, padx=4, pady=5)
                self.inputs.append(entry)
                amount = text(frame, '$0.00', 12, color=MUTED, width=80)
                amount.grid(row=row, column=2, padx=6, pady=5, sticky='e')
                self.row_totals[key] = amount
                var.trace_add('write', self._calculate_total)
        detail = ctk.CTkFrame(body, fg_color=WHITE, corner_radius=14)
        detail.grid(row=1, column=1, sticky='nsew', padx=6, pady=8)
        detail.grid_columnconfigure(0, weight=1)
        text(detail, 'Resumen del turno', 20, True).grid(row=0, column=0, columnspan=2, sticky='w', padx=20, pady=(16, 8))
        self.breakdown = {}
        for row, (key, caption) in enumerate((('opening_amount','Fondo inicial'), ('cash_sales','Ventas en efectivo'),
                ('cash_in','Entradas de efectivo'), ('cash_out','Salidas de efectivo'),
                ('cash_refunds','Devoluciones en efectivo')), 1):
            text(detail, caption, color=MUTED).grid(row=row, column=0, sticky='w', padx=20, pady=5)
            val = text(detail, '—', 14, True)
            val.grid(row=row, column=1, sticky='e', padx=20)
            self.breakdown[key] = val
        text(detail, 'Tarjetas y transferencias no forman parte del efectivo físico.', 12,
             color=MUTED, wraplength=400, justify='left').grid(row=6, column=0, columnspan=2, padx=20, pady=12, sticky='w')
        text(detail, 'Observaciones del corte', 14, True).grid(row=7, column=0, columnspan=2, padx=20, sticky='w')
        self.txt_notes = ctk.CTkTextbox(detail, height=82, fg_color='#F8FAFC', text_color=INK, border_width=1, border_color='#DCE4EE')
        self.txt_notes.grid(row=8, column=0, columnspan=2, padx=20, pady=8, sticky='ew')
        self.txt_notes.bind('<KeyRelease>', self._notes_changed)
        self.counted_verified = ctk.BooleanVar(value=False)
        self.counted_verified.trace_add('write', lambda *a: self._invalidate_review())
        self.verified_check = ctk.CTkCheckBox(detail, text='Terminé de contar todo el efectivo',
            variable=self.counted_verified, command=self._invalidate_review, text_color=INK, fg_color=TEAL)
        keyboard_checkbox(self.verified_check)
        self.verified_check.grid(row=9, column=0, columnspan=2, padx=20, pady=(8, 16), sticky='w')
        self.notice = text(body, 'Abre esta pestaña para consultar el saldo del turno.', 13,
                           color=MUTED, wraplength=1000, justify='left', anchor='w')
        self.notice.grid(row=2, column=0, columnspan=2, sticky='ew', padx=12, pady=8)
        self.review_frame = ctk.CTkFrame(body, fg_color='#EAF6F3', corner_radius=12)
        self.review_frame.grid(row=3, column=0, columnspan=2, sticky='ew', padx=6, pady=6)
        self.review_frame.grid_columnconfigure(0, weight=1)
        self.review_label = text(self.review_frame, '', 14, True, TEAL, wraplength=920, justify='left')
        self.review_label.grid(row=0, column=0, padx=18, pady=14, sticky='w')
        self.confirm_button = self._button(self.review_frame, 'Confirmar cierre de turno', self._on_confirm, True)
        self.confirm_button.grid(row=1, column=0, padx=18, pady=(0, 14), sticky='e')
        self.review_frame.grid_remove()
        footer = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=0)
        footer.grid(row=2, column=0, sticky='ew')
        footer.grid_columnconfigure(1, weight=1)
        self.back_button = self._button(footer, 'Volver a Venta · Ctrl+1', lambda: self.on_back_callback() if self.on_back_callback else None)
        self.back_button.grid(row=0, column=0, padx=22, pady=12)
        self.ready_hint = text(footer, '', 12, color=MUTED, wraplength=390)
        self.ready_hint.grid(row=0, column=1, padx=8, sticky='ew')
        self.review_button = self._button(footer, 'Revisar y cerrar turno  →', self.review, True, width=230)
        self.review_button.grid(row=0, column=2, padx=22, pady=12)
        self.activity = Activity(self)
        self.activity.grid(row=3, column=0, padx=22, sticky='ew')
        self.activity.grid_remove()

    def _notes_changed(self, event=None):
        self._invalidate_review()

    def _invalidate_review(self):
        if not self._ready or self.closed:
            return
        self._reviewing = False
        self.review_frame.grid_remove()
        self.confirm_button.configure(state='disabled')
        self._sync_actions()

    def _reason_not_ready(self):
        if self.closed: return 'Turno cerrado.'
        if self._busy: return 'Guardando corte…'
        if not self.on_confirm_callback: return 'Cierre no disponible para este usuario.'
        if self.balance is None: return 'Actualiza el saldo para continuar.'
        if self.total_cents is None: return 'Corrige las cantidades del conteo.'
        if self.pending_sale_callback(): return 'Cobra o vacía el ticket pendiente.'
        if not self.counted_verified.get(): return 'Marca que terminaste de contar el efectivo.'
        notes = self.txt_notes.get('1.0', 'end-1c').strip()
        if len(notes) > 1000: return 'Máximo 1,000 caracteres en observaciones.'
        if self.total_cents != self.balance['expected_cash'] and not notes:
            return 'Explica la diferencia en observaciones.'
        return None

    def _sync_actions(self):
        if not self._ready: return
        reason = self._reason_not_ready()
        self.review_button.configure(state='disabled' if reason else 'normal')
        self.ready_hint.configure(text=reason or 'Todo listo. Revisa antes de confirmar.')
        self.confirm_button.configure(state='normal' if self._reviewing and reason is None else 'disabled')

    def _calculate_total(self, *args):
        if not self._ready:
            return
        self.counted_verified.set(False)
        self._invalidate_review()
        try:
            values = {key: var.get() for key, var in self.entries.items()}
            total = count_cash(values)
        except ValueError as exc:
            self.total_cents = None
            self.review_button.configure(state='disabled')
            self.notice.configure(text=str(exc), text_color=RED)
            self.summary_labels['counted'].configure(text='Revisa el conteo')
            self.summary_labels['difference'].configure(text='—')
            self._sync_actions()
            return
        self.total_cents = total
        self.current_total = Decimal(total) / 100
        self.total_var.set(money(total))
        for key, raw in values.items():
            self.row_totals[key].configure(text=money(key[1] * int(raw or '0')))
        self.summary_labels['counted'].configure(text=money(total))
        self._show_difference()
        self._sync_actions()

    def _show_difference(self):
        if self.balance is not None and self.total_cents is not None:
            diff = self.total_cents - self.balance['expected_cash']
            caption = 'Cuadra · $0.00' if diff == 0 else ('Faltante ' if diff < 0 else 'Sobrante ') + money(abs(diff))
            self.summary_labels['difference'].configure(text=caption, text_color=RED if diff < 0 else TEAL)

    def _error(self, exc):
        if isinstance(exc, ValueError) or type(exc).__module__.startswith('utils.exceptions'):
            return str(exc)
        log.exception('Error de caja')
        return 'No se pudo consultar o guardar el corte. El conteo se conserva.'

    def refresh(self):
        if self.closed or self._busy:
            return False
        self._invalidate_review()
        try:
            if self.balance_callback is None:
                raise ValueError('Conecta la consulta de saldo y el cierre para habilitar el corte.')
            value = dict(self.balance_callback())
            for key in ('expected_cash', *self.breakdown.keys()):
                if type(value.get(key)) is not int:
                    raise ValueError('El saldo debe incluir importes enteros en centavos.')
            self.balance = value
            self.summary_labels['expected_cash'].configure(text=money(value['expected_cash']))
            for key, lbl in self.breakdown.items():
                lbl.configure(text=money(value[key]))
            self._show_difference()
            pending = self.pending_sale_callback()
            self.notice.configure(text='Hay un ticket pendiente. Puedes contar, pero debes cobrarlo o vaciarlo antes de cerrar.'
                                  if pending else 'Saldo actualizado. El conteo se conserva al cambiar de pestaña.',
                                  text_color=RED if pending else MUTED)
            self._sync_actions()
            return True
        except Exception as exc:
            self.balance = None
            self.summary_labels['expected_cash'].configure(text='No disponible')
            self.summary_labels['difference'].configure(text='—')
            self.notice.configure(text=self._error(exc), text_color=RED)
            self._sync_actions()
            return False

    def review(self):
        if self._reason_not_ready() is not None:
            self._sync_actions()
            return
        if not self.refresh():
            return
        if self.pending_sale_callback():
            return
        if not self.counted_verified.get():
            self.notice.configure(text='Marca que terminaste de contar; también es necesario cuando el efectivo es cero.', text_color=RED)
            return
        notes = self.txt_notes.get('1.0', 'end-1c').strip()
        if len(notes) > 1000:
            self.notice.configure(text='Las observaciones no deben superar 1,000 caracteres.', text_color=RED)
            return
        diff = self.total_cents - self.balance['expected_cash']
        if diff and not notes:
            self.notice.configure(text='Escribe una observación para explicar el faltante o sobrante.', text_color=RED)
            return
        self._reviewing = True
        self._sync_actions()
        self._review_snapshot = (self.total_cents, notes, self.balance['expected_cash'])
        self.review_label.configure(text=f"Cerrar turno con {money(self.total_cents)} contados. "
            f"Diferencia: {money(diff)}. Al confirmar, este turno dejará de aceptar ventas.")
        self.review_frame.grid()
        self.update_idletasks()
        self._body._parent_canvas.yview_moveto(1.0)
        self.notice.configure(text='Revisa los importes y confirma abajo. Todavía no se ha cerrado el turno.', text_color=TEAL)

    def _on_confirm(self):
        if self.closed or self._busy or not self._reviewing or not self.on_confirm_callback:
            return
        counted, notes, expected = self._review_snapshot
        if (counted != self.total_cents or notes != self.txt_notes.get('1.0', 'end-1c').strip()
                or not self.counted_verified.get() or self.pending_sale_callback()):
            self._invalidate_review()
            self.notice.configure(text='Los datos cambiaron. Revisa el corte nuevamente.', text_color=RED)
            return
        self._busy = True
        self.confirm_button.configure(state='disabled', text='Guardando corte…')
        self._lock_inputs(True)
        self.activity.grid()
        self.activity.start('Guardando el corte. Espera la confirmación…')
        self.jobs.later(70, lambda: self._commit_close(counted, notes, expected))

    def _commit_close(self, counted, notes, expected):
        try:
            # Pesos exactos y saldo revisado. El controlador compara este saldo bajo transacción.
            result = self.on_confirm_callback(Decimal(counted) / 100, notes, expected)
            if not isinstance(result, dict) or any(type(result.get(k)) is not int
                    for k in ('expected_cash', 'counted_cash', 'difference')):
                raise ValueError('No llegó confirmación del cierre. Verifica el estado del turno antes de reintentar.')
            if (result['counted_cash'] != counted or result['expected_cash'] != expected
                    or result['difference'] != counted - expected):
                raise ValueError('La confirmación no coincide con el corte revisado. Verifica el turno.')
        except Exception as exc:
            self.notice.configure(text=self._error(exc), text_color=RED)
            self._busy = False
            self.activity.stop()
            self.activity.grid_remove()
            self._lock_inputs(False)
            self.confirm_button.configure(state='normal', text='Confirmar cierre de turno')
            self._invalidate_review()
            return
        self._busy = False
        self.closed = True
        self.activity.stop()
        self.activity.grid_remove()
        self.back_button.configure(state='normal')
        self.ready_hint.configure(text='Corte guardado. Puedes volver a Venta o salir.')
        self.review_frame.grid_remove()
        for entry in self.inputs:
            entry.configure(state='disabled')
        self.txt_notes.configure(state='disabled')
        self.verified_check.configure(state='disabled')
        self.review_button.configure(state='disabled', text='Turno cerrado')
        self.refresh_button.configure(state='disabled')
        self.notice.configure(text=f"Corte guardado. Contado: {money(counted)} · Diferencia: {money(result['difference'])}.", text_color=TEAL)
        if self.on_closed_callback:
            try:
                self.on_closed_callback(result)
            except Exception:
                log.exception('El corte se guardó, pero no se pudo actualizar la pantalla principal')
                self.notice.configure(text='Corte guardado. Vuelve a iniciar sesión para actualizar la terminal.', text_color=RED)

    def _lock_inputs(self, locked):
        state = 'disabled' if locked else 'normal'
        for entry in self.inputs: entry.configure(state=state)
        self.txt_notes.configure(state=state)
        self.verified_check.configure(state=state)
        self.refresh_button.configure(state=state)
        self.back_button.configure(state=state)
        self._sync_actions()

    def destroy(self):
        self.jobs.close()
        super().destroy()
