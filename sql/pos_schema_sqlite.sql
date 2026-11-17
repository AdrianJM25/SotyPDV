-- =====================================================================
--  POS OFFLINE-FIRST  ·  Esquema local SQLite3  ·  v1.0
-- =====================================================================
--  REGLAS DE SINCRONIZACIÓN (aplican a TODAS las tablas):
--    1. id TEXT = UUID (36 chars). Genera el UUID en Python (uuid4 o, mejor, uuid7).
--       El DEFAULT de cada id es solo una red de seguridad (UUID v4 válido).
--    2. sync_status INTEGER: 0 = pendiente de subir, 1 = sincronizado.
--    3. created_at / updated_at / deleted_at en TEXT ISO-8601 UTC
--       ('2026-10-13T18:30:00.123Z'). Nunca se borra físicamente: se llena deleted_at.
--
--  CONVENCIONES:
--    * Dinero: INTEGER en centavos (1250 = $12.50)  -> en PostgreSQL: bigint o numeric.
--    * Cantidades: REAL (permiten kg, lt, etc.).
--    * Porcentajes: REAL (16.0 = 16 %).
--    * Booleanos: INTEGER 0/1.
--    * Los índices UNIQUE son PARCIALES (WHERE deleted_at IS NULL) para que un registro
--      eliminado lógicamente no bloquee reutilizar su SKU, código de barras, etc.
--
--  USO EN CADA CONEXIÓN (PRAGMA no persiste foreign_keys):
--      PRAGMA foreign_keys = ON;
--      PRAGMA journal_mode = WAL;
--  NO activar PRAGMA recursive_triggers.
--
--  TRIGGERS DE SINCRONIZACIÓN:
--    * Cualquier UPDATE normal de la app refresca updated_at y pone sync_status = 0.
--    * Al marcar como sincronizado usa:
--        UPDATE <tabla> SET sync_status = 1 WHERE id = ? AND updated_at = ?;
--      (el filtro por updated_at evita marcar como enviado un cambio hecho durante el push).
--    * Al aplicar datos descargados de la nube (pull), escribe updated_at del servidor
--      y sync_status = 1 en el mismo UPDATE/UPSERT: el trigger no se dispara.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- =====================================================================
-- 0. CONFIGURACIÓN Y ESTRUCTURA DEL NEGOCIO
-- =====================================================================

