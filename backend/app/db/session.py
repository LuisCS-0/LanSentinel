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


async def init_db():
    """Crea las tablas si no existen (development). En producción usar Alembic."""
    if settings.is_development:
        async with engine.begin() as conn:
            from app.models import device, alert, firewall_rule, network_usage  # noqa
            await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """Dependency de FastAPI para inyectar sesión de BD."""
    async with AsyncSessionLocal() as session:
        yield session
