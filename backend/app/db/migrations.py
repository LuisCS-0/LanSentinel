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
]


async def apply_migrations(conn: AsyncConnection) -> None:
    for statement in STATEMENTS:
        await conn.execute(text(statement))