-- Configuración clave/valor (moneda, ticket, impuestos incluidos, etc.)
CREATE TABLE IF NOT EXISTS settings (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    setting_key   TEXT NOT NULL,
    setting_value TEXT,
    value_type    TEXT NOT NULL DEFAULT 'string'
                  CHECK (value_type IN ('string','integer','decimal','boolean','json')),
    description   TEXT,
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_settings_key ON settings (setting_key) WHERE deleted_at IS NULL;

-- Sucursales
CREATE TABLE IF NOT EXISTS branches (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    address     TEXT,
    city        TEXT,
    state       TEXT,
    postal_code TEXT,
    phone       TEXT,
    email       TEXT,
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_branches_code ON branches (code) WHERE deleted_at IS NULL;

-- Cajas / terminales físicas (cada PC con el POS instalado)
CREATE TABLE IF NOT EXISTS cash_registers (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    branch_id         TEXT NOT NULL REFERENCES branches (id),
    code              TEXT NOT NULL,                 -- Ej: 'C01'
    name              TEXT NOT NULL,                 -- Ej: 'Caja principal'
    ticket_series     TEXT NOT NULL DEFAULT 'A',     -- Serie del folio: 'A', 'B'...
    device_identifier TEXT,                          -- Identificador del equipo
    is_active         INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_cash_registers_code ON cash_registers (branch_id, code) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_cash_registers_branch ON cash_registers (branch_id);


-- =====================================================================
-- 1. USUARIOS Y PERMISOS
-- =====================================================================

CREATE TABLE IF NOT EXISTS roles (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    name        TEXT NOT NULL,                       -- 'Administrador', 'Supervisor', 'Cajero'
    description TEXT,
    is_system   INTEGER NOT NULL DEFAULT 0 CHECK (is_system IN (0,1)),  -- 1 = no editable
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_roles_name ON roles (name) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS permissions (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    code        TEXT NOT NULL,                       -- Ej: 'sales.cancel'
    name        TEXT NOT NULL,
    module      TEXT NOT NULL,                       -- Ej: 'sales', 'inventory'
    description TEXT,
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_permissions_code ON permissions (code) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS role_permissions (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    role_id       TEXT NOT NULL REFERENCES roles (id),
    permission_id TEXT NOT NULL REFERENCES permissions (id),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_role_permissions ON role_permissions (role_id, permission_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_role_permissions_permission ON role_permissions (permission_id);

CREATE TABLE IF NOT EXISTS users (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    branch_id           TEXT REFERENCES branches (id),   -- NULL = acceso a todas las sucursales
    role_id             TEXT NOT NULL REFERENCES roles (id),
    username            TEXT NOT NULL,
    full_name           TEXT NOT NULL,
    email               TEXT,
    phone               TEXT,
    password_hash       TEXT,                            -- Para panel admin / nube (bcrypt/argon2)
    pin_hash            TEXT,                            -- PIN de caja, SIEMPRE hasheado con sal
    pin_failed_attempts INTEGER NOT NULL DEFAULT 0 CHECK (pin_failed_attempts >= 0),
    pin_locked_until    TEXT,                            -- Bloqueo temporal tras N intentos
    is_active           INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    last_login_at       TEXT,
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username ON users (username) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON users (email) WHERE deleted_at IS NULL AND email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_role ON users (role_id);
CREATE INDEX IF NOT EXISTS idx_users_branch ON users (branch_id);

-- Bitácora de auditoría (cancelaciones, descuentos, cambios de precio, accesos...)
CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    user_id          TEXT REFERENCES users (id),
    branch_id        TEXT REFERENCES branches (id),
    cash_register_id TEXT REFERENCES cash_registers (id),
    action           TEXT NOT NULL,                      -- Ej: 'sale.cancel', 'product.price_change'
    entity_type      TEXT,                               -- Ej: 'sales'
    entity_id        TEXT,                               -- UUID del registro afectado (sin FK: polimórfico)
    old_values       TEXT,                               -- JSON
    new_values       TEXT,                               -- JSON
    description      TEXT,
    occurred_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_occurred ON audit_logs (occurred_at);


-- =====================================================================
-- 2. CATÁLOGO DE PRODUCTOS
--    Montos de dinero: INTEGER en centavos (1250 = $12.50).
--    Cantidades: REAL (permiten venta por peso/volumen).
-- =====================================================================

CREATE TABLE IF NOT EXISTS units (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    code           TEXT NOT NULL,                        -- 'PZA', 'KG', 'LT'
    name           TEXT NOT NULL,
    allows_decimals INTEGER NOT NULL DEFAULT 0 CHECK (allows_decimals IN (0,1)),
    is_active      INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_units_code ON units (code) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS tax_rates (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    code       TEXT NOT NULL,                            -- 'IVA16', 'IVA0', 'EXENTO'
    name       TEXT NOT NULL,
    rate       REAL NOT NULL DEFAULT 0 CHECK (rate >= 0 AND rate <= 100),   -- Porcentaje: 16.0
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0,1)),
    is_active  INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_tax_rates_code ON tax_rates (code) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS categories (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    parent_id   TEXT REFERENCES categories (id),         -- Subcategorías (auto-referencia)
    name        TEXT NOT NULL,
    description TEXT,
    color       TEXT,                                    -- Hex para botones táctiles: '#FF8800'
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories (parent_id);
CREATE INDEX IF NOT EXISTS idx_categories_name ON categories (name);


-- Proveedores (definido antes de products porque este lo referencia)
CREATE TABLE IF NOT EXISTS suppliers (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    code               TEXT,
    name               TEXT NOT NULL,                    -- Nombre comercial
    legal_name         TEXT,                             -- Razón social
    tax_id             TEXT,                             -- RFC / NIT / etc.
    contact_name       TEXT,
    phone              TEXT,
    email              TEXT,
    address            TEXT,
    city               TEXT,
    state              TEXT,
    postal_code        TEXT,
    payment_terms_days INTEGER NOT NULL DEFAULT 0 CHECK (payment_terms_days >= 0),
    notes              TEXT,
    is_active          INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_suppliers_code ON suppliers (code) WHERE deleted_at IS NULL AND code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers (name);

CREATE TABLE IF NOT EXISTS products (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    category_id         TEXT REFERENCES categories (id),
    unit_id             TEXT NOT NULL REFERENCES units (id),
    tax_rate_id         TEXT REFERENCES tax_rates (id),
    default_supplier_id TEXT REFERENCES suppliers (id),
    sku                 TEXT NOT NULL,
    name                TEXT NOT NULL,
    description         TEXT,
    cost_price          INTEGER NOT NULL DEFAULT 0 CHECK (cost_price >= 0),   -- Precio de compra (centavos)
    sale_price          INTEGER NOT NULL DEFAULT 0 CHECK (sale_price >= 0),   -- Precio de venta (centavos)
    track_inventory     INTEGER NOT NULL DEFAULT 1 CHECK (track_inventory IN (0,1)),  -- 0 = servicio / sin stock
    min_stock           REAL NOT NULL DEFAULT 0 CHECK (min_stock >= 0),
    max_stock           REAL CHECK (max_stock IS NULL OR max_stock >= 0),
    image_path          TEXT,
    is_active           INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_products_sku ON products (sku) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_products_name ON products (name);
CREATE INDEX IF NOT EXISTS idx_products_category ON products (category_id);
CREATE INDEX IF NOT EXISTS idx_products_unit ON products (unit_id);
CREATE INDEX IF NOT EXISTS idx_products_tax_rate ON products (tax_rate_id);
CREATE INDEX IF NOT EXISTS idx_products_supplier ON products (default_supplier_id);

-- Un producto puede tener varios códigos de barras (presentaciones, EAN/UPC alternos)
CREATE TABLE IF NOT EXISTS product_barcodes (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    product_id TEXT NOT NULL REFERENCES products (id),
    barcode    TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0,1)),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_product_barcodes_barcode ON product_barcodes (barcode) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_product_barcodes_product ON product_barcodes (product_id);

-- Historial de cambios de costo/precio
CREATE TABLE IF NOT EXISTS product_price_history (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    product_id     TEXT NOT NULL REFERENCES products (id),
    changed_by     TEXT REFERENCES users (id),
    old_cost_price INTEGER,
    new_cost_price INTEGER,
    old_sale_price INTEGER,
    new_sale_price INTEGER,
    reason         TEXT,
    changed_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_price_history_product ON product_price_history (product_id, changed_at);


-- =====================================================================
-- 3. CLIENTES
-- =====================================================================

CREATE TABLE IF NOT EXISTS customers (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    code        TEXT,
    name        TEXT NOT NULL,
    legal_name  TEXT,                                    -- Razón social (para facturar)
    tax_id      TEXT,                                    -- RFC / NIT / etc.
    phone       TEXT,
    email       TEXT,
    address     TEXT,
    city        TEXT,
    state       TEXT,
    postal_code TEXT,
    birth_date  TEXT,                                    -- ISO 'YYYY-MM-DD'
    notes       TEXT,
    is_default  INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0,1)),  -- 1 = 'Público en general'
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_customers_code ON customers (code) WHERE deleted_at IS NULL AND code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customers_name ON customers (name);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers (phone);
CREATE INDEX IF NOT EXISTS idx_customers_tax_id ON customers (tax_id);


-- =====================================================================
-- 4. MÉTODOS DE PAGO Y DESCUENTOS (catálogos usados por ventas y caja)
-- =====================================================================

CREATE TABLE IF NOT EXISTS payment_methods (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    code               TEXT NOT NULL,                    -- 'CASH', 'CARD', 'TRANSFER'
    name               TEXT NOT NULL,
    method_type        TEXT NOT NULL CHECK (method_type IN ('cash','card','transfer','voucher','other')),
    requires_reference INTEGER NOT NULL DEFAULT 0 CHECK (requires_reference IN (0,1)),  -- Folio de voucher, etc.
    opens_cash_drawer  INTEGER NOT NULL DEFAULT 0 CHECK (opens_cash_drawer IN (0,1)),
    sort_order         INTEGER NOT NULL DEFAULT 0,
    is_active          INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_payment_methods_code ON payment_methods (code) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS discounts (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    name                   TEXT NOT NULL,
    discount_type          TEXT NOT NULL CHECK (discount_type IN ('percent','fixed')),
    value                  REAL NOT NULL CHECK (value > 0),    -- % (10.0) o monto en centavos si 'fixed'
    requires_authorization INTEGER NOT NULL DEFAULT 0 CHECK (requires_authorization IN (0,1)),
    valid_from             TEXT,
    valid_until            TEXT,
    is_active              INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_discounts_name ON discounts (name);


-- =====================================================================
-- 5. CONTROL DE CAJA (TURNOS)
-- =====================================================================

CREATE TABLE IF NOT EXISTS cash_sessions (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    branch_id           TEXT NOT NULL REFERENCES branches (id),
    cash_register_id    TEXT NOT NULL REFERENCES cash_registers (id),
    opened_by_user_id   TEXT NOT NULL REFERENCES users (id),
    closed_by_user_id   TEXT REFERENCES users (id),
    status              TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
    opening_amount      INTEGER NOT NULL DEFAULT 0 CHECK (opening_amount >= 0),  -- Fondo inicial
    opened_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    closed_at           TEXT,
    expected_cash_amount INTEGER,                        -- Snapshot al cerrar (ver v_cash_session_balance)
    counted_cash_amount  INTEGER,                        -- Efectivo contado físicamente
    cash_difference      INTEGER,                        -- counted - expected (negativo = faltante)
    opening_notes       TEXT,
    closing_notes       TEXT,
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT,
    CHECK (
        (status = 'open'   AND closed_at IS NULL)
        OR
        (status = 'closed' AND closed_at IS NOT NULL AND closed_by_user_id IS NOT NULL)
    )
);
-- Solo un turno abierto por caja
CREATE UNIQUE INDEX IF NOT EXISTS ux_cash_sessions_one_open
    ON cash_sessions (cash_register_id) WHERE status = 'open' AND deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_cash_sessions_register ON cash_sessions (cash_register_id, opened_at);
CREATE INDEX IF NOT EXISTS idx_cash_sessions_branch ON cash_sessions (branch_id);
CREATE INDEX IF NOT EXISTS idx_cash_sessions_opened_by ON cash_sessions (opened_by_user_id);

-- Arqueo por denominaciones (billetes y monedas), en apertura y/o cierre
CREATE TABLE IF NOT EXISTS cash_session_denominations (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    cash_session_id TEXT NOT NULL REFERENCES cash_sessions (id),
    count_type      TEXT NOT NULL CHECK (count_type IN ('opening','closing')),
    denomination    INTEGER NOT NULL CHECK (denomination > 0),   -- Centavos: $500 = 50000
    quantity        INTEGER NOT NULL CHECK (quantity >= 0),
    subtotal        INTEGER NOT NULL CHECK (subtotal >= 0),      -- denomination * quantity
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT,
    CHECK (subtotal = denomination * quantity)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_cash_denominations
    ON cash_session_denominations (cash_session_id, count_type, denomination) WHERE deleted_at IS NULL;

-- Resumen de cierre por método de pago (corte Z)
CREATE TABLE IF NOT EXISTS cash_session_totals (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    cash_session_id   TEXT NOT NULL REFERENCES cash_sessions (id),
    payment_method_id TEXT NOT NULL REFERENCES payment_methods (id),
    sales_amount      INTEGER NOT NULL DEFAULT 0,
    refunds_amount    INTEGER NOT NULL DEFAULT 0,
    expected_amount   INTEGER NOT NULL DEFAULT 0,
    counted_amount    INTEGER,                           -- NULL si no se contó (ej. transferencias)
    difference_amount INTEGER,
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_cash_session_totals
    ON cash_session_totals (cash_session_id, payment_method_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_cash_session_totals_method ON cash_session_totals (payment_method_id);

-- Entradas y salidas manuales de efectivo durante el turno
CREATE TABLE IF NOT EXISTS cash_movements (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    cash_session_id        TEXT NOT NULL REFERENCES cash_sessions (id),
    user_id                TEXT NOT NULL REFERENCES users (id),
    authorized_by_user_id  TEXT REFERENCES users (id),
    supplier_id            TEXT REFERENCES suppliers (id),   -- Pago a proveedor desde caja
    movement_type          TEXT NOT NULL CHECK (movement_type IN ('cash_in','cash_out')),
    category               TEXT NOT NULL DEFAULT 'other'
                           CHECK (category IN ('deposit','change_fund','withdrawal','expense','supplier_payment','other')),
    amount                 INTEGER NOT NULL CHECK (amount > 0),   -- Siempre positivo; el signo lo da movement_type
    description            TEXT NOT NULL,
    occurred_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_cash_movements_session ON cash_movements (cash_session_id);
CREATE INDEX IF NOT EXISTS idx_cash_movements_user ON cash_movements (user_id);
CREATE INDEX IF NOT EXISTS idx_cash_movements_supplier ON cash_movements (supplier_id);


-- =====================================================================
-- 6. COMPRAS A PROVEEDORES
-- =====================================================================

CREATE TABLE IF NOT EXISTS purchases (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    supplier_id             TEXT NOT NULL REFERENCES suppliers (id),
    branch_id               TEXT NOT NULL REFERENCES branches (id),
    user_id                 TEXT NOT NULL REFERENCES users (id),
    supplier_invoice_number TEXT,                        -- Folio de la factura/remisión del proveedor
    status                  TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','received','cancelled')),
    purchase_date           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    received_at             TEXT,
    subtotal                INTEGER NOT NULL DEFAULT 0 CHECK (subtotal >= 0),
    tax_total               INTEGER NOT NULL DEFAULT 0 CHECK (tax_total >= 0),
    total                   INTEGER NOT NULL DEFAULT 0 CHECK (total >= 0),
    notes                   TEXT,
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT,
    CHECK (total = subtotal + tax_total)
);
CREATE INDEX IF NOT EXISTS idx_purchases_supplier ON purchases (supplier_id);
CREATE INDEX IF NOT EXISTS idx_purchases_branch ON purchases (branch_id, purchase_date);
CREATE INDEX IF NOT EXISTS idx_purchases_user ON purchases (user_id);

CREATE TABLE IF NOT EXISTS purchase_items (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    purchase_id   TEXT NOT NULL REFERENCES purchases (id),
    product_id    TEXT NOT NULL REFERENCES products (id),
    quantity      REAL NOT NULL CHECK (quantity > 0),
    unit_cost     INTEGER NOT NULL CHECK (unit_cost >= 0),     -- Centavos, antes de impuestos
    tax_rate      REAL NOT NULL DEFAULT 0 CHECK (tax_rate >= 0),  -- % aplicado (snapshot)
    line_subtotal INTEGER NOT NULL CHECK (line_subtotal >= 0),
    tax_amount    INTEGER NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
    line_total    INTEGER NOT NULL CHECK (line_total >= 0),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT,
    CHECK (line_total = line_subtotal + tax_amount)
);
CREATE INDEX IF NOT EXISTS idx_purchase_items_purchase ON purchase_items (purchase_id);
CREATE INDEX IF NOT EXISTS idx_purchase_items_product ON purchase_items (product_id);


-- =====================================================================
-- 7. VENTAS
--    Convención de montos (todo en centavos, ya con descuentos aplicados):
--      line_subtotal = base gravable de la línea (después de descuento, antes de impuesto)
--      line_total    = line_subtotal + tax_amount
--      sales.subtotal = SUM(line_subtotal) ; sales.tax_total = SUM(tax_amount)
--      sales.total    = subtotal + tax_total
--      sales.discount_total = descuentos otorgados (informativo; ya descontados arriba).
--    Un descuento global del ticket se prorratea en las líneas para calcular bien el impuesto.
-- =====================================================================

CREATE TABLE IF NOT EXISTS sales (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    branch_id            TEXT NOT NULL REFERENCES branches (id),
    cash_register_id     TEXT NOT NULL REFERENCES cash_registers (id),
    cash_session_id      TEXT NOT NULL REFERENCES cash_sessions (id),
    user_id              TEXT NOT NULL REFERENCES users (id),          -- Cajero que realizó la venta
    customer_id          TEXT REFERENCES customers (id),
    discount_id          TEXT REFERENCES discounts (id),               -- Descuento global aplicado (si hubo)
    ticket_number        TEXT NOT NULL,                                -- Ej: 'C01-A-000123'
    folio_number         INTEGER NOT NULL CHECK (folio_number > 0),    -- Consecutivo por caja
    status               TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('held','completed','cancelled')),
    prices_include_tax   INTEGER NOT NULL DEFAULT 1 CHECK (prices_include_tax IN (0,1)),  -- Snapshot del setting
    subtotal             INTEGER NOT NULL DEFAULT 0 CHECK (subtotal >= 0),
    discount_total       INTEGER NOT NULL DEFAULT 0 CHECK (discount_total >= 0),
    tax_total            INTEGER NOT NULL DEFAULT 0 CHECK (tax_total >= 0),
    total                INTEGER NOT NULL DEFAULT 0 CHECK (total >= 0),
    discount_reason      TEXT,
    notes                TEXT,
    sold_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    cancelled_at         TEXT,
    cancelled_by_user_id TEXT REFERENCES users (id),
    cancel_reason        TEXT,
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT,
    CHECK (total = subtotal + tax_total),
    CHECK (status <> 'cancelled' OR (cancelled_at IS NOT NULL AND cancel_reason IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_sales_register_folio ON sales (cash_register_id, folio_number) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_sales_ticket ON sales (ticket_number);
CREATE INDEX IF NOT EXISTS idx_sales_branch_date ON sales (branch_id, sold_at);
CREATE INDEX IF NOT EXISTS idx_sales_session ON sales (cash_session_id);
CREATE INDEX IF NOT EXISTS idx_sales_user ON sales (user_id);
CREATE INDEX IF NOT EXISTS idx_sales_customer ON sales (customer_id);
CREATE INDEX IF NOT EXISTS idx_sales_discount ON sales (discount_id);
CREATE INDEX IF NOT EXISTS idx_sales_status ON sales (status);

CREATE TABLE IF NOT EXISTS sale_items (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    sale_id         TEXT NOT NULL REFERENCES sales (id),
    product_id      TEXT NOT NULL REFERENCES products (id),
    product_sku     TEXT NOT NULL,                       -- Snapshot: el producto puede cambiar después
    product_name    TEXT NOT NULL,                       -- Snapshot
    quantity        REAL NOT NULL CHECK (quantity > 0),
    unit_price      INTEGER NOT NULL CHECK (unit_price >= 0),     -- Precio de lista cobrado por unidad
    unit_cost       INTEGER NOT NULL DEFAULT 0 CHECK (unit_cost >= 0),  -- Snapshot del costo (para utilidad)
    discount_amount INTEGER NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    tax_rate_id     TEXT REFERENCES tax_rates (id),
    tax_rate        REAL NOT NULL DEFAULT 0 CHECK (tax_rate >= 0),     -- % aplicado (snapshot)
    line_subtotal   INTEGER NOT NULL CHECK (line_subtotal >= 0),
    tax_amount      INTEGER NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
    line_total      INTEGER NOT NULL CHECK (line_total >= 0),
    notes           TEXT,
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT,
    CHECK (line_total = line_subtotal + tax_amount)
);
CREATE INDEX IF NOT EXISTS idx_sale_items_sale ON sale_items (sale_id);
CREATE INDEX IF NOT EXISTS idx_sale_items_product ON sale_items (product_id);
CREATE INDEX IF NOT EXISTS idx_sale_items_tax_rate ON sale_items (tax_rate_id);

-- Pagos de la venta (soporta pago mixto: parte efectivo, parte tarjeta)
CREATE TABLE IF NOT EXISTS sale_payments (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    sale_id           TEXT NOT NULL REFERENCES sales (id),
    payment_method_id TEXT NOT NULL REFERENCES payment_methods (id),
    amount            INTEGER NOT NULL CHECK (amount > 0),            -- Monto aplicado a la venta (sin cambio)
    amount_tendered   INTEGER CHECK (amount_tendered IS NULL OR amount_tendered >= amount),  -- Lo que entregó el cliente
    change_amount     INTEGER NOT NULL DEFAULT 0 CHECK (change_amount >= 0),
    reference         TEXT,                                           -- Autorización de tarjeta, folio de transferencia
    paid_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_sale_payments_sale ON sale_payments (sale_id);
CREATE INDEX IF NOT EXISTS idx_sale_payments_method ON sale_payments (payment_method_id);

-- Devoluciones
CREATE TABLE IF NOT EXISTS sale_returns (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    sale_id                  TEXT NOT NULL REFERENCES sales (id),
    branch_id                TEXT NOT NULL REFERENCES branches (id),
    cash_session_id          TEXT REFERENCES cash_sessions (id),      -- Turno en el que se entregó el reembolso
    user_id                  TEXT NOT NULL REFERENCES users (id),
    authorized_by_user_id    TEXT REFERENCES users (id),
    refund_payment_method_id TEXT NOT NULL REFERENCES payment_methods (id),
    reason                   TEXT,
    subtotal                 INTEGER NOT NULL DEFAULT 0 CHECK (subtotal >= 0),
    tax_total                INTEGER NOT NULL DEFAULT 0 CHECK (tax_total >= 0),
    total                    INTEGER NOT NULL DEFAULT 0 CHECK (total >= 0),
    returned_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT,
    CHECK (total = subtotal + tax_total)
);
CREATE INDEX IF NOT EXISTS idx_sale_returns_sale ON sale_returns (sale_id);
CREATE INDEX IF NOT EXISTS idx_sale_returns_session ON sale_returns (cash_session_id);
CREATE INDEX IF NOT EXISTS idx_sale_returns_user ON sale_returns (user_id);
CREATE INDEX IF NOT EXISTS idx_sale_returns_method ON sale_returns (refund_payment_method_id);

CREATE TABLE IF NOT EXISTS sale_return_items (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    sale_return_id TEXT NOT NULL REFERENCES sale_returns (id),
    sale_item_id   TEXT NOT NULL REFERENCES sale_items (id),
    product_id     TEXT NOT NULL REFERENCES products (id),
    quantity       REAL NOT NULL CHECK (quantity > 0),
    line_subtotal  INTEGER NOT NULL CHECK (line_subtotal >= 0),
    tax_amount     INTEGER NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
    line_total     INTEGER NOT NULL CHECK (line_total >= 0),
    restock        INTEGER NOT NULL DEFAULT 1 CHECK (restock IN (0,1)),  -- 1 = regresa a inventario, 0 = merma
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT,
    CHECK (line_total = line_subtotal + tax_amount)
);
CREATE INDEX IF NOT EXISTS idx_sale_return_items_return ON sale_return_items (sale_return_id);
CREATE INDEX IF NOT EXISTS idx_sale_return_items_item ON sale_return_items (sale_item_id);
CREATE INDEX IF NOT EXISTS idx_sale_return_items_product ON sale_return_items (product_id);


-- =====================================================================
-- 8. INVENTARIO Y KARDEX
--    inventory_movements = FUENTE DE VERDAD (append-only, inmutable).
--    inventory_stock     = existencia actual por producto/sucursal; la mantiene
--                          el trigger trg_inventory_movements_apply (no escribir a mano).
-- =====================================================================

CREATE TABLE IF NOT EXISTS inventory_stock (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    product_id TEXT NOT NULL REFERENCES products (id),
    branch_id  TEXT NOT NULL REFERENCES branches (id),
    quantity   REAL NOT NULL DEFAULT 0,                  -- Puede ser negativo si se permite vender sin existencia
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT,
    UNIQUE (product_id, branch_id)
);
CREATE INDEX IF NOT EXISTS idx_inventory_stock_branch ON inventory_stock (branch_id);

CREATE TABLE IF NOT EXISTS inventory_movements (
    id TEXT NOT NULL PRIMARY KEY
        DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + (abs(random()) % 4), 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
        CHECK (length(id) = 36),
    branch_id        TEXT NOT NULL REFERENCES branches (id),
    product_id       TEXT NOT NULL REFERENCES products (id),
    user_id          TEXT REFERENCES users (id),
    movement_type    TEXT NOT NULL CHECK (movement_type IN (
                         -- ENTRADAS (quantity_change > 0)
                         'initial',          -- Inventario inicial
                         'purchase',         -- Compra a proveedor
                         'sale_return',      -- Devolución de cliente / cancelación de venta
                         'adjustment_in',    -- Ajuste positivo (conteo físico)
                         'transfer_in',      -- Traspaso recibido
                         -- SALIDAS (quantity_change < 0)
                         'sale',             -- Venta
                         'purchase_return',  -- Devolución a proveedor
                         'adjustment_out',   -- Ajuste negativo (conteo físico)
                         'shrinkage',        -- Merma (caducidad, daño, robo)
                         'transfer_out'      -- Traspaso enviado
                     )),
    quantity_change  REAL NOT NULL,                      -- Con signo: + entra, - sale
    unit_cost        INTEGER NOT NULL DEFAULT 0 CHECK (unit_cost >= 0),  -- Costo unitario al momento del movimiento
    stock_after      REAL,                               -- Saldo resultante (lo llena el trigger)
    -- Documento origen (a lo más uno)
    sale_id          TEXT REFERENCES sales (id),
    sale_return_id   TEXT REFERENCES sale_returns (id),
    purchase_id      TEXT REFERENCES purchases (id),
    reason           TEXT,                               -- Obligatorio en la práctica para mermas/ajustes
    occurred_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    sync_status INTEGER NOT NULL DEFAULT 0 CHECK (sync_status IN (0,1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at  TEXT,
    CHECK (
        (movement_type IN ('initial','purchase','sale_return','adjustment_in','transfer_in') AND quantity_change > 0)
        OR
        (movement_type IN ('sale','purchase_return','adjustment_out','shrinkage','transfer_out') AND quantity_change < 0)
    ),
    CHECK (
        (sale_id IS NOT NULL) + (sale_return_id IS NOT NULL) + (purchase_id IS NOT NULL) <= 1
    )
);
CREATE INDEX IF NOT EXISTS idx_inv_mov_product_date ON inventory_movements (product_id, branch_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_inv_mov_branch ON inventory_movements (branch_id);
CREATE INDEX IF NOT EXISTS idx_inv_mov_type ON inventory_movements (movement_type);
CREATE INDEX IF NOT EXISTS idx_inv_mov_user ON inventory_movements (user_id);
CREATE INDEX IF NOT EXISTS idx_inv_mov_sale ON inventory_movements (sale_id);
CREATE INDEX IF NOT EXISTS idx_inv_mov_sale_return ON inventory_movements (sale_return_id);
CREATE INDEX IF NOT EXISTS idx_inv_mov_purchase ON inventory_movements (purchase_id);


-- =====================================================================
-- 9. VISTAS ÚTILES (no son tablas: no llevan columnas de sincronización)
-- =====================================================================

-- Efectivo esperado en cada turno: fondo + ventas en efectivo + entradas - salidas - devoluciones en efectivo
CREATE VIEW IF NOT EXISTS v_cash_session_balance AS
SELECT *,
       (opening_amount + cash_sales + cash_in - cash_out - cash_refunds) AS expected_cash
FROM (
    SELECT
        cs.id AS cash_session_id,
        cs.cash_register_id,
        cs.status,
        cs.opening_amount,
        COALESCE((SELECT SUM(sp.amount)
                  FROM sale_payments sp
                  JOIN sales s ON s.id = sp.sale_id
                  JOIN payment_methods pm ON pm.id = sp.payment_method_id
                  WHERE s.cash_session_id = cs.id AND s.status = 'completed'
                    AND s.deleted_at IS NULL AND sp.deleted_at IS NULL
                    AND pm.method_type = 'cash'), 0) AS cash_sales,
        COALESCE((SELECT SUM(m.amount) FROM cash_movements m
                  WHERE m.cash_session_id = cs.id AND m.movement_type = 'cash_in'
                    AND m.deleted_at IS NULL), 0) AS cash_in,
        COALESCE((SELECT SUM(m.amount) FROM cash_movements m
                  WHERE m.cash_session_id = cs.id AND m.movement_type = 'cash_out'
                    AND m.deleted_at IS NULL), 0) AS cash_out,
        COALESCE((SELECT SUM(r.total)
                  FROM sale_returns r
                  JOIN payment_methods pm ON pm.id = r.refund_payment_method_id
                  WHERE r.cash_session_id = cs.id AND r.deleted_at IS NULL
                    AND pm.method_type = 'cash'), 0) AS cash_refunds
    FROM cash_sessions cs
    WHERE cs.deleted_at IS NULL
);

-- Existencias vs. mínimo (alerta de reabasto)
CREATE VIEW IF NOT EXISTS v_stock_status AS
SELECT
    p.id   AS product_id,
    p.sku,
    p.name AS product_name,
    b.id   AS branch_id,
    b.name AS branch_name,
    COALESCE(st.quantity, 0) AS quantity,
    p.min_stock,
    CASE WHEN COALESCE(st.quantity, 0) <= p.min_stock THEN 1 ELSE 0 END AS is_low_stock
FROM products p
CROSS JOIN branches b
LEFT JOIN inventory_stock st
       ON st.product_id = p.id AND st.branch_id = b.id AND st.deleted_at IS NULL
WHERE p.deleted_at IS NULL AND p.is_active = 1 AND p.track_inventory = 1
  AND b.deleted_at IS NULL;


-- =====================================================================
-- 10. ÍNDICES PARA LA COLA DE SINCRONIZACIÓN (registros con sync_status = 0)
-- =====================================================================
CREATE INDEX IF NOT EXISTS idx_settings_pending ON settings (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_branches_pending ON branches (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_cash_registers_pending ON cash_registers (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_roles_pending ON roles (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_permissions_pending ON permissions (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_role_permissions_pending ON role_permissions (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_users_pending ON users (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_audit_logs_pending ON audit_logs (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_units_pending ON units (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_tax_rates_pending ON tax_rates (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_categories_pending ON categories (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_suppliers_pending ON suppliers (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_products_pending ON products (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_product_barcodes_pending ON product_barcodes (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_product_price_history_pending ON product_price_history (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_customers_pending ON customers (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_payment_methods_pending ON payment_methods (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_discounts_pending ON discounts (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_cash_sessions_pending ON cash_sessions (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_cash_session_denominations_pending ON cash_session_denominations (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_cash_session_totals_pending ON cash_session_totals (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_cash_movements_pending ON cash_movements (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_purchases_pending ON purchases (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_purchase_items_pending ON purchase_items (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_sales_pending ON sales (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_sale_items_pending ON sale_items (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_sale_payments_pending ON sale_payments (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_sale_returns_pending ON sale_returns (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_sale_return_items_pending ON sale_return_items (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_inventory_stock_pending ON inventory_stock (updated_at) WHERE sync_status = 0;
CREATE INDEX IF NOT EXISTS idx_inventory_movements_pending ON inventory_movements (updated_at) WHERE sync_status = 0;

-- =====================================================================
-- 11. TRIGGERS DE AUDITORÍA/SYNC: refrescan updated_at y marcan sync_status = 0
--     (no se disparan si el UPDATE ya cambió updated_at o sync_status)
-- =====================================================================
CREATE TRIGGER IF NOT EXISTS trg_settings_touch
AFTER UPDATE ON settings
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE settings
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_branches_touch
AFTER UPDATE ON branches
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE branches
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_cash_registers_touch
AFTER UPDATE ON cash_registers
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE cash_registers
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_roles_touch
AFTER UPDATE ON roles
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE roles
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_permissions_touch
AFTER UPDATE ON permissions
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE permissions
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_role_permissions_touch
AFTER UPDATE ON role_permissions
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE role_permissions
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_users_touch
AFTER UPDATE ON users
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE users
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_audit_logs_touch
AFTER UPDATE ON audit_logs
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE audit_logs
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_units_touch
AFTER UPDATE ON units
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE units
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_tax_rates_touch
AFTER UPDATE ON tax_rates
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE tax_rates
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_categories_touch
AFTER UPDATE ON categories
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE categories
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_suppliers_touch
AFTER UPDATE ON suppliers
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE suppliers
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_products_touch
AFTER UPDATE ON products
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE products
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_product_barcodes_touch
AFTER UPDATE ON product_barcodes
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE product_barcodes
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_product_price_history_touch
AFTER UPDATE ON product_price_history
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE product_price_history
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_customers_touch
AFTER UPDATE ON customers
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE customers
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_payment_methods_touch
AFTER UPDATE ON payment_methods
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE payment_methods
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_discounts_touch
AFTER UPDATE ON discounts
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE discounts
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_cash_sessions_touch
AFTER UPDATE ON cash_sessions
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE cash_sessions
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_cash_session_denominations_touch
AFTER UPDATE ON cash_session_denominations
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE cash_session_denominations
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_cash_session_totals_touch
AFTER UPDATE ON cash_session_totals
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE cash_session_totals
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_cash_movements_touch
AFTER UPDATE ON cash_movements
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE cash_movements
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_purchases_touch
AFTER UPDATE ON purchases
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE purchases
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_purchase_items_touch
AFTER UPDATE ON purchase_items
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE purchase_items
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_sales_touch
AFTER UPDATE ON sales
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE sales
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_sale_items_touch
AFTER UPDATE ON sale_items
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE sale_items
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_sale_payments_touch
AFTER UPDATE ON sale_payments
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE sale_payments
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_sale_returns_touch
AFTER UPDATE ON sale_returns
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE sale_returns
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_sale_return_items_touch
AFTER UPDATE ON sale_return_items
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE sale_return_items
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_inventory_stock_touch
AFTER UPDATE ON inventory_stock
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE inventory_stock
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_inventory_movements_touch
AFTER UPDATE ON inventory_movements
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at AND NEW.sync_status = OLD.sync_status
BEGIN
    UPDATE inventory_movements
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), sync_status = 0
     WHERE id = NEW.id;
END;

-- =====================================================================
-- 12. TRIGGERS DEL KARDEX
-- =====================================================================

-- Cada movimiento actualiza la existencia en la MISMA transacción y guarda el saldo resultante.
-- No aplica a productos con track_inventory = 0 (servicios).
CREATE TRIGGER IF NOT EXISTS trg_inventory_movements_apply
AFTER INSERT ON inventory_movements
FOR EACH ROW
WHEN (SELECT track_inventory FROM products WHERE id = NEW.product_id) = 1
BEGIN
    INSERT INTO inventory_stock (product_id, branch_id, quantity)
    VALUES (NEW.product_id, NEW.branch_id, round(NEW.quantity_change, 3))
    ON CONFLICT (product_id, branch_id) DO UPDATE SET
        quantity    = round(quantity + excluded.quantity, 3),
        updated_at  = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
        sync_status = 0;

    UPDATE inventory_movements
       SET stock_after = (SELECT quantity FROM inventory_stock
                           WHERE product_id = NEW.product_id AND branch_id = NEW.branch_id)
     WHERE id = NEW.id;
END;

-- El kardex es inmutable: los errores se corrigen con un movimiento contrario, no editando.
CREATE TRIGGER IF NOT EXISTS trg_inventory_movements_immutable
BEFORE UPDATE OF branch_id, product_id, movement_type, quantity_change, unit_cost,
                 sale_id, sale_return_id, purchase_id, occurred_at
ON inventory_movements
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'El kardex es inmutable: registre un movimiento de ajuste o reverso.');
END;

CREATE TRIGGER IF NOT EXISTS trg_inventory_movements_no_delete
BEFORE DELETE ON inventory_movements
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Prohibido borrar kardex: use un movimiento contrario.');
END;

-- =====================================================================
-- 13. PROTECCIÓN: sin DELETE físico en tablas financieras (usa deleted_at / status)
--     Si necesitas una purga administrativa, elimina estos triggers explícitamente.
-- =====================================================================
CREATE TRIGGER IF NOT EXISTS trg_sales_no_delete
BEFORE DELETE ON sales
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Eliminación física prohibida en sales: use deleted_at (soft delete).');
END;

CREATE TRIGGER IF NOT EXISTS trg_sale_items_no_delete
BEFORE DELETE ON sale_items
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Eliminación física prohibida en sale_items: use deleted_at (soft delete).');
END;

CREATE TRIGGER IF NOT EXISTS trg_sale_payments_no_delete
BEFORE DELETE ON sale_payments
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Eliminación física prohibida en sale_payments: use deleted_at (soft delete).');
END;

CREATE TRIGGER IF NOT EXISTS trg_sale_returns_no_delete
BEFORE DELETE ON sale_returns
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Eliminación física prohibida en sale_returns: use deleted_at (soft delete).');
END;

CREATE TRIGGER IF NOT EXISTS trg_sale_return_items_no_delete
BEFORE DELETE ON sale_return_items
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Eliminación física prohibida en sale_return_items: use deleted_at (soft delete).');
END;

CREATE TRIGGER IF NOT EXISTS trg_cash_sessions_no_delete
BEFORE DELETE ON cash_sessions
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Eliminación física prohibida en cash_sessions: use deleted_at (soft delete).');
END;

CREATE TRIGGER IF NOT EXISTS trg_cash_movements_no_delete
BEFORE DELETE ON cash_movements
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Eliminación física prohibida en cash_movements: use deleted_at (soft delete).');
END;

CREATE TRIGGER IF NOT EXISTS trg_purchases_no_delete
BEFORE DELETE ON purchases
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Eliminación física prohibida en purchases: use deleted_at (soft delete).');
END;

CREATE TRIGGER IF NOT EXISTS trg_purchase_items_no_delete
BEFORE DELETE ON purchase_items
FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, 'Eliminación física prohibida en purchase_items: use deleted_at (soft delete).');
END;

