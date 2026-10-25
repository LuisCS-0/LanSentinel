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
]


async def apply_migrations(conn: AsyncConnection) -> None:
    for statement in STATEMENTS:
        await conn.execute(text(statement))
