"""Ventas SQLite: validación autoritativa, transacción e identificación de reintentos.

Conserva create_sale(payload, branch_id, register_id, session_id, cashier_name).
Descuentos: el servidor recalcula descuentos de producto y global, y rechaza el cobro si no
coinciden con lo que mandó la pantalla. El kardex se escribe como en la versión original.
"""
import copy
import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import UUID
from models.base_model import BaseModel
from utils.discounts import calc_amount, is_valid_now, prorate
from utils.exceptions import BusinessRuleError, POSError

log = logging.getLogger(__name__)

DISCOUNT_PERM = 'sales.discount'


class SalesController(BaseModel):
    def __init__(self):
        super().__init__()
        self.printer = None

    @staticmethod
    def _integer(value, name):
        if type(value) is not int or value < 0 or value > 100000000:
            raise BusinessRuleError(f'{name} debe ser un entero de 0 a 100,000,000 centavos.')
        return value

    @staticmethod
    def _quantity(value):
        try:
            qty = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise BusinessRuleError('Cantidad inválida.') from None
        if not qty.is_finite() or qty <= 0 or qty > 999999 or qty != qty.quantize(Decimal('.001')):
            raise BusinessRuleError('La cantidad debe ser positiva, hasta 999999 y con máximo tres decimales.')
        return qty

    def _validate_payload(self, payload):
        if not isinstance(payload, dict) or not isinstance(payload.get('items'), list) or not payload['items']:
            raise BusinessRuleError('No se puede registrar una venta vacía.')
        if len(payload['items']) > 1000:
            raise BusinessRuleError('El ticket tiene demasiados productos.')
        try:
            request = str(UUID(str(payload['request_id'])))
        except (KeyError, ValueError, TypeError, AttributeError):
            raise BusinessRuleError('Falta un identificador UUID válido para la venta.') from None
        if payload.get('payment_method') not in ('cash', 'card', 'transfer'):
            raise BusinessRuleError('Forma de pago no válida.')
        for key in ('total_cents', 'received_cents', 'change_cents'):
            self._integer(payload.get(key), key)
        total, received = payload['total_cents'], payload['received_cents']
        if total <= 0:
            raise BusinessRuleError('El total de la venta debe ser mayor a cero.')
        if received < total or payload['change_cents'] != received - total:
            raise BusinessRuleError('El importe recibido o el cambio no coincide con la venta.')
        if payload['payment_method'] != 'cash' and (received != total or payload['change_cents'] != 0):
            raise BusinessRuleError('Los pagos externos deben cubrir el total exacto, sin cambio.')
        self._integer(payload.get('discount_total_cents', 0), 'Descuento')
        for key in ('discount_id', 'authorized_by', 'customer_id'):
            if payload.get(key) is not None and not isinstance(payload[key], str):
                raise BusinessRuleError('Datos de la venta inválidos.')
        seen = set()
        for item in payload['items']:
            if not isinstance(item, dict) or not isinstance(item.get('product_id'), str) or not item['product_id']:
                raise BusinessRuleError('Falta identificar un producto.')
            if item['product_id'] in seen:
                raise BusinessRuleError('Agrupa las cantidades del mismo producto antes de cobrar.')
            seen.add(item['product_id'])
            self._quantity(item.get('quantity'))
            self._integer(item.get('unit_price_cents'), 'Precio')
            self._integer(item.get('line_total_cents'), 'Importe del producto')
            self._integer(item.get('discount_cents', 0), 'Descuento del producto')
            if item.get('discount_id') is not None and not isinstance(item['discount_id'], str):
                raise BusinessRuleError('Datos del descuento inválidos.')
        return request

    # ------------------------------------------------------------------ descuentos (dentro de la transacción)
    def _has_permission(self, user_id, code):
        return self.cursor.execute(
            'SELECT 1 FROM users u '
            'JOIN role_permissions rp ON rp.role_id = u.role_id AND rp.deleted_at IS NULL '
            'JOIN permissions p ON p.id = rp.permission_id AND p.deleted_at IS NULL '
            'WHERE u.id = ? AND u.is_active = 1 AND u.deleted_at IS NULL AND p.code = ?',
            (user_id, code)).fetchone() is not None

    def _load_discount(self, discount_id):
        return self.cursor.execute('SELECT * FROM discounts WHERE id = ? AND deleted_at IS NULL',
                                   (discount_id,)).fetchone()

    def _linked_discount(self, product_id, discount_id):
        return self.cursor.execute(
            'SELECT d.* FROM discounts d '
            'JOIN product_discounts pd ON pd.discount_id = d.id AND pd.deleted_at IS NULL '
            'WHERE d.id = ? AND pd.product_id = ? AND d.deleted_at IS NULL',
            (discount_id, product_id)).fetchone()

    def _apply_discounts(self, payload, user, validated):
        """Recalcula descuentos y valida que coincidan con la pantalla.
        Devuelve (lineas, total, descuento_total, descuento_global|None, motivo)."""
        lines, used = [], []
        for item, prod, qty, gross in validated:
            pdisc = 0
            if item.get('discount_id'):
                d = self._linked_discount(prod['id'], item['discount_id'])
                if d is None or not is_valid_now(d):
                    raise BusinessRuleError(f"El descuento de {prod['name']} ya no está vigente. Actualiza el ticket.")
                pdisc = calc_amount(d['discount_type'], d['value'], gross)
                used.append(d)
            lines.append({'item': item, 'prod': prod, 'qty': qty, 'gross': gross,
                          'pdisc': pdisc, 'base': gross - pdisc})

        g_row, gdisc = None, 0
        if payload.get('discount_id'):
            g_row = self._load_discount(payload['discount_id'])
            if g_row is None or not is_valid_now(g_row):
                raise BusinessRuleError('El descuento seleccionado ya no está vigente.')
            gdisc = calc_amount(g_row['discount_type'], g_row['value'], sum(l['base'] for l in lines))
            if gdisc <= 0:
                raise BusinessRuleError('El descuento no aplica a este importe.')
            used.append(g_row)

        for l, share in zip(lines, prorate(gdisc, [l['base'] for l in lines])):
            l['disc'] = l['pdisc'] + share
            l['net'] = l['base'] - share
            it = l['item']
            if it['line_total_cents'] != l['net'] or it.get('discount_cents', 0) != l['disc']:
                raise BusinessRuleError('Los descuentos cambiaron. Actualiza el ticket antes de cobrar.')

        total = sum(l['net'] for l in lines)
        discount_total = sum(l['disc'] for l in lines)
        if total != payload['total_cents'] or discount_total != payload.get('discount_total_cents', 0):
            raise BusinessRuleError('El total no coincide con los productos y descuentos del ticket.')

        reason = None
        if used:
            names = list(dict.fromkeys(d['name'] for d in used))
            reason = ' · '.join(names)
            if any(d['requires_authorization'] for d in used) and not self._has_permission(user['id'], DISCOUNT_PERM):
                auth_id = payload.get('authorized_by')
                if not auth_id or not self._has_permission(auth_id, DISCOUNT_PERM):
                    raise BusinessRuleError('Los descuentos aplicados requieren autorización de un supervisor.')
                sup = self.cursor.execute('SELECT username FROM users WHERE id = ?', (auth_id,)).fetchone()
                reason += f" (autorizó: {sup['username']})"
        return lines, total, discount_total, g_row, reason

    # ------------------------------------------------------------------ reintentos
    def _retry_result(self, sale_id, payload, branch_id, register_id, session_id):
        sale = self.cursor.execute('SELECT * FROM sales WHERE id = ?', (sale_id,)).fetchone()
        if not sale:
            return None
        if (sale['status'] != 'completed' or sale['deleted_at'] is not None or
                any(sale[k] != val for k, val in (('branch_id',branch_id),('cash_register_id',register_id),
                    ('cash_session_id',session_id),('user_id',payload.get('user_id')),('total',payload['total_cents'])))):
            raise BusinessRuleError('Ese identificador ya pertenece a otra operación. Verifica el ticket registrado.')
        def signature(items):
            return sorted((i['product_id'], i['sku'], str(self._quantity(i['quantity']).normalize()),
                           i['unit_price_cents'], i['line_total_cents']) for i in items)
        rows = self.cursor.execute('SELECT product_id, product_sku AS sku, quantity, unit_price AS unit_price_cents, '
            'line_total AS line_total_cents FROM sale_items WHERE sale_id = ? AND deleted_at IS NULL', (sale_id,)).fetchall()
        payments = self.cursor.execute('SELECT pm.method_type, sp.amount, sp.amount_tendered, sp.change_amount '
            'FROM sale_payments sp JOIN payment_methods pm ON pm.id = sp.payment_method_id '
            'WHERE sp.sale_id = ? AND sp.deleted_at IS NULL', (sale_id,)).fetchall()
        if (signature(rows) != signature(payload['items']) or len(payments) != 1 or
                tuple(payments[0]) != (payload['payment_method'], payload['total_cents'],
                                      payload['received_cents'], payload['change_cents'])):
            raise BusinessRuleError('Este intento no coincide con la venta guardada. Verifica su folio antes de continuar.')
        return {'success': True, 'sale_id': sale['ticket_number'], 'replayed': True,
                'print_warning': 'Venta recuperada: no se volvió a imprimir el ticket.'}

    # ------------------------------------------------------------------ venta
    def create_sale(self, payload, branch_id, register_id, session_id, cashier_name='Cajero'):
        payload = copy.deepcopy(payload)
        sale_id = self._validate_payload(payload)
        if self.db.in_transaction:
            raise BusinessRuleError('Hay otra operación pendiente en esta conexión.')
        now = self.get_timestamp()
        try:
            self.cursor.execute('BEGIN IMMEDIATE')
            user = self.cursor.execute('SELECT id, branch_id FROM users WHERE id = ? AND is_active = 1 '
                'AND deleted_at IS NULL', (payload.get('user_id'),)).fetchone()
            if not user or user['branch_id'] not in (None, branch_id):
                raise BusinessRuleError('El cajero no está activo o no pertenece a la sucursal.')
            previous = self._retry_result(sale_id, payload, branch_id, register_id, session_id)
            if previous:
                self.db.commit()
                return previous
            session = self.cursor.execute('SELECT cs.id FROM cash_sessions cs '
                'JOIN cash_registers cr ON cr.id = cs.cash_register_id '
                "WHERE cs.id = ? AND cs.status = 'open' AND cs.deleted_at IS NULL "
                'AND cs.cash_register_id = ? AND cs.branch_id = ? AND cr.branch_id = ? '
                'AND cr.is_active = 1 AND cr.deleted_at IS NULL',
                (session_id, register_id, branch_id, branch_id)).fetchone()
            if not session:
                raise BusinessRuleError('El turno está cerrado o no corresponde a esta caja y sucursal.')
            payment = self.cursor.execute('SELECT id FROM payment_methods WHERE method_type = ? '
                'AND deleted_at IS NULL', (payload['payment_method'],)).fetchall()
            if len(payment) != 1:
                raise BusinessRuleError('Configura exactamente un método de pago activo de este tipo.')
            customer_id = payload.get('customer_id') or None
            if customer_id and not self.cursor.execute('SELECT 1 FROM customers WHERE id = ? AND deleted_at IS NULL',
                                                       (customer_id,)).fetchone():
                raise BusinessRuleError('El cliente seleccionado ya no existe.')
            setting = self.cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'allow_negative_stock' "
                                          'AND deleted_at IS NULL').fetchone()
            allow_negative = setting is None or str(setting['setting_value']).strip().lower() in ('1','true','yes')
            validated = []
            for item in payload['items']:
                prod = self.cursor.execute('SELECT p.id, p.sku, p.name, p.sale_price, p.cost_price, p.track_inventory, '
                    'u.allows_decimals, COALESCE(s.quantity,0) AS stock FROM products p '
                    'JOIN units u ON u.id = p.unit_id LEFT JOIN inventory_stock s '
                    'ON s.product_id = p.id AND s.branch_id = ? AND s.deleted_at IS NULL '
                    'WHERE p.id = ? AND p.is_active = 1 AND p.deleted_at IS NULL',
                    (branch_id, item['product_id'])).fetchone()
                if not prod:
                    raise BusinessRuleError('Uno de los productos ya no está disponible.')
                qty = self._quantity(item['quantity'])
                if not prod['allows_decimals'] and qty != qty.to_integral_value():
                    raise BusinessRuleError(f"{prod['name']} solo admite unidades enteras.")
                price = self._integer(prod['sale_price'], 'Precio de catálogo')
                gross = int((qty * price).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                if item.get('sku') != prod['sku'] or item['unit_price_cents'] != price:
                    raise BusinessRuleError('El producto o su precio cambió. Actualiza el ticket antes de cobrar.')
                if prod['track_inventory'] and not allow_negative and qty > Decimal(str(prod['stock'])):
                    raise BusinessRuleError(f"Existencias insuficientes de {prod['name']}.")
                item['product_name'] = prod['name']
                validated.append((item, prod, qty, gross))

            lines, total, discount_total, g_row, reason = self._apply_discounts(payload, user, validated)
            if total <= 0:
                raise BusinessRuleError('El total de la venta debe ser mayor a cero.')

            folio = self.cursor.execute('SELECT COALESCE(MAX(folio_number), 0) + 1 AS next '
                'FROM sales WHERE cash_register_id = ?', (register_id,)).fetchone()['next']
            ticket = f'TKT-{folio:06d}'
            self.cursor.execute('INSERT INTO sales (id, branch_id, cash_register_id, cash_session_id, user_id, '
                'customer_id, discount_id, ticket_number, folio_number, subtotal, discount_total, total, '
                'discount_reason, status, sold_at, created_at, updated_at) '
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?)",
                (sale_id, branch_id, register_id, session_id, user['id'], customer_id,
                 g_row['id'] if g_row else None, ticket, folio, total, discount_total, total,
                 reason, now, now, now))
            for l in lines:
                prod, qty = l['prod'], l['qty']
                self.cursor.execute('INSERT INTO sale_items (id, sale_id, product_id, product_sku, product_name, '
                    'quantity, unit_price, unit_cost, discount_amount, line_subtotal, line_total, created_at, updated_at) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (self.generate_uuid(), sale_id, prod['id'], prod['sku'], prod['name'], str(qty),
                     prod['sale_price'], prod['cost_price'], l['disc'], l['net'], l['net'], now, now))
                if prod['track_inventory']:
                    self.cursor.execute('INSERT INTO inventory_movements (id, branch_id, product_id, user_id, '
                        'movement_type, quantity_change, unit_cost, sale_id, occurred_at, created_at, updated_at) '
                        "VALUES (?, ?, ?, ?, 'sale', ?, ?, ?, ?, ?, ?)",
                        (self.generate_uuid(), branch_id, prod['id'], user['id'], str(-qty), prod['cost_price'],
                         sale_id, now, now, now))
            self.cursor.execute('INSERT INTO sale_payments (id, sale_id, payment_method_id, amount, '
                'amount_tendered, change_amount, paid_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (self.generate_uuid(), sale_id, payment[0]['id'], total, payload['received_cents'],
                 payload['change_cents'], now, now, now))
            self.db.commit()
        except POSError:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            log.exception('Error registrando venta')
            raise POSError('No se pudo registrar la venta. El ticket se conserva.') from exc
        result = {'success': True, 'sale_id': ticket}
        try:
            if self.printer is None:
                from utils.printer import TicketPrinter
                self.printer = TicketPrinter()
            name = self.cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'business_name' "
                                       'AND deleted_at IS NULL').fetchone()
            printed = self.printer.print_ticket(name['setting_value'] if name else 'SotyPOS', ticket, cashier_name, payload)
            if printed is False:
                raise RuntimeError('La impresora no confirmó la impresión')
        except Exception:
            log.exception('Venta guardada; falló la impresión')
            result['print_warning'] = 'No se pudo imprimir. Revisa la impresora; no vuelvas a cobrar.'
        return result

    def get_sales_list(self, limit=100, search_query=""):
        """Obtiene la lista de ventas recientes, opcionalmente filtrada por ticket."""
        query = """
            SELECT s.id, s.ticket_number, s.total, s.status, s.sold_at, u.username AS cashier_name
            FROM sales s
            LEFT JOIN users u ON u.id = s.user_id
            WHERE s.deleted_at IS NULL
        """
        params = []
        if search_query:
            query += " AND s.ticket_number LIKE ?"
            params.append(f"%{search_query}%")

        query += " ORDER BY s.sold_at DESC LIMIT ?"
        params.append(limit)

        return self.cursor.execute(query, params).fetchall()

    def get_sale_details(self, sale_id):
        """Obtiene los productos y el detalle de pago de una venta específica."""
        items = self.cursor.execute("""
            SELECT product_sku, product_name, quantity, unit_price, discount_amount, line_total
            FROM sale_items
            WHERE sale_id = ? AND deleted_at IS NULL
        """, (sale_id,)).fetchall()

        payment = self.cursor.execute("""
            SELECT pm.method_type, sp.amount_tendered, sp.change_amount
            FROM sale_payments sp
            JOIN payment_methods pm ON pm.id = sp.payment_method_id
            WHERE sp.sale_id = ? AND sp.deleted_at IS NULL
        """, (sale_id,)).fetchone()

        return {'items': items, 'payment': payment}