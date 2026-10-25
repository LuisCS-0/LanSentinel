from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.is_development,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Fecha actual con zona horaria (UTC), para los default de los modelos."""
    return datetime.now(timezone.utc)


async def init_db():
    """
    Crea las tablas que falten (solo en desarrollo; en producción las crea
    init.sql) y aplica las migraciones idempotentes de app/db/migrations.py.
    """
    from app.db.migrations import apply_migrations

    async with engine.begin() as conn:
        if settings.is_development:
            from app.models import device, alert, firewall_rule, network_usage, user  # noqa
            await conn.run_sync(Base.metadata.create_all)
        await apply_migrations(conn)


async def get_db() -> AsyncSession:
    """Dependency de FastAPI para inyectar sesión de BD."""
    async with AsyncSessionLocal() as session:
        yield session
