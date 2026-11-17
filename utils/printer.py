import logging
import os
import win32print
from datetime import datetime

log = logging.getLogger(__name__)

class TicketPrinter:
    # Comandos ESC/POS universales
    INIT = b'\x1B\x40'
    CUT = b'\x1D\x56\x00'
    DRAWER = b'\x1B\x70\x00\x19\xFA'
    CENTER = b'\x1B\x61\x01'
    LEFT = b'\x1B\x61\x00'
    BOLD_ON = b'\x1B\x45\x01'
    BOLD_OFF = b'\x1B\x45\x00'

    def __init__(self, printer_name=None, columns=32):
        # 32 columnas para 58mm. Si usas 80mm, cámbialo a 48.
        self.columns = columns
        try:
            self.printer_name = printer_name or win32print.GetDefaultPrinter()
        except Exception as e:
            self.printer_name = None

    def _format_line(self, left_text, right_text):
        """Acomoda el texto a la izquierda y el precio a la derecha."""
        left_str = str(left_text)
        right_str = str(right_text)
        space_len = self.columns - len(left_str) - len(right_str)
        if space_len > 0:
            return left_str + (" " * space_len) + right_str
        return left_str[:(self.columns - len(right_str) - 1)] + " " + right_str

    def _send_raw_data(self, raw_data):
        """Envía los bytes a la impresora física si existe."""
        if not self.printer_name:
            return False
        try:
            hPrinter = win32print.OpenPrinter(self.printer_name)
            try:
                hJob = win32print.StartDocPrinter(hPrinter, 1, ("Ticket SotyPDV", None, "RAW"))
                win32print.StartPagePrinter(hPrinter)
                win32print.WritePrinter(hPrinter, raw_data)
                win32print.EndPagePrinter(hPrinter)
                win32print.EndDocPrinter(hPrinter)
                return True
            finally:
                win32print.ClosePrinter(hPrinter)
        except Exception as e:
            log.warning(f"No se pudo imprimir físicamente en {self.printer_name}: {e}")
            return False

    def print_ticket(self, business_name, ticket_number, cashier_name, payload):
        # =================================================================
        # 1. GENERAR COPIA DIGITAL (.txt) PARA VERLA EN LA COMPUTADORA
        # =================================================================
        text_lines = []
        text_lines.append(business_name.center(self.columns))
        text_lines.append("PUNTO DE VENTA".center(self.columns))
        text_lines.append("-" * self.columns)
        text_lines.append(f"Folio: {ticket_number}")
        text_lines.append(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        text_lines.append(f"Cajero: {cashier_name}")
        text_lines.append("-" * self.columns)
        
        for item in payload['items']:
            qty = float(item['quantity'])
            name = item['product_name']
            total = float(item['line_total_cents']) / 100.0
            text_lines.append(f"{qty:g} x {name}")
            text_lines.append(self._format_line("", f"${total:.2f}"))
            
        text_lines.append("-" * self.columns)
        total_str = f"${float(payload['total_cents'])/100:.2f}"
        text_lines.append(self._format_line("TOTAL:", total_str))
        
        method = "Efectivo" if payload['payment_method'] == 'cash' else "Tarjeta/Transf."
        recibido_str = f"${float(payload['received_cents'])/100:.2f}"
        cambio_str = f"${float(payload['change_cents'])/100:.2f}"
        
        text_lines.append(self._format_line(f"Pagado ({method}):", recibido_str))
        text_lines.append(self._format_line("Cambio:", cambio_str))
        text_lines.append(" ")
        text_lines.append("¡Gracias por su compra!".center(self.columns))
        text_lines.append(" ")
        
        # Crear la carpeta "tickets" si no existe y guardar el archivo
        os.makedirs("tickets", exist_ok=True)
        with open(f"tickets/{ticket_number}.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(text_lines))

        # =================================================================
        # 2. GENERAR BINARIO ESC/POS PARA LA IMPRESORA FÍSICA
        # =================================================================
        def encode(text):
            return (text + '\n').encode('cp858', errors='replace')

        data = bytearray()
        data += self.INIT
        
        # Encabezado centrado
        data += self.CENTER + self.BOLD_ON + encode(business_name) + self.BOLD_OFF
        data += encode("PUNTO DE VENTA") + encode("-" * self.columns)
        
        # Cuerpo a la izquierda
        data += self.LEFT
        data += encode(f"Folio: {ticket_number}")
        data += encode(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        data += encode(f"Cajero: {cashier_name}")
        data += encode("-" * self.columns)
        
        for item in payload['items']:
            qty = float(item['quantity'])
            name = item['product_name']
            total = float(item['line_total_cents']) / 100.0
            data += encode(f"{qty:g} x {name}")
            data += encode(self._format_line("", f"${total:.2f}"))
            
        data += encode("-" * self.columns)
        data += self.BOLD_ON + encode(self._format_line("TOTAL:", total_str)) + self.BOLD_OFF
        data += encode(self._format_line(f"Pagado ({method}):", recibido_str))
        data += encode(self._format_line("Cambio:", cambio_str))
        
        # Pie centrado
        data += self.CENTER + encode(" ") + encode("¡Gracias por su compra!")
        data += encode(" ") * 4  # Espacio en blanco para que salga el papel del rodillo
        data += self.CUT
        
        if payload['payment_method'] == 'cash':
            data += self.DRAWER

        self._send_raw_data(bytes(data))


    def print_z_report(self, business_name, register_name, cashier_name, totals):
        """Genera e imprime el ticket de Corte de Caja (Corte Z)."""
        text_lines = []
        text_lines.append(business_name.center(self.columns))
        text_lines.append("CORTE DE CAJA (Z)".center(self.columns))
        text_lines.append("-" * self.columns)
        text_lines.append(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        text_lines.append(f"Caja: {register_name}")
        text_lines.append(f"Cajero: {cashier_name}")
        text_lines.append("-" * self.columns)

        exp = float(totals['expected_cash']) / 100.0
        cnt = float(totals['counted_cash']) / 100.0
        diff = float(totals['difference']) / 100.0

        text_lines.append(self._format_line("Efectivo Esperado:", f"${exp:.2f}"))
        text_lines.append(self._format_line("Efectivo Contado:", f"${cnt:.2f}"))
        text_lines.append("-" * self.columns)

        diff_str = f"${abs(diff):.2f}"
        if diff < 0:
            text_lines.append(self._format_line("FALTANTE:", f"-{diff_str}"))
        elif diff > 0:
            text_lines.append(self._format_line("SOBRANTE:", f"+{diff_str}"))
        else:
            text_lines.append(self._format_line("DIFERENCIA:", "EXACTO"))

        text_lines.append(" ")
        text_lines.append("Firma del Cajero".center(self.columns))
        text_lines.append(" ")
        text_lines.append("______________________".center(self.columns))
        text_lines.append(" ")

        # 1. Guardar la copia digital (.txt) en la carpeta
        os.makedirs("tickets", exist_ok=True)
        report_id = f"CorteZ-{datetime.now().strftime('%Y%m%d%H%M')}"
        with open(f"tickets/{report_id}.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(text_lines))

        # 2. Generar código RAW ESC/POS para la impresora física
        def encode(text):
            return (text + '\n').encode('cp858', errors='replace')

        data = bytearray()
        data += self.INIT
        for line in text_lines:
            if "CORTE" in line or "FALTANTE" in line or "SOBRANTE" in line:
                data += self.BOLD_ON + encode(line) + self.BOLD_OFF
            else:
                data += encode(line)

        data += encode(" ") * 4
        data += self.CUT
        
        self._send_raw_data(bytes(data))