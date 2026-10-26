"""
Ajustes persistentes que se cambian desde el panel (tabla settings).

Los que se configuran una vez al desplegar (tokens, interfaces...) siguen en
.env; aquí van los que el usuario activa y desactiva en el día a día, como el
modo cuarentena.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import AsyncSessionLocal
from app.models.setting import SystemSetting

QUARANTINE_MODE = "trusted_only_mode"
# Modo router: estado elegido en el panel y último ROUTER_MODE visto en .env
ROUTER_MODE = "router_mode"
ROUTER_MODE_ENV = "router_mode_env"


async def get_setting(key: str, default=None):
    async with AsyncSessionLocal() as db:
        value = (await db.execute(select(SystemSetting.value).where(SystemSetting.key == key))).scalar()
    return default if value is None else value


async def set_setting(key: str, value, description: str | None = None) -> None:
    now = datetime.now(timezone.utc)
    stmt = pg_insert(SystemSetting).values(key=key, value=value, description=description, updated_at=now)
    stmt = stmt.on_conflict_do_update(index_elements=["key"], set_={"value": value, "updated_at": now})
    async with AsyncSessionLocal() as db:
        await db.execute(stmt)
        await db.commit()
