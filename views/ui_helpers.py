"""Comportamientos compartidos de teclado, ventanas y estados de trabajo (Tk 8.6)."""
import tkinter as tk
import customtkinter as ctk


class Jobs:
    """Temporizadores cancelables; no quedan callbacks sobre widgets destruidos."""
    def __init__(self, owner):
        self.owner, self.ids = owner, set()

    def later(self, delay, callback):
        token = None
        def invoke():
            self.ids.discard(token)
            if self.owner.winfo_exists():
                callback()
        token = self.owner.after(delay, invoke)
        self.ids.add(token)
        return token

    def cancel(self, token):
        if token in self.ids:
            self.ids.discard(token)
            self.owner.after_cancel(token)

    def close(self):
        for token in tuple(self.ids):
            try:
                self.owner.after_cancel(token)
            except tk.TclError:
                pass
        self.ids.clear()


def keyboard_button(widget):
    """Tab para enfocar y Enter/Espacio para activar; respeta state=disabled."""
    widget._canvas.configure(takefocus=1)
    def activate(event=None):
        if widget.cget('state') == 'normal':
            widget.invoke()
        return 'break'
    widget._canvas.bind('<Return>', activate, add='+')
    widget._canvas.bind('<space>', activate, add='+')
    widget._canvas.bind('<FocusIn>', lambda e: widget.configure(border_width=2, border_color='#0891B2'), add='+')
    widget._canvas.bind('<FocusOut>', lambda e: widget.configure(border_width=0), add='+')
    return widget


def keyboard_checkbox(widget):
    """Permite marcar con Espacio/Enter y muestra el foco del teclado."""
    widget._canvas.configure(takefocus=1)
    original_border = widget.cget('border_color')
    def activate(event=None):
        if widget.cget('state') == 'normal':
            widget.toggle()
        return 'break'
    widget._canvas.bind('<space>', activate, add='+')
    widget._canvas.bind('<Return>', activate, add='+')
    widget._canvas.bind('<FocusIn>', lambda e: widget.configure(border_color='#0891B2'), add='+')
    widget._canvas.bind('<FocusOut>', lambda e: widget.configure(border_color=original_border), add='+')
    return widget


def select_entry(entry):
    entry.focus_set()
    entry.select_range(0, 'end')


def center_window(win, parent, width, height, *, modal=True):
    """Centrar después del trazado y corregir el reajuste inicial de CTk/Windows.

    Usar coordenadas reales del padre evita enviar la ventana a otro monitor.
    El tamaño lógico se escala mediante CTk; los desplazamientos son píxeles Tk.
    """
    win.withdraw()
    win.geometry(f'{width}x{height}')
    win.transient(parent)
    jobs = Jobs(win)
    win._position_jobs = jobs
    win.bind('<Destroy>', lambda event: jobs.close() if event.widget is win else None, add='+')
    def position():
        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        if w <= 1 or h <= 1:
            w, h = width, height
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - w) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - h) // 2)
        # Usar + antes de valores negativos conserva coordenadas de monitores a la izquierda.
        win.tk.call('wm', 'geometry', win._w, f'{w}x{h}+{x}+{y}')
    def release_hidden(event):
        if event.widget is win and win.grab_current() is win:
            win.grab_release()

    def activate_visible(event=None):
        if event is not None and event.widget is not win:
            return
        if not win.winfo_viewable():
            return
        # Nunca bloquear la aplicación detrás de una ventana invisible.
        current = win.grab_current()
        if modal and current in (None, win):
            win.grab_set()

    win.bind('<Unmap>', release_hidden, add='+')
    win.bind('<Map>', activate_visible, add='+')

    def reveal():
        win.deiconify()
        win.update_idletasks()
        position()
        win.lift()
        activate_visible()
        target = getattr(win, '_initial_focus', None)
        if target is not None:
            target.focus_set()
        else:
            win.focus_set()
    jobs.later(10, reveal)
    def settle():
        # CTk puede ocultar/restaurar la ventana al decorar su título en Windows.
        if not win.winfo_viewable() and parent.winfo_viewable():
            reveal()
        else:
            position()
            activate_visible()
    jobs.later(350, settle)
    return jobs


class Activity(ctk.CTkFrame):
    """Indica trabajo sin porcentajes ficticios. Las consultas conservan su hilo SQLite."""
    def __init__(self, parent):
        super().__init__(parent, fg_color='transparent')
        self.caption = ctk.CTkLabel(self, text='', text_color='#0F766E', font=ctk.CTkFont(size=12))
        self.caption.pack(anchor='w')
        self.bar = ctk.CTkProgressBar(self, mode='determinate', height=4,
                                     progress_color='#0F766E', fg_color='#DCE4EE')
        self.bar.pack(fill='x', pady=(2, 6))
        self.bar.set(0)

    def start(self, message):
        self.caption.configure(text=message)
        self.bar.configure(mode='indeterminate')
        self.bar.start()
        self.update_idletasks()

    def stop(self, message=''):
        self.bar.stop()
        self.bar.configure(mode='determinate')
        self.bar.set(0)
        self.caption.configure(text=message)

    def destroy(self):
        self.bar.stop()
        super().destroy()
