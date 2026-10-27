"""
Gestión de usuarios del panel: creación del administrador inicial,
autenticación, cambio de contraseña y alta, edición y baja de usuarios con
rol (administrador o solo lectura). Siempre queda al menos un administrador
activo: si no, nadie podría volver a cambiar nada desde el panel.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import generate_password, hash_password, next_password_change, verify_password
from app.db.session import AsyncSessionLocal
from app.models.user import ROLE_ADMIN, ROLES, User

log = structlog.get_logger(__name__)

# Hash con el que comparar cuando el usuario no existe, para que la respuesta
# tarde lo mismo y no se pueda averiguar qué usuarios existen midiendo tiempos
_DUMMY_HASH = hash_password("lansentinel-dummy-password")


async def ensure_admin_user() -> None:
    """
    Si no hay ningún usuario, crea el administrador inicial (ADMIN_USERNAME).
    Usa ADMIN_PASSWORD si está definida; si no, genera una contraseña
    aleatoria y la guarda en INITIAL_PASSWORD_PATH (solo legible por root):
    el instalador la enseña al terminar y el panel pide cambiarla mientras
    siga siendo la inicial (initial_password_pending).
    """
    async with AsyncSessionLocal() as db:
        count = (await db.execute(select(func.count()).select_from(User))).scalar()
        if count:
            # Si el fichero de la contraseña inicial ya no vale, se borra ahora:
            # el instalador la enseña al terminar y no debe enseñar una vieja
            if admin := await get_by_username(db, settings.ADMIN_USERNAME):
                initial_password_pending(admin)
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


# (id, password_changed_at, fichero) → si sigue con la contraseña inicial.
# Comprobar el hash cuesta (Argon2): se hace una vez por contraseña y fichero.
_initial_pending: dict[tuple, bool] = {}


def initial_password_pending(user: User) -> bool:
    """
    Si el administrador inicial sigue con la contraseña generada al instalar
    (la del fichero INITIAL_PASSWORD_PATH): el panel le pide cambiarla. Si
    el fichero ya no coincide (se cambió con una versión que no lo borraba),
    se borra: esa contraseña ya no sirve para nada.
    """
    if user.username.lower() != settings.ADMIN_USERNAME.lower():
        return False
    path = Path(settings.INITIAL_PASSWORD_PATH)
    try:
        stat = path.stat()
    except OSError:
        return False
    key = (user.id, user.password_changed_at, stat.st_mtime_ns, stat.st_size)
    if key not in _initial_pending:
        try:
            initial = path.read_text().strip()
        except OSError:
            initial = ""
        pending = bool(initial) and verify_password(initial, user.password_hash)
        if not pending:
            try:
                path.unlink(missing_ok=True)
                log.info("auth.initial_password_stale_removed", path=str(path))
            except OSError:
                pass
        _initial_pending[key] = pending
    return _initial_pending[key]


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
    user.password_changed_at = next_password_change(user.password_changed_at, now)
    user.updated_at = now
    await db.commit()

    # La contraseña inicial generada (la del administrador inicial) ya no
    # sirve: no dejarla en disco
    if user.username.lower() == settings.ADMIN_USERNAME.lower():
        try:
            Path(settings.INITIAL_PASSWORD_PATH).unlink(missing_ok=True)
        except OSError:
            pass
    log.info("auth.password_changed", username=user.username)


# ── Usuarios y roles ─────────────────────────────────────────────────────────

class UserError(ValueError):
    """Petición imposible (nombre repetido, dejar el sistema sin administrador...)."""


def leaves_without_admin(users: list[User], target_id: int, *, role: str | None = None,
                         is_active: bool | None = None, deleting: bool = False) -> bool:
    """Si el cambio pedido sobre target_id dejaría el sistema sin ningún administrador activo."""
    remaining = 0
    for u in users:
        if u.id == target_id:
            if deleting:
                continue
            new_role = role if role is not None else u.role
            new_active = is_active if is_active is not None else u.is_active
            remaining += new_role == ROLE_ADMIN and new_active
        else:
            remaining += u.role == ROLE_ADMIN and u.is_active
    return remaining == 0


async def list_users(db: AsyncSession) -> list[User]:
    return list((await db.execute(select(User).order_by(User.id))).scalars().all())


async def create_user(db: AsyncSession, username: str, password: str, role: str) -> User:
    if role not in ROLES:
        raise UserError(f"Rol desconocido: {role}")
    if await get_by_username(db, username):
        raise UserError(f"Ya existe el usuario {username}")
    user = User(username=username, password_hash=hash_password(password), role=role)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    log.info("auth.user_created", username=username, role=role)
    return user


async def update_user(db: AsyncSession, user: User, *, role: str | None = None,
                      is_active: bool | None = None) -> User:
    """Cambia rol o estado. Desactivar cierra sus sesiones (se comprueba en cada petición)."""
    if role is not None and role not in ROLES:
        raise UserError(f"Rol desconocido: {role}")
    if leaves_without_admin(await list_users(db), user.id, role=role, is_active=is_active):
        raise UserError("Tiene que quedar al menos un administrador activo")
    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    log.info("auth.user_updated", username=user.username, role=user.role, is_active=user.is_active)
    return user


async def delete_user(db: AsyncSession, user: User) -> None:
    if leaves_without_admin(await list_users(db), user.id, deleting=True):
        raise UserError("Tiene que quedar al menos un administrador activo")
    await db.delete(user)
    await db.commit()
    log.info("auth.user_deleted", username=user.username)
