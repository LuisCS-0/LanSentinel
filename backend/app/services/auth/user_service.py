"""
Gestión de usuarios del panel: creación del administrador inicial,
autenticación y cambio de contraseña.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import generate_password, hash_password, verify_password
from app.db.session import AsyncSessionLocal
from app.models.user import User

log = structlog.get_logger(__name__)

# Hash con el que comparar cuando el usuario no existe, para que la respuesta
# tarde lo mismo y no se pueda averiguar qué usuarios existen midiendo tiempos
_DUMMY_HASH = hash_password("lansentinel-dummy-password")


async def ensure_admin_user() -> None:
    """
    Si no hay ningún usuario, crea el administrador inicial (ADMIN_USERNAME).
    Usa ADMIN_PASSWORD si está definida; si no, genera una contraseña
    aleatoria y la guarda en INITIAL_PASSWORD_PATH (solo legible por root),
    de donde se lee con: sudo cat /var/lib/lansentinel/initial_admin_password
    """
    async with AsyncSessionLocal() as db:
        count = (await db.execute(select(func.count()).select_from(User))).scalar()
        if count:
            return

        password = settings.ADMIN_PASSWORD or generate_password()
        db.add(User(username=settings.ADMIN_USERNAME, password_hash=hash_password(password)))
        await db.commit()

    if settings.ADMIN_PASSWORD:
        log.warning("auth.admin_created", username=settings.ADMIN_USERNAME, source="ADMIN_PASSWORD")
        return

    path = Path(settings.INITIAL_PASSWORD_PATH)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(password + "\n")
        os.chmod(path, 0o600)
        log.warning(
            "auth.admin_created",
            username=settings.ADMIN_USERNAME,
            password_file=str(path),
            hint="Inicia sesión con esa contraseña y cámbiala desde el panel",
        )
    except OSError as exc:
        # Sin volumen donde guardarla, el log es la única forma de conocerla
        log.warning(
            "auth.admin_created",
            username=settings.ADMIN_USERNAME,
            password=password,
            error=str(exc),
            hint="No se pudo guardar la contraseña en disco; cámbiala tras iniciar sesión",
        )


async def get_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(func.lower(User.username) == username.lower()))
    return result.scalar_one_or_none()


async def authenticate(db: AsyncSession, username: str, password: str) -> User | None:
    """Usuario si las credenciales son correctas y está activo; None si no."""
    user = await get_by_username(db, username)
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    if not user.is_active or not verify_password(password, user.password_hash):
        return None

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    return user


async def change_password(db: AsyncSession, user: User, new_password: str) -> None:
    """
    Cambia la contraseña. Al actualizar password_changed_at, todas las sesiones
    abiertas con la contraseña anterior dejan de ser válidas.
    """
    now = datetime.now(timezone.utc)
    user.password_hash = hash_password(new_password)
    user.password_changed_at = now
    user.updated_at = now
    await db.commit()

    # La contraseña inicial generada ya no sirve: no dejarla en disco
    try:
        Path(settings.INITIAL_PASSWORD_PATH).unlink(missing_ok=True)
    except OSError:
        pass
    log.info("auth.password_changed", username=user.username)
