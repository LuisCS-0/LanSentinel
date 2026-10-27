"""
Migraciones ligeras del esquema.

docker/db/init.sql solo se ejecuta cuando el volumen de PostgreSQL está vacío,
así que una instalación existente no recibiría las columnas añadidas después.
Estas sentencias son idempotentes (IF NOT EXISTS) y se ejecutan en cada
arranque del backend, tanto en desarrollo como en producción.

Al añadir una columna nueva: incluirla en init.sql (instalaciones nuevas) y
añadir aquí la sentencia equivalente (instalaciones existentes).
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

STATEMENTS: list[str] = [
    # Bloqueo de dispositivos por MAC
    "ALTER TABLE firewall_rules ADD COLUMN IF NOT EXISTS src_mac VARCHAR(17)",
    "CREATE INDEX IF NOT EXISTS idx_fw_rules_src_mac ON firewall_rules(src_mac)",
    # Agrupación de alertas repetidas
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS fingerprint VARCHAR(255)",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS occurrences INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ",
    "UPDATE alerts SET last_seen_at = created_at WHERE last_seen_at IS NULL",
    "ALTER TABLE alerts ALTER COLUMN last_seen_at SET DEFAULT NOW()",
    "ALTER TABLE alerts ALTER COLUMN last_seen_at SET NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_alerts_fingerprint ON alerts(fingerprint, last_seen_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_alerts_last_seen ON alerts(last_seen_at DESC)",
    # Usuarios del panel (autenticación)
    """
    CREATE TABLE IF NOT EXISTS users (
        id                  SERIAL PRIMARY KEY,
        username            VARCHAR(64)  NOT NULL UNIQUE,
        password_hash       VARCHAR(255) NOT NULL,
        is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
        password_changed_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        last_login_at       TIMESTAMPTZ,
        created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    )
    """,
    # Histórico de tráfico: minutos en bruto (la tabla ya venía en init.sql
    # pero no se usaba) y agregado por horas
    """
    CREATE TABLE IF NOT EXISTS network_usage (
        id           BIGSERIAL PRIMARY KEY,
        device_id    UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
        bytes_sent   BIGINT NOT NULL DEFAULT 0,
        bytes_recv   BIGINT NOT NULL DEFAULT 0,
        packets_sent BIGINT NOT NULL DEFAULT 0,
        packets_recv BIGINT NOT NULL DEFAULT 0,
        recorded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_network_usage_recorded ON network_usage(recorded_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS network_usage_hourly (
        device_id    UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
        hour         TIMESTAMPTZ NOT NULL,
        bytes_sent   BIGINT NOT NULL DEFAULT 0,
        bytes_recv   BIGINT NOT NULL DEFAULT 0,
        packets_sent BIGINT NOT NULL DEFAULT 0,
        packets_recv BIGINT NOT NULL DEFAULT 0,
        PRIMARY KEY (device_id, hour)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_network_usage_hourly_hour ON network_usage_hourly(hour DESC)",
    # Escaneo periódico de puertos
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS last_port_scan_at TIMESTAMPTZ",
    # Dominios y huellas TLS por dispositivo (1.10)
    """
    CREATE TABLE IF NOT EXISTS device_domains (
        device_id   UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
        domain      VARCHAR(255) NOT NULL,
        hits        BIGINT NOT NULL DEFAULT 0,
        via_dns     BOOLEAN NOT NULL DEFAULT FALSE,
        via_tls     BOOLEAN NOT NULL DEFAULT FALSE,
        first_seen  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_seen   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (device_id, domain)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_device_domains_last_seen ON device_domains(last_seen)",
    """
    CREATE TABLE IF NOT EXISTS device_tls_fingerprints (
        device_id   UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
        fingerprint VARCHAR(128) NOT NULL,
        ja3         VARCHAR(32),
        last_sni    VARCHAR(255),
        hits        BIGINT NOT NULL DEFAULT 0,
        first_seen  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_seen   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (device_id, fingerprint)
    )
    """,
    # Usuarios con roles y registro de acciones (1.11). Los usuarios que ya
    # existían eran administradores
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(16) NOT NULL DEFAULT 'admin'",
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        id          BIGSERIAL    PRIMARY KEY,
        created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        username    VARCHAR(64),
        ip          VARCHAR(45),
        method      VARCHAR(8)   NOT NULL,
        path        VARCHAR(255) NOT NULL,
        action      VARCHAR(128) NOT NULL,
        target      VARCHAR(255),
        status_code INTEGER      NOT NULL,
        details     JSONB
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at DESC)",
    # Auditorías con IA (1.12)
    """
    CREATE TABLE IF NOT EXISTS ai_audits (
        id            SERIAL PRIMARY KEY,
        created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        finished_at   TIMESTAMPTZ,
        status        VARCHAR(16)  NOT NULL,
        requested_by  VARCHAR(64),
        provider      VARCHAR(32)  NOT NULL,
        model         VARCHAR(100) NOT NULL,
        local         BOOLEAN      NOT NULL DEFAULT FALSE,
        input_tokens  INTEGER,
        output_tokens INTEGER,
        cost_usd      DOUBLE PRECISION,
        snapshot      JSONB,
        mapping       JSONB,
        report        JSONB,
        discarded     JSONB,
        error         TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ai_audits_created_at ON ai_audits(created_at DESC)",
    # Ajustes del panel (modo cuarentena); la tabla ya venía en init.sql
    """
    CREATE TABLE IF NOT EXISTS settings (
        key         VARCHAR(100) PRIMARY KEY,
        value       JSONB NOT NULL,
        description TEXT,
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
]


async def apply_migrations(conn: AsyncConnection) -> None:
    for statement in STATEMENTS:
        await conn.execute(text(statement))
