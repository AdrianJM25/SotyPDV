-- =====================================================================
--  POS OFFLINE-FIRST  ·  Datos semilla (OPCIONAL)  ·  ejecutar DESPUÉS de pos_schema_sqlite.sql
-- =====================================================================
--  IMPORTANTE (multi-tenant / varias cajas):
--    Los ids se generan al azar, así que este script debe correr UNA sola vez por
--    cliente (tenant), en la primera instalación. Las demás cajas deben recibir estos
--    registros por sincronización inicial (pull), o terminarás con catálogos duplicados.
--    Lo ideal en el SaaS: que Laravel haga el provisioning y la caja solo lo descargue.
--
--  Es idempotente en la misma base local (INSERT OR IGNORE + índices únicos parciales).
--  Los datos que SÍ debe crear el asistente de primer uso (en Python): sucursal,
--  caja, usuario administrador con su PIN hasheado.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- Unidades de medida
INSERT OR IGNORE INTO units (code, name, allows_decimals) VALUES
    ('PZA',  'Pieza',     0),
    ('CAJA', 'Caja',      0),
    ('KG',   'Kilogramo', 1),
    ('GR',   'Gramo',     1),
    ('LT',   'Litro',     1),
    ('ML',   'Mililitro', 1);

-- Impuestos (ajusta a tu país)
INSERT OR IGNORE INTO tax_rates (code, name, rate, is_default) VALUES
    ('IVA16',  'IVA 16%', 16.0, 1),
    ('IVA0',   'IVA 0%',   0.0, 0),
    ('EXENTO', 'Exento',   0.0, 0);

-- Métodos de pago
INSERT OR IGNORE INTO payment_methods (code, name, method_type, requires_reference, opens_cash_drawer, sort_order) VALUES
    ('CASH',     'Efectivo',      'cash',     0, 1, 1),
    ('CARD',     'Tarjeta',       'card',     1, 0, 2),
    ('TRANSFER', 'Transferencia', 'transfer', 1, 0, 3),
    ('VOUCHER',  'Vales',         'voucher',  1, 0, 4);

-- Cliente genérico para ventas de mostrador
INSERT INTO customers (name, is_default)
SELECT 'Público en general', 1
WHERE NOT EXISTS (SELECT 1 FROM customers WHERE is_default = 1 AND deleted_at IS NULL);

-- Configuración inicial
INSERT OR IGNORE INTO settings (setting_key, setting_value, value_type, description) VALUES
    ('business_name',        'Mi Negocio',  'string',  'Nombre que aparece en el ticket'),
    ('currency_code',        'MXN',         'string',  'Moneda ISO 4217'),
    ('currency_symbol',      '$',           'string',  'Símbolo de moneda'),
    ('prices_include_tax',   'true',        'boolean', 'Los precios de venta ya incluyen impuesto'),
    ('allow_negative_stock', 'true',        'boolean', 'Permitir vender sin existencia registrada'),
    ('ticket_width_mm',      '80',          'integer', 'Ancho del papel térmico'),
    ('ticket_header',        '',            'string',  'Texto superior del ticket'),
    ('ticket_footer',        '¡Gracias por su compra!', 'string', 'Texto inferior del ticket'),
    ('pin_max_attempts',     '5',           'integer', 'Intentos de PIN antes de bloquear'),
    ('pin_lock_minutes',     '5',           'integer', 'Minutos de bloqueo tras exceder intentos');

-- Roles base
INSERT OR IGNORE INTO roles (name, description, is_system) VALUES
    ('Administrador', 'Acceso total al sistema',                      1),
    ('Supervisor',    'Operación completa, sin gestión de usuarios',  1),
    ('Cajero',        'Ventas y manejo de su propio turno de caja',   1);

-- Permisos
INSERT OR IGNORE INTO permissions (code, name, module) VALUES
    ('sales.create',          'Realizar ventas',                    'sales'),
    ('sales.discount',        'Aplicar descuentos',                 'sales'),
    ('sales.price_override',  'Modificar precio en venta',          'sales'),
    ('sales.cancel',          'Cancelar ventas',                    'sales'),
    ('sales.return',          'Procesar devoluciones',              'sales'),
    ('sales.view_all',        'Ver ventas de otros cajeros',        'sales'),
    ('cash.open',             'Abrir turno de caja',                'cash'),
    ('cash.close',            'Cerrar turno de caja',               'cash'),
    ('cash.movements',        'Registrar entradas/salidas de efectivo', 'cash'),
    ('cash.view_reports',     'Ver cortes de caja',                 'cash'),
    ('products.view',         'Consultar productos',                'catalog'),
    ('products.manage',       'Crear/editar productos',             'catalog'),
    ('products.change_price', 'Cambiar costos y precios',           'catalog'),
    ('categories.manage',     'Administrar categorías',             'catalog'),
    ('inventory.view',        'Consultar inventario y kardex',      'inventory'),
    ('inventory.adjust',      'Realizar ajustes de inventario',     'inventory'),
    ('inventory.shrinkage',   'Registrar mermas',                   'inventory'),
    ('suppliers.manage',      'Administrar proveedores',            'purchases'),
    ('purchases.view',        'Consultar compras',                  'purchases'),
    ('purchases.manage',      'Registrar compras',                  'purchases'),
    ('customers.view',        'Consultar clientes',                 'customers'),
    ('customers.manage',      'Crear/editar clientes',              'customers'),
    ('reports.view',          'Ver reportes',                       'reports'),
    ('users.manage',          'Administrar usuarios',               'admin'),
    ('roles.manage',          'Administrar roles y permisos',       'admin'),
    ('settings.manage',       'Cambiar configuración',              'admin');

-- Administrador: todos los permisos
INSERT OR IGNORE INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r CROSS JOIN permissions p
WHERE r.name = 'Administrador' AND r.deleted_at IS NULL AND p.deleted_at IS NULL;

-- Supervisor: todo excepto administración de usuarios/roles/configuración
INSERT OR IGNORE INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r CROSS JOIN permissions p
WHERE r.name = 'Supervisor' AND r.deleted_at IS NULL AND p.deleted_at IS NULL
  AND p.code NOT IN ('users.manage', 'roles.manage', 'settings.manage');

-- Cajero: operación básica de mostrador
INSERT OR IGNORE INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r JOIN permissions p
  ON p.code IN ('sales.create', 'cash.open', 'cash.close', 'cash.movements',
                'products.view', 'inventory.view', 'customers.view', 'customers.manage')
WHERE r.name = 'Cajero' AND r.deleted_at IS NULL AND p.deleted_at IS NULL;
