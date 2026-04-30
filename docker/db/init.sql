-- =============================================================================
-- LanSentinel — Esquema inicial de base de datos
-- =============================================================================

-- Extensiones útiles
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- búsqueda de texto en alertas

-- -----------------------------------------------------------------------------
-- DISPOSITIVOS
-- Tabla central: cada dispositivo detectado en la red
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS devices (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mac         VARCHAR(17) NOT NULL UNIQUE,   -- formato AA:BB:CC:DD:EE:FF
    ip          VARCHAR(45),                   -- IPv4 o IPv6
    hostname    VARCHAR(255),
    vendor      VARCHAR(255),                  -- fabricante inferido de la MAC (OUI)
    device_type VARCHAR(100),                  -- router, phone, laptop, iot, unknown…
    is_trusted  BOOLEAN NOT NULL DEFAULT FALSE,
    is_blocked  BOOLEAN NOT NULL DEFAULT FALSE,
    notes       TEXT,
    first_seen  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_devices_ip      ON devices(ip);
CREATE INDEX idx_devices_mac     ON devices(mac);
CREATE INDEX idx_devices_trusted ON devices(is_trusted);
CREATE INDEX idx_devices_blocked ON devices(is_blocked);

-- -----------------------------------------------------------------------------
-- SNAPSHOTS DE USO DE RED POR DISPOSITIVO
-- Serie temporal: consumo de ancho de banda por dispositivo
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS network_usage (
    id              BIGSERIAL PRIMARY KEY,
    device_id       UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    bytes_sent      BIGINT NOT NULL DEFAULT 0,
    bytes_recv      BIGINT NOT NULL DEFAULT 0,
    packets_sent    BIGINT NOT NULL DEFAULT 0,
    packets_recv    BIGINT NOT NULL DEFAULT 0,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_network_usage_device    ON network_usage(device_id);
CREATE INDEX idx_network_usage_recorded  ON network_usage(recorded_at DESC);

-- -----------------------------------------------------------------------------
-- ESCANEOS DE PUERTOS
-- Resultados de nmap u otras herramientas por dispositivo
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS port_scans (
    id          BIGSERIAL PRIMARY KEY,
    device_id   UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    port        INTEGER NOT NULL,
    protocol    VARCHAR(10) NOT NULL DEFAULT 'tcp',   -- tcp | udp
    state       VARCHAR(20) NOT NULL,                 -- open | closed | filtered
    service     VARCHAR(100),                         -- http, ssh, ftp…
    version     VARCHAR(255),
    scanned_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_port_scans_device  ON port_scans(device_id);
CREATE INDEX idx_port_scans_port    ON port_scans(port);

-- -----------------------------------------------------------------------------
-- ALERTAS
-- Eventos de seguridad generados por Suricata o por la lógica propia
-- -----------------------------------------------------------------------------
CREATE TYPE alert_severity AS ENUM ('info', 'low', 'medium', 'high', 'critical');
CREATE TYPE alert_source   AS ENUM ('suricata', 'monitor', 'firewall', 'system');
CREATE TYPE alert_status   AS ENUM ('new', 'acknowledged', 'resolved', 'ignored');

CREATE TABLE IF NOT EXISTS alerts (
    id              BIGSERIAL PRIMARY KEY,
    device_id       UUID REFERENCES devices(id) ON DELETE SET NULL,
    severity        alert_severity NOT NULL DEFAULT 'info',
    source          alert_source   NOT NULL DEFAULT 'system',
    status          alert_status   NOT NULL DEFAULT 'new',
    title           VARCHAR(255) NOT NULL,
    description     TEXT,
    raw_payload     JSONB,          -- payload original de Suricata u otras fuentes
    acknowledged_by VARCHAR(100),  -- usuario que gestionó la alerta (futuro: auth)
    acknowledged_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alerts_device    ON alerts(device_id);
CREATE INDEX idx_alerts_severity  ON alerts(severity);
CREATE INDEX idx_alerts_status    ON alerts(status);
CREATE INDEX idx_alerts_created   ON alerts(created_at DESC);
CREATE INDEX idx_alerts_payload   ON alerts USING GIN(raw_payload);

-- -----------------------------------------------------------------------------
-- REGLAS DE FIREWALL
-- Reglas gestionadas por el usuario, aplicadas vía iptables
-- -----------------------------------------------------------------------------
CREATE TYPE fw_action    AS ENUM ('accept', 'drop', 'reject', 'log');
CREATE TYPE fw_direction AS ENUM ('inbound', 'outbound', 'forward');
CREATE TYPE fw_protocol  AS ENUM ('tcp', 'udp', 'icmp', 'any');

CREATE TABLE IF NOT EXISTS firewall_rules (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    priority        INTEGER NOT NULL DEFAULT 100,      -- menor = mayor prioridad
    direction       fw_direction NOT NULL DEFAULT 'inbound',
    action          fw_action    NOT NULL DEFAULT 'drop',
    protocol        fw_protocol  NOT NULL DEFAULT 'any',
    src_ip          VARCHAR(50),    -- CIDR o IP individual, NULL = cualquiera
    dst_ip          VARCHAR(50),
    src_port        VARCHAR(50),    -- puerto o rango "80" / "8000:8080"
    dst_port        VARCHAR(50),
    device_id       UUID REFERENCES devices(id) ON DELETE SET NULL,
    auto_generated  BOOLEAN NOT NULL DEFAULT FALSE,   -- creada automáticamente
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_fw_rules_active   ON firewall_rules(is_active);
CREATE INDEX idx_fw_rules_device   ON firewall_rules(device_id);
CREATE INDEX idx_fw_rules_priority ON firewall_rules(priority);

-- -----------------------------------------------------------------------------
-- CONEXIONES ACTIVAS (caché de estado)
-- Se usan para mostrar en tiempo real las conexiones de cada dispositivo.
-- Esta tabla actúa como caché: se limpia y reescribe periódicamente.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS active_connections (
    id          BIGSERIAL PRIMARY KEY,
    device_id   UUID REFERENCES devices(id) ON DELETE SET NULL,
    src_ip      VARCHAR(45) NOT NULL,
    src_port    INTEGER,
    dst_ip      VARCHAR(45) NOT NULL,
    dst_port    INTEGER,
    protocol    VARCHAR(10),
    state       VARCHAR(30),        -- ESTABLISHED, TIME_WAIT, etc.
    pid         INTEGER,            -- PID del proceso (si disponible)
    process     VARCHAR(255),
    seen_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_active_conn_device ON active_connections(device_id);
CREATE INDEX idx_active_conn_src    ON active_connections(src_ip);

-- -----------------------------------------------------------------------------
-- CONFIGURACIÓN DEL SISTEMA
-- Tabla clave-valor para ajustes globales de LanSentinel
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS settings (
    key         VARCHAR(100) PRIMARY KEY,
    value       JSONB NOT NULL,
    description TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Valores por defecto
INSERT INTO settings (key, value, description) VALUES
    ('monitor_interval_seconds', '30',                        'Frecuencia de escaneo de dispositivos en segundos'),
    ('alert_auto_block',         'false',                     'Bloquear automáticamente dispositivos con alertas críticas'),
    ('trusted_only_mode',        'false',                     'Bloquear todo dispositivo no marcado como confiable'),
    ('scan_ports_on_discovery',  'false',                     'Escanear puertos al descubrir un dispositivo nuevo'),
    ('suricata_log_path',        '"/var/log/suricata/eve.json"', 'Ruta al log EVE de Suricata'),
    ('network_cidr',             '"192.168.1.0/24"',          'Rango de red a monitorizar')
ON CONFLICT (key) DO NOTHING;

-- -----------------------------------------------------------------------------
-- FUNCIÓN: actualizar updated_at automáticamente
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_devices_updated_at
    BEFORE UPDATE ON devices
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_alerts_updated_at
    BEFORE UPDATE ON alerts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_fw_rules_updated_at
    BEFORE UPDATE ON firewall_rules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_settings_updated_at
    BEFORE UPDATE ON settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
